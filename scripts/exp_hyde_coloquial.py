"""EXP: ¿HyDE rescata la recuperabilidad de queries COLOQUIALES?

Para cada coloquial in-domain, compara gold_rank (post-BGE) con la query CRUDA
vs query+HyDE (reescritura legal hipotética para el lado vectorial, como hyde_in_simple).
HyDE = puente de vocabulario general (coloquial→legal). Mide si el gold entra al pool.

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_hyde_coloquial
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights
from src.pipelines.expansion import hyde

POS = [(json.loads(l)["query"],
        f"{json.loads(l)['expected_norma']}/{json.loads(l)['expected_articulo']}")
       for l in open("data/eval/queries_complex_v3.jsonl")
       if json.loads(l)["category"] == "cx_coloquial"]


def gold_rank(store, emb, rr, query, vec_text, gold):
    bm25 = store.search_bm25(query, top_k=50)          # BM25 siempre query original
    vec = store.search_vector(emb.embed([vec_text])[0], top_k=50)  # vector con HyDE
    fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(vec_text))[:50]
    if not fused:
        return None, 0.0
    scored = rr.rerank(query, [c["contextual_text"] for c in fused], top_k=30)
    order = [fused[i] for i, _ in scored]
    bge_max = max((s for _, s in scored), default=0.0)
    gn, ga = gold.split("/", 1)
    for i, c in enumerate(order):
        if str(c.get("id_norma")) == gn and str(c.get("articulo_numero")) == ga:
            return i + 1, bge_max
    return None, bge_max


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    llm = get_llm_provider()
    print(f"reranker={type(rr).__name__}\n")
    base_ok = hyde_ok = 0
    for q, g in POS:
        rb, _ = gold_rank(store, emb, rr, q, q, g)
        h = hyde(q, llm=llm)
        rh, bge_h = gold_rank(store, emb, rr, q, f"{q}\n{h}", g)
        base_ok += 1 if (rb and rb <= 10) else 0
        hyde_ok += 1 if (rh and rh <= 10) else 0
        flag = "↑" if (rh and (not rb or rh < rb)) else ("=" if rb == rh else "↓" if rb and (not rh or rh > rb) else "")
        print(f"  base={str(rb):>4} hyde={str(rh):>4} {flag}  gold {g}  | {q[:46]}")
        print(f"       HyDE: {h[:120]}")
    n = len(POS)
    print(f"\nGold∈top10:  CRUDA {base_ok}/{n}  →  +HyDE {hyde_ok}/{n}")


if __name__ == "__main__":
    main()
