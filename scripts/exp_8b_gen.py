"""Fase 2 (3090) — gen eval cita_ok del embedder 8B vs 4B-1024.

Antes el 8B "no cabía" en la GTX 1080 y solo se SCREENeó (vector-only, ≈4B). La 3090 permite
medirlo en generación completa. OFF = 4B-1024 dense | ON = 8B dense (4096-dim, seq-scan).
SimpleRetriever, BGE en GPU. Two-phase (embed luego genera) para no chocar 8B-embed con 9b-gen.

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_8b_gen [top_k]
"""
import json, sys, subprocess
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/emb8b_gen")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _ok(res, golds):
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits) and REFUSAL_TEXT.lower() not in res["text"].lower()


def main():
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=== FASE A: retrieval OFF(4B-1024) + ON(8B) ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            cfg.settings.embed_8b_dense = False; cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
            off = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.embed_4b_dense = False; cfg.settings.embed_8b_dense = True
            on = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.embed_8b_dense = False
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)), "off": off, "on": on})
        print(f"  [{setname}] {len([c for c in cache if c['set']==setname])}", flush=True)
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)

    print("=== FASE B: generación cita_ok (9b) ===", flush=True)
    agg = {}
    for c in cache:
        golds = {tuple(g) for g in c["golds"]}
        a = agg.setdefault(c["set"], {"n": 0, "4b": 0, "8b": 0})
        a["n"] += 1
        a["4b"] += _ok(generate_answer(c["q"], c["off"], llm=llm), golds)
        a["8b"] += _ok(generate_answer(c["q"], c["on"], llm=llm), golds)
        print(f"[{c['set']}] 4b={a['4b']} 8b={a['8b']} n={a['n']} | {c['q'][:30]}", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"top_k": top_k, "agg": agg}, ensure_ascii=False, indent=2))
    print("\n=== VEREDICTO cita_ok (4B-1024 vs 8B) ===", flush=True)
    for s, a in agg.items():
        print(f"  {s:10s} n={a['n']:2d}  4B={a['4b']:2d}  8B={a['8b']:2d}  ({a['8b']-a['4b']:+d})", flush=True)


if __name__ == "__main__":
    main()
