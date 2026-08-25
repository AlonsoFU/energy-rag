# Normativa que el sector cita en sus discrepancias

Generado por `scripts/extraer_de_discrepancias.py` sobre los PDF de
`data/discrepancias/`. **Es descubrimiento por USO, no por búsqueda**: una norma que
aparece en una discrepancia real ante el Panel de Expertos es normativa viva del
sector. El frente de descubrimiento prospectivo estaba bloqueado porque los sitios
bloquean el scraping; esta vía no depende de ellos.

- documentos leídos: **9**
- citas artículo→norma detectadas: **21**
- resueltas a normas del corpus: **17** (15 con el artículo también presente — sirven de gold para evaluar)
- apuntan a normas que **faltan**: **4**

## Normas citadas que NO están en el corpus

⚠️ Un `quizá` señala que el número no existe pero un prefijo suyo sí: casi siempre
es el `-layout` de pdftotext pegando una numeración de línea. **No se corrige solo** —
resolverlo por truncamiento sesgaría el reporte hacia *"ya lo tenemos"*.

| tipo | número | veces | quizá | ejemplo de la cita |
|---|---|---|---|---|
| LEY | 198801 | 1 | LEY 19880 | artículo 62 de la Ley N°19.8801 |
| DECRETO | 97 | 1 | — | artículo 6 del Decreto Supremo N°97 |
| DECRETO | 244 | 1 | — | artículo 39 del Decreto Supremo N°244 |
| DECRETO | 8810 | 1 | DECRETO 88 | artículo 9 del Decreto Supremo Nº8810 |

## Pares artículo–norma utilizables como gold

| norma | artículo | documento |
|---|---|---|
| LEY 20936 (`1092695`) | 95 | disc_66d778f5.pdf |
| DECRETO 44 (`1113260`) | 27 | disc_66d778f5.pdf |
| DECRETO 44 (`1113260`) | 27 | disc_betel_2024.pdf |
| DECRETO 44 (`1113260`) | 32 | disc_betel_2024.pdf |
| DECRETO 88 (`1150437`) | 9 | informe_panel_2024.pdf |
| LEY 19880 (`210676`) | 62 | dictamen_19_2025.pdf |
| DFL 4 (`258171`) | 208 | disc_66d778f5.pdf |
| DFL 4 (`258171`) | 208 | disc_betel_2024.pdf |
| DFL 4 (`258171`) | 79 | disc_689a68a2.pdf |
| LEY 18410 (`29819`) | 16 | dictamen_4_2023_chilquinta.pdf |
| LEY 18410 (`29819`) | 3 | dictamen_4_2023_chilquinta.pdf |
