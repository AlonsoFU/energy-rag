# 03 · Actualización desde BCN (monitor semanal)

**Sí, el sistema se actualiza solo desde BCN LeyChile.** Corre cada lunes a las 06:00 por cron
(`0 6 * * 1 scripts/monitor_run.sh`) y deja su salida en `logs/monitor_AAAAMMDD.log` y
`docs/monitor-ultimo-informe.md`.

## Qué hace, paso a paso (`scripts/monitor_run.sh`)
| paso | script | qué hace |
|---|---|---|
| 0 | `rescrape_partial --limit 4` | re-baja normas que quedaron con «Loading…» (BCN renderiza tarde) |
| 1 | `rescrape_modificadas --alcance dominio --frescura 6` | re-baja las 76 normas del dominio y compara un **hash estable** del texto (normaliza espacios, tildes y adornos de BCN; el hash crudo daba falsos cambios en 13 de 25) |
| 2 | `monitor_diff` | compara la DB contra el último snapshot y registra eventos en `norma_evento` |
| 3 | `monitor_report --marcar` | informe legible: qué cambió **y qué artículos del corpus citan lo que cambió** |
| 3b | `aplicar_cambios --aplicar` | aplica al corpus los cambios detectados, vía `actualizar_norma` |
| 3c | `detectar_articulos_duplicados`, `detectar_derogaciones`, `estructura_articulado`, `resolver_citas_normas` | reprocesa lo que cambió |
| 4 | `monitor_diff --snapshot` | congela el estado nuevo como base para la próxima semana |

Tipos de evento (`norma_evento`): `norma_nueva`, `texto_modificado`, `version_nueva`,
`estado_cambiado`, `vinculacion_nueva`, `articulo_derogado`. Cada evento guarda su `impacto`:
los artículos del corpus que citan la norma afectada.

## Guardas antes de reemplazar un texto (`actualizar_norma`)
Reemplazar es destructivo, así que antes de borrar valida:
1. **Identidad:** el tipo y número que declara la norma bajada coinciden con los pedidos.
2. **No encoger:** el texto nuevo no es más de 10 % más corto que el guardado (un scrape a medias se ve igual que una derogación masiva). `--permitir-encoger` para el caso legítimo.
3. **Articulado:** la cantidad de artículos tampoco encoge.
Lo que no pasa queda pendiente para revisión manual; no se fuerza ni se marca aplicado.

## Throttle
BCN responde 429 si se le pide rápido. 20 s entre normas por defecto, resumible. Una corrida
completa toma ~50 min (la del 2026-09-21: 06:00 → 06:51).

## Normas nuevas (no automático)
`bajar_candidatas.py` + `ingerir_nuevas.py`: resuelve tipo+número → idNorma con el buscador de
BCN y valida **identidad** antes de ingerir (medido: 9 de 24 descargas eran otra norma, ej.
«DECRETO 42» devolvía «ACUERDO 42»). Se corre a mano; las candidatas salen de
`docs/descubrimiento-pendiente.md` (normas citadas por el corpus que el corpus no tiene).

## Bugs que tuvo el monitor (arreglados)
1. **Nunca detectaba nada:** llamaba a `rescrape_partial`, que solo arregla «Loading…»; con 0
   parciales informaba «sin cambios» sin haber mirado. Ahora usa `rescrape_modificadas`.
2. **Miraba 16 normas en vez de las del dominio** (alcance viejo; hoy 76).
3. **Re-rompía el corpus cada lunes** (arreglado 2026-09-20, commit `42f1388`):
   `actualizar_norma`, `ingerir_nuevas` y `reingest_faltantes` llamaban a `_extract_articulos`
   con texto crudo, saltándose `quitar_notas_bcn`. La corrida del 2026-09-14 re-rompió 60
   artículos. Ahora la limpieza vive dentro de `_extract_articulos`; test:
   `tests/parsers/test_nota_no_crea_articulo.py`.

## Efecto sobre la evaluación
Cada corrida del monitor que aplica cambios **cambia el corpus**, y las mediciones hechas antes
dejan de ser comparables con las de después. Eso ensució 10 días de decisiones (el «−1 de ruido»
del 2026-09-14 eran 333 artículos cambiados). Desde el 2026-09-20 cada `result.json` guarda
`db_huella` y `scripts/comparar_corridas.py` avisa si difiere. La corrida del 2026-09-21
detectó 0 cambios (72 iguales, 4 fallos de descarga).

## Lo que NO cubre
- No alerta a nadie: el informe queda en archivo. Sigue sin notificación (pendiente desde 09-14).
- Normas fuera del dominio no se re-bajan.
- No sigue derogaciones que BCN no publica como vinculación: se detectan leyendo el texto.
