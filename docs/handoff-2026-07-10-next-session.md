# Handoff — arranque próxima sesión (2026-07-10)

Punto de entrada. Lee esto primero. Estado, backlog priorizado, y primer paso de cada gap.

## Estado producción (rama `adopt-winners`, no mergeada a main)
```
EMBEDDER   Qwen3-Embedding-4B (MRL-1024, HNSW) + alias_union     [embed_4b_dense=True]
BM25       híbrido, peso por largo de query
FUSIÓN     RRF k=60
RERANKER   bge-reranker-v2-m3                                     [use_bge_reranker=True]
CHUNKING   section-aware + Contextual Retrieval (LLM escribe rol) [asis, contextual_text]
GATE       off-topic AND
GENERADOR  claude-sonnet-4-6 (API)  ·  mejor LOCAL medido = qwen3:30b-a3b (+9, NO adoptado)
```
Métrica: **cita_ok**. Sets: coloquial 39, dev 44, holdout 18, balanced_v2 339.
Techo actual: coloquial 31/39, dev 36/44. **Único win real de toda la campaña = generador 30b-a3b (+9).**

## Regla de oro (aprendida N veces)
El **screen (gold∈topN) MIENTE.** Sube el retrieval, NO sube cita_ok. Confirmado con 8b(−1),
ensemble(−3), inciso(−2), small-to-big(−2/−4). **Nada se adopta sin confirmar cita_ok end-to-end.**

## Diagnóstico de los 8 fallos coloquiales (medido)
- **4 retrieval** (gold ni entró al top10): pregunta por función/concepto, cero palabras del art.
  → art 87 (planificación), 104 (vida útil), 118 (tope ganancia), 212 (Panel). Fix = **grafo**.
- **4 generación** (gold en pool, a veces rank 1, citó vecino) → *misgrounded*. Fix = **generador/self-consistency**.
- Mitad del problema NO está en retrieval. Por eso 9 experimentos retrieval-side no movieron la aguja.

---

## BACKLOG PRIORIZADO (del gap-analysis `roadmap-gap-analysis-2026-07-10.md`)

### FASE 1 — correctitud legal (table-stakes)
1. **Vigencia — no citar normas derogadas.** ⚠️ **AUDITADO 2026-07-10: es gap de DATOS, no de código.**
   `normas.metadata->>'estado'` está vacío: de 95 normas → 89 DESCONOCIDO, 4 None, 1 VIGENTE, 1 DEROGADA.
   NO se puede filtrar derogadas porque no sabemos cuáles lo están. Hay `metadata->'versiones'` (a veces
   con "Decreto X modifica...") como pista parcial.
   - 1er paso REAL: derivar `estado` desde BCN (scrape) o desde `versiones`/vinculaciones. Trabajo de
     datos, más grande que un flag. BCN vinculaciones vienen vacías (ver `reference_chilean_norm_hierarchy`).
   - Recién con `estado` poblado: agregar filtro/downrank en retrieval + medir cita_ok.
2. **Metadata filtering en `search_vector`.** HOY: recupera de TODO el corpus, sin filtrar por
   norma/tipo/fecha. Es table-stakes.
   - 1er paso: añadir cláusula WHERE opcional (id_norma, tipo, vigente) a `vectorstore.search_vector*`.
3. **Autoridad pesa el ranking.** HOY: `extraction/authority.py` extrae jerarquía pero no influye.
   - 1er paso: boost por rango (LEY≡DFL≡DL > DECRETO > RESOLUCIÓN) en fusión. Ver `reference_chilean_norm_hierarchy`.

### FASE 2 — medir bien (table-stakes, desbloquea todo lo demás)
4. **RAGAS / faithfulness metric.** HOY: cita_ok casero, NO medimos faithfulness/context-precision
   ni "misgrounded" directo.
   - 1er paso: `pip install ragas`; correr faithfulness + context_precision sobre coloquial+dev;
     comparar con cita_ok. Da la métrica estándar para los gen-fails.

### FASE 3 — generación (el cuello real de cita_ok)
5. **Generador fuerte cabeza a cabeza:** Claude Sonnet vs qwen3:30b-a3b sobre los mismos pools.
   Prueba la hipótesis del usuario (mejor generador aguanta el ruido que hundió al rewrite).
   - 1er paso: reusar pools cacheados en `data/eval/results/chunk_e2e/*__pools.json`, generar con
     ambos, comparar cita_ok en los 8 fallos.
6. **self-consistency** (N muestras, votar) + **lost-in-the-middle reorder** + **context compression**.
   Baratos, atacan los 4 gen-fails. Ninguno implementado.

### FASE 4 — grafo (retrieval-fail, alto valor, infra parcial)
7. **Grafo concepto→artículo.** Infra a medias: `graph_builder.py`, `follow_remissions.py`,
   `glossary_define_edges.py`. Ataca los 4 retrieval-fail SIN meter distractores (quirúrgico).
   - 1er paso: aristas define_termino para Panel→212, tope-ganancia→118, vida-útil→104, planif→87;
     inyectar al pool (no como boost post-fusión — ver duda resuelta en chunking-rules). Medir cita_ok.

### FASE 5 — raíz, caro, último
8. **Fine-tune** embedder (pares coloquial→artículo, con set grande, cuidar overfit) → reranker → generador (LoRA/RAFT).
   Orden field-consensus: curación → set sintético → embedder FT → reranker FT → generador FT.

---

## Diferido explícito (frontier — hasta los vendors lo pasan a humano)
point-in-time, term-scoping, amendment tracking completo, Self-RAG/CoVe, SPLADE/ColBERT/RAPTOR,
agentic RAG, observabilidad (Langfuse/Phoenix), feedback loops. No urgente para pre-producción.

## Deuda técnica que limpiar
- **`fragmentos_inciso` MEZCLADA:** 1248/7141 chunks recontextualizados con phi4 (rematch a medias).
  Decidir: terminar (~10h), revertir los 1248, o **dropear** (recomendado — inciso no se adopta).
- `_MARK2` no cubre 29 artículos (§, N°, romano). Centralizar reglas de estructura en registro.
- Rama `adopt-winners` sin mergear a main.
- Decisión generador pendiente: Claude ($, calidad) vs 30b-a3b (local, +9 medido).

## Docs de referencia
- `docs/roadmap-gap-analysis-2026-07-10.md` — estándar SOTA vs sistema, técnica por técnica.
- `docs/chunking-rules.md` — reglas, regex, QA, sweep+e2e+small-to-big, lección "screen miente".
- `docs/handoff-2026-07-06-mejoras-pipeline.md` — mapa 13 etapas con estado por etapa.
- Memoria: `project_energy_rag_state.md` (estado vivo), `reference_chilean_norm_hierarchy`.

## Scripts clave
- `exp_stage_split.py` — separa fallo embedder vs reranker (el diagnóstico más útil).
- `exp_chunk_sweep.py` / `qa_chunking.py` / `exp_chunk_e2e.py` / `exp_small_to_big.py` — chunking.
- `exp_reranker_bakeoff.py` — bake-off rerankers.

## Infra / gotchas
- Cuello máquina = RAM 14GB (no VRAM 24GB). Modelos 7B+ por HF crashean; usar GGUF/Ollama.
- Reaper mata jobs background/monitores en cada mensaje; jobs detached ACTIVOS sobreviven. Cron one-shot es confiable para trabajo diferido.
- `pkill -f exp_...` se autokillea (exit 144) — matar por PID.
- DB = Docker `energy_rag_pg` (puerto 5434 host→5432). Estaba apagado; `docker start energy_rag_pg`.
- Modelos en disco externo `/home/alonso/datos` (root chico).
