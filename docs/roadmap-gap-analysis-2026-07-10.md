# Gap analysis — estándar SOTA RAG-legal vs este sistema (2026-07-10)

Auditoría honesta. Se investigó el estándar 2025-2026 completo (3 agentes: retrieval, generación,
legal+data) y se cruzó técnica-por-técnica contra lo que el repo YA tiene. Objetivo: NO decir
"solo falta grafo". Decir la verdad de qué falta y qué está.

**Ancla de realidad (Stanford RegLab, JELS 2025):** el mejor legal-RAG comercial aún alucina
(Lexis+ ~17%, Westlaw >34%). Dos fallos: *incorrecto* (mal la ley) y *misgrounded* (ley correcta,
cita que no la respalda). Nuestros 4 gen-fails (gold rank 1, cita vecino) = exactamente *misgrounded*.

Estados: **✅ PROD** (en producción) · **🔬 probado, no convirtió** (flag off) · **🏗️ infra parcial**
(código existe, no cableado/medido) · **❌ ausente**.

---

## RETRIEVAL

| técnica | estándar | estado | nota |
|---|---|---|---|
| BM25 híbrido | table-stakes | ✅ PROD | |
| embedder denso (Qwen3-4B) | table-stakes | ✅ PROD | |
| Matryoshka/MRL (trunc 1024) | standard | ✅ PROD | |
| fusión RRF + peso por largo | table-stakes | ✅ PROD | falta score-normalization fusion (🔬) |
| reranker cross-encoder (bge-v2-m3) | table-stakes | ✅ PROD | 10 modelos probados, imbatible |
| chunking section-aware + contextual (LLM) | standard | ✅ PROD | Anthropic Contextual Retrieval |
| alias/glosario coloquial→legal | standard | ✅ PROD (parcial, a mano) | |
| gate off-topic | standard | ✅ PROD | |
| HNSW | table-stakes | ✅ PROD | |
| query rewrite / HyDE / ensemble | standard | 🔬 off | +retrieval, −cita_ok (distractores) |
| doc2query | standard | 🔬 off (`bm25_doc2query`) | probado, no convirtió |
| CRAG corrective | advanced | 🔬 off (`crag_routing`) | implementado, off |
| small-to-big / parent-doc | standard | 🔬 probado 2026-07-10 | no gana (−2/−4), ver chunking-rules §6b |
| concept_inference | — | 🔬 off | trade-off |
| **grafo concepto→artículo** | advanced (alto valor legal) | 🏗️ infra parcial | `graph_builder.py`, `follow_remissions.py`, `glossary_define_edges.py`. NO medido end-to-end. **Ataca 4 retrieval-fail** |
| **cross-ref / remisión following** | advanced | 🏗️ infra parcial | `follow_remissions.py` existe, no cableado a retrieval |
| **decomposición / multi-hop** | standard | 🏗️ infra parcial | `exp_multihop.py`, `diag_decompose.py`. No en prod |
| **metadata filtering (por norma/tipo/fecha)** | table-stakes | ❌ ausente en `search_vector` | el vectorstore NO filtra por metadata; se recupera de todo el corpus |
| SPLADE / learned sparse | standard | ❌ ausente | |
| ColBERT / multi-vector | advanced | ❌ ausente | |
| RAPTOR (árbol de resúmenes) | advanced | ❌ ausente | |
| step-back prompting | advanced | ❌ ausente | útil para preguntas por principio |
| self-query (NL→filtros) | standard | ❌ ausente | |
| MMR / diversidad | standard | ❌ ausente | |

## GENERACIÓN — el cuello real de cita_ok

| técnica | estándar | estado | nota |
|---|---|---|---|
| grounding constraint ("solo del contexto") | table-stakes | ✅ PROD | `prompts.py` |
| instrucción de cita inline | table-stakes | ✅ PROD | |
| abstención / rechazo | table-stakes | ✅ PROD | gate + refusal |
| stuff/compact synthesis | table-stakes | ✅ PROD | |
| low-temp decoding | table-stakes | ✅ PROD | |
| constrained decoding / JSON | table-stakes | ✅ PROD (`grammar.py`) | flag `use_constrained_decoding` |
| reranker+filtro antes de generar | table-stakes | ✅ PROD | |
| citation verify post-hoc | standard | 🔬 off (`citation_repair`) | verify-cite dio 0/6 |
| **generador fuerte (Claude vs 30b head-to-head)** | standard | ❌ NO medido | 30b-a3b +9 fue el único win; Claude nunca comparado directo. **Hipótesis del usuario: mejor generador aguanta el ruido que hunde al rewrite** |
| **self-consistency (N muestras, votar)** | standard | ❌ ausente | ataca los 4 gen-fails |
| **lost-in-the-middle reordering** | standard | ❌ ausente | barato |
| **context compression (LLMLingua)** | standard | ❌ ausente | menos ruido al LLM |
| faithfulness/NLI groundedness score | standard | ❌ ausente | mide misgrounded, no lo arregla |
| Chain-of-Verification (CoVe) | advanced | ❌ ausente | |
| Self-RAG reflection tokens | advanced | ❌ ausente | |
| generator ensemble + LLM-judge | advanced | ❌ ausente | |

## LEGAL-ESPECÍFICO

| técnica | estándar | estado | nota |
|---|---|---|---|
| cita a artículo exacto + rastreable (`articulo_id`) | table-stakes | ✅ PROD | |
| jerarquía/autoridad de norma | table-stakes (como metadata) | 🏗️ `extraction/authority.py` | extraído, **no pesa el ranking** |
| defined-terms / glosario | advanced | ✅ PROD (parcial) | |
| **vigencia / qué ley está EN FUERZA** | table-stakes legal | ❌ ausente (crítico) | `date_extraction.py` saca fecha_publicacion pero **NO se filtra derogadas**. Task #101 pendiente. **Citar ley muerta = error grave** |
| derogación / amendment tracking | advanced | 🏗️ parcial | derogación CC 52-53 conocida; BCN vinculaciones VACÍAS en datos |
| point-in-time (texto vigente a fecha X) | advanced (frontier) | ❌ ausente | vendors lo difieren a humano — defer explícito es válido |
| term-scoping (def según contexto/ley) | advanced (poco commoditizado) | ❌ ausente | mapea a "contexto manda sobre rango" |
| jurisdiction filtering | table-stakes | N/A | corpus mono-jurisdicción (Chile) |
| provenance / audit trail | table-stakes (regulado) | 🏗️ parcial | se loguea, no auditoría formal |
| human-in-the-loop review gate | table-stakes profesional | ❌ ausente | |

## DATA / EVAL

| técnica | estándar | estado | nota |
|---|---|---|---|
| set eval (gold, dev/holdout) | table-stakes | ✅ PROD | coloquial 39, dev 44, holdout 18, balanced_v2 339 |
| eval no-regresión dev+holdout | table-stakes | ✅ PROD (disciplina manual) | |
| curación glosario/alias | table-stakes (barato) | ✅ PROD (parcial, a mano) | precedente: Spanish Legal terminology RAG |
| hard-negative mining (BM25+CE) | standard (si fine-tune) | ❌ ausente | |
| **RAGAS / DeepEval / faithfulness metric** | table-stakes | ❌ ausente | medimos cita_ok casero, NO faithfulness/context-precision estándar |
| observabilidad (Langfuse/Phoenix) | table-stakes prod | ❌ ausente | |
| feedback loop (thumbs, click) | table-stakes | ❌ ausente | pre-producción |
| fine-tune embedder (pares dominio) | advanced alto valor | ❌ ausente | fine-tune 0.6B dio overfit; falta con set grande |
| fine-tune reranker | advanced | ❌ ausente | |
| fine-tune generador (LoRA/RAFT) | advanced último recurso | ❌ ausente | |

---

## Veredicto honesto — NO "solo falta grafo"

**Gaps table-stakes REALES (no cosméticos):**
1. **Vigencia** — no se filtran normas derogadas. Legal-crítico. Puede citar ley muerta. (task #101)
2. **Metadata filtering** — `search_vector` no filtra por norma/tipo/fecha; recupera de todo.
3. **Faithfulness metric estándar** (RAGAS) — medimos cita_ok casero, no el estándar; no medimos "misgrounded" directo.
4. **Autoridad no pesa el ranking** — la jerarquía se extrae pero no influye retrieval.

**Gaps de generación (el cuello de cita_ok, poco tocado):**
5. Generador fuerte (Claude) nunca medido cabeza a cabeza vs 30b.
6. self-consistency, lost-in-the-middle reorder, context compression — todos ausentes, baratos.

**Alto valor, infra parcial (empujar):**
7. **Grafo concepto→artículo** — ataca los 4 retrieval-fail. Infra a medias.
8. Cross-ref/remisión, multi-hop — infra a medias.

**Diferido explícito (frontier, hasta vendors lo defieren a humano):**
- point-in-time, term-scoping, amendment tracking, fine-tune (todos), agentic/Self-RAG/CoVe, SPLADE/ColBERT/RAPTOR.

**Lo mejor probado ya está en producción.** El stack core (híbrido+RRF+reranker+contextual+alias+gate)
es estándar completo. Lo que falta se parte en: (a) **correctitud legal** (vigencia, metadata, autoridad),
(b) **generación** (el cuello), (c) **grafo** (retrieval-fail), (d) **medición estándar** (RAGAS/obs).

**Recomendación de orden (revisada tras auditar vigencia 2026-07-10):**
RAGAS/faithfulness (accionable YA, mide misgrounded) → generador fuerte + self-consistency (cuello) →
grafo (retrieval-fail) → metadata+autoridad (código prod) → vigencia (BLOQUEADO: `estado` vacío,
89/95 DESCONOCIDO — derivar desde BCN primero) → fine-tune (raíz, caro, último).
