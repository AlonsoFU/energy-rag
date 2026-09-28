# scripts/archivo/

Herramientas de un solo uso ya cumplidas: descargas puntuales, diagnósticos de campañas
cerradas, curación manual de glosario/alias, migraciones a Postgres, exploración de BCN.
**Nada de acá lo llama el camino de producción ni el cron.** Se mueven, no se borran, porque
`docs/` las cita como evidencia de los números.

Criterio para estar acá (2026-09-28): no aparece en `scripts/*.sh`, `scripts/plan_maestro.txt`,
`docs/sistema/`, `src/` ni `scripts/preguntar.py`. Si una hace falta: `git mv` de vuelta.

Los experimentos numerados viven aparte, en `scripts/experimentos/`.
