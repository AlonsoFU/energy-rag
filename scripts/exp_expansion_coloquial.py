"""EXP cheap-first: técnicas ESTÁNDAR de query-expansion para la brecha de
vocabulario coloquial→legal. Retrieval-only, gold_rank post-BGE, sobre las 11
coloquiales de v3. Compara: base, HyDE, multi-query (RAG-Fusion), step-back, y combos.

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_expansion_coloquial
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights
from src.pipelines.expansion import hyde, multi_query, step_back

POS = [(json.loads(l)["query"], f"{json.loads(l)['expected_norma']}/{json.loads(l)['expected_articulo']}")
       for l in open("data/eval/queries_complex_v3.jsonl") if json.loads(l)["category"] == "cx_coloquial"]


def rank(store, emb, rr, query, vec_texts):
    """vec_texts: lista de textos para el lado vectorial (RRF entre ellos + BM25 con query original)."""
    rankings = [store.search_bm25(query, top_k=50)]
    for t in vec_texts:
        rankings.append(store.search_vector(emb.embed([t])[0], top_k=50))
    fused = rrf_fusion(rankings, k=60)[:50]
    if not fused:
        return None
    scored = rr.rerank(query, [c["contextual_text"] for c in fused], top_k=30)
    order = [fused[i] for i, _ in scored]
    return order


def gr(order, gold):
    if not order:
        return None
    gn, ga = gold.split("/", 1)
    for i, c in enumerate(order):
        if str(c.get("id_norma")) == gn and str(c.get("articulo_numero")) == ga:
            return i + 1
    return None


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    llm = get_llm_provider()
    strategies = ["base", "hyde", "multiquery", "stepback", "hyde+mq"]
    tot = {s: dict(t10=0, t15=0) for s in strategies}
    for q, g in POS:
        h = hyde(q, llm=llm)
        mq = multi_query(q, llm=llm)
        sb = step_back(q, llm=llm)
        variants = {
            "base": [q],
            "hyde": [q, h],
            "multiquery": [q] + mq,
            "stepback": [q, sb],
            "hyde+mq": [q, h] + mq,
        }
        line = f"  {g:14s}"
        for s in strategies:
            r = gr(rank(store, emb, rr, q, variants[s]), g)
            if r and r <= 10: tot[s]["t10"] += 1
            if r and r <= 15: tot[s]["t15"] += 1
            line += f" {s}={str(r):>4}"
        print(line + f"  | {q[:34]}")
    n = len(POS)
    print(f"\n=== gold∈topK sobre {n} coloquiales ===")
    for s in strategies:
        print(f"  {s:11s}  top10={tot[s]['t10']}/{n}  top15={tot[s]['t15']}/{n}")


if __name__ == "__main__":
    main()
