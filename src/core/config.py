from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "energy_rag"
    postgres_user: str = "energy_rag"
    postgres_password: str

    anthropic_api_key: str

    qwen_embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    qwen_reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    embedder_device: str = "auto"  # "auto" | "cuda" | "cpu" — set "cpu" when LLM occupies GPU
    reranker_device: str = "auto"  # same semantics as embedder_device

    llm_default: str = "claude-sonnet-4-6"
    llm_haiku: str = "claude-haiku-4-5-20251001"
    llm_opus: str = "claude-opus-4-7"

    log_level: str = "INFO"

    # Curated concept-definition injection. When the query matches a
    # definitional pattern ("qué es X" / "definición de X" / ...) AND X is
    # an exact match (normalized) of a curated concept name in the DB, the
    # defining article is force-prepended to the retrieved pool. Targets
    # the recall+art ceiling (33% of in-domain queries miss the defining
    # article in top-K). Legal-safe: strict-exact normalization, no fuzzy,
    # curated edges only.
    inject_curated_definitions: bool = True

    # Post-hoc DETERMINISTIC citation anchoring (generate._anchor_authoritative_
    # citation): when a query centers on a single curated concept whose
    # authoritative article A is known and the answer cited NOTHING from A's
    # norma, append a curated "[Art. A de N]". Monotonic on cita_ok (only adds a
    # citation, never removes) → cannot regress the metric. Guarded against
    # general-vs-detalle (skips if the answer already cited A's norma). Off by
    # default until measured.
    anchor_authoritative_citation: bool = False

    # Guard mode for the anchor (only relevant when the anchor is on). False =
    # norma-level (skip if any article from A's norma is cited; conservative).
    # True = article-level (skip only if A's exact norma+art is cited) → fixes
    # intra-norma attribution (glossary art 13 vs operative sibling 56) but may
    # re-anchor where the reglamento article was wanted. Off until A/B-measured.
    anchor_guard_exact_article: bool = False

    # When True (and inject_curated_definitions is on), the injected doc carries
    # the FOCUSED curated definition (conceptos.definicion, ~300 chars) instead
    # of the FULL defining article. Glossary articles (e.g. art 13 de 250604 =
    # ~10k chars defining ~50 terms) bury the relevant definition far from its
    # citable [Art. N de ID] header, so the model reproduces the definition but
    # cites a tighter sibling article. A focused chunk co-locates the verbatim
    # definition with its exact citation header → the model copies the right
    # cite. Legal-safe: definition is verbatim glossary text, citation is the
    # real defining article. The full article (if retrieved) is replaced by the
    # focused chunk to avoid two docs sharing one header.
    # DORMANT (default False): the A/B (2026-05-22) showed this recovers
    # glossary-buried citations but REGRESSES entity-collision cases (it shrinks
    # our target below a competing definition → position-forces the wrong pick).
    # Needs competitor-aware gating before enabling — see spec
    # docs/superpowers/specs/2026-05-22-canonical-concept-names-design.md §10.
    inject_focused_definition: bool = False

    # Eval runner: when True, the LLM is called even if retrieval didn't put
    # the expected article in the top-K (full_hit=False). Measures the real
    # production behavior (where the system always generates on retrieved
    # docs). When False, the runner shortcuts to save time but inflates the
    # "empty" bucket with eval-only artifacts. Default True (honest).
    eval_always_generate: bool = True

    # Hybrid citation pattern: when False, generate plain (no JSON schema)
    # and validate citations post-hoc with verify_citations + retry-on-fail.
    # Set False by default because Ollama's JSON-schema constrained decoding
    # deadlocks on qwen3.5 (upstream issues #15540, #15260, #15502 — combined
    # with our think=false makes the format constraint silently fail or hang).
    # Switch True only with a runtime that implements constrained decoding
    # correctly (vLLM, llama.cpp direct, API providers like Anthropic/OpenAI).
    use_constrained_decoding: bool = False

    # Char budget for the article block in the generation prompt. Tail-trims
    # docs (lowest rank dropped first) so prompt fits in num_ctx and the
    # JSON-schema-constrained sampler doesn't deadlock. Default 45000 chars
    # ≈ 13k tokens (Spanish + qwen BPE ≈ 3.5 chars/token), leaving room for
    # system (~1.5k tokens) + query + response in 16k ctx. 0 disables.
    prompt_doc_char_budget: int = 45000

    # Ollama context window. MUST exceed prompt + max_tokens de salida.
    # At 8192 the prompt overflows and the JSON-schema-constrained sampler
    # DEADLOCKS (0 tokens, connection held forever) — root cause of the
    # "deterministic Ollama hang".
    # 2026-08-06: 16384 VOLVIÓ A QUEDAR CORTO. Medido en balanced_v2, las queries
    # "Costo de Falla" arman prompts de 48-50k chars ≈ 15.0-15.6k tokens; sumando
    # max_tokens=2000 de salida da ~17.6k > 16384 → cuelgan hasta el timeout de
    # litellm (300s × 3 reintentos = 900s perdidos por query, y el runner las
    # anotaba como cita_ok=False, o sea FALSO NEGATIVO en el eval).
    # 32768 da margen real (prompt tope ~15.6k + salida 2k + sistema).
    # VRAM verificada en la 3090: 21510 MiB / 24576 con qwen3:30b-a3b cargado.
    # ⚠️ A ESCALA: esto crece con el corpus. El techo NO es la solución de largo
    # plazo — hay que acotar el contenido (prompt_doc_char_budget mide SOLO los
    # docs: con budget=45000 el prompt completo igual llegó a 50035 chars).
    ollama_num_ctx: int = 32768

    # HyDE expansion in the SIMPLE branch. The COMPLEJO branch already expands
    # (hyde+step_back+multi_query); but the router sends many SITUATIONAL/
    # paraphrased queries to SIMPLE, where the paraphrase embedding misses the
    # defining/operative article. Measured (2026-05-31, gold∈pool@20 on 15
    # indep_complex): query+HyDE lifts recall 5→9/15 (+27pp). When True, the
    # SimpleRetriever prepends a hypothetical legal paragraph (generated by the
    # local LLM) to the BM25+vector query text; rerank/concepts stay on the
    # ORIGINAL query. Legal-safe: only changes WHAT is retrieved, citation stays
    # exact. Off by default until the 49q A/B confirms no regression on the
    # definitional class (which already works at 83% and needs no expansion).
    hyde_in_simple: bool = False

    # EXP (campaña 2026-06): top_rerank del SimpleRetriever. El default efectivo
    # (10) CORTA el pool a 10 antes de graph_boost/hierarchical → el gold en
    # rango 11-20 se descarta antes de poder promoverlo. >0 lo sobreescribe para
    # dejar sobrevivir candidatos más profundos al boost. 0 = default (10).
    # ACTIVADO 2026-06 (campaña): 30 para que BGE rerankee un pool suficiente.
    top_rerank_override: int = 30

    # EXP (campaña 2026-06): extiende el boost fuerte define_termino (+10) de
    # graph_boost a conceptos por NOMBRE canónico, no solo alias. Promueve el
    # artículo que define el concepto de la query. Default OFF (el gate de alias
    # existía para evitar falsos positivos; se mide en dev+holdout).
    graph_boost_all: bool = False

    # EXP (2026-07-15): boost por AUTORIDAD/jerarquía normativa en el ranking.
    # La jerarquía chilena (LEY≡DFL≡DL=3 > DECRETO/DS=2 > RESOLUCIÓN=1, ver
    # src/extraction/norm_rank.derive_rank) se EXTRAE pero nunca pesó el ranking.
    # authority_rank_boost=β aplica factor multiplicativo (1+β·(rank-2)) al score
    # tras graph_boost: LEGAL ×(1+β), DECRETO ×1, RESOLUCIÓN ×(1-β). β pequeño
    # (0.05-0.15) para nudge, no override del reranker. Default 0.0 (OFF).
    # CAVEAT: mucha regla operativa vive en DECRETO (reglamentos); subir LEY a
    # ciegas puede hundir el DECRETO correcto → medir dev+holdout, no-regresión.
    authority_rank_boost: float = 0.0

    # EXP (campaña 2026-06): usar el cross-encoder BGE como reranker de
    # producción (src.components.reranker.get_reranker). En el sweep retrieval-only
    # subió gold∈pool@5 en dev (25→33) y holdout (15→17) y destapó la clase
    # situacional. Default OFF hasta que la eval de generación confirme que el
    # +recall se traduce en +cita_ok (BGE históricamente bajaba el grounding).
    # Requiere top_rerank_override ~30 para que BGE rerankee un pool suficiente.
    # ACTIVADO 2026-06 (campaña): validado cita_ok dev 25→32, holdout 14→17,
    # grounding intacto. COSTO: BGE en CPU (~+seg/query). Revertir a False si la
    # latencia no es aceptable en producción.
    use_bge_reranker: bool = True

    # Gate de off-topic SEMÁNTICO (flag OFF). Reemplaza el guard léxico
    # `is_off_topic` (bolsa de palabras OOV) por: rechazar si el mejor score de
    # BGE sobre el pool < umbral. El léxico rechaza queries COLOQUIALES in-domain
    # ("máquina para respirar"→electrodependiente) por no nombrar el término;
    # el semántico usa la relevancia que BGE ya computa. Experimento 2026-06-03:
    # coloquial cita_ok 4→6, answered 6→8, CERO regresión en rechazo off-topic
    # (NEG claro 5/5) ni in-domain. Requiere use_bge_reranker=True (con Identity
    # el score es 1/(rank) → el gate nunca dispara). Default OFF: es decisión de
    # producto (cambia comportamiento de rechazo + cuesta un retrieval por query).
    semantic_offtopic_gate: bool = False
    offtopic_bge_threshold: float = 0.01
    # Modo del gate off-topic: "lexical" (OOV vocab), "semantic" (max BGE < τ),
    # "and" (rechaza solo si AMBOS coinciden). ADOPTADO 2026-06-08 = "and":
    # rescata coloquial in-domain (cita_ok 26→30) SIN regresión — verificado en
    # los 6 sets: REGRESA_NEG=0 (rechazo off-topic 100% intacto), queries formales
    # no se tocan (propiedad: AND ⊆ rechazos del léxico → solo puede rescatar).
    # Requiere use_bge_reranker=True (con Identity el score no separa).
    offtopic_gate_mode: str = "and"

    # bm25_doc2query (flag OFF): BM25 busca sobre tsv_aug = contextual_text +
    # preguntas coloquiales generadas offline por doc2query español (mT5). Ataca
    # la ceguera de BM25 en coloquial (medido: BM25 None en las 13 fallas).
    # Requiere haber poblado fragmentos.doc2query_text (scripts/doc2query_generate).
    bm25_doc2query: bool = False

    # crag_routing (flag OFF): routing CRAG-style. Retrieval barato (rama simple,
    # sin expansión LLM) primero; si max BGE >= umbral, responde con eso (ahorra
    # step-back+HyDE+multi-query); si no, escala a la rama compleja. Mide en exp.
    crag_routing: bool = False
    crag_answer_threshold: float = 0.5

    # ensemble_bgem3 (flag OFF): agrega bge-m3 como 2da pata densa (RRF de 3:
    # BM25 + Qwen + bge-m3). Complementarios (cada uno halla lo que el otro pierde).
    # Retrieval gold∈top10 2026-06-09: coloquial 28→32, dev 37→40, holdout 17→18
    # (sube TODO, cero regresión). Requiere fragmentos.embedding_bgem3 poblada
    # (scripts/embed_bgem3). Costo a escala: +1 columna vector + 1 embed + 1 ANN/query.
    ensemble_bgem3: bool = False

    # Reformulación SELECTIVA coloquial→legal (flag OFF). Un call LLM condicional
    # (expansion.selective_reform) que reescribe SOLO las queries en lenguaje
    # cotidiano a registro legal formal; las ya-legales devuelven "IGUAL" y no se
    # tocan. Se aplica ADITIVO y vector-only en Simple/ComplexRetriever: la query
    # original queda en BM25/rerank, la reescritura solo aumenta la representación
    # vectorial. Experimento retrieval 2026-06-05: coloquial gold∈top10 28→34/39
    # (+6), dev 12→12 (cero regresión). Es el estándar 2025 (PreQRAG, "not all
    # queries need rewriting"). Default OFF: cuesta 1 call LLM/query de latencia;
    # se adopta solo si la eval de GENERACIÓN confirma +cita_ok sin regresión.
    selective_reform: bool = False

    # embed_4b_dense (flag OFF): usa Qwen3-Embedding-4B (GGUF Ollama, col embedding_4b)
    # como pata densa en vez del 0.6B. El screen vector-only mostró gold∈top10 coloquial
    # 26→33 (+7), dev +9, holdout −3. El 4B GGUF cuantizado SÍ cabe en la GTX 1080 (~4.9GB,
    # a diferencia de fp16/bitsandbytes). Requiere fragmentos.embedding_4b poblada
    # (scripts.embed_4b) + Ollama qwen3-embedding:4b. Mide si el +retrieval convierte a
    # cita_ok + no-regresión holdout. Default OFF.
    embed_4b_dense: bool = True   # ADOPTADO 2026-07-06: Qwen3-Embedding-4B campeón (vs 0.6B, +top5/dev; empata al 8B pero más barato/indexable)
    embed_4b_dim: int = 1024      # MRL prefix 1024 (HNSW indexable, escala) — validado igual/mejor que 2560
    embed_4b_cpu: bool = False  # fuerza el embed 4B en CPU (Ollama num_gpu=0) para coexistir con el 9B sin swap

    # alias_union (flag OFF): vocabulario controlado coloquial→legal (query-side, sin DB,
    # determinista). Si la query dispara un alias curado (src/pipelines/alias_map.py), se
    # embebe TAMBIÉN la query reemplazada por el término legal y se UNE (RRF) con la original
    # en la pata densa. Rescata muros de vocabulario (oráculo: 118/212 gold→top-2 con el término
    # correcto). Screen exp_alias_screen: 87 17→3, 118 >50→9, 212 >50→6, caso2 8→9 (no rompe).
    # Solo afecta retrieval, nunca la cita. CAVEAT: alias a mano = overfit; la versión que escala
    # los deriva del corpus (Exp #2-AUTO). Requiere embed_4b_dense ON. Default OFF.
    alias_union: bool = True   # ADOPTADO 2026-07-06: +3 coloquial (cita_ok 27→30), sin regresión. Requiere embed_4b_dense

    # embed_8b_dense (flag OFF, requiere 3090/24GB): pata densa Qwen3-Embedding-8B (GGUF Ollama,
    # col embedding_8b 4096-dim, seq-scan exacto). Antes "no cabía" en la GTX 1080 (8GB). En GGUF
    # el screen lo daba ≈4B; con la 3090 se re-mide en gen completo. Excluyente con embed_4b_dense.
    embed_8b_dense: bool = False

    # def_fragments (flag OFF): M2 "1 definición = 1 fragmento". Tabla fragmentos_definicion
    # (252 defs extraídas de 21 artículos-glosario densos, embedding_4b_1024). Se fusiona (RRF)
    # con la pata densa 4B para que la def enterrada en un glosario de ~10k chars suba al top-k;
    # mapea al artículo padre (cita [Art N de NORMA]). Ataca las fallas de RECALL de definiciones
    # (89/106 fallas E0). Construir con scripts.build_def_fragments (WRITE=1). Requiere embed_4b_dim=1024.
    def_fragments: bool = False

    # glossary_exclude (flag OFF): parte del rechunk M2. Excluye del search 4b-1024 los chunks
    # de los 62 artículos-glosario gigantes (re-fragmentados en fragmentos_definicion), para que
    # el def-fragment los REEMPLACE en vez de competir/diluir. Rechunk = def_fragments + glossary_exclude.
    glossary_exclude: bool = False

    # glossary_inject (ADOPTADO 2026-08-05, default ON): inyección DETERMINISTA término-glosario→
    # artículo. En query de definición, si el concepto matchea EXACTO un término de
    # `fragmentos_definicion`, garantiza el artículo padre en el top-k (lo inyecta al tope si falta).
    # Alta precisión (exact-match) → NO desplaza como def_fragments RRF. Es G1/GraphRAG-1-salto bien
    # hecho (como alias_map).
    # MEDIDO (McNemar pareado, balanced_v2_clean in_domain 279q): 233 -> 249 (+16, 0 pérdidas),
    # p=0.0000. Mayor WIN de retrieval de la campaña. Sortea el muro del reranker (prefiere artículo
    # FUNCIONAL sobre DEFINICIÓN) que RK1/Qwen3-Reranker NO pudo romper.
    glossary_inject: bool = True

    # concept_inference (flag OFF): inferencia del CONCEPTO legal implícito (estándar
    # legal IR 2025 — STARD / razonamiento de conceptos implícitos). El LLM devuelve los
    # TÉRMINOS técnico-legales exactos de una query coloquial (corto, sin alucinar leyes)
    # y se añaden ADITIVO vector-only a la query (BM25/rerank usan la original). Ataca el
    # muro de vocabulario coloquial (ej "tope de ganancia"→"tasa de descuento") que la
    # reformulación verbosa (selective_reform) no cruzaba. Mide gold∈pool dev+holdout,
    # no-regresión, default OFF. Cuesta 1 call LLM/query.
    concept_inference: bool = False

    # citation_repair (flag OFF): corrección de cita post-hoc (CiteFix-similarity,
    # ACL 2025). Tras generar, puntúa RESPUESTA↔cada doc del pool con el
    # cross-encoder BGE y, si el doc que MEJOR sostiene la respuesta no está
    # citado, AÑADE su cita. Ataca el cuello medido: gold en el top-k pero el LLM
    # cita el artículo vecino. SOLO AÑADE → cita_ok monótona (no regresa por
    # construcción); el costo a vigilar es PRECISIÓN (citas de más). Requiere
    # pasar un reranker a generate_answer (reusa el BGE ya cargado; cabe en la
    # 1080 fp16). Mide cita_ok + precisión de citas añadidas + no-regresión.
    citation_repair: bool = False
    citation_repair_min_score: float = 0.0   # umbral cross-encoder para añadir
    citation_repair_max_add: int = 1         # tope de citas añadidas por respuesta

    # Candidate-pool depth fed into RRF fusion (BM25 + vector each retrieve
    # this many before fusion/rerank). Default 50 = unchanged behavior. Raise
    # via env (RETRIEVAL_POOL_DEPTH) to test whether grounding is recall-limited
    # (right norma missed by shallow retrieval) vs generation-limited (LLM
    # ceiling). Pure deterministic recall lever — no fuzzy, no thresholds.
    retrieval_pool_depth: int = 50

    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()  # singleton
