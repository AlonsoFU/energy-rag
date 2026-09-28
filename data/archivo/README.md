# data/archivo/

Datos de la etapa de exploración (2025 – abril 2026): índices FAISS y grafo NetworkX de la v1,
búsquedas de BCN, análisis de discrepancias, normas "procesadas"/"estructuradas" de pipelines que
ya no existen. **Ningún código vivo los lee** (verificado 2026-09-28: ni `src/`, ni `scripts/*.py`
vivos, ni `scripts/*.sh`, ni `tests/`, ni `alembic/`). Se mueven, no se borran, porque los scripts de
`scripts/archivo/` y los docs de `docs/bitacora/` los citan.

Lo vivo de `data/`:

| carpeta | qué | lo usa |
|---|---|---|
| `eval/` | sets de preguntas, red golden (`eval/redes/`), resultados (ignorados por git) | eval, `red_golden.py`, `estado.py` |
| `intents/` | clasificador de intención (¿pide una definición?) | `src/pipelines/intent_gate.py` |
| `normas_completas/` | JSON de las normas; `nuevas/` es donde deja el monitor lo re-bajado | `actualizar_norma.py`, `aplicar_cambios.py` |
| `normas/`, `textos/`, `vinculaciones/` | salida cruda del crawler | `src/crawlers/norm_detail_crawler.py`, `extract_vinculaciones.py` |
