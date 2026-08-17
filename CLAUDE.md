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
- **`glossary_inject` (default ON desde 2026-08-05)**: inyección determinista término-glosario→artículo
  padre en queries de definición (`vectorstore.def_exact` + `retrieve._definition_concept`).
  **+16 queries, 0 pérdidas, McNemar p=0.0000** → cita_ok in_domain 83.5%→**89.2%**.
- reranker BGE en GPU (`BGE_DEVICE=cuda`), gate off-topic `AND` (léxico+BGE).
- gen LLM: **`qwen3:30b-a3b`** (`.env` LLM_DEFAULT) — ganó bake-off de 13 modelos.
- **`self_consistency_n=3` (ADOPTADO 2026-08-10)**: 3 generaciones a T=0.7, se elige la que más
  respalda el consenso de citas (las que salen en ≥2 de 3). **cita_perfecta 85→114, precisión
  0.59→0.66, cita_ok plano.** Rompe el sesgo funcional-vs-definitorio. ⚠️ COSTO: 3× latencia
  (20.8→61.4 s) — bajar a 0 si la latencia manda.
- `articulos.derogado` marcado en 2 artículos (D1 offline; la vigencia por NORMA sigue bloqueada
  por BCN 429).

**Resultados cita_ok:** coloquial ~26→**37/39** (95%), dev ~29→**36/44**, holdout **17/18** (sin regresión).
Coloquial subió por RETRIEVAL (4B+alias); dev por GENERACIÓN (30b-a3b).

**Ya probado — NO repetir** (detalle: `architecture-status.md` + `docs/handoff-2026-07-31.md`):
- embedder 8B = trade-off (dev +5, coloq −4), NO gana coloquial. 4B queda.
- ningún embedder (0.6b/8b/bge-m3) rescata los muros coloquiales; solo alias.
- LLMs gen probados: 30b-a3b > qwen3:32b > 9b > qwen2.5:32b/phi4 > mistral/gemma3 > deepseek-r1. gemma2:27b roto (no cita).
- NEGATIVOS previos: citation_repair, concept_inference, doc2query, fine-tune 0.6b, HyDE, selective_reform.

**Frentes ABIERTOS:** (1) dev cluster **art 225** (glosario LGSE, 4 fallas); (2) coloquial residual 104 (vida útil) + 250604/2 (planta solar); (3) commit del combo 3090 (NADA commiteado aún).

**REALIDAD DE LA MÉTRICA (2026-08-10, CRÍTICO):** cita_ok **contestables 261/264 = 98.9%**
(`data/eval/queries_balanced_v2_clean.jsonl`). Camino: 62% (eval sucio) → 84% (E0b `also_gold`) →
89.2% (`glossary_inject` +16) → 90.7% (fixes de gen: num_ctx+num_predict, los timeouts se contaban
como False) → **94.4% (E0c: 12 queries marcadas `unanswerable` — piden definiciones que el corpus
NO contiene; el sistema rechaza CORRECTAMENTE y el eval lo penalizaba)**.
→ **97.4% (GEN9a: `CITATION_PATTERN` no aceptaba `[Art. primero de X]`; 9% del corpus no era
citable y `strip_malformed_citations` BORRABA la cita de la respuesta. +7, p=0.016)**.
⚠️ Las `unanswerable` deben puntuar **rechazo = acierto** (como `off_corpus`). Hoy 8/12.
Probados y NEGATIVOS/flat (McNemar pareado): M1 pool, G1 grafo crudo, M2 def_fragments, rechunk,
RK1 Qwen3-Reranker. Lo que SÍ movió: arreglar la métrica (+19) y `glossary_inject` (+16).
**CALIDAD (E1, `scripts/eval_metrics.py`):** `cita_ok` **PREMIA ROCIAR** — mide "¿alguna cita pega?".
Por eso `think=True` parecía negativo (−16) cuando en precisión ganaba. **RESUELTO 2026-08-10
adoptando GEN2 self-consistency**, que sube precisión SIN costar aciertos:
`cita_limpia` 170→**188/264** · `cita_perfecta` 85→**114** · precisión 0.59→**0.66**.
`think=True` y el híbrido quedan DESCARTADOS (pierden 16 y 10 golds respectivamente).

**REGLAS (cada una costó un error real):**
1. Auditar el gold ANTES de construir el fix.
2. Todo scorer nuevo declara cómo puntúa el RECHAZO antes de correrse (fallado 2 veces).
3. Auditar el eval exige las MISMAS normalizaciones que usa el eval.
4. Medir pareado, ambos brazos en la misma sesión.
5. Persistir el TEXTO de las respuestas, no solo el booleano.
6. Re-puntuar texto viejo SUBESTIMA cambios que alteran el bucle de generación.
Detalle: **`docs/handoff-2026-08-09.md`** · `docs/experimentos-registro.md` §6-§8.

**LECCIÓN TRANSVERSAL (2026-08):** cuando el ordenador (cross-encoder) prefiere sistemáticamente el
tipo de documento equivocado, **cambiar de reranker NO sirve** (RK1: Δ+2 ruido) — se sortea con
**inyección determinista** basada en estructura de datos (`glossary_inject` +16, `alias_map` +3).
Ganancias de DATOS/ESTRUCTURA, no swaps de modelo.

**REGLA — MARCAR EL BACKLOG (obligatorio):** al terminar CUALQUIER experimento, marcar su checkbox
en `docs/backlog-mejoras.md` en el mismo commit: `[x]` adoptado / `[-]` probado-descartado / `[~]`
en curso, con el Δ medido (ej "+3 McNemar p=0.25 ruido"). Si no está en el backlog, agregarlo. NUNCA
dejar un experimento corrido sin su check — el backlog es la única fuente de "qué falta / qué ya se probó".

**Backlog UNIFICADO de mejoras:** cola activa única en `docs/backlog-mejoras.md` — consolida el
research verificado (`docs/research-improvements-2026-07-31.md`) + TODO el trabajo futuro previo
disperso (handoffs, `graphrag-roadmap.md`, `roadmap-gap-analysis`, ADRs). Protocolo: flag-gated,
medir dev+holdout, anotar HECHO con Δ; si mejora sin regresión → **reemplaza la config vigente de
arriba**; si no → "PROBADO — NO repetir". **REGLA DE ORO: el screen (gold∈topN) MIENTE, solo
adopta cita_ok e2e.** **Orden vigente = plan por FASES A-D en `docs/backlog-mejoras.md` §PRIORIDAD**
(A exprimir buscador · B gap de gen vía RAGAS · C table-stakes legal · D gate GraphRAG).
Ya cerrados: E0/E0b · glossary_inject(+16) · E3 · E0c(+Tránsito) · D2 · D3 · GEN9a(+7) ·
strip `<think>` · E1 métricas · no-regresión · **GEN2 self-consistency ADOPTADO** ·
D1 mitad offline. Descartados: M1/G1/M2/rechunk/RK1/GEN8a/GEN8b/GEN9b/GEN10/GEN11/GEN12.
**FRENTES DE RETRIEVAL Y GENERACIÓN AGOTADOS.** Siguiente valor: **D1 vigencia por NORMA**
(BLOQUEADO: BCN `obtxml` da 429 de cuota) y **D4 UX de ambigüedad**.
Bloqueante legal aparte: D1 vigencia/derogación (gap de DATOS, no citar norma derogada). NO hacer:
HyDE/multi-query (dañan cita_ok). El stack actual YA es baseline SOTA legal 2024-26 — ganancias de
datos/estructura, no swaps de modelo. Frontera solo como REFERENCIA "si escalo", no cola activa.

**GOTCHA correr evals (post-reboot):** usar `env -i` limpio (el env heredado rompe HF offline aun con
HF_HOME seteado) + PATH con `/usr/local/bin` (ollama) + `HF_HOME=/home/alonso/datos/hf`. Detached con
`setsid` + log al dir del proyecto (la sesión se reinicia, borra /tmp, mata procs no-setsid). Modelos
viven en `/home/alonso/datos` (Ollama + HF), NO en root. Postgres `energy_rag_pg` (Docker :5434) se
apaga solo → `docker start energy_rag_pg`.

**REGLA — NADA DE REGEX COMO MECANISMO PRINCIPAL (2026-08-17, decisión del usuario):**
La detección de intención NO se hace con listas hardcodeadas. Se hace con un clasificador
(embeddings sobre ejemplos, o modelo liviano); **el regex solo puede ir al final como REGLA de
override/fallback**. Motivo medido: `_DEF_INTENT` falla 6 de 13 fraseos naturales
("cómo se define X", "defíneme X", "X definición", "qué entiende la ley por X") y —peor— las
279 queries del set primario usan LAS MISMAS 3 plantillas del regex, así que **el eval se mide
contra sí mismo**. El 99.2% es sobre fraseos que el regex cubre por construcción, no sobre
generalización. Estándar de la industria: regex como primera pasada está bien, quedarse ahí no.
**Antes de cualquier arreglo: queries de test con fraseos que el regex NO cubra**, o toda mejora
se verá como nula.

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
