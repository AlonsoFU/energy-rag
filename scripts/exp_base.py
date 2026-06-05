"""Baseline retrieval-only del pipeline actual sobre un set: gold∈top10.
Uso: ... ./venv-gpu/bin/python -m scripts.exp_base data/eval/queries_coloquial_v2.jsonl
"""
import json, sys
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights

PATH = sys.argv[1]
rows = [json.loads(l) for l in open(PATH) if json.loads(l).get("expected_norma")]


def rank(store, emb, rr, q, golds):
    bm = store.search_bm25(q, top_k=50)
    vec = store.search_vector(emb.embed([q])[0], top_k=50)
    fused = rrf_fusion([bm, vec], k=60, weights=_length_weights(q))[:50]
    sc = rr.rerank(q, [c["contextual_text"] for c in fused], top_k=30)
    order = [fused[i] for i, _ in sc]
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    return next((i + 1 for i, c in enumerate(order) if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset), None)


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    top10 = 0
    hard = []
    for r in rows:
        golds = [f"{r['expected_norma']}/{r['expected_articulo']}"] + (r.get("also_gold") or [])
        rk = rank(store, emb, rr, r["query"], golds)
        if rk and rk <= 10:
            top10 += 1
        else:
            hard.append((rk, golds[0], r["query"]))
    print(f"\n=== {PATH}: gold∈top10 = {top10}/{len(rows)} ===")
    print("DUROS (no top10):")
    for rk, g, q in hard:
        print(f"  rank={rk} {g:14s} | {q[:60]}")


if __name__ == "__main__":
    main()
