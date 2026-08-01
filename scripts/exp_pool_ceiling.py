"""Techo de recall: ¿en qué profundidad de pool (BM25+Qwen dense) aparece el gold?
Marca el máximo que CUALQUIER reranker podría recuperar. v3-coloquial + dev.

Uso: HF_HUB_OFFLINE=1 EMBEDDER_DEVICE=cpu ./venv-gpu/bin/python -m scripts.exp_pool_ceiling
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights


def _load(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if d.get("category") in cats and d.get("expected_norma"):
            golds = [f"{d['expected_norma']}/{d['expected_articulo']}"] + (d.get("also_gold") or [])
            out.append((d["query"], golds))
    return out

POS = _load("data/eval/queries_complex_v3.jsonl", {"cx_coloquial"})
REG = _load("data/eval/queries_independent.jsonl", {"indep_def", "indep_complex"})[:12]


def rank_in_pool(store, emb, q, golds, depth):
    bm = store.search_bm25(q, top_k=depth)
    vec = store.search_vector(emb.embed([q])[0], top_k=depth)
    fused = rrf_fusion([bm, vec], k=60, weights=_length_weights(q))[:depth]
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    for i, c in enumerate(fused):
        if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset:
            return i + 1
    return None


def main():
    store, emb = PostgresStore(), Qwen3Embedder()
    for items, tag in [(POS, "COLOQUIAL"), (REG, "DEV")]:
        print(f"--- {tag} ---")
        cnt = {d: 0 for d in (50, 100, 200, 500)}
        for q, golds in items:
            r = rank_in_pool(store, emb, q, golds, 500)
            for d in cnt:
                if r and r <= d:
                    cnt[d] += 1
            print(f"  rank@500={str(r):>4} | {q[:48]}")
        n = len(items)
        print(f"  gold∈pool: " + "  ".join(f"@{d}={cnt[d]}/{n}" for d in (50, 100, 200, 500)) + "\n")


if __name__ == "__main__":
    main()
