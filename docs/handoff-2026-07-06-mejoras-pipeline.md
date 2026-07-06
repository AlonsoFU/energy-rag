# Handoff 2026-07-06 — Mejoras por etapa del pipeline

## Estado adoptado (rama `adopt-winners`, commit 37fd9bf)
```
Producción AHORA:
  EMBEDDER   Qwen3-Embedding-4B (MRL-1024, HNSW)  + alias_union   [embed_4b_dense=True]
  BM25       híbrido, peso por largo de query
  FUSIÓN     RRF (k=60)
  RERANKER   BAAI/bge-reranker-v2-m3              [use_bge_reranker=True]
  GATE       off-topic modo AND
  POOL       depth 50, top_k 10
  GENERADOR  claude-sonnet-4-6 (API)  ·  mejor LOCAL medido = qwen3:30b-a3b
```
Métrica: **cita_ok** (¿el sistema cita el artículo gold?). Sets con gold: coloquial 39, dev 44, holdout 18, balanced_v2 339.

## Techo actual y dónde falla (medido)
- Retrieval gold∈top5 = **57.9%** sobre 339q (4b y 8b idénticos). ~42% el gold NO entra al top5 con NINGÚN embedder.
- Los 12 fallos del ganador se parten: **6 = retrieval** (gold fuera de pool, coloquial sin vocabulario común) + **6 = generación** (gold en pool, LLM citó vecino; ej. 118 "tope de ganancia"→concepto mal entendido).

## Mapa de etapas: estado + próximo experimento

| # | Etapa | Estado | Próximo lever (cómo probar) |
|---|-------|--------|------------------------------|
| 1 | Chunking | ✓ contextual | **Re-chunkear art 225** (glosario gigante, 1 def=1 frag) → rescata 225-tasa/almacenamiento. Script tipo `reembed`+split. |
| 2 | Query-side | ✓ alias (+3) · ✗ ensemble/rewrite (−3) | **LLM-rewrite con modelo CHICO (9b)** anclado al glosario (371 conceptos), unión RRF. El 30b se cuelga; usar 9b. |
| 3 | Embedder | ✓✓ AGOTADO (13 modelos) | Nada. 4b≈8b≈sfr end-to-end. Ni el 9B gana. |
| 4 | BM25 | ✗ doc2query | Tunear **peso BM25 vs vector** en `_length_weights` (retrieve.py:131). Barato. |
| 5 | Fusión RRF | ✓ grid corrido (2026-07-06) | **RESULTADO** ↓. Mejor k=10 peso BM25:Vec=2:1 = 188/309 top5 (+6 vs actual ~182). k y peso NO interactúan (tunear por separado bastaba). Favorecer BM25 gana en balanced; falta desglose coloquial + end-to-end antes de adoptar. |
| 6 | **RERANKER** | ⏳ **HUECO** — solo depth + bge-v2-m3 | **Probar otros modelos**: Qwen3-Reranker (familia ganadora acá), bge-reranker-v2-gemma (2B), jina-reranker-v2. Chicos, RAM-safe. Editar `get_reranker()` / `BGEReranker` para parametrizar el modelo. ← ALTO VALOR: decide el orden final; puede convertir los golds que el embedder ya encuentra. |
| 7 | Pool/top_k | ✓ (10-15, 50/100/200) | Nada. |
| 8 | Gate off-topic | ✓ AND (+4) | Nada. |
| 9 | Generador | ✓ 30b-a3b (+9 local) · Claude prod | Decidir Claude (calidad, $) vs 30b-a3b (gratis, peor). No medido Claude vs 30b. |
| 10 | Cita/prompt | ✗ verify-cite (0/6) · ✗ prompt enfático | Los 6 gen-fails son concepto mal entendido, NO cita descuidada → no lo arregla el prompt. |
| 11 | Grafo aristas | ⏳ | **define_termino concepto→artículo** para 76 (dedicados)/212 (Panel)/149. Ver `follow_remissions.py`, `glossary_define_edges.py`. |
| 12 | Fine-tune | ⏳ NO hecho | Embedder/reranker con pares coloquial→artículo. SOTA para dominio pero caro/tedioso (curar datos). Diferido por decisión usuario. |
| 13 | Datos/eval | ⏳ | Usar **balanced_v2 (339q)** en vez de coloquial (39q) para medir sin ruido. Más pares coloquiales reales = mejor señal. |

## Resultado experimento FUSIÓN (2026-07-06, `.scratch/fusion_grid.py`, balanced_v2 309q, gold∈top5)
```
k    BM25:Vec  top5  top10
10     2:1     188   206   ← mejor top5
20     3:1     187   205
10     1:1     185   207   ← mejor top10
60     1:1     182   204   ← ~config actual
80     1:2     179   194   ← peor (favorece vector)
```
- **k y peso NO interactúan** (fijo el peso, k mueve ±3; la fórmula RRF lo predecía). Tunear por separado bastaba; el grid conjunto solo era barato y elimina la duda.
- **Favorecer BM25 (2:1, 3:1) gana; favorecer vector (1:2, 1:3) pierde** — en balanced (mayoría formal). k chico (10) apenas mejor.
- Ganancia +6 top5 (+2%) = marginal, y el screen MIENTE. **NO adoptado**: falta (a) desglose por clase (coloquial puede querer más vector), (b) confirmación end-to-end cita_ok. Producción sigue con peso adaptativo-por-largo + k=60.

## Orden recomendado (por valor/costo)
1. **Reranker: otros modelos** (Qwen3-Reranker primero) — el hueco real, barato, ataca la conversión.
2. ~~Fusión RRF~~ ✓ HECHO (marginal +2%, no adoptado; ver arriba).
3. **Grafo concept→artículo** — rescata 76/212/149 (retrieval-miss estructurales).
4. **Re-chunk art 225** — rescata los def buried.
5. Fine-tune — el de raíz, pero último (caro).

Siguiente inmediato = **reranker (Qwen3-Reranker)**.

## AGOTADO (no rehacer, todo negativo medido)
embedders (13 modelos, incl. 9B via GGUF) · ensemble retrieval (−3) · verify-cite (0/6) · quant q5/q6 (=q4) · pool depth · doc2query · citation_repair · concept_inference · HyDE · fine-tune 0.6B (overfit).

## Regla de oro (aprendida a la mala)
El **screen (gold∈top5) MIENTE** — no predice cita_ok. Ej: 8b ganó screen (+2) y perdió end-to-end (−1). **Todo candidato se confirma end-to-end (cita_ok) o no cuenta.** Y con set grande (339q), no con 39.

## Infra / gotchas
- Cuello de la máquina = **RAM 14GB**, no VRAM 24GB. Modelos 7B+ por HF crashean al cargar; usar **GGUF/Ollama** (mmap directo a GPU). Ver `reference_ram_vram_ollama_loading` (memoria). NO cerrar servicios del usuario sin permiso.
- Ollama 30b/32b: cuelgue no-determinista → fix retry en `llm.py` (commiteado).
- Modelos/caches en disco externo `/home/alonso/datos` (root chico).
