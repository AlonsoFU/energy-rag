# Architecture Status — Energy-RAG vs 2026 Meta

> **Última actualización**: 2026-06-01 (campaña BGE)
> **Branch**: `feat/definition-source-resolver`
> **Doc de campaña**: `docs/campaign-2026-06-01.md`

Este documento mapea el estado actual del pipeline RAG contra el "meta" de
industria 2026 (lo que usan Glean, Perplexity, Cohere, Anthropic API).

> **NOVEDAD 2026-06-01 — GAP CRÍTICO #1 (reranker) RESUELTO.** El cross-encoder
> `bge-reranker-v2-m3` fue validado en campaña con set held-out: recall@5 dev
> 25→33, holdout 15→17; cita_ok (generación) dev 25→**32**, holdout 14→**17**
> con top_k=10; **grounding intacto** (43/44, 18/18). Cableado flag-gated
> (`use_bge_reranker`+`top_rerank_override`, OFF por default). Ver §8.
> HyDE y graph_boost_all se DESCARTARON por overfit (el held-out lo reveló).

---

## 1. Pipeline meta — esquema completo con status

```
═════════════════════════════════════════════════════════════════
   META 2026 — PIPELINE RAG INDUSTRIA ESTÁNDAR
═════════════════════════════════════════════════════════════════

USUARIO escribe query
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. QUERY UNDERSTANDING                                       │
│ ────────────────────────────                                 │
│ ⚠️  Adaptive router: SimpleRetriever vs ComplexRetriever     │
│ ⚠️  HyDE / multi-query / step-back   ← solo en "complejo"    │
│                                          (raramente activado) │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. RETRIEVAL — HYBRID SEARCH                                 │
│ ────────────────────────────                                 │
│ ✅ BM25 (tsvector Postgres)                                  │
│ ✅ Dense vector (Qwen3-Embedding + pgvector HNSW)            │
│ ✅ RRF fusion → top 50                                       │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CROSS-ENCODER RERANKING  ✅ RESUELTO (2026-06-01)         │
│ ────────────────────────────                                 │
│ ✅ bge-reranker-v2-m3 (CPU; Pascal sm_61 sin kernels GPU)    │
│ ✅ get_reranker(): BGE si use_bge_reranker, si no Identity   │
│ ✅ top_rerank_override≈30 (el rerank cortaba el pool a 10    │
│    ANTES del boost → ahora deja sobrevivir el gold profundo) │
│ ⚠️  Default OFF (costo: latencia CPU ~+seg/query)            │
│ Medido: cita_ok dev 25→32, holdout 14→17; grounding intacto  │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. CONTEXTUAL CHUNKS  ⭐ GAP CRÍTICO #2                      │
│ ────────────────────────────                                 │
│ ⚠️  Columna `contextual_text` EXISTE en DB                   │
│ ⚠️  Hoy: contextual_text = text + preamble                  │
│      (no es contextual real)                                 │
│ ◯ Falta: para cada chunk, generar resumen del doc completo  │
│   con LLM y prependerlo al chunk antes de embeddear         │
│                                                              │
│ Lift esperado: +5 a +10 pp recall                            │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. GRAPH BOOST                                               │
│ ────────────────────────────                                 │
│ ✅ Tabla `referencias` con 4,300 edges                       │
│ ✅ graph_boost() multiplica score por tipo_relacion          │
│ ✅ Concept extraction usa aliases del glosario               │
│ ⚠️  Domain filter activado pero no testeado en eval         │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. HIERARCHICAL EXPANSION  (potencial: parent-doc)           │
│ ────────────────────────────                                 │
│ ⚠️  Existe pero solo expande chunks → artículos parciales   │
│ ◯ Mejora posible: parent-doc retrieval completo             │
│                                                              │
│ Lift esperado: +3 a +10 pp queries descriptivas              │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. ANSWER GENERATION                                         │
│ ────────────────────────────                                 │
│ ✅ Constrained decoding (JSON schema enum de citas)          │
│ ✅ Few-shot prompts (3 ejemplos)                             │
│ ✅ Retry-on-fail con initial_top                             │
│ ✅ Ollama qwen3.5:9b local                                   │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. ANTI-HALLUCINATION                                        │
│ ────────────────────────────                                 │
│ ✅ Grounding verifier: cada cita verbatim contra docs        │
│ ✅ Reject + retry si falla                                   │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
USUARIO recibe respuesta con citas
```

---

## 2. Resumen de posición por capa

| Capa | Status | Notas |
|---|---|---|
| **Foundation** (BM25 + dense + RRF + grounding) | ✅ **Completo** | Al nivel del meta |
| **Cross-encoder reranking** | ✅ **Resuelto (flag, OFF)** | bge-reranker-v2-m3 validado: +cita_ok dev 25→32 / holdout 14→17, grounding intacto. CPU. |
| **Contextual chunks** | ⚠️ **Estructura sin contenido** | Columna existe, hoy = text + preamble |
| **Graph augmentation** | ✅ **Avanzado** | Tabla `referencias` con 4,300 edges, una de las cosas más adelantadas del proyecto |
| **Generation con citas** | ✅ **Completo** | Constrained decoding + verifier verbatim |

---

## 3. Métricas actuales (post-Sprint 1+2+3 + SemanticChunker)

Eval completa 50 queries (`data/eval/results/20260512T180156Z.json`):

| Métrica | Baseline 2-may | Post-Sprint 12-may | Δ |
|---|---|---|---|
| recall@5 (norma+articulo) | 95.8% | 93.8% | -2.0 pp |
| recall@5 (norma) | 95.8% | 95.8% | 0 |
| grounding_pass | 70.8% | 66.0% | -4.8 pp |
| negative_correct | 100% | 50.0% | -50 pp |
| latency p50 | 44s | 35.5s | -19% (mejor) |
| n_with_generation | 48 | 47 | -1 |

Eval queries-con-aliases 15 queries (`data/eval/results/20260512T004231Z.json`):

| Métrica | Pre-chunker | Post-chunker v2 | Δ |
|---|---|---|---|
| recall@5 | 13.3% | 46.7% | **+33.4 pp** ⭐ |
| grounding | 100% (de 2) | 100% (de 7) | 3.5× más queries acertando |

**Tradeoff observado**: el SemanticChunker mejora drásticamente queries cortas
(aliases, conceptos puntuales) pero degrada queries descriptivas largas. El
Sprint completo es mejora local + regresión global.

---

## 4. Próximos pasos al meta — ranking por ROI

| # | Acción | Effort | Lift esperado | Riesgo |
|---|---|---|---|---|
| 1 | **Reemplazar reranker** Qwen3 → bge-reranker-v2-m3 | 1-2 h | +5 a +15 pp grounding | bajo — sin re-ingest |
| 2 | **Contextual Retrieval real** (LLM genera resumen de doc para cada chunk) | 4-6 h cómputo Ollama | +5 a +10 pp recall | bajo — re-ingest 3,318 chunks |
| 3 | **Parent-doc retrieval** completo en `hierarchical_expand` | 2-3 h | +3 a +10 pp queries descriptivas | bajo — sin re-ingest |
| 4 | **GraphRAG** sobre tabla `referencias` (caminos de 2-3 saltos) | 3-5 días | +5 a +15 pp queries complejas | medio — refactor |

---

## 5. Frontera 2026 que NO recomiendo todavía

| Técnica | Por qué no |
|---|---|
| **ColBERT / late interaction** | Sería gran ganancia pero requiere modelo distinto y re-índice completo (5-7 días). Ataque cuando los pasos 1-3 estén hechos. |
| **Long-context LLM** como reemplazo (Gemini 2M, Claude 200k) | Tu sistema es local-first sin API paga. No aplica. |
| **Generative retrieval (DSI)** | Research, no production-ready. |
| **Self-RAG / Adaptive RAG** | +2-5 LLM calls por query, latencia 2-3× actual. Considerar después de los pasos 1-3. |

---

## 6. Tabla de cambios aplicados en Sprint 2026-05-04 a 2026-05-12

Lista cronológica de commits en `feat/postgres-rag-v1`:

| Commit | Cambio |
|---|---|
| `f9056bb` | Auto-validate 23 high-confidence aliases (Fase 1 glosario) |
| `4f6615c` | Promote 18 medium aliases post-WebSearch (Fase 2) |
| `f532be4` | Reranker init fix (pad_token, logits shape) — quedó como identity |
| `b43fe3b` | Reranker → identity rerank explícito (post-eval regression) |
| `141b058` | Sprint 1+2+3 (#1, #2, #3, #5, #7, #8, #10) |
| `1fdb66b` | SemanticChunker v1 + re-ingest 279 articulos (introdujo regresión) |
| `b4fa949` | SemanticChunker fix: `;` como sentence boundary (+33pp recall en aliases) |

---

## 8. Pipeline vigente tras la campaña 2026-06-01 (lógicas y algoritmos)

Orden real de ejecución de una query (rama `feat/definition-source-resolver`):

1. **Off-topic gate** (`off_topic.is_off_topic`): si las palabras significativas de la
   query no están en el vocabulario del corpus → rechazo directo, sin LLM. Anti-alucinación.
2. **Router** (`AdaptiveRouter`, TF-IDF + LinearSVC): clasifica `simple` vs `complejo`.
   - `complejo` → `ComplexRetriever`: expande con **HyDE + step_back + multi_query** (LLM local)
     y fusiona por RRF sobre todas las variantes. (OJO: HyDE aquí es del Complex, distinto del
     flag `hyde_in_simple` que se DESCARTÓ por overfit.)
   - `simple` → `SimpleRetriever`.
3. **Retrieval híbrido** (ambas ramas): **BM25** (tsvector) + **denso** (Qwen3-Embedding-0.6B,
   pgvector HNSW) → **RRF fusion** ponderada por largo de query (`_length_weights`: query corta
   pesa BM25, larga pesa vectores). Pool = `retrieval_pool_depth` (50).
4. **Rerank** (`get_reranker`): **NUEVO** — `BGEReranker` (cross-encoder bge-reranker-v2-m3, CPU)
   reordena el pool por relevancia semántica query↔doc cuando `use_bge_reranker=True`; si no,
   `IdentityReranker` (preserva orden RRF). `top_rerank_override` (≈30) controla cuántos
   candidatos sobreviven a esta etapa (antes 10 fijo → truncaba el gold profundo).
5. **Concept extraction + graph_boost**: detecta conceptos del glosario en la query y sube los
   artículos con arista `define_termino`/`cita` a esos conceptos. El boost fuerte (+10) aplica a
   match por **alias**; `graph_boost_all` (extenderlo a match canónico) se PROBÓ y DESCARTÓ (overfit).
6. **Hierarchical expand**: fragmento → artículo padre.
7. **Inject curado** (`inject_definition`, solo queries definicionales "qué es X" con match exacto
   de concepto): antepone el artículo-definición curado, aun si retrieval lo perdió. Legal-safe
   (normalización estricta, aristas curadas). Para alias inyecta el link «alias»→«canónico».
8. **Generación** (`generate_answer`, Ollama qwen3.5:9b, top_k=10 recomendado): prompt few-shot;
   patrón híbrido (sin JSON-schema, que deadlockea en Ollama) + **verify_citations** post-hoc.
9. **Anti-alucinación**: cada cita se verifica verbatim contra el pool; si falla, retry con
   instrucción más estricta; fallback a verificación contra corpus (existe (norma,art) en DB).
10. **Anchor determinista** (`_anchor_authoritative_citation`, flag OFF): si la query centra en
    un concepto con artículo autoritativo A y la respuesta no citó la norma de A, anexa la cita
    curada. Monótono sobre cita_ok.

**Config recomendada por la campaña**: `use_bge_reranker=True` + `top_rerank_override=30` +
`--top-k 10`. Descartados por held-out: `hyde_in_simple`, `graph_boost_all`. Nulos: pool_depth>50.

## 8b. Registro de límites de hardware (distinguir "bloqueado" de "solo más lento")

**Bloqueo DURO** (literalmente no ejecuta hoy → mejora teórica para cuando cambie el hardware):

| Lever | Hipótesis | Bloqueo | Qué lo desbloquea |
|---|---|---|---|
| **BGE en GPU** | reranker ~10-50× más rápido → elimina el costo de latencia que frena adoptarlo por default | GTX 1080 (Pascal sm_61) sin kernels para el cross-encoder ("no kernel image") | GPU Turing+/Ampere (RTX 20xx+) |

**Solo MÁS LENTO** (corre en CPU/tarda más → se mide igual, la latencia es dato de costo, no bloqueo):

| Lever | Hipótesis | Costo hoy | Acción |
|---|---|---|---|
| **BGE `max_length` 512→2048** | cubre el ~30% de chunks (>1800 chars) que hoy se truncan a 512 | CPU ~4× cómputo por par | **medible ahora** (background); latencia = decisión de producto |
| **Contextual chunks (gap #2)** | resumen del artículo por LLM antepuesto a cada chunk → +recall en paráfrasis | re-ingesta ~3.900 chunks = horas Ollama | medible (re-ingesta lenta, no bloqueo) |
| **Re-chunk glosario fino (art 225)** | 1 def = 1 fragmento → cada def cabe entera en el reranker | re-ingesta + re-embed | medible (lento, no bloqueo) |

## 7. Conclusión

**Estás más cerca del meta de lo que parece.** La foundation es sólida (hybrid
search, grounding verifier, glosario curado, referencias graph).

- ✅ **Gap #1 (reranker) RESUELTO** (2026-06-01): bge-reranker-v2-m3 validado con held-out,
  +cita_ok sin perder grounding. Flag-gated (OFF). Falta decisión de producto por la latencia CPU.
- ◯ **Gap #2 (Contextual Retrieval real)** sigue pendiente: hoy `contextual_text` = text + preamble.
  Es el próximo lift de recall (resumen del artículo por LLM, antepuesto al chunk antes de embeddear)
  — ataca directo el fallo "operativo no glosario / paráfrasis no matchea".

**Lección de método de la campaña**: medir SIEMPRE en un set held-out independiente (gold leído de
la ley, no del propio sistema). Reveló que HyDE y graph_boost_all eran overfit — habrían sido
adoptados mirando solo el set de desarrollo.
