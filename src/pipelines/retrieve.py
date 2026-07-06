"""SIMPLE branch retrieval pipeline.

Combines BM25 + vector search via RRF fusion, applies graph-aware boosting
using the referencias table, then expands fragment-level hits to their parent
articulos. Exposes a `SimpleRetriever` orchestrator that ties everything
together with a reranker.
"""
import re as _re
from psycopg.rows import dict_row

from src.storage.connection import with_connection
from src.components.llm import LLMProvider, get_llm_provider
from src.pipelines.expansion import hyde, multi_query, step_back
from src.pipelines.normalize import normalize_for_match, find_term_in_query


# ---------------------------------------------------------------------------
# Step 1: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def rrf_fusion(rankings: list[list[dict]], k: int = 60,
               weights: list[float] | None = None) -> list[dict]:
    """Reciprocal Rank Fusion. Each input list ordered by relevance.
    Items must have 'id'. Returns deduped list ordered by RRF score desc.

    `weights[i]` scales the contribution of rankings[i]. Default = all 1.0
    (classic RRF, preserves prior behavior + tests). Used to bias toward BM25
    for short queries (acronyms/exact terms) and toward vectors for long ones
    (semantics) — see SimpleRetriever.retrieve.
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}
    for ranking, w in zip(rankings, weights):
        for rank, item in enumerate(ranking, start=1):
            iid = item["id"]
            scores[iid] = scores.get(iid, 0.0) + w * (1.0 / (k + rank))
            items[iid] = item
    return [items[i] for i in sorted(scores, key=lambda i: scores[i], reverse=True)]


def _embed_4b_query(text: str, model: str = "qwen3-embedding:4b"):
    """Embebe la query con un embedder Qwen3 vía Ollama (GGUF). [] si falla."""
    import json as _json, urllib.request as _u
    from src.core import config as _c
    try:
        payload = {"model": model, "input": [text]}
        # embed_4b_cpu: fuerza el embed en CPU (num_gpu=0) para coexistir con el 9B en
        # GPU sin swap (necesario en la ruta complejo, que usa el 9B para expansiones).
        if getattr(_c.settings, "embed_4b_cpu", False):
            payload["options"] = {"num_gpu": 0}
        data = _json.dumps(payload).encode()
        req = _u.Request("http://localhost:11434/api/embed", data=data,
                         headers={"Content-Type": "application/json"})
        with _u.urlopen(req, timeout=120) as r:
            return _json.loads(r.read())["embeddings"][0]
    except Exception:
        return []


def _vector_4b_search(text, store, top_k):
    """Embebe `text` con 4B (Ollama) y busca; MRL-1024 (HNSW) o 2560 (seq-scan). [] si falla."""
    from src.core import config as _c
    emb = _embed_4b_query(text)
    if not emb:
        return []
    if getattr(_c.settings, "embed_4b_dim", 2560) == 1024:
        import math as _m
        s = emb[:1024]
        nrm = _m.sqrt(sum(x*x for x in s)) or 1.0
        return store.search_vector_4b_1024([x/nrm for x in s], top_k=top_k)
    return store.search_vector_4b(emb, top_k=top_k)


def _vector_leg(text, embedder, store, top_k, raw_query=None):
    """Pata densa: 4B (Ollama, embedding_4b) si embed_4b_dense, si no 0.6B (sentence-transf).

    alias_union (flag, requiere 4B): si la query coloquial dispara un alias curado, embebe
    TAMBIÉN la query reemplazada por el término legal y UNE (RRF) con la original. Protege
    casos buenos (original) y rescata muros de vocabulario (alias). `raw_query` = query del
    usuario sin augmentar (para el match del alias); si None, usa `text`."""
    from src.core import config as _c
    # embed_8b_dense (flag, 3090): pata densa 8B fp16/GGUF (embedding_8b, 4096-dim, seq-scan).
    # Antes imposible en GTX 1080. Excluyente con 4B. Sin alias_union (experimento aislado del embedder).
    if getattr(_c.settings, "embed_8b_dense", False):
        emb = _embed_4b_query(text, model="qwen3-embedding:8b")
        if emb:
            res = store.search_vector_8b(emb, top_k=top_k)
            if res:
                return res
    if getattr(_c.settings, "embed_4b_dense", False):
        base = _vector_4b_search(text, store, top_k)
        if base and getattr(_c.settings, "alias_union", False):
            from src.pipelines.alias_map import apply_alias
            q = raw_query if raw_query is not None else text
            aug = apply_alias(q)
            if aug != q:  # disparó un alias → busca con el término legal y une
                alt = _vector_4b_search(aug, store, top_k)
                if alt:
                    return rrf_fusion([base, alt], k=60)[:top_k]
        if base:
            return base
    return store.search_vector(embedder.embed([text])[0], top_k=top_k)


_BGEM3 = None


def _bgem3_leg(query: str, store, top_k: int) -> list[dict]:
    """2da pata densa del ensemble: codifica la query con bge-m3 y busca sobre
    embedding_bgem3. Embedder cargado perezosamente y cacheado. [] si algo falla
    (degrada a 2 patas, nunca rompe el retrieval)."""
    global _BGEM3
    try:
        if _BGEM3 is None:
            from sentence_transformers import SentenceTransformer
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            from src.core.config import settings as _s
            dev = (_s.embedder_device if (_s.embedder_device or "auto") != "auto" else dev)
            _BGEM3 = SentenceTransformer("BAAI/bge-m3", device=dev)
            _BGEM3.max_seq_length = 512
        qv = _BGEM3.encode([query], normalize_embeddings=True)[0].tolist()
        return store.search_vector_bgem3(qv, top_k=top_k)
    except Exception:
        return []


def _length_weights(query: str) -> list[float]:
    """[bm25_w, vec_w] biased by query length. Short queries (acronyms, exact
    legal terms) lean BM25; long descriptive queries lean vectors. Thresholds
    are deterministic; significant words = tokens longer than 3 chars."""
    n = len([w for w in query.split() if len(w) > 3])
    if n <= 3:
        return [0.65, 0.35]
    if n >= 7:
        return [0.35, 0.65]
    return [0.5, 0.5]


# ---------------------------------------------------------------------------
# Step 2: Graph boost
# ---------------------------------------------------------------------------

GRAPH_BOOST_FACTOR = {
    "define_termino": 2.0,
    "aplica": 2.0,
    "modifica": 1.5,
    "cita": 1.3,
    "menciona": 1.2,
    "remite": 1.3,
    "complementa": 1.4,
    "deroga": 1.5,
    "referencia_implicita": 1.1,
}


def graph_boost(candidates: list[dict], query_concepts: list,
                boost_all: bool = False) -> list[dict]:
    """Boost candidates whose articulo has a `referencias` edge to one of the
    query concepts.

    `query_concepts` is either:
      - list[str]  (legacy callers): concept names; no alias info.
      - list[dict]: {"name": str, "matched_by_alias": bool}; the additive
        define_termino boost applies ONLY to concepts that matched via alias
        (e.g. "CNE" in the query → boost the def article for "Comisión").
        Concepts matched via canonical name don't get the strong boost
        because the canonical-name path was already finding the right doc.
    """
    if not query_concepts or not candidates:
        return candidates

    # Normalize input. alias_matched_names = set of canonical names that
    # came from an alias match (eligible for additive define_termino boost).
    # Legacy str-list callers don't carry alias info, so they fall back to
    # the original multiplicative boost (preserves prior behavior + tests).
    if query_concepts and isinstance(query_concepts[0], dict):
        all_names = [qc["name"] for qc in query_concepts]
        alias_matched_names = {
            qc["name"].lower() for qc in query_concepts
            if qc.get("matched_by_alias")
        }
        legacy_caller = False
    else:
        all_names = list(query_concepts)
        alias_matched_names = set()
        legacy_caller = True

    # EXP graph_boost_all: extend the strong define_termino +10 boost to
    # concepts matched by CANONICAL name (not only aliases). Tests whether
    # promoting a query concept's defining article to the top recovers the
    # situational/definitional misses (gold survives rerank but loses top-5).
    # Risk = canonical-name false positives (the alias gate existed for that);
    # measured on dev+holdout before adopting.
    if boost_all and not legacy_caller:
        alias_matched_names = {n.lower() for n in all_names}

    art_ids = [c["articulo_id"] for c in candidates]

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT r.origen_articulo_id, r.tipo_relacion, c.nombre AS concepto_nombre,
                   n.fecha_publicacion, n.clase
            FROM referencias r
            JOIN conceptos c ON c.id = r.destino_concepto_id
            JOIN articulos a ON a.id = r.origen_articulo_id
            JOIN normas n ON n.id_norma = a.id_norma
            WHERE r.origen_articulo_id = ANY(%s::bigint[])
              AND lower(c.nombre) = ANY(%s::text[])
        """, (art_ids, [n.lower() for n in all_names]))
        edges_by_art: dict[int, list[dict]] = {}
        for row in cur.fetchall():
            edges_by_art.setdefault(row["origen_articulo_id"], []).append(row)

    out = []
    for c in candidates:
        edges = edges_by_art.get(c["articulo_id"], [])
        if edges:
            new = dict(c)
            # define_termino boost only applies if the linked concept was
            # alias-matched in the query (avoids false positives like
            # "Comisión de acreedores" hijacking the boost via the eléctrica
            # "Comisión" alias when the canonical-name path already worked).
            define_via_alias = any(
                e["tipo_relacion"] == "define_termino"
                and (e["concepto_nombre"] or "").lower() in alias_matched_names
                for e in edges
            )
            if define_via_alias:
                # Temporalidad (Exp T-C): when a concept is defined in several
                # norms (e.g. C.O.M.A. in Decreto 10 AND in 1160108) every
                # defining article gets +10 → tie. Add a small recency tie-
                # breaker so the MORE RECENT norm (proxy for "vigente") wins,
                # plus a nudge for clase=reglamento_base (stable definitional
                # source). This is a HEURISTIC ranking aid, NOT a legal
                # vigencia ruling — real derogation parsing is Exp T-B.
                define_edges = [
                    e for e in edges
                    if e["tipo_relacion"] == "define_termino"
                    and (e["concepto_nombre"] or "").lower() in alias_matched_names
                ]
                years = [e["fecha_publicacion"].year for e in define_edges
                         if e.get("fecha_publicacion")]
                recency = 0.0
                if years:
                    # Map [1935, 2025] → [0, 0.9]; recent ≈ +0.9, old ≈ 0.
                    recency = min(max((max(years) - 1935) / 90.0, 0.0), 1.0) * 0.9
                base_nudge = 0.3 if any(
                    (e.get("clase") or "") == "reglamento_base"
                    for e in define_edges
                ) else 0.0
                new["score"] = c["score"] + 10.0 + recency + base_nudge
                new["graph_boost_factor"] = (
                    f"define_termino+10 (alias) +rec{recency:.2f}+base{base_nudge:.1f}"
                )
            elif legacy_caller:
                # Legacy: original multiplicative behavior (define_termino=2.0)
                factor = max(GRAPH_BOOST_FACTOR.get(e["tipo_relacion"], 1.0) for e in edges)
                new["score"] = c["score"] * factor
                new["graph_boost_factor"] = factor
            else:
                # Dict caller without alias match: skip define_termino factor
                # (it would over-promote on canonical-name matches like
                # "Comisión de acreedores" hijacking the eléctrica boost).
                factor = max(
                    (GRAPH_BOOST_FACTOR.get(e["tipo_relacion"], 1.0)
                     for e in edges if e["tipo_relacion"] != "define_termino"),
                    default=1.0,
                )
                new["score"] = c["score"] * factor
                new["graph_boost_factor"] = factor
            out.append(new)
        else:
            out.append(c)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Step 3: Hierarchical expansion (fragment -> parent articulo)
# ---------------------------------------------------------------------------

def hierarchical_expand(candidates: list[dict]) -> list[dict]:
    """Replace fragment-level candidates with their parent articulos.
    Deduplicates by articulo_id, keeping max score per articulo."""
    if not candidates:
        return []
    by_art: dict[int, dict] = {}
    for c in candidates:
        aid = c["articulo_id"]
        if aid not in by_art or c["score"] > by_art[aid]["score"]:
            by_art[aid] = c

    art_ids = list(by_art.keys())
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT a.id, a.id_norma, a.numero, a.titulo, a.texto, n.titulo AS norma_titulo
            FROM articulos a
            JOIN normas n ON n.id_norma = a.id_norma
            WHERE a.id = ANY(%s::bigint[])
        """, (art_ids,))
        details = {r["id"]: r for r in cur.fetchall()}

    out = []
    for aid, frag in by_art.items():
        d = details.get(aid)
        if not d:
            continue
        out.append({
            **frag,
            "articulo_text": d["texto"],
            "articulo_numero": d["numero"],
            "articulo_titulo": d["titulo"],
            "id_norma": d["id_norma"],
            "norma_titulo": d["norma_titulo"],
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Step 4: Query concept extraction
# ---------------------------------------------------------------------------

def extract_query_concepts(query: str, conceptos: list[dict]) -> list[dict]:
    """Return concepts (with optional aliases) found verbatim in the query.

    Each entry: {"name": canonical_name, "matched_by_alias": bool}.
    `matched_by_alias=True` means the query mentioned an alias (e.g. "CNE"),
    not the canonical name (e.g. "Comisión"). Downstream graph_boost uses
    this flag to apply the strong define_termino boost only when an alias
    triggered the match — queries that already use the canonical name
    don't benefit from the boost (they were already finding the right doc).

    Matching is EXACT but under deterministic normalization (case, accents,
    acronym dots) — see normalize.py. NOT fuzzy: a term that isn't literally
    the same modulo orthography will not match.
    """
    nquery = normalize_for_match(query)
    out = []
    for c in conceptos:
        canonical = c["nombre"]
        aliases = c.get("aliases") or []
        # Check canonical first
        if find_term_in_query(canonical, nquery):
            out.append({"name": canonical, "matched_by_alias": False})
            continue
        # Then aliases
        for n in aliases:
            if not n:
                continue
            if find_term_in_query(n, nquery):
                out.append({"name": canonical, "matched_by_alias": True})
                break
    return out


# ---------------------------------------------------------------------------
# Step 5: SimpleRetriever orchestrator (with auto concept detection)
# ---------------------------------------------------------------------------

class SimpleRetriever:
    """SIMPLE branch retriever.

    Pipeline: BM25 + vector -> RRF fusion -> rerank -> graph boost ->
    hierarchical expansion -> top_k.
    """

    def __init__(self, store, embedder, reranker,
                 top_bm25: int = 50, top_vector: int = 50, top_rerank: int = 10,
                 llm: LLMProvider | None = None):
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.top_bm25 = top_bm25
        self.top_vector = top_vector
        self.top_rerank = top_rerank
        self.llm = llm  # only needed when hyde_in_simple is on

    def _search_text(self, query: str) -> str:
        """Query text used for BM25+vector. Two optional, additive augmentations
        (both flag-gated, both vector-only — the ORIGINAL query stays in BM25 via
        retrieve(); rerank/concepts always use the original):

        - ``selective_reform``: if the query is colloquial, append its legal-register
          restatement so the everyday phrasing lands near the formal article text.
          A query already in legal register is left untouched ("IGUAL").
        - ``hyde_in_simple``: append a hypothetical legal paragraph.

        Legal-safe: changes only WHAT is retrieved, never the citation."""
        from src.core import config as _cfg
        text = query
        self._last_concept_terms = ""
        if getattr(_cfg.settings, "concept_inference", False):
            try:
                from src.pipelines.expansion import infer_legal_concept as _ilc
                terms = _ilc(query, llm=self.llm)
                if terms:
                    self._last_concept_terms = terms
                    text = f"{text} {terms}"
            except Exception:
                pass  # LLM hiccup: degrade to plain query, never break retrieval
        if getattr(_cfg.settings, "selective_reform", False):
            try:
                from src.pipelines.expansion import selective_reform as _sr
                rw = _sr(query, llm=self.llm)
                if rw:  # "" cuando la query ya es legal (IGUAL) → no se toca
                    text = f"{query} {rw}"
            except Exception:
                pass  # LLM hiccup: degrade to plain query, never break retrieval
        if getattr(_cfg.settings, "hyde_in_simple", False):
            try:
                from src.pipelines.expansion import hyde as _hyde
                h = _hyde(query, llm=self.llm)
                if h:
                    text = f"{text}\n{h}"
            except Exception:
                pass
        return text

    def retrieve(self, query: str, top_k: int = 5,
                 query_concepts: list[str] | None = None) -> list[dict]:
        # HyDE is VECTOR-ONLY: the hypothetical legal paragraph augments the
        # embedding (semantic bridge for paraphrases) but NOT BM25 (its
        # hallucinated tokens would add lexical noise; BM25 wants the user's
        # real query terms). Fusion weights use the embedded text's length so a
        # HyDE-augmented (long) vector side gets its due weight instead of being
        # down-weighted as if the query were a short keyword lookup.
        vec_text = self._search_text(query)
        # 1. BM25 — original query terms only
        bm25 = self.store.search_bm25(query, top_k=self.top_bm25)
        # 2. Vector — HyDE-augmented when the flag is on. Pata densa 0.6B o 4B (flag).
        vec = _vector_leg(vec_text, self.embedder, self.store, self.top_vector, raw_query=query)
        # 3. RRF (length-weighted: short→BM25, long→vectors). ensemble_bgem3:
        # agrega una 3ra pata densa (bge-m3) complementaria al Qwen.
        from src.core import config as _cfg0
        legs, weights = [bm25, vec], _length_weights(vec_text)
        if getattr(_cfg0.settings, "ensemble_bgem3", False):
            bg = _bgem3_leg(query, self.store, self.top_vector)
            if bg:
                legs.append(bg)
                weights = weights + [1.0]
        fused = rrf_fusion(legs, k=60, weights=weights)[: self.top_bm25]
        # 4. Rerank. top_rerank_override (EXP) widens the survivors so graph_boost
        # can promote a deeper gold instead of it being truncated here.
        from src.core import config as _cfg
        _tr = getattr(_cfg.settings, "top_rerank_override", 0) or self.top_rerank
        # alias_union: el alias rescata el gold al pool vectorial, pero el reranker lo
        # bota si puntúa solo contra la query coloquial (el gold matchea el TÉRMINO legal,
        # no la frase coloquial). Rerankeamos contra query+término (append) cuando dispara.
        rerank_q = query
        if getattr(_cfg.settings, "alias_union", False) and getattr(_cfg.settings, "embed_4b_dense", False):
            from src.pipelines.alias_map import apply_alias as _aa
            _alias = _aa(query)
            if _alias != query:
                rerank_q = f"{query} {_alias}"
        bge_max = 0.0
        if fused:
            scored = self.reranker.rerank(
                rerank_q,
                [c["contextual_text"] for c in fused],
                top_k=_tr,
            )
            bge_max = max((s for _, s in scored), default=0.0)
            fused = [{**fused[i], "score": float(s)} for i, s in scored]
        # 5. Auto-detect concepts if not provided. Filter out off-domain concepts
        # (regulatorio_otros, energía_otra, indeterminado) so an alias match on,
        # say, "Deudor" from concursal/ley_20720 doesn't pollute an electrical query.
        # Unclassified concepts (metadata.domain_primary IS NULL) are included as a
        # safe default since many DB concepts predate the YAML hierarchy.
        if query_concepts is None:
            with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT nombre, aliases FROM conceptos "
                    "WHERE metadata->>'domain_primary' = 'electricidad' "
                    "   OR metadata->>'domain_primary' IS NULL"
                )
                all_concepts = cur.fetchall()
            query_concepts = extract_query_concepts(query, all_concepts)
        # 6. Graph boost
        if query_concepts:
            fused = graph_boost(
                fused, query_concepts=query_concepts,
                boost_all=getattr(_cfg.settings, "graph_boost_all", False),
            )
        # 7. Hierarchical expand
        expanded = hierarchical_expand(fused)
        out = expanded[:top_k]
        for d in out:  # señal para el gate de off-topic semántico (generate.py)
            d["_bge_max"] = bge_max
        return out


# ---------------------------------------------------------------------------
# Step 6: ComplexRetriever (expansion + multi-query merge)
# ---------------------------------------------------------------------------

class ComplexRetriever(SimpleRetriever):
    """COMPLEJO branch retriever.

    Pipeline: expand query (step-back + HyDE + 3 multi-query variants) ->
    BM25 + vector + RRF per query -> merge across queries via RRF -> rerank
    -> graph boost -> hierarchical expand -> top_k.
    """

    def __init__(self, *args, llm: LLMProvider | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = llm or get_llm_provider()

    def retrieve(self, query: str, top_k: int = 10,
                 query_concepts: list[str] | None = None) -> list[dict]:
        # 1. Generate expansions
        sb = step_back(query, llm=self.llm)
        hd = hyde(query, llm=self.llm)
        mq = multi_query(query, llm=self.llm)
        all_queries = [query, sb, hd] + mq

        # selective_reform (flag): legal-register restatement of a COLLOQUIAL query,
        # applied ADITIVELY and VECTOR-ONLY to the original query (q index 0). BM25
        # keeps the user's real terms; the reform only bridges the everyday↔legal
        # register gap on the embedding side. "" when the query is already legal.
        from src.core import config as _cfg
        reform = ""
        if getattr(_cfg.settings, "selective_reform", False):
            try:
                from src.pipelines.expansion import selective_reform as _sr
                reform = _sr(query, llm=self.llm)
            except Exception:
                reform = ""

        # concept_inference (flag): términos técnico-legales EXACTOS del concepto
        # implícito, añadidos ADITIVO vector-only a la query original (q índice 0).
        # Mismo cableado que reform; ataca el muro de vocabulario coloquial.
        concept_terms = ""
        if getattr(_cfg.settings, "concept_inference", False):
            try:
                from src.pipelines.expansion import infer_legal_concept as _ilc
                concept_terms = _ilc(query, llm=self.llm)
            except Exception:
                concept_terms = ""
        _aug0 = " ".join(t for t in (reform, concept_terms) if t)

        # 2. Run BM25+vector+RRF for each, then merge across queries via RRF
        from src.core import config as _cfg0
        _ens = getattr(_cfg0.settings, "ensemble_bgem3", False)
        rankings = []
        for i, q in enumerate(all_queries):
            bm25 = self.store.search_bm25(q, top_k=self.top_bm25)
            vec_text = f"{q} {_aug0}" if (i == 0 and _aug0) else q
            # alias solo se evalúa contra la query original del usuario (i==0)
            vec = _vector_leg(vec_text, self.embedder, self.store, self.top_vector,
                              raw_query=(query if i == 0 else None))
            legs = [bm25, vec]
            if _ens:
                bg = _bgem3_leg(q, self.store, self.top_vector)
                if bg:
                    legs.append(bg)
            rankings.append(rrf_fusion(legs, k=60)[: self.top_bm25])
        fused = rrf_fusion(rankings, k=60)[: self.top_bm25]

        # 3. Rerank against the original query
        bge_max = 0.0
        if fused:
            scored = self.reranker.rerank(
                query, [c["contextual_text"] for c in fused], top_k=15
            )
            bge_max = max((s for _, s in scored), default=0.0)
            fused = [{**fused[i], "score": float(s)} for i, s in scored]

        # 4. Auto-detect concepts if not provided (same domain filter as SimpleRetriever)
        if query_concepts is None:
            with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT nombre, aliases FROM conceptos "
                    "WHERE metadata->>'domain_primary' = 'electricidad' "
                    "   OR metadata->>'domain_primary' IS NULL"
                )
                all_c = cur.fetchall()
            query_concepts = extract_query_concepts(query, all_c)

        # 5. Graph boost
        if query_concepts:
            fused = graph_boost(fused, query_concepts=query_concepts)

        # 6. Hierarchical expand
        expanded = hierarchical_expand(fused)
        out = expanded[:top_k]
        for d in out:  # señal para el gate de off-topic semántico (generate.py)
            d["_bge_max"] = bge_max
        return out


# ---------------------------------------------------------------------------
# Step 7: AdaptiveRetriever (router + simple/complejo branches)
# ---------------------------------------------------------------------------

class AdaptiveRetriever:
    """Routes queries to the appropriate retriever based on a classifier.

    Returns ``(branch, results)`` so callers can log/observe routing decisions.
    """

    def __init__(self, simple: SimpleRetriever, complejo: ComplexRetriever, router):
        self.simple = simple
        self.complejo = complejo
        self.router = router

    def retrieve(self, query: str, top_k: int = 10):
        from src.core import config as _cfg
        # CRAG-style routing (flag): hace retrieval BARATO primero (rama simple,
        # SIN las 3 expansiones LLM); si el mejor score BGE es ALTO, responde con
        # eso (se ahorra step-back+HyDE+multi-query); si es bajo, ESCALA a la rama
        # compleja. Estándar adaptado (CRAG evaluate-then-branch + Adaptive-RAG
        # escalate-to-multistep), reusando el score que el reranker ya computa.
        if getattr(_cfg.settings, "crag_routing", False):
            cheap = self.simple.retrieve(query, top_k=top_k)
            bge = max((d.get("_bge_max", 0.0) for d in cheap), default=0.0)
            if bge >= getattr(_cfg.settings, "crag_answer_threshold", 0.5):
                branch, docs = "simple", cheap          # barato basta → no expandir
            else:
                branch, docs = "complejo", self.complejo.retrieve(query, top_k=top_k)
        else:
            branch = self.router.classify(query)
            if branch == "simple":
                docs = self.simple.retrieve(query, top_k=top_k)
            else:
                docs = self.complejo.retrieve(query, top_k=top_k)
        # Curated concept-definition injection (legal-safe, exact-normalized).
        # When query is "qué es X" and X matches a curated concept exactly,
        # prepend the defining article to docs even if retrieval missed it.
        from src.core import config as _cfg
        if getattr(_cfg.settings, "inject_curated_definitions", False):
            from src.pipelines.concept_injection import inject_definition
            docs = inject_definition(query, docs)[:top_k]
        return branch, docs
