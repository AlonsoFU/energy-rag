"""Separa los 2 fallos de retrieval: (A) embedder no mete el gold ni al pool@50,
(B) reranker bota el gold que SÍ estaba en el pool. Pipeline real (4b-1024+alias).

Uso: BGE_DEVICE=cuda EMBEDDER_DEVICE=cpu HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.exp_stage_split
"""
import json
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.vectorstore import PostgresStore
from src.components.reranker import get_reranker
from src.pipelines.retrieve import _vector_leg, rrf_fusion, _length_weights
from src.pipelines.grounding import _normalize_art

SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl")]


def load_queries():
    out = []
    for s, p in SETS:
        for l in Path(p).read_text().splitlines():
            if not l.strip():
                continue
            q = json.loads(l)
            if q.get("expected_norma") is None:
                continue
            g = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
            for x in q.get("also_gold") or []:
                n, a = str(x).split("/", 1); g.add((n, _normalize_art(a)))
            out.append((s, q["query"], g))
    return out


def gkey(c):
    return (str(c.get("id_norma")), _normalize_art(str(c.get("articulo_numero"))))


def main():
    import os
    dump = os.environ.get("DUMP", "")  # 'poolmiss' o 'rrfail'
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    qs = load_queries()
    agg = {}
    for s, q, gold in qs:
        bm = store.search_bm25(q, top_k=50)
        vec = _vector_leg(q, emb, store, 50, raw_query=q)
        fused = rrf_fusion([bm, vec], k=60, weights=_length_weights(q))[:50]
        in50 = any(gkey(c) in gold for c in fused)
        # ranks del gold en cada pata (para diagnostico)
        rbm = next((i+1 for i, c in enumerate(bm) if gkey(c) in gold), None)
        rvec = next((i+1 for i, c in enumerate(vec) if gkey(c) in gold), None)
        sc = rr.rerank(q, [c["contextual_text"] for c in fused], top_k=10)
        order = [fused[i] for i, _ in sc]
        pos = next((i + 1 for i, c in enumerate(order) if gkey(c) in gold), None)
        a = agg.setdefault(s, {"n": 0, "in50": 0, "t10": 0, "t5": 0})
        a["n"] += 1; a["in50"] += in50
        a["t10"] += (pos is not None and pos <= 10); a["t5"] += (pos is not None and pos <= 5)
        if dump == "poolmiss" and not in50:
            print(f"[{s}] GOLD={sorted(gold)} bm_rank={rbm} vec_rank={rvec}\n   Q: {q}", flush=True)
        if dump == "rrfail" and in50 and (pos is None or pos > 5):
            print(f"[{s}] GOLD={sorted(gold)} bm_rank={rbm} vec_rank={rvec} pos_tras_rerank={pos}\n   Q: {q}", flush=True)
    print(f"{'set':10s} {'n':>3s} {'gold∈pool50':>11s} {'∈top10':>7s} {'∈top5':>6s}  |  fallo-embedder  fallo-reranker(en50 pero fuera-top5)")
    for s, a in agg.items():
        emb_fail = a["n"] - a["in50"]
        rr_fail = a["in50"] - a["t5"]
        print(f"{s:10s} {a['n']:>3d} {a['in50']:>11d} {a['t10']:>7d} {a['t5']:>6d}  |  {emb_fail:>14d}  {rr_fail:>14d}")


if __name__ == "__main__":
    main()
