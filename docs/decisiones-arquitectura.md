# Decisiones de Arquitectura — Energy-RAG

> ADR compacto. Una línea por decisión: **qué + por qué + estado**. Para el
> detalle de una sesión ver el handoff correspondiente.

---

## Algoritmos del pipeline (orden de ejecución)

| # | Etapa | Algoritmo | Nota |
|---|---|---|---|
| 1 | Retrieval léxico | BM25 sobre `tsvector` (Postgres `to_tsvector('spanish')`) | top-50 |
| 2 | Retrieval denso | Qwen3-Embedding-0.6B + pgvector HNSW (cosine) | top-50, CPU FP32 |
| 3 | Fusión | RRF `1/(k+rank)`, k=60, **pesos por largo de query** | corta→BM25 0.65, larga→vector 0.65 |
| 4 | Rerank | **Identity** (preserva orden RRF) | BGE real probado, −57pp grounding → descartado |
| 5 | Graph boost | `define_termino` +10 si concepto **alias-matched** + tiebreak recencia | sobre `referencias` |
| 6 | Expansión jerárquica | fragmento → artículo padre | dedup por articulo_id |
| 7 | Generación | qwen3.5:9b vía Ollama, **JSON schema constrained** (enum de citas) | `think:False` |
| 8 | Verificación | grounding verifier: regex cita verbatim vs docs | retry-on-fail |

---

## Decisiones (ADR)

| Decisión | Por qué | Estado |
|---|---|---|
| **Postgres+pgvector** (no vector DB dedicada) | dataset chico-medio, 1 stack, SQL+grafo en mismo motor | firme |
| **Constrained decoding** (JSON enum de citas) | el sampler impide citar fuera del set recuperado → anti-alucinación dura | firme |
| **Grounding = señal de calidad, NO latencia** | tiempo no correlaciona con calidad (cuelgues Ollama son bug, no dificultad) | firme |
| **Identity reranker** | cross-encoder genérico (BGE) reordena y confunde el JSON enum → −57pp | firme; reabrir solo con estrategia legal-aware |
| **Chunking atómico de glosarios** (1 def = 1 fragmento) | mega-artículo de 70 defs diluye embedding/BM25 → la def nunca entra al pool | firme; umbral MIN_DEFS=4, resto intacto |
| **Cadena de 4 deps**: alias→arista→rechunk→pool | romper 1 eslabón = 0 efecto; graph_boost solo reordena, no inyecta | documentado |
| **Normalización determinista, NO fuzzy** | dominio legal: "potencia firme"≠"inicial"; fuzzy alucina. Match exacto bajo case/tildes/puntos-acrónimo | firme |
| **Off-topic detector pre-LLM** = vocab corpus + aliases curados | rechazar trampas sin gastar LLM; aliases curados son del dominio (fix PELP) | firme |
| **T-C recencia = proxy de vigencia, NO ruling legal** | desempata defs múltiples por fecha+reglamento_base; vigencia real (T-B) es otro proyecto | proxy interino |
| **Fallback ante timeout ≠ refusal legal** | en derecho, "fallo técnico" debe ser distinguible de "la norma no existe"; mismo texto induciría error legal | **pendiente de implementar** |
| **Eval por dominio** | `queries_chilean_electric` estaba 36% contaminado con concursal (cuelga Ollama); medir el producto = medir su dominio | hecho: `queries_electrico.jsonl` |
| **Sin API paga** | decisión del usuario; mantener 100% local salvo que pregunte por costo | vigente |
| **Auditar composición del eval ANTES de medir** | se gastaron horas midiendo contra instrumento contaminado; validar el instrumento es prerequisito | lección |

---

## Anti-patrones (no reintentar sin nueva estrategia)

- Curar aliases sin arista+rechunk → inerte (cadena de 4 deps).
- Reranker cross-encoder genérico para QA legal con citas verbatim → −57pp.
- Medir contra `queries_chilean_electric.jsonl` crudo → 36% ruido off-domain.
- Retry de Ollama esperando que arregle cuelgues **deterministas** → los empeora (450-900s).
- Usar latencia como proxy de calidad → falso (cuelgue = bug de runtime, no dificultad).

---

## Blockers estructurales

1. **Ollama qwen3.5:9b cuelga determinista 400-900s** en queries off-domain. Sin causa raíz (no es n_docs, categoría ni constrained-decoding).
2. **Varianza Ollama ±3pp** entre runs idénticos → 1 run no concluyente, promediar 2-3.
3. **Techo local ~70-75%** grounding eléctrico con qwen3.5:9b.
4. **Vigencia/temporalidad real** (parsing derogaciones) sin implementar — T-C es solo proxy por fecha.
