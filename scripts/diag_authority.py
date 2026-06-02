"""Diagnóstico A0 — authority/norma miss.

Para queries que NOMBRAN una norma, dump del pool en 2 etapas (post-RRF, post-BGE)
con (id_norma/articulo, score) y el RANGO del gold. Responde: ¿está el gold en el
pool? ¿en qué rango cae antes/después de BGE? ¿qué norma detecta `confirmados`?

NO cambia el pipeline; reproduce los pasos 1-4 de SimpleRetriever.retrieve.
Uso: ./venv-gpu/bin/python -m scripts.diag_authority
"""
import json
import re
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights

# queries con su gold (norma/articulo) — los 2 frentes del set extremo
CASES = [
    ("a qué se le dice energía firme en el reglamento de transferencias de potencia",
     "250604", "13", "ext_autoridad (MISS)"),
    ("el coordinador opera el sistema, pero ¿quién aprueba finalmente el plan de expansión de la transmisión?",
     "258171", "92", "ext_distractor (MISS)"),
]


def _norm(t):
    t = t.lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_norma(query):
    """Detecta si la query nombra una norma vía config/alias_normas.json confirmados."""
    data = json.load(open("config/alias_normas.json"))
    conf = data["confirmados"]
    q = _norm(query)
    hits = [(name, idn) for name, idn in conf.items() if _norm(name) in q]
    # preferir el match más largo (más específico)
    hits.sort(key=lambda x: len(x[0]), reverse=True)
    return hits


def rank_of(pool, gold_norma, gold_art):
    for i, c in enumerate(pool):
        if str(c.get("id_norma")) == gold_norma and str(c.get("articulo_numero")) == gold_art:
            return i + 1, c.get("score")
    return None, None


def main():
    store = PostgresStore()
    embedder = Qwen3Embedder()
    reranker = get_reranker()
    print(f"reranker={type(reranker).__name__}\n")

    for query, gnorma, gart, tag in CASES:
        print("=" * 90)
        print(f"Q [{tag}]: {query}")
        print(f"GOLD: {gnorma}/{gart}")
        hits = detect_norma(query)
        print(f"NORMA detectada (confirmados): {hits if hits else 'NINGUNA'}")

        bm25 = store.search_bm25(query, top_k=50)
        q_emb = embedder.embed([query])[0]
        vec = store.search_vector(q_emb, top_k=50)
        fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(query))[:50]
        r_rrf, s_rrf = rank_of(fused, gnorma, gart)
        print(f"  POST-RRF (pool={len(fused)}): gold rank = {r_rrf}  score={s_rrf}")

        scored = reranker.rerank(query, [c["contextual_text"] for c in fused], top_k=30)
        bge = [{**fused[i], "score": float(s)} for i, s in scored]
        r_bge, s_bge = rank_of(bge, gnorma, gart)
        print(f"  POST-BGE (top30):           gold rank = {r_bge}  score={s_bge}")

        # cuántos del pool son de la norma-objetivo (si se detectó)
        if hits:
            tgt = hits[0][1]
            in_rrf = sum(1 for c in fused if str(c.get("id_norma")) == tgt)
            print(f"  candidatos de la norma-objetivo {tgt} en pool RRF: {in_rrf}")
        # top-5 post-BGE para ver qué gana
        print("  TOP-5 post-BGE:")
        for i, c in enumerate(bge[:5]):
            print(f"    {i+1}. {c.get('id_norma')}/{c.get('articulo_numero')}  score={c.get('score'):.3f}")
        print()


if __name__ == "__main__":
    main()
