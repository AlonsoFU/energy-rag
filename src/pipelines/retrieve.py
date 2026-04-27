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


# ---------------------------------------------------------------------------
# Step 1: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def rrf_fusion(rankings: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion. Each input list ordered by relevance.
    Items must have 'id'. Returns deduped list ordered by RRF score desc."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            iid = item["id"]
            scores[iid] = scores.get(iid, 0.0) + 1.0 / (k + rank)
            items[iid] = item
    return [items[i] for i in sorted(scores, key=lambda i: scores[i], reverse=True)]


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


def graph_boost(candidates: list[dict], query_concepts: list[str]) -> list[dict]:
    """Boost candidates whose articulo has a `referencias` edge to one of the
    query concepts. Multiplies the candidate's score by a per-relation factor."""
    if not query_concepts or not candidates:
        return candidates
    art_ids = [c["articulo_id"] for c in candidates]

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT r.origen_articulo_id, r.tipo_relacion, c.nombre AS concepto_nombre
            FROM referencias r
            JOIN conceptos c ON c.id = r.destino_concepto_id
            WHERE r.origen_articulo_id = ANY(%s::bigint[])
              AND lower(c.nombre) = ANY(%s::text[])
        """, (art_ids, [n.lower() for n in query_concepts]))
        edges_by_art: dict[int, list[dict]] = {}
        for row in cur.fetchall():
            edges_by_art.setdefault(row["origen_articulo_id"], []).append(row)

    out = []
    for c in candidates:
        edges = edges_by_art.get(c["articulo_id"], [])
        if edges:
            factor = max(GRAPH_BOOST_FACTOR.get(e["tipo_relacion"], 1.0) for e in edges)
            new = dict(c)
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

def extract_query_concepts(query: str, conceptos: list[dict]) -> list[str]:
    """Return the names of concepts (with optional aliases) found verbatim
    (case-insensitive, word-bounded) in the query."""
    out = []
    for c in conceptos:
        names = [c["nombre"]] + (c.get("aliases") or [])
        for n in names:
            if not n:
                continue
            if _re.search(r"\b" + _re.escape(n) + r"\b", query, _re.IGNORECASE):
                out.append(c["nombre"])
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
        # 3. RRF
        fused = rrf_fusion([bm25, vec], k=60)[: self.top_bm25]
        # 4. Rerank
        if fused:
            scored = self.reranker.rerank(
                query,
                [c["contextual_text"] for c in fused],
                top_k=self.top_rerank,
            )
            fused = [{**fused[i], "score": float(s)} for i, s in scored]
        # 5. Auto-detect concepts if not provided
        if query_concepts is None:
            with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT nombre, aliases FROM conceptos")
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

        # 4. Auto-detect concepts if not provided
        if query_concepts is None:
            with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT nombre, aliases FROM conceptos")
                all_c = cur.fetchall()
            query_concepts = extract_query_concepts(query, all_c)

        # 5. Graph boost
        if query_concepts:
            fused = graph_boost(fused, query_concepts=query_concepts)

        # 6. Hierarchical expand
        expanded = hierarchical_expand(fused)
        return expanded[:top_k]
