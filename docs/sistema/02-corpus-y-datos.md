# 02 · Corpus y datos

Postgres 16 + pgvector en Docker (`energy_rag_pg`, puerto 5434, db/usuario `energy_rag`).
El contenedor se apaga solo; `preguntar.py` lo levanta si no responde.

## Qué hay (conteo al 2026-09-21)
| tabla | filas | qué es |
|---|---|---|
| `normas` | 124 | una fila por ley/decreto/resolución; `texto_completo` = scrape de BCN |
| `articulos` | 5.354 | artículos parseados; `derogado`, `metadata.fantasma`, `metadata.duplicado_de` |
| `fragmentos` | 6.611 | chunks de artículos con `embedding` (0.6B) y `embedding_4b_1024` (4B, la que usa producción); `tsv` para BM25 |
| `fragmentos_definicion` | 649 | una definición de glosario = un fragmento |
| `fragmentos_inciso` | 7.141 | experimental, no lo usa producción |
| `conceptos` / `norma_concepto` | 371 / 992 | glosario y en qué normas aparece |
| `referencias` | 5.803 | citas internas (concepto, artículo precedente, definición) |
| `norma_norma` / `norma_vinculacion` | 549 / 204 | relaciones entre normas (BCN solo trae «modifica») |
| `obligacion` | 3.634 | obligaciones extraídas por sujeto (`preguntar.py --obligaciones`) |
| `norma_evento` / `norma_snapshot` | 25 / 124 | monitor de cambios (ver 03) |
| `consultas_log` | 33 | bitácora de preguntas reales hechas con `preguntar.py` |

## Filtros que aplica la búsqueda
- `NOT articulos.derogado` (`filtrar_derogados`).
- `metadata.fantasma IS NULL`: filas basura o partidas por el parser, ocultas sin borrar.
- `metadata.duplicado_de`: copia de un artículo que vive en otra norma (ej. LEY 20936 guardó 55 artículos que pertenecen al DFL 4).

## Defectos encontrados y reparados

### Notas marginales de BCN leídas como artículos (exp #69b, #84)
BCN intercala notas de modificación (`Ley 20402 / Art. 10 Nº 1 / D.O. 03.12.2009`, y en la LGSE
`D.F.L. Nº 1, de 1982 / Art. 147º / D.O. 13.09.1982`, que es la **numeración de la ley vieja**).
El parser tomaba ese `Art. 147º` como artículo nuevo:
- **65 filas falsas en la LGSE** (+10 en otras normas). La fila «147º» tenía el texto del art. 222;
  el 147 real (clientes regulados) no existía. El sistema citó `[Art. 84 de 258171]` con el texto del 141.
- Arreglo: `NormStructureParser.quitar_notas_bcn` antes de segmentar; `scripts/reparar_articulos.py`
  (clase `NOTA_NUMERO`) llevó el texto correcto a la DB sin cambiar ids y re-embebió.
- Aplicado 2026-09-20: 135 artículos, 168 fragmentos. LGSE visibles que arrancan en nota: 62 → 8.

### Notas de modificación dentro del texto (exp #69a)
`scripts/limpiar_notas_bcn.py` + `scripts/reembeber_limpiados.py`: 1.047 artículos, 1.050
fragmentos, 692 incisos. Se midió 3 veces; se quedó al tercer intento (dev 80 → 83).

### Norma derogada servida como vigente (exp #85)
D.S. 3.386 de 1935 (id 202975, 236 artículos), derogado por el **art. 329 letra b) del D.S. 327**.
BCN lo trae con estado «DESCONOCIDO». `scripts/marcar_norma_derogada.py` marcó `derogado=true` +
`metadata.derogado_por`. Respuestas que lo citaban: dev 9 → 0, reales 4 → 0.
**El campo `estado` de BCN no es confiable en ninguna dirección** (marca DEROGADA al D.S. 327, vigente).

## Cómo revertir cada cambio aplicado a la DB
```bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
# #69a (limpieza de notas): primero vectores, después texto
PYTHONPATH=. venv/bin/python -m scripts.reembeber_limpiados --revertir
PYTHONPATH=. venv/bin/python -m scripts.limpiar_notas_bcn --revertir
# #84 (artículos falsos de notas marginales)
BAK=84 PYTHONPATH=. venv/bin/python -m scripts.reparar_articulos --revertir
# #85 (decreto de 1935 derogado)
PYTHONPATH=. venv/bin/python -m scripts.marcar_norma_derogada 202975 124102/329 --revertir
```
Respaldos: `articulos_bak_84`, `fragmentos_bak_84`, `*_bak_notas_20260906`,
`fragmentos_bak_emb_20260917`, `articulos_bak_69b`, `fragmentos_bak_69b`.

## Pendientes de datos
- 8 filas de la LGSE aún arrancan en residuo de nota; 426 casos en REVISAR de `reparar_articulos`
  (123 en la norma 1007469). No se fuerzan: el parser no los resuelve con seguridad.
- La vigencia hay que leerla del texto («Deróganse…»). El escaneo simple no halló más normas
  enteras derogadas, pero solo detecta derogaciones con número explícito.
- Todos los modelos y cachés viven en `/home/alonso/datos` (no en `/`).
