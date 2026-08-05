# Energy-RAG — instrucciones de proyecto

RAG sobre normativa eléctrica chilena (y futuro: toda la normativa chilena). Stack:
Postgres + pgvector + BM25 (tsvector) + BGE cross-encoder reranker + LLM local (Ollama).
**Hardware (desde 2026-06-29): RTX 3090 24GB, 14GB RAM, offline.** (Antes GTX 1080 8GB Pascal —
esa era imponía "BGE solo CPU", "embedder grande no cabe", "LLM tope 9b"; TODO eso quedó OBSOLETO,
ver `docs/architecture-status.md`.)

## Estado actual (2026-07-31) — leer ANTES de re-experimentar (no rehacer trabajo)

**Config vigente (mejor medida, retrieval por flags default-OFF + gen en `.env`):**
- embedder: `qwen3-embedding:4b` truncado MRL a 1024-dim (`embed_4b_dense`+`embed_4b_dim=1024`), col `embedding_4b_1024` (HNSW).
- `alias_union` (flag): vocabulario controlado coloquial→legal query-side (`src/pipelines/alias_map.py`).
- reranker BGE en GPU (`BGE_DEVICE=cuda`), gate off-topic `AND` (léxico+BGE).
- gen LLM: **`qwen3:30b-a3b`** (`.env` LLM_DEFAULT) — ganó bake-off de 13 modelos.

**Resultados cita_ok:** coloquial ~26→**37/39** (95%), dev ~29→**36/44**, holdout **17/18** (sin regresión).
Coloquial subió por RETRIEVAL (4B+alias); dev por GENERACIÓN (30b-a3b).

**Ya probado — NO repetir** (detalle: `architecture-status.md` + `docs/handoff-2026-07-31.md`):
- embedder 8B = trade-off (dev +5, coloq −4), NO gana coloquial. 4B queda.
- ningún embedder (0.6b/8b/bge-m3) rescata los muros coloquiales; solo alias.
- LLMs gen probados: 30b-a3b > qwen3:32b > 9b > qwen2.5:32b/phi4 > mistral/gemma3 > deepseek-r1. gemma2:27b roto (no cita).
- NEGATIVOS previos: citation_repair, concept_inference, doc2query, fine-tune 0.6b, HyDE, selective_reform.

**Frentes ABIERTOS:** (1) dev cluster **art 225** (glosario LGSE, 4 fallas); (2) coloquial residual 104 (vida útil) + 250604/2 (planta solar); (3) commit del combo 3090 (NADA commiteado aún).

**REALIDAD DE LA MÉTRICA (2026-08, CRÍTICO):** el cita_ok in_domain real es ~84% (confirmado eval v2, 234/279) (eval limpio
con `also_gold`, `data/eval/queries_balanced_v2_clean.jsonl`), NO el 62% que daba el eval sucio.
El "62%" era **injusticia de eval** (rechazaba definiciones alternativas válidas). Frente
retrieval/reranker AGOTADO: M1 pool, G1 grafo, M2 def_fragments, rechunk, RK1 Qwen3-Reranker →
TODOS negativos/flat (medidos con McNemar pareado). La mejor mejora de la campaña fue **arreglar la
métrica** (+19). cita_ok(81%)≈gold@10(85%) → casi no hay gap de gen. Antes de más experimentos:
LIMPIAR EL EVAL (quedan golds rotos: Mora 250604/5, Reposición 29819/2 D). Detalle: `docs/campaign-def-recall-2026-08.md`.

**REGLA — MARCAR EL BACKLOG (obligatorio):** al terminar CUALQUIER experimento, marcar su checkbox
en `docs/backlog-mejoras.md` en el mismo commit: `[x]` adoptado / `[-]` probado-descartado / `[~]`
en curso, con el Δ medido (ej "+3 McNemar p=0.25 ruido"). Si no está en el backlog, agregarlo. NUNCA
dejar un experimento corrido sin su check — el backlog es la única fuente de "qué falta / qué ya se probó".

**Backlog UNIFICADO de mejoras:** cola activa única en `docs/backlog-mejoras.md` — consolida el
research verificado (`docs/research-improvements-2026-07-31.md`) + TODO el trabajo futuro previo
disperso (handoffs, `graphrag-roadmap.md`, `roadmap-gap-analysis`, ADRs). Protocolo: flag-gated,
medir dev+holdout, anotar HECHO con Δ; si mejora sin regresión → **reemplaza la config vigente de
arriba**; si no → "PROBADO — NO repetir". **REGLA DE ORO: el screen (gold∈topN) MIENTE, solo
adopta cita_ok e2e.** Orden sugerido: **E0 robustez de eval (BLOQUEANTE — sets 39/44/18 no detectan Δ≤2; usar
balanced_v2 339q + McNemar pareado + gen 2×)** → M1 rerank 50-100 (gratis) → G1 grafo concepto→art
cableado (infra ya existe, ataca 4 fallas) → M2 1def=1frag → E1 métrica RAGAS → RK1 upgrade reranker
Qwen3-Reranker (gap ~14pts, open, cabe en 3090) → M3 STARA → M4 step-back.
Bloqueante legal aparte: D1 vigencia/derogación (gap de DATOS, no citar norma derogada). NO hacer:
HyDE/multi-query (dañan cita_ok). El stack actual YA es baseline SOTA legal 2024-26 — ganancias de
datos/estructura, no swaps de modelo. Frontera solo como REFERENCIA "si escalo", no cola activa.

**GOTCHA correr evals (post-reboot):** usar `env -i` limpio (el env heredado rompe HF offline aun con
HF_HOME seteado) + PATH con `/usr/local/bin` (ollama) + `HF_HOME=/home/alonso/datos/hf`. Detached con
`setsid` + log al dir del proyecto (la sesión se reinicia, borra /tmp, mata procs no-setsid). Modelos
viven en `/home/alonso/datos` (Ollama + HF), NO en root. Postgres `energy_rag_pg` (Docker :5434) se
apaga solo → `docker start energy_rag_pg`.

## Principios de arquitectura (OBLIGATORIOS al diseñar)

1. **Pensar a ESCALA GRANDE, siempre.** El corpus hoy es chico (~78 normas / ~3000 artículos)
   pero crecerá a TODAS las leyes chilenas (miles de normas, cientos de miles de artículos).
   La prueba final NO es con los datos chicos de hoy. Toda decisión de arquitectura debe
   incluir un análisis de cómo escala: índices aproximados (HNSW) vs exactos; umbrales
   absolutos (frágiles) vs recalibrables; costo por query constante vs creciente; filtrado
   de dominio que aguante más leyes; degradar con gracia al crecer.

2. **Investigar el estándar/vanguardia ANTES de construir.** Mapear qué hace la industria y
   componer sobre piezas estándar; no reinventar ni sobrevender una composición propia como
   si fuera un patrón con nombre. Verificar quién lo usa así, en concreto.

3. **Disciplina experimental.** Flag-gated (default OFF hasta validar), medir dev Y held-out
   (caza overfit), no-regresión, documentar el ADR/handoff junto al cambio. El gold del
   held-out se lee de la ley, no se deriva del sistema.

4. **Restricciones duras.** Sin API paga (solo Ollama/local). HF_HUB_OFFLINE=1. Verificar
   GPU+RAM antes de evals largos. Respuestas y commits: ver memoria del proyecto.
