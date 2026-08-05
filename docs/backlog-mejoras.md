# Backlog UNIFICADO de mejoras (trabajo futuro)

Consolida: (a) research verificado 2026-07-31 (`docs/research-improvements-2026-07-31.md`) +
(b) TODO el trabajo futuro previo disperso en los docs del repo (handoffs, roadmaps, ADRs,
graphrag-roadmap, gap-analysis). Es la **cola activa única** — reemplaza backlogs sueltos.

## Protocolo (OBLIGATORIO por experimento)
1. Flag-gated, default OFF.
2. Medir dev + holdout (caza overfit) + no-regresión vs config vigente.
3. Al terminar: anotar en **HECHO** con Δ medido (dev/coloq/holdout).
4. Si da MEJOR sin regresión → se adopta y **reemplaza la config vigente** (`CLAUDE.md` + flags/`.env`).
   Si no → pasa a **PROBADO — NO repetir** con el nombre.
5. ADR/handoff junto al cambio, no al final.

## ⚠️ REGLA DE ORO (aprendida a los golpes)
**El screen (gold ∈ topN) MIENTE.** Nada se adopta por screen, solo por **cita_ok end-to-end**.
Test para cada item nuevo: *¿esto AGREGA el gold al pool, o solo mete ruido alrededor de un gold
que ya estaba?* (`experimentos-registro.md`, `chunking-rules.md §6`).

## ⚠️ ROBUSTEZ ESTADÍSTICA (los sets chicos NO detectan deltas chicos)
Sets actuales: coloquial **39**, dev **44**, holdout **18** (~101). Ruido binomial ≈ **±2 queries
= 1σ**; holdout ±2 casi inútil. El LLM **flickea ±1** por corrida (verificado). → **Δ≤2 es RUIDO,
NO se adopta.** Los WINs grandes de la campaña (+7, +11) SÍ son reales (~4-5σ); de acá en adelante
los deltas serán chicos (1-3) → hay que endurecer la medición:
- **Set primario `balanced_v2` (339q)**, no coloquial (39q). Más n = menos ruido. (Ya existe.)
- **McNemar pareado** (retrieval/pool fijo → pares): mirar los FLIPS, no 37/39 vs 38/39. Necesitas
  **≥5-6 flips netos** para p<0.05. Reportar qué queries flipean.
- **Gen 2× + promediar** (LLM flickea ±1).
- Gold **se lee de la ley**, NO se deriva del sistema (`CLAUDE.md` principio 3).

Estados: `[ ]` pendiente · `[~]` en curso · `[x]` hecho-adoptado · `[-]` probado-descartado ·
`🏗️` infra existe, sin medir e2e · `❌` ausente · `⏳` diferido.

---

## PRIORIDAD RECOMENDADA (actualizada 2026-08-05 — plan por FASES)

**HECHO esta campaña:** [x] E0/E0b (eval real 84%, no 62%) · [-] M1 (ruido) · [-] G1 crudo (aristas
vacías) · [-] M2/def_fragments/rechunk (flat) · [-] RK1 (Δ+2, dead). Detalle: `campaign-def-recall-2026-08.md`.

**Diagnóstico del buscador (2026-08):** recall@10 = 89%. De 45 fails in_domain: 13 ranking +
19 embedding-miss (6 glosario / 2 acrónimos / 5 coloquial) + ~13 gen.

### FASE A — exprimir el buscador (local/barato)
1. [~] **glossary_inject** — arista determinista término→artículo (GraphRAG-1-salto). Ataca 6 glosario. EN CURSO (parcial 7-0).
2. [ ] **M1 re-test pool=100 sobre eval limpio** — ataca 13 ranking (gold en vector@50-100). Gratis.
3. [ ] **D2 siglas** — extractor determinista para 2 acrónimos (TON, DIP).
4. [ ] **G3 fix dedup** `build_candidates` — bug conocido, barato.
5. [ ] **5 coloquiales** — curación manual de aliases (no ingeniería).
   Techo teórico si TODO pega: 84% → ~93% retrieval-side.

### FASE B — gap de GEN (~13 fails no-retrieval)
6. [ ] **E1 RAGAS faithfulness** — medir QUÉ falla en gen ANTES de tocar gen.
7. [ ] **GEN6 fix runner** (trivial) + **GEN3 reordering** (barato) + **GEN2 self-consistency** si E1 lo justifica.

### FASE C — table-stakes legal pre-producción
8. [ ] **D1 vigencia** (scrape BCN) — proyecto de DATOS, paralelo, sin GPU. Único error GRAVE del sistema (citar norma derogada).
9. [ ] **R1 metadata filtering** + **GEN5 fallback≠rechazo**.

### FASE D — gate GraphRAG
10. [ ] **G9 eval multi-hop** — gold relacional para DECIDIR si G5-G10 valen. Sin esto no se invierte en traversal.

**Diferido:** FT1/FT2, escala, frontera (referencia).

### ADMIN / limpieza
- [ ] **E0c · golds rotos restantes** — Mora 250604/5, Reposición 29819/2-D (nombrados en CLAUDE.md).
- [ ] **ADM1 · merge PR #12 a main** — todo vive en `adopt-winners`, nada en main. Cerrar cuando glossary_inject decida.
- [ ] **C2-drop · drop tabla `fragmentos_inciso`** mixta (1248/7141 phi4) — recomendado, deuda vieja (ver C2).

> **Bloqueante legal aparte (D1 vigencia):** citar norma derogada = error grave. Es gap de DATOS,
> no de código. No bloquea M1-M4 pero es prioritario antes de producción real.

---

## RETRIEVAL

- [-] **M1 · rerank 50-100 candidatos** (no top-10). 1 param (`retrieval_pool_depth` al rerank).
  PROBADO 2026-08: +3 McNemar p=0.25 = RUIDO (no adoptado). El gold no está en rank 50-100.
  NOTA: diagnóstico posterior mostró 13 ranking-fails (gold en vector@50-100) → re-probar con eval limpio.
- [ ] **R1 · metadata filtering en `search_vector`** (WHERE por norma/tipo/fecha). Hoy recupera del
  corpus entero, sin filtro. Table-stakes a escala. `roadmap-gap-analysis`. ❌ ausente.
- [ ] **R2 · authority_rank_boost** (LEY>DECRETO>RES en fusión). Flag existe, medido FLAT (corpus
  76% LEGAL, mono-tier). 🔬 OFF — **reactivar cuando el corpus sea multi-tier**. `exp-authority-2026-07-16`.
- [ ] **R3 · Query2Doc** (HyDE ADITIVO: concatena pseudo-doc con query original, NO reemplaza).
  Candidato "seguro", prompt listo, nunca implementado. Distinto de HyDE puro. `tecnicas-query-retrieval #2`.
- [ ] **R4 · intent/entity extraction** — prototipo coloquial +1/dev −1 (term drift). Prompt listo.
  🔬 marginal. `tecnicas-query-retrieval #6`.
- [ ] **R5 · router by confidence (bge_max)** en vez de TF-IDF `AdaptiveRouter`. ⏳ idea. `architecture-status §8`.
- [ ] **R6 · bajar umbral router: coloquial→simple cuando embed_4b activo** (evita 3 llamadas LLM
  redundantes de Complex). ⏳ decisión pendiente. `architecture-status 2026-06-16`.
- [ ] **R7 · score-normalization fusion** (vs RRF+length-weight actual). ⏳. `roadmap-gap-analysis`.
- [ ] **R8 · BM25 weight tuning** (`_length_weights` retrieve.py:131). ⏳ barato.
- [-] **RK1 · upgrade reranker bge-reranker-v2-m3 → Qwen3-Reranker-4B/8B** — PROBADO 2026-08
  (screen recall@10): BGE 237 vs Qwen3 239 = Δ+2 ruido, y Qwen3 17× más lento. El reranker NO es
  el muro (ambos ~85% gold@10). NO adoptar. Clase `Qwen3Reranker` queda (RERANKER_KIND=qwen3, OOM-safe).
- [ ] **R9 (dif) · MMR/diversity, self-query (NL→filtros), SPLADE, RAPTOR, CRAG routing** (flag OFF).
  ❌/🔬 estándar-avanzado, diferido.

## CHUNKING

- [-] **M2 · 1 def = 1 fragmento + parent-doc** — PROBADO 2026-08 (`build_def_fragments.py`, 62
  glosarios→608 defs, tabla `fragmentos_definicion`). Inyección RRF (`def_fragments`): −10 (ruido gen).
  Rechunk limpio (`glossary_exclude`, McNemar pareado): +7/−10 p=0.63 FLAT. En dev: +1 p=1.0 flat.
  MUERTO — el RRF desplaza. Infra queda (flags OFF). El fix bueno = `glossary_inject` determinista (ver abajo).
- [ ] **C1 · Contextual Retrieval REAL** — resumen LLM por-chunk del artículo, prepend antes de
  embeder (~3900 chunks, overnight). Hoy `contextual_text` = texto+preámbulo, NO resumen LLM real.
  Nombrado "el próximo recall lift". Relacionado a SAC pero distinto (resumen de ART vs de NORMA).
  ⏳. `architecture-status §4/§7`, `plan-experimentos-2026-06 Fase3`.
- [ ] **M5 · SAC** (resumen de NORMA prepend a cada chunk) — contra cross-doc mismatch. ⚠️ corpus
  ~78 puede no necesitarlo → medir. Research (halving refutado 1-2).
- [ ] **C2 · "rematch justo": inciso + recontextualización LLM** — el único experimento de chunking
  no hecho de forma justa. **DEUDA:** tabla `fragmentos_inciso` MIXTA (1248/7141 con phi4 luego
  matado). Decidir: terminar (~10h) / revertir 1248 / **drop tabla (recomendado)**. `chunking-rules §7`.
- [ ] **C3 · QA metrics chunking** (Coverage@k, Redundancy@k, MRR@k) + deudas: `glossary` chunker
  pierde texto en 10 arts; `_MARK2` falsos positivos en romanos + pierde 29 arts (§/N°/roman);
  `HUGE=3000` sin tunear. ⏳. `chunking-rules §3`.

## GRAPH (el mayor cuerpo de trabajo diferido; master: `graphrag-roadmap.md`)

Estado base: aristas define_termino (222) ✅; norma→norma 0; concepto→concepto 0; sin traversal
query-time; sin community detection; sin router. `graph_boost` existe pero **subalimentado**
(vinculaciones BCN vacías en datos).

- [-] **G1 · grafo concepto→artículo cableado + MEDIDO e2e** — PROBADO 2026-08: las aristas
  `define_termino` art-level están vacías/mal (0/45 fallas tienen arista correcta). G1 CRUDO muerto.
  RENACE bien como `glossary_inject` (abajo) — arista determinista desde `fragmentos_definicion`.
- [~] **G1b / glossary_inject · inyección DETERMINISTA término→artículo** (EN CURSO 2026-08). En query
  de definición, concepto matchea EXACTO un término de glosario → inyecta el artículo padre al top-k,
  sin desplazar (a diferencia de def_fragments RRF). Es GraphRAG-1-salto bien hecho. Smoke ✅ (mete
  Infracciones/Estado Deteriorado). Ataca 6 embedding-miss de glosario. Midiendo cita_ok pareado.
  Flag `glossary_inject`, `vectorstore.def_exact`, `retrieve._definition_concept`.
- [ ] **G2 · seguir cross-references / remisiones** en retrieval (`follow_remissions.py` existe, no
  cableado; ej AVI art48 remite a LGSE 104/118). 🏗️.
- [ ] **G3 · fix dedup `build_candidates`**: `define_termino` debe ganar a `cita` para el mismo
  artículo (hoy guarda `cita`, esconde la definición real → gold errado, ej "Escenario Energético"
  1160108/art2). ⏳ bug conocido, fix documentado. `modelo-datos-conceptos-definiciones`.
- [ ] **G4 · entity resolution / disambiguación** ("mismo nombre = misma entidad" es la falla raíz;
  "Cliente" en decreto 1935 ≠ moderno). Regla: excluir derogado → mismo ámbito → fecha → si no,
  marcar conflicto. **Precede traversal.** `graphrag-roadmap Rev-2 §A` (CRÍTICO).
- [ ] **M7 / G5 · GraphRAG traversal query-time** (Fase 3): multi-concept detection + traversal
  local (relaciones "A vs B"). Para respuestas multi-hop, NO para "def enterrada en 1 art". ⏳.
- [ ] **G6 · query router grafo/vector/inject** (Fase 4, reglas deterministas; grafo NO debe
  dispararse en simples — medido que daña). ⏳.
- [ ] **G7 · aristas norma→norma** (deroga/modifica/cita, Fase 2). ⚠️ mayoría refs FUERA del corpus
  → bajo ROI hasta crecer. ⏳ diferido.
- [ ] **G8 · aristas concepto→concepto** (Fase 5, LLM-extract + verificador verbatim; solo aceptar
  verbatim). ⏳ riesgo alucinación.
- [ ] **G9 · eval multi-hop (Fase 7)** — construir gold relacional para DECIDIR si GraphRAG (fases
  3-6) vale (invertir si recall@k multi-hop <60%). ⏳ **gate de decisión.**
- [ ] **G10 (dif) · global search (Leiden communities + summaries, Fase 6)**, incremental indexing,
  traversal vía CTE recursivo en Postgres (migrar a AGE/Neo4j solo si cuello), covariates. YAGNI.

## DATA / CURACIÓN / CORRECCIÓN LEGAL

- [ ] **D1 · vigencia/derogación** (no citar norma derogada) — **#1 gap legal table-stakes.** Gap de
  DATOS no código: `normas.metadata->>'estado'` vacío (89/95 DESCONOCIDO). Derivar `estado` de scrape
  BCN (`obtxml?opt=7&idNorma=`, campos `derogado`+`FechaDerogacion`) + parsear "Derógase/Reemplázase
  ley N°X" → luego filtro/downrank. Task #101. ❌ **bloqueado en datos. Crítico pre-producción.**
- [ ] **D2 · extractor automático de aliases/siglas** (46→~100): detectores deterministas (glosario
  SIGLA:expansión, "Nombre (SIGLA)", "en adelante X"). ⚠️ auto dio 51 acrónimos pero NO paráfrasis
  coloquiales (muro coloquial NO auto-derivable). `graphrag-roadmap Fase1`.
- [ ] **D3 · lex specialis por ámbito** (desambiguar defs por dominio). ⏳ diferido (corpus casi todo
  energía). `authority-resolution §9`.
- [ ] **D4 · UX de ambigüedad** (query matcha varios conceptos → mostrar opciones, preguntar, NO
  adivinar por posición). ⏳. `authority-resolution §9-B3`.
- [ ] **D5 · aplicar cola de revisión glosario** `glossary/incoming/canonical_review.yaml` +
  focused-definition gating (flag `inject_focused_definition` dormido, gating pendiente). ⏳.
- [ ] **D6 · expandir eval con más pares coloquiales REALES / usar balanced_v2 (339q)** no
  coloquial (39q) → mejor señal. ⏳ parcial. `handoff-07-06`.

## GENERATION ("el cuello real de cita_ok", según varios docs)

- [ ] **GEN1 · head-to-head generador fuerte** (Claude Sonnet vs qwen3:30b-a3b, mismos pools) —
  NUNCA medido directo. ⚠️ rompe "sin API paga" → solo diagnóstico de techo. Ver research frontera.
  `roadmap-gap-analysis`, `handoff-07-10 Fase3`.
- [ ] **GEN2 · self-consistency** (N samples + voto) — ataca 4 gen-fails, barato, ausente. ❌.
- [ ] **GEN3 · lost-in-the-middle reordering** — barato, ausente. ❌.
- [ ] **GEN4 · context compression (LLMLingua)** — menos ruido al LLM, ausente. ❌.
- [ ] **GEN5 · fallback-on-timeout ≠ rechazo legal** ("falla técnica" ≠ "norma no existe"). ⏳
  pendiente implementar. `decisiones-arquitectura ADR`.
- [ ] **GEN6 · fix runner full_hit-skip** (`deepeval_runner.py:174` infla bucket "empty"; parcial con
  `eval_always_generate`). ⏳ trivial.
- [ ] **M4 · step-back rewriting** (coloquial↔legal, abstracción). Complemento del alias-map, NO
  reemplazo. GPU ✅. Research 3-0. Residuos coloquiales.
- [ ] **GEN7 (dif) · CoVe, Self-RAG, generator ensemble+judge, NLI groundedness**. ❌ avanzado.

## EVAL / OBSERVABILIDAD / INFRA

- [x] **E0 · robustez de eval (BLOQUEANTE)** — HECHO/ADOPTADO 2026-08. `balanced_v2` (339q) primario
  + McNemar pareado (`exp_e0_baseline.py` resumible). Reveló que el eval MENTÍA: cita_ok in_domain
  real = **84%** (234/279), no 62%. E0b (`audit_golds.py`): 159 also_gold → `queries_balanced_v2_clean.jsonl`.
  El +22 fue 100% limpieza de eval. dev/coloquial/holdout NO estaban subestimados (solo balanced_v2).
- [ ] **E1 · RAGAS/DeepEval faithfulness + context_precision** — hoy solo cita_ok casero, NO
  faithfulness estándar. "La medición más accionable ahora". ❌. `roadmap-gap-analysis #3`.
- [ ] **E2 (dif) · observabilidad** (Langfuse/Phoenix), feedback loop, human-in-the-loop gate,
  provenance/audit trail. ❌ pre-producción.

## FINE-TUNING (raíz, caro, "al final" — orden: curación→set sintético→embedder→reranker→generator)

- [ ] **FT1 · fine-tune embedder** (pares coloquial→artículo, set curado grande, ojo overfit). 0.6B
  dio overfit (v1 +1/v2 −3). ⏳ set grande nunca hecho. Requiere **hard-negative mining (BM25+CE)**.
- [ ] **FT2 (dif) · fine-tune reranker, generator (LoRA/RAFT), Tulio/Patana→embedder chileno**. ❌ último recurso.

---

## NO hacer / PROBADO — NO repetir (descartados, con Δ)

- **HyDE / multi-query** — alucinan cifras, dañan cita_ok (research 0-3). PERO sub-idea abierta:
  "subir top_k para que la recall de HyDE llegue al prompt" nunca resuelta (`handoff-2026-05-30`).
- **DMQR fan-out completo, Mix-of-Granularity (router entrenado)** — research: sobre-ingeniería.
- **inciso/section chunking** (dev +10 screen, e2e NET −2 = espejismo), **small-to-big genérico**
  (64 vs 67), **regla4 cross-ref determinista** (dose-response negativo). `chunking-rules`.
- **citation_repair** (0/6), **concept_inference** (trade-off +3/−1), **selective_reform** (+1/−1),
  **query decomposition/multi-hop** (−2), **graph_boost_all** (overfit +4/−2), **doc2query** (neg),
  **query expansion sinónimos** (rompió off-topic), **fine-tune 0.6b** (overfit), **gemma2:27b** (roto),
  **8B embedder** (trade-off dev+5/coloq−4), **fusión RRF k×peso** (+2% marginal).

## PROBADO — NO repetir (campaña def-recall 2026-08, detalle: `campaign-def-recall-2026-08.md`)
- **M1** pool 50→100: +3, p=0.25 ruido. El gold no está en rank 50-100.
- **G1** grafo concepto→art: MUERTO. 0/45 fallas tienen arista art-level correcta (solo 48/371 la tienen).
- **M2** def_fragments inyección: −10 pero contaminado por ruido de gen (método malo).
- **rechunk** (def_fragments+glossary_exclude, McNemar pareado limpio): **+7/−10, p=0.63 = FLAT**. No adoptar.
- Infra def_fragments queda (flags OFF, 608 fragmentos): sirve, pero muro del reranker la limita.

## Muros identificados (estado final 2026-08)
- **Reranker prefiere FUNCIONAL sobre DEFINICIÓN** (Coordinador 0.9985 vs 0.981) — probado que
  Qwen3-Reranker NO lo arregla (RK1 dead). Es muro de cross-encoders, se sortea con inyección
  determinista (glossary_inject), no con otro reranker.
- **E0b golds** — RESUELTO: 159 also_gold, eval real 84%. Los residuos son 5 coloquiales (muro
  semántico) + acrónimos (D2).

## HECHO / adoptado (esta campaña 3090)
- Embedder qwen3-4B MRL-1024, alias_union, BGE-GPU, gate AND, gen qwen3:30b-a3b. Ver `handoff-2026-07-31.md`.
- Método de eval robusto: balanced_v2 (339q) + McNemar pareado (ver `campaign-def-recall-2026-08.md`).

## REFERENCIA — SI ALGÚN DÍA ESCALO (NO es cola activa)
Deep-research frontera verificado (2026-08-01), detalle: `docs/research-improvements-2026-07-31.md`
sección "vs frontera". Resumen con números:
- **Embedder: YA superas a frontera cerrado** (Qwen3-emb-8B 70.58 #1 MTEB multi > Gemini 68.37 >
  Cohere-v3 61.12 > OpenAI text-emb-3-large 58.93). Truncar 1024 = zona segura. NO es el cuello.
  ⚠️ excepción: Voyage-law-2 (legal-específico) sin probar.
- **Gen frontera NO mueve cita_ok**: escalar LLM no da cita (closed-book Claude Sonnet 4.5 6.8/100,
  Llama 70B≈8B). Retrieval > generador (2510.06999, 2605.14503 peer-reviewed). Rompería "sin API paga"
  por ganancia marginal. Solo diagnóstico de techo, nunca producción.
- ~~RK1 reranker~~ — PROBADO 2026-08: Δ+2 ruido, 17× lento. Ningún upgrade de modelo pendiente
  con retorno real.
- Cuello de escala real = **RAM host 14GB** (HNSW en RAM) + pgvector sin multi-vector indexado
  (VectorChord), **NO la GPU**. LLM denso 70B+ (>24GB) = upside marginal en cita_ok.
- `ROADMAP_ESCALABILIDAD.txt` (abr-26) mayormente obsoleto (pgvector ya en prod).
