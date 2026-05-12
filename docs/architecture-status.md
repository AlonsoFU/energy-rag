# Architecture Status — Energy-RAG vs 2026 Meta

> **Última actualización**: 2026-05-12
> **Branch**: `feat/postgres-rag-v1`
> **PR abierto**: [#2](https://github.com/AlonsoFU/energy-rag/pull/2)

Este documento mapea el estado actual del pipeline RAG contra el "meta" de
industria 2026 (lo que usan Glean, Perplexity, Cohere, Anthropic API).

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
│ 3. CROSS-ENCODER RERANKING  ⭐ GAP CRÍTICO #1                │
│ ────────────────────────────                                 │
│ ❌ Qwen3-Reranker carga PERO el classifier head está vacío  │
│ ❌ Hoy: identity rerank → NO reordena nada                  │
│ ◯ Falta: bge-reranker-v2-m3 (OSS, funcional)                │
│                                                              │
│ Lift esperado: +5 a +15 pp grounding                         │
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
| **Cross-encoder reranking** | ❌ **Roto** | Modelo carga pero classifier head vacío → identity rerank |
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

## 7. Conclusión

**Estás más cerca del meta de lo que parece.** La foundation es sólida (hybrid
search, grounding verifier, glosario curado, referencias graph). Faltan **2
piezas mayores** para llegar al meta completo:

1. **Reranker funcional** (gap crítico #1)
2. **Contextual Retrieval real** (gap crítico #2)

Cualquiera de las dos da lift medible. Las dos juntas ponen el sistema al
nivel de productos comerciales para Q&A factual.
