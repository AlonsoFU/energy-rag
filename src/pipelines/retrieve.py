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


def graph_boost(candidates: list[dict], query_concepts: list) -> list[dict]:
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
                 top_bm25: int = 50, top_vector: int = 50, top_rerank: int = 10):
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.top_bm25 = top_bm25
        self.top_vector = top_vector
        self.top_rerank = top_rerank

    def retrieve(self, query: str, top_k: int = 5,
                 query_concepts: list[str] | None = None) -> list[dict]:
        # 1. BM25
        bm25 = self.store.search_bm25(query, top_k=self.top_bm25)
        # 2. Vector
        q_emb = self.embedder.embed([query])[0]
        vec = self.store.search_vector(q_emb, top_k=self.top_vector)
        # 3. RRF (length-weighted: short→BM25, long→vectors)
        fused = rrf_fusion([bm25, vec], k=60,
                           weights=_length_weights(query))[: self.top_bm25]
        # 4. Rerank
        if fused:
            scored = self.reranker.rerank(
                query,
                [c["contextual_text"] for c in fused],
                top_k=self.top_rerank,
            )
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
            fused = graph_boost(fused, query_concepts=query_concepts)
        # 7. Hierarchical expand
        expanded = hierarchical_expand(fused)
        return expanded[:top_k]


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

        # 2. Run BM25+vector+RRF for each, then merge across queries via RRF
        rankings = []
        for q in all_queries:
            bm25 = self.store.search_bm25(q, top_k=self.top_bm25)
            q_emb = self.embedder.embed([q])[0]
            vec = self.store.search_vector(q_emb, top_k=self.top_vector)
            rankings.append(rrf_fusion([bm25, vec], k=60)[: self.top_bm25])
        fused = rrf_fusion(rankings, k=60)[: self.top_bm25]

        # 3. Rerank against the original query
        if fused:
            scored = self.reranker.rerank(
                query, [c["contextual_text"] for c in fused], top_k=15
            )
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
        return expanded[:top_k]


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
