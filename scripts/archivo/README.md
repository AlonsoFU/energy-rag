# scripts/archivo/

Herramientas de un solo uso ya cumplidas: descargas puntuales, diagnósticos de campañas
cerradas, curación manual de glosario/alias, migraciones a Postgres, exploración de BCN.
**Nada de acá lo llama el camino de producción ni el cron.** Se mueven, no se borran, porque
`docs/` las cita como evidencia de los números.

Criterio (2026-09-28): no lo llama el crontab, ningún `.sh` vivo, `src/`, `preguntar.py` ni la
cadena del monitor, y no es una herramienta de operación de `scripts/INDICE.md`. Incluye los 12
drivers `.sh` de campañas cerradas y los scripts que alimentaban flags ya borrados del pipeline
(`embed_8b`, `embed_bgem3`, `doc2query_generate`, `build_def_fragments`). Si una hace falta:
`git mv` de vuelta.

Los experimentos numerados viven aparte, en `scripts/experimentos/`.
