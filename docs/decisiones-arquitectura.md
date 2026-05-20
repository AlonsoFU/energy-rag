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
| **Patrón híbrido: NO usar JSON-schema en Ollama, validar post-hoc** | Ollama qwen3.5 deadlockea con `format` JSON-schema (issues #15540, #15260). `verify_citations` post-hoc + retry con prompt estricto enforce la misma garantía legal sin el bug del runtime | firme; flag `use_constrained_decoding=False` |
| **num_ctx = 16384** (NO 8192) | prompts grandes (10 docs + Contextual) llegan a ~15k tokens; 8k desborda y dispara el cuelgue del sampler | firme |
| **Char budget de 45000 sobre el bloque de artículos** | recorte determinista del tail si el pool excede ctx; previene futuros overflow sin depender del techo del modelo | firme |
| **Verifier en 2 capas: in-pool → corpus** | la cita debe ser real. Capa 1: presente en docs retrieved (estricto). Capa 2: si no, ¿existe en la DB completa? Si sí → válida (legal-safe, strict-exact, sin fuzzy). Mismatch retrieval-cita = no es alucinación si la cita es real | firme |
| **Strip de citas malformadas en el texto entregado** | `[Art. ag de NORMA]` (identificador no-numérico) son inventos del LLM; la regex estricta ya los ignora, ahora se borran del texto al usuario para que no confundan | firme |
| **Set canónico `queries_balanced.jsonl` (80q, 3 categorías)** | mide 3 comportamientos distintos por separado: in_domain (energía), off_domain_corpus (lo cargado pero off-product), off_corpus (lo NO cargado). NO agregar el % | firme |
| **No subir pool RRF a 100** | medido: -2pp answered, -4pp recall. Pool más grande mete ruido en el ranking. Mantener pool=50 | empírico |
| **No subir top-k a 15** | medido: idéntico al baseline. El runner skip-ea LLM por full_hit en top-5; ampliar top_k no cambia el skip | empírico |

---

## Anti-patrones (no reintentar sin nueva estrategia)

- Curar aliases sin arista+rechunk → inerte (cadena de 4 deps).
- Reranker cross-encoder genérico para QA legal con citas verbatim → −57pp.
- Medir contra `queries_chilean_electric.jsonl` crudo → 36% ruido off-domain.
- Retry de Ollama esperando que arregle cuelgues **deterministas** → los empeora (450-900s).
- Usar latencia como proxy de calidad → falso (cuelgue = bug de runtime, no dificultad).
- Confiar en `queries_electrico.jsonl` (31q) como "instrumento limpio" → seguía 35% contaminado con telepeaje vial + Ley Tránsito + sueldos sector público; auditar por DB-clase, no por keyword.
- Confiar en `grounding_pass` agregado como métrica única — es guardrail, no calidad; bajo constrained-decoding casi tautológico; el denominador `n_with_generation` esconde los cuelgues.
- Asumir que el cuelgue de Ollama era off-domain-only → falso, también pega en términos in-domain (Acometida 900s). Causa raíz: JSON-schema + `think=false`.
- Subir el pool RRF de 50→100 → -2pp answered, -4pp recall. Más candidatos ≠ mejor ranking.

---

## Blockers estructurales

1. ~~**Ollama qwen3.5:9b cuelga determinista 400-900s** en queries off-domain. Sin causa raíz~~ → **RESUELTO 2026-05-20**: causa = JSON-schema constrained-decoding + `think=false`. Fix = patrón híbrido (sin schema, verificador post-hoc).
2. ~~**Varianza Ollama ±3pp**~~ → **RESUELTO** con el patrón híbrido: varianza ≈ 0 entre corridas idénticas.
3. **Techo recall+art = 76%** en in_domain (12/50 queries tienen el artículo definidor fuera del top-5). Las 12 que no llegan al top-5, el eval runner skip-ea el LLM. Atacar con re-ranker concepto-específico o mini-chunks de summary.
4. **El runner skip-ea LLM cuando `full_hit=False`** (`deepeval_runner.py:174`) → métricas como "answered_rate in_domain" están limitadas por el techo de `recall+art`, no miden el comportamiento real del sistema. Cambio trivial pendiente.
5. **Vigencia/temporalidad real** (parsing derogaciones) sin implementar — T-C es solo proxy por fecha. Otro proyecto.
