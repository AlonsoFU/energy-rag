"""Bake-off de modelos de GENERACIÓN (3090). Retrieval FIJO (4B-1024+alias, cacheado 1 vez);
se genera desde los MISMOS docs con cada modelo → cita_ok aislado por modelo gen.

Two-phase: cachea docs (4B embed), luego itera modelos (stop entre cada uno para no swapear de más).
Lee la lista de modelos de argv (ollama/...). Escribe data/eval/results/gen_bakeoff_8b/result.json.

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_gen_bakeoff ollama/qwen3.5:9b ollama/qwen3:32b ...
"""
import json, sys, subprocess, time, os
from pathlib import Path

# PACE: segundos de pausa entre cada query gen (suaviza la carga GPU → fan menos brusco).
# Sin sudo. Cuesta tiempo. Default 0; setear PACE=2 para correr más gentil.
PACE = float(os.environ.get("PACE", "0"))
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/gen_bakeoff_8b")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]
DEFAULT = ["ollama/qwen3.5:9b", "ollama/qwen3:32b", "ollama/qwen2.5:32b",
           "ollama/gemma2:27b", "ollama/mistral-small:24b"]


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _ok(res, golds):
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits) and REFUSAL_TEXT.lower() not in res["text"].lower()


def _stop(m):
    subprocess.run(["ollama", "stop", m.replace("ollama/", "")], capture_output=True)


def main():
    models = sys.argv[1:] or DEFAULT
    for m in models + ["ollama/qwen3-embedding:8b"]:
        _stop(m)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_8b_dense = True

    print("=== FASE A: retrieval 8B (sin alias), cachea docs ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)),
                          "docs": retr.retrieve(q["query"], top_k=10)})
        print(f"  [{setname}] {len([c for c in cache if c['set']==setname])}", flush=True)
    cfg.settings.embed_8b_dense = False; _stop("ollama/qwen3-embedding:8b")
    # libera BGE de GPU (solo se usa en retrieval; en gen estorba ~2GB y puede OOMear los 20GB)
    try:
        import torch, gc
        del r, retr.reranker
        gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass

    # resume: carga agg previo y salta modelos ya hechos (sobrevive crashes/detach)
    agg = {}  # model -> set -> count
    rj = OUTDIR / "result.json"
    if rj.exists():
        try:
            agg = json.loads(rj.read_text()).get("agg", {})
            print(f"[resume] ya hechos: {list(agg.keys())}", flush=True)
        except Exception:
            pass
    for model in models:
        if model in agg:
            print(f"=== SKIP {model} (ya hecho) ===", flush=True)
            continue
        for o in models:
            if o != model:
                _stop(o)
        t0 = time.time()
        print(f"=== GEN con {model} ===", flush=True)
        for c in cache:
            golds = {tuple(g) for g in c["golds"]}
            ok = _ok(generate_answer(c["q"], c["docs"], llm=llm, model=model), golds)
            c[f"ok::{model}"] = ok
            agg.setdefault(model, {}).setdefault(c["set"], 0)
            agg[model][c["set"]] += ok
            if PACE:
                time.sleep(PACE)
        print(f"  {model} listo en {time.time()-t0:.0f}s", flush=True)
        (OUTDIR / "result.json").write_text(json.dumps({"agg": agg, "detail": cache}, ensure_ascii=False, indent=2, default=str))

    ns = {s: len([c for c in cache if c["set"] == s]) for s, _ in SETS}
    print("\n=== BAKE-OFF cita_ok (mismos docs, retrieval 4B+alias) ===", flush=True)
    print(f"{'modelo':26s} {'coloq/'+str(ns['coloquial']):>9s} {'dev/'+str(ns['dev']):>7s} {'hold/'+str(ns['holdout']):>8s}  total", flush=True)
    for m in models:
        a = agg.get(m, {})
        tot = sum(a.values())
        print(f"{m:26s} {a.get('coloquial',0):>9d} {a.get('dev',0):>7d} {a.get('holdout',0):>8d}  {tot}", flush=True)


if __name__ == "__main__":
    main()
