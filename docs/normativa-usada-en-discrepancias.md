# Normativa que el sector cita en sus discrepancias

Generado por `scripts/extraer_de_discrepancias.py` sobre los PDF de
`data/discrepancias/`. **Es descubrimiento por USO, no por búsqueda**: una norma que
aparece en una discrepancia real ante el Panel de Expertos es normativa viva del
sector. El frente de descubrimiento prospectivo estaba bloqueado porque los sitios
bloquean el scraping; esta vía no depende de ellos.

- documentos leídos: **3**
- citas artículo→norma detectadas: **13**
- resueltas a normas del corpus: **1** (1 con el artículo también presente — sirven de gold para evaluar)
- apuntan a normas que **faltan**: **12**

## Normas citadas que NO están en el corpus

⚠️ Un `quizá` señala que el número no existe pero un prefijo suyo sí: casi siempre
es el `-layout` de pdftotext pegando una numeración de línea. **No se corrige solo** —
resolverlo por truncamiento sesgaría el reporte hacia *"ya lo tenemos"*.

| tipo | número | veces | quizá | ejemplo de la cita |
|---|---|---|---|---|
| DECRETO | 44 | 5 | — | artículos 27 y siguientes del Reglamento del Panel de Expertos conteni |
| DECRETO | 88 | 4 | — | artículo 124 del Reglamento para Medios de Generación de Pequeña Escal |
| DECRETO | 97 | 1 | — | artículo 6 del Decreto Supremo N°97 |
| DECRETO | 244 | 1 | — | artículo 39 del Decreto Supremo N°244 |
| DECRETO | 8810 | 1 | — | artículo 9 del Decreto Supremo Nº8810 |

## Pares artículo–norma utilizables como gold

| norma | artículo | documento |
|---|---|---|
| DFL 4 (`258171`) | 208 | disc_betel_2024.pdf |
