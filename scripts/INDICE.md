# Índice de `scripts/`

Ordenado el 2026-09-28. **34 `.py` y 10 `.sh` en la raíz: todo lo que se usa.** El resto se movió
(no se borró, porque `docs/bitacora/` lo cita como evidencia):

| carpeta | qué | cuántos |
|---|---|---|
| `scripts/` | lo que usa la operación, el monitor, la ingesta o el eval | 34 `.py` + 10 `.sh` |
| `experimentos/` | experimentos ya decididos; resultado en `docs/bitacora/plan-operacion.md` | 87 |
| `archivo/` | herramientas de un solo uso ya cumplidas y drivers de campañas cerradas | 155 |

Si hace falta uno de `archivo/`: `git mv` de vuelta. Antes de escribir uno nuevo, buscar ahí.

## Usar el sistema
```
preguntar.py                 la interfaz: --buscar, respuesta, --obligaciones, --plazos, --cambios...
mapa_obligaciones.py         obligaciones por sujeto, plazos, procesos, impacto (lo usa preguntar.py)
estado.py                    los números del sistema, generados (--markdown para los docs)
```

## Corren solas (crontab)
```
watchdog.sh        cada 15 min   relanza la cola si algo muere
trabajar.sh        cada 10 min   copia plan_maestro.txt a cola.txt y llama a runner.sh
runner.sh          cada hora :30 corre la primera tarea no hecha; reintenta hasta 3 veces
retomar.sh         cada 3 h      quita pausas, levanta Postgres, reaplica el tope de GPU
latido.sh          cada hora     deja constancia de que la máquina está viva
gpu_vigia.sh       cada minuto   temperatura, W y MHz de la 3090 mientras hay trabajo
monitor_run.sh     lunes 06:00   el monitor semanal de BCN (ver abajo)
```
Apoyo: `gpu_guard.sh` (tope de 180 W antes de lanzar), `gpu_modo.sh` (elegir el tope),
`drenar_cola.sh` (vaciar la cola a mano). Cola: `plan_maestro.txt` → `cola.txt`.

## Monitor semanal de BCN (lo que encadena `monitor_run.sh`)
```
rescrape_partial.py          repara los JSON que quedaron en 'Loading...'
rescrape_modificadas.py      re-baja las normas del dominio y compara un hash estable
monitor_diff.py              compara contra el snapshot, escribe norma_evento
monitor_report.py            informe -> docs/monitor-ultimo-informe.md
aplicar_cambios.py           aplica al corpus lo detectado (vía actualizar_norma.py)
actualizar_norma.py          reemplaza una norma ya ingerida, con guardas (identidad, no encoger)
detectar_articulos_duplicados.py   artículos repetidos entre ley modificatoria y cuerpo modificado
detectar_derogaciones.py     qué está derogado, para no citarlo como vigente
estructura_articulado.py     de qué proceso habla cada obligación, según el articulado
resolver_citas_normas.py     citas norma→norma desde el texto -> docs/frontera-candidatas.md
monitor_schema.py            crea las tablas del monitor (una vez, en una instalación nueva)
```

## Ampliar o reparar el corpus
```
bajar_candidatas.py          descarga de BCN validando identidad (el buscador de BCN miente)
ingerir_nuevas.py            parsea e ingesta
extract_vinculaciones.py     vinculaciones entre normas desde BCN
marcar_fuera_dominio.py      frontera de mercados (MARCA, no borra)
marcar_norma_derogada.py     marca una norma entera como derogada, con evidencia. Reversible
reingest_faltantes.py        re-ingesta normas que quedaron con 0 artículos
reparar_articulos.py         repara artículos cortados por notas BCN (backup por corrida: BAK=)
limpiar_notas_bcn.py         quita las notas de modificación de BCN intercaladas en el texto
resolve_authority.py         norma autoritativa para conceptos definidos en varias normas
migrate_to_postgres.py       instalación nueva: JSON de data/normas_completas/ -> Postgres
```

## Embeddings
```
embed_all.py                 ingesta completa: chunk -> contexto -> embed -> store
embed_4b.py                  re-embebe con Qwen3-Embedding-4B (el vigente)
reembeber_limpiados.py       re-embebe en sitio solo lo que cambió de texto
train_intent_gate.py         entrena el clasificador definición/no-definición (data/intents/)
```

## Medir
```
exp_think_paired.py          el harness del eval: pareado + McNemar, FLAGS/SETCFG/VAR, db_huella
comparar_corridas.py         compara dos corridas: cita_ok, McNemar, huella, texto idéntico
eval_metrics.py              métricas de cita (cita_ok, cita_limpia, precisión)
red_golden.py                red de búsqueda: prueba un refactor de retrieve.py en ~15 min
diag_donde_falla.py          ¿las fallas son de búsqueda o de redacción?
medir_tiempos_busqueda.py    tiempo por etapa
```
Reglas para medir: `docs/sistema/04-evaluacion.md`.
