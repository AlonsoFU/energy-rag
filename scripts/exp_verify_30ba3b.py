"""Verifica el ganador del bakeoff (qwen3:30b-a3b): corre 2× (varianza) + lista fallas ESTABLES
(fallan en ambas corridas = reales; fallan en una = ruido). Retrieval fijo 4B-1024+alias, cacheado.

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_verify_30ba3b
"""
import json, subprocess, time
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

MODEL = "ollama/qwen3:30b-a3b"
OUTDIR = Path("data/eval/results/verify_30ba3b")
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
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    print("=== FASE A: retrieval 4B-1024+alias, cachea ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)),
                          "docs": retr.retrieve(q["query"], top_k=10)})
        print(f"  [{setname}] {len([c for c in cache if c['set']==setname])}", flush=True)
    cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass

    runs = []
    for run in (1, 2):
        agg = {}
        print(f"=== GEN run {run} con {MODEL} ===", flush=True)
        t0 = time.time()
        for c in cache:
            golds = {tuple(g) for g in c["golds"]}
            c[f"ok{run}"] = _ok(generate_answer(c["q"], c["docs"], llm=llm, model=MODEL), golds)
            agg.setdefault(c["set"], {"n": 0, "ok": 0})
            agg[c["set"]]["n"] += 1; agg[c["set"]]["ok"] += c[f"ok{run}"]
        runs.append(agg)
        print(f"  run {run} en {time.time()-t0:.0f}s", flush=True)
        # guarda tras CADA corrida (sobrevive muertes de sesión)
        (OUTDIR / "result.json").write_text(json.dumps({"runs": runs, "detail": cache}, ensure_ascii=False, indent=2, default=str))

    print("\n=== VARIANZA (2 corridas, mismos docs) ===", flush=True)
    for s in ("coloquial", "dev", "holdout"):
        a1, a2 = runs[0][s], runs[1][s]
        print(f"  {s:10s} run1={a1['ok']:2d}/{a1['n']}  run2={a2['ok']:2d}/{a2['n']}", flush=True)
    print("\n=== FALLAS ESTABLES (fallan en AMBAS = reales) ===", flush=True)
    for c in cache:
        if not c["ok1"] and not c["ok2"]:
            g = ",".join(sorted(f"{n}/{ar}" for n, ar in {tuple(x) for x in c["golds"]}))
            print(f"  [{c['set']:9s}] {g:14s} | {c['q'][:52]}", flush=True)
    print("\n=== INESTABLES (fallan en solo 1 = ruido) ===", flush=True)
    for c in cache:
        if c["ok1"] != c["ok2"]:
            print(f"  [{c['set']:9s}] {c['q'][:52]}", flush=True)


if __name__ == "__main__":
    main()
