"""E0a: baseline ROBUSTO sobre balanced_v2 (339q: 279 in_domain + 30 off_domain_corpus con gold
+ 30 off_corpus = rechazo). Config campeona vigente (4B-1024 + alias_union + qwen3:30b-a3b).

Guarda resultado POR-QUERY (ok bool) → base para McNemar pareado al medir M1 y siguientes.
Corre 1× por defecto (RUNS=2 para varianza). ~35s/query (MoE) → 339q ≈ 3.3h/run.

Uso (env limpio, ver logs/run_e0.sh):
  PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_e0_baseline
"""
import json, subprocess, time, os
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
RUNS = int(os.environ.get("RUNS", "1"))
SET = ("balanced_v2", "data/eval/queries_balanced_v2.jsonl")
OUTDIR = Path("data/eval/results/e0_baseline")


def _golds(q):
    if q.get("expected_norma") is None:
        return set()
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _is_refusal(text):
    return REFUSAL_TEXT.lower() in text.lower()


def _ok(res, golds, is_offcorpus):
    # off_corpus (sin gold): correcto = RECHAZA. Con gold: correcto = cita gold Y no rechaza.
    if is_offcorpus:
        return _is_refusal(res["text"])
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits) and not _is_refusal(res["text"])


def main():
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    setname, path = SET
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    limit = int(os.environ.get("LIMIT", "0"))
    if limit:
        rows = rows[:limit]; print(f"  [SMOKE] LIMIT={limit}", flush=True)
    print(f"=== FASE A: retrieval cacheado sobre {setname} ({len(rows)}q) ===", flush=True)
    cache = []
    t0 = time.time()
    for i, q in enumerate(rows):
        cat = q.get("category", "?")
        cache.append({"cat": cat, "q": q["query"], "golds": list(_golds(q)),
                      "offcorpus": cat == "off_corpus", "docs": retr.retrieve(q["query"], top_k=10)})
        if (i + 1) % 50 == 0:
            print(f"  retrieval {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass

    def _gen_ok(c, run):
        """Genera con tolerancia: 2 intentos; si igual falla, marca errored (ok=False) y sigue.
        Un timeout transitorio NO debe matar un run de 3.2h."""
        golds = {tuple(g) for g in c["golds"]}
        for attempt in (1, 2):
            try:
                res = generate_answer(c["q"], c["docs"], llm=llm, model=MODEL)
                c[f"err{run}"] = False
                return _ok(res, golds, c["offcorpus"])
            except Exception as ex:
                print(f"    ! gen fail (intento {attempt}) q='{c['q'][:30]}': {type(ex).__name__}", flush=True)
                time.sleep(3)
        c[f"err{run}"] = True  # marcado para no contaminar el baseline (ok=False pero flag)
        return False

    runs = []
    for run in range(1, RUNS + 1):
        agg = {}
        print(f"=== GEN run {run}/{RUNS} con {MODEL} ===", flush=True)
        t0 = time.time()
        for j, c in enumerate(cache):
            c[f"ok{run}"] = _gen_ok(c, run)
            agg.setdefault(c["cat"], {"n": 0, "ok": 0, "err": 0})
            agg[c["cat"]]["n"] += 1; agg[c["cat"]]["ok"] += c[f"ok{run}"]; agg[c["cat"]]["err"] += c.get(f"err{run}", False)
            if (j + 1) % 25 == 0:
                print(f"  gen {j+1}/{len(cache)} ({time.time()-t0:.0f}s)", flush=True)
                # guardado INCREMENTAL: un crash a mitad no pierde el progreso
                (OUTDIR / "result.json").write_text(
                    json.dumps({"model": MODEL, "set": setname, "runs": runs + [agg], "detail": cache},
                               ensure_ascii=False, indent=2, default=str))
        runs.append(agg)
        print(f"  run {run} en {time.time()-t0:.0f}s (errored: {sum(a['err'] for a in agg.values())})", flush=True)
        (OUTDIR / "result.json").write_text(
            json.dumps({"model": MODEL, "set": setname, "runs": runs, "detail": cache},
                       ensure_ascii=False, indent=2, default=str))

    print("\n=== BASELINE por categoría ===", flush=True)
    for run in range(1, RUNS + 1):
        parts = " | ".join(f"{cat} {a['ok']:3d}/{a['n']:3d}" for cat, a in sorted(runs[run-1].items()))
        tot_ok = sum(a["ok"] for a in runs[run-1].values()); tot_n = sum(a["n"] for a in runs[run-1].values())
        print(f"  run{run}: {parts} | TOTAL {tot_ok}/{tot_n}", flush=True)
    print("\n=== FALLAS run1 (base para McNemar) ===", flush=True)
    for c in cache:
        if not c.get("ok1"):
            g = ",".join(sorted(f"{n}/{ar}" for n, ar in {tuple(x) for x in c["golds"]})) or "(rechazo)"
            print(f"  [{c['cat']:18s}] {g:14s} | {c['q'][:50]}", flush=True)


if __name__ == "__main__":
    main()
