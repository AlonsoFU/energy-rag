"""RK1 screen (BARATO, sin gen): ¿Qwen3-Reranker mete más golds al top-10 que BGE?
Condición necesaria para RK1: si no mejora gold@10, el gen no mejora (aunque screen miente en
el otro sentido). Usa eval LIMPIO (also_gold). ~5min.

Uso: RERANKER_KIND no aplica aquí (instancia ambos). BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_rk1_screen
"""
import json, subprocess, time
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import BGEReranker, Qwen3Reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.grounding import _normalize_art
from src.core import config as cfg

SET = "data/eval/queries_balanced_v2_clean.jsonl"


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def gold_at_10(docs, gs):
    top = {(str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero")))) for d in docs[:10]}
    return bool(top & gs)


def run(retr, rows):
    hit = 0
    for q in rows:
        docs = retr.retrieve(q["query"], top_k=10)
        hit += gold_at_10(docs, golds(q))
    return hit


def main():
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    rows = [q for q in rows if q.get("category") == "in_domain"]
    e = Qwen3Embedder(); store = PostgresStore(); llm = get_llm_provider()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    print(f"in_domain (clean, also_gold): {len(rows)}", flush=True)
    # BGE
    print("=== rerank BGE ===", flush=True); t0 = time.time()
    rb = BGEReranker()
    retr = SimpleRetriever(store, e, rb, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    bge = run(retr, rows)
    print(f"  BGE gold@10: {bge}/{len(rows)}  ({time.time()-t0:.0f}s)", flush=True)
    del rb, retr.reranker
    import torch, gc; gc.collect(); torch.cuda.empty_cache()
    # Qwen3
    print("=== rerank Qwen3-Reranker-4B ===", flush=True); t0 = time.time()
    rq = Qwen3Reranker()
    retr2 = SimpleRetriever(store, e, rq, top_bm25=cfg.settings.retrieval_pool_depth,
                            top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    qw = run(retr2, rows)
    print(f"  Qwen3 gold@10: {qw}/{len(rows)}  ({time.time()-t0:.0f}s)", flush=True)

    print(f"\n=== RK1 SCREEN ===", flush=True)
    print(f"  BGE   gold@10: {bge}/{len(rows)}", flush=True)
    print(f"  Qwen3 gold@10: {qw}/{len(rows)}", flush=True)
    print(f"  Δ = {qw-bge:+d}  -> {'vale el gen largo' if qw-bge >= 5 else 'RK1 no rescata recall, NO seguir'}", flush=True)


if __name__ == "__main__":
    main()
