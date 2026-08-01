"""EXP ColBERT (late-interaction, bge-m3 multi-vector) como reranker de pool amplio.

El gold duro (SEC 29819/2) está a rank ~131 en pool@200 → un reranker normal sobre
pool@50 no lo ve. ColBERT hace match token-a-token (MaxSim) — fuerte para entidades.
Compara, sobre v3-coloquial + muestra dev:
  base   = pipeline actual (BM25+Qwen dense, pool 50 → BGE cross-encoder rerank)
  colbert= pool AMPLIO (BM25+Qwen dense, 200) → reordenar por MaxSim de bge-m3

Uso: HF_HUB_OFFLINE=1 EMBEDDER_DEVICE=cpu COLBERT_DEVICE=cuda \
       ./venv-gpu/bin/python -m scripts.exp_colbert
"""
import json, os
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights
from FlagEmbedding import BGEM3FlagModel


def _load(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if d.get("category") in cats and d.get("expected_norma"):
            golds = [f"{d['expected_norma']}/{d['expected_articulo']}"] + (d.get("also_gold") or [])
            out.append((d["query"], golds, d["category"]))
    return out

POS = _load("data/eval/queries_complex_v3.jsonl", {"cx_coloquial"})
REG = _load("data/eval/queries_independent.jsonl", {"indep_def", "indep_complex"})[:12]
WIDE = 200


def wide_pool(store, emb, q, depth=WIDE):
    bm = store.search_bm25(q, top_k=depth)
    vec = store.search_vector(emb.embed([q])[0], top_k=depth)
    return rrf_fusion([bm, vec], k=60, weights=_length_weights(q))[:depth]


def in_top(order, golds, k=10):
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    for i, c in enumerate(order[:k]):
        if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset:
            return i + 1
    # buscar rank completo
    for i, c in enumerate(order):
        if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset:
            return i + 1
    return None


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    dev = os.environ.get("COLBERT_DEVICE", "cpu")
    cb = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, devices=dev)
    print(f"colbert device={dev}\n")

    def evaluate(items, tag):
        b10 = c10 = 0
        for q, golds, cat in items:
            pool = wide_pool(store, emb, q)
            # base: pool@50 -> BGE cross-encoder rerank
            p50 = pool[:50]
            sc = rr.rerank(q, [c["contextual_text"] for c in p50], top_k=30)
            base_order = [p50[i] for i, _ in sc]
            rb = in_top(base_order, golds)
            # colbert: MaxSim sobre pool amplio
            qv = cb.encode([q], return_dense=False, return_sparse=False,
                           return_colbert_vecs=True, max_length=512)["colbert_vecs"][0]
            dv = cb.encode([c["contextual_text"] for c in pool], return_dense=False,
                           return_sparse=False, return_colbert_vecs=True, max_length=512,
                           batch_size=16)["colbert_vecs"]
            scores = [cb.colbert_score(qv, d) for d in dv]
            cb_order = [pool[i] for i in sorted(range(len(pool)), key=lambda i: float(scores[i]), reverse=True)]
            rc = in_top(cb_order, golds)
            b10 += 1 if (rb and rb <= 10) else 0
            c10 += 1 if (rc and rc <= 10) else 0
            flag = "↑" if (rc and rc <= 10 and (not rb or rb > 10)) else ("↓" if rb and rb <= 10 and (not rc or rc > 10) else "")
            print(f"  base={str(rb):>4} colbert={str(rc):>4} {flag} {golds[0]:14s} | {q[:38]}")
        n = len(items)
        print(f"=== {tag}: gold∈top10  base {b10}/{n} -> colbert {c10}/{n} ===\n")

    print("--- v3 COLOQUIAL ---"); evaluate(POS, "COLOQUIAL")
    print("--- dev (no-reg) ---"); evaluate(REG, "DEV")


if __name__ == "__main__":
    main()
