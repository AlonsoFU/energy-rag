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
| 1 | Chunking | ✓✓ SWEEP 2026-07-07 (12 estrategias) | **GANADOR screen = `inciso+path`** (partir por subdivisión legal + header-path): dev +10, cx +2. inciso subsume el re-chunk de glosarios. Slide(fijo) peor. `scripts/exp_chunk_sweep.py`. ⏳ PENDIENTE confirmar end-to-end (tabla `fragmentos_inciso` + gen). |
| 2 | Query-side | ✓ alias (+3) · ✗ ensemble/rewrite (−3) | **LLM-rewrite con modelo CHICO (9b)** anclado al glosario (371 conceptos), unión RRF. El 30b se cuelga; usar 9b. |
| 3 | Embedder | ✓✓ AGOTADO (13 modelos) | Nada. 4b≈8b≈sfr end-to-end. Ni el 9B gana. |
| 4 | BM25 | ✗ doc2query | Tunear **peso BM25 vs vector** en `_length_weights` (retrieve.py:131). Barato. |
| 5 | Fusión RRF | ✓ grid corrido (2026-07-06) | **RESULTADO** ↓. Mejor k=10 peso BM25:Vec=2:1 = 188/309 top5 (+6 vs actual ~182). k y peso NO interactúan (tunear por separado bastaba). Favorecer BM25 gana en balanced; falta desglose coloquial + end-to-end antes de adoptar. |
| 6 | **RERANKER** | ✓✓ AGOTADO (10 modelos, 2026-07-06) | **RESULTADO** ↓. Baseline **bge-v2-m3 sigue rey** (cx 32/dev 36). Nadie supera coloquial. bge-large empata suma (68) con trade (+3 dev,−3 cx). Nada que adoptar. Script `exp_reranker_bakeoff.py`. |
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

## Resultado experimento RERANKER (2026-07-06, `scripts/exp_reranker_bakeoff.py`, pipeline real, coloquial 39 + dev 44, gold∈topN)
```
reranker              cx_t5  dev_t5   nota
bge-v2-m3 (baseline)    32     36     ← ADOPTADO, rey coloquial
bge-reranker-large      29     39     trade: +3 dev, -3 cx (empata suma 68)
identity (sin rerank)   29     30     control
mxbai-large-v1          29     30
qwen3-rerank-0.6b       27     33     generativo (yes/no logits)
mmarco-miniLM-es        26     33     (español mMARCO)
bge-reranker-base       19     33
gte-modernbert          18     35
jina-v2-multi           —      —      incompat transformers 5.9 (falta create_position_ids)
bge-gemma2 (2B)         —      —      template distinto al Qwen → scores basura; descartado
qwen3-rerank-4b (4B)    —      —      MURO RAM: HF/bnb carga fp16 8GB a RAM(14) → OOM-kill
```
- **Ningún reranker supera el baseline en coloquial (32).** El cross-encoder bge-v2-m3 se queda.
- Generativos (Qwen3-Reranker): loader propio (logits yes/no, prompt Instruct/Query/Document). 0.6b < baseline; 4b no corrió (RAM). Su familia NO es superior acá.
- Los grandes LLM-based (bge-gemma2, qwen3-4b) exigen GGUF/Ollama o 4-bit; 4-bit igual choca RAM al cargar shards fp16. Valor esperado bajo (el 0.6b ya perdió) → cerrado.

## Resultado campaña CHUNKING (2026-07-07, `scripts/exp_chunk_sweep.py`, vector-screen 4b-1024, coloquial39+dev44)
Barrido no-destructivo de 12 estrategias (chunker × contexto) re-chunkeando en memoria desde `articulos.texto`. Baseline `asis` (fragmentos actuales) = cx5 **27**, dev5 **28**.
```
estrategia            frags  cx5  dev5   Δcx5  Δdev5
asis (baseline)        3907   27   28      +0    +0
inciso+path            7087   29   38      +2   +10   ← GANADOR screen
inciso+light           7087   28   37      +1    +9
whole+path             2978   30   26      +3    -2
glossary+path          3203   30   26      +3    -2
glossary+light         3203   28   28      +1    +0
slide1000_200+light    6255   25   32      -2    +4
slide500_100+light    11080   25   33      -2    +5
whole+none             2978   28   26      +1    -2
```
- **Regla 1 (section-aware) — GANA `inciso`** (partir por subdivisión legal a./1./incisos): dev **+10**, cx +2. Rescata pool-miss estructurales. La regla GENERAL (cualquier subdivisión) SUBSUME a la narrow (solo glosarios: dev +0).
- **Regla 3 (context header-path) — ayuda**: en inciso, `light→path` = cx+1/dev+1 (estrictamente mejor). En `whole` el path sube cx pero baja dev (mezcla ruido de artículo entero).
- **Slide (tamaño fijo) PEOR en cx** (−1/−2) → confirma el estándar: no romper la provisión.
- **RONDA 2 (2026-07-07, QA de estructura + chunkers robustos):** el QA (`scripts/exp_chunk_qa.py`) marcó: inciso deja 2442/2978 en 1 chunk; 378 arts grandes 1-chunk (367 prosa sin marcador); 152 frags >3000c; 29 arts con marcadores NO cubiertos (§14, N°11, guion3, romano1). Se agregaron chunkers y se midió:
```
estrategia            frags  cx5  dev5   Δcx  Δdev
inciso+path            7087   29   38    +2   +10   ← techo
inciso_robust+path     7141   29   38    +2   +10   ← MISMO score + cubre §/N°/romano (mejor escala)
inciso_robust+light    7141   28   37    +1    +9
inciso_maxsplit+path   7316   29   37    +2    +9    (partir gigantes NO ayuda)
recursive+path         9979   27   31    +0    +3    (prosa: peor, chunks chicos = ruido)
recursive+light        9979   25   32    -2    +4
```
- **GANADOR = `inciso_robust+path`** (empata inciso+path pero robusto a §/N°/romano → future-proof, cero downside). recursive/maxsplit descartados.
- **CAVEAT (regla de oro): es VECTOR-SCREEN, no cita_ok.** El +10 es DEV (formal), coloquial (frente real) solo +2. Más frags (7141 vs 3907, 1.8×) sube recall pero puede NO convertir (distractor, cf. ensemble −3). **PENDIENTE confirmar `inciso_robust+path` end-to-end** — tabla paralela `fragmentos_inciso` (chunks+embedding+tsv) + eval gen. NO adoptado hasta eso.

## Orden recomendado (por valor/costo)
1. ~~Reranker~~ ✓ AGOTADO (10 modelos, marginal/negativo; baseline se queda).
2. ~~Fusión RRF~~ ✓ HECHO (marginal +2%, no adoptado; ver arriba).
3. **Grafo concept→artículo** — rescata 76/212/149 (retrieval-miss estructurales). ← siguiente inmediato.
4. **Re-chunk art 225** — rescata los def buried.
5. **BM25 weight / doc2query** — tunear `_length_weights` (barato).
6. Fine-tune — el de raíz, pero último (caro).

Siguiente inmediato = **grafo concept→artículo** (etapa 11).

## AGOTADO (no rehacer, todo negativo medido)
embedders (13 modelos, incl. 9B via GGUF) · **rerankers (10 modelos: bge×3, mxbai, mmarco-es, gte-modernbert, qwen3-rerank-0.6b/4b, jina, bge-gemma2 — baseline bge-v2-m3 imbatible)** · ensemble retrieval (−3) · verify-cite (0/6) · quant q5/q6 (=q4) · pool depth · doc2query · citation_repair · concept_inference · HyDE · fine-tune 0.6B (overfit).

## Regla de oro (aprendida a la mala)
El **screen (gold∈top5) MIENTE** — no predice cita_ok. Ej: 8b ganó screen (+2) y perdió end-to-end (−1). **Todo candidato se confirma end-to-end (cita_ok) o no cuenta.** Y con set grande (339q), no con 39.

## Infra / gotchas
- Cuello de la máquina = **RAM 14GB**, no VRAM 24GB. Modelos 7B+ por HF crashean al cargar; usar **GGUF/Ollama** (mmap directo a GPU). Ver `reference_ram_vram_ollama_loading` (memoria). NO cerrar servicios del usuario sin permiso.
- Ollama 30b/32b: cuelgue no-determinista → fix retry en `llm.py` (commiteado).
- Modelos/caches en disco externo `/home/alonso/datos` (root chico).
