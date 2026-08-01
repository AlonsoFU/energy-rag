"""¿El cross-encoder BGE sobre pool AMPLIO recupera los golds profundos?
El gold coloquial está en pool@200 (techo 11/11) pero el reranker solo ve pool@50.
Compara gold∈top10 reordenando pool@50 vs @100 vs @200 con el MISMO BGE cross-encoder.

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_rerank_wide
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights


def _load(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if d.get("category") in cats and d.get("expected_norma"):
            out.append((d["query"], [f"{d['expected_norma']}/{d['expected_articulo']}"] + (d.get("also_gold") or [])))
    return out

POS = _load("data/eval/queries_complex_v3.jsonl", {"cx_coloquial"})
REG = _load("data/eval/queries_independent.jsonl", {"indep_def", "indep_complex"})[:12]
DEPTHS = [50, 100, 200]


def ranks(store, emb, rr, q, golds):
    bm = store.search_bm25(q, top_k=200)
    vec = store.search_vector(emb.embed([q])[0], top_k=200)
    fused = rrf_fusion([bm, vec], k=60, weights=_length_weights(q))[:200]
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    res = {}
    for d in DEPTHS:
        pool = fused[:d]
        sc = rr.rerank(q, [c["contextual_text"] for c in pool], top_k=d)  # rerank TODO el pool
        order = [pool[i] for i, _ in sc]
        r = next((i + 1 for i, c in enumerate(order) if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset), None)
        res[d] = r
    return res


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    print(f"reranker={type(rr).__name__}\n")
    for items, tag in [(POS, "COLOQUIAL"), (REG, "DEV")]:
        print(f"--- {tag} ---")
        cnt = {d: 0 for d in DEPTHS}
        for q, golds in items:
            r = ranks(store, emb, rr, q, golds)
            for d in DEPTHS:
                if r[d] and r[d] <= 10:
                    cnt[d] += 1
            print("  " + " ".join(f"@{d}={str(r[d]):>4}" for d in DEPTHS) + f" | {q[:40]}")
        n = len(items)
        print("  gold∈top10 tras rerank: " + "  ".join(f"pool@{d}={cnt[d]}/{n}" for d in DEPTHS) + "\n")


if __name__ == "__main__":
    main()
