"""M2: def_fragments (1 def = 1 fragmento). Re-retrieva con la flag ON, solo re-genera los top-10 cambiados vs baseline E0. McNemar pareado.
Eficiente: re-retrieva 339q (rapido), y SOLO re-genera los queries cuyo top-10 CAMBIO vs
baseline E0 (+ los errored del baseline). Los no-cambiados reutilizan ok del baseline.
McNemar pareado vs baseline (retrieval fijo por-query -> pares).

Baseline: data/eval/results/e0_baseline/result.json (config pool=50).
Uso (env limpio, ver logs/run_m1.sh):
  PYTHONPATH=. BGE_DEVICE=cuda POOL=100 venv/bin/python -m scripts.exp_m2_deffrag
"""
import json, subprocess, time, os, math
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
POOL = int(os.environ.get("POOL", "100"))
BASELINE = Path("data/eval/results/e0_baseline/result.json")
OUTDIR = Path("data/eval/results/m2_gated")


def _is_refusal(t): return REFUSAL_TEXT.lower() in t.lower()

def _ok(res, golds, offcorpus):
    if offcorpus: return _is_refusal(res["text"])
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits) and not _is_refusal(res["text"])

def _ids(docs): return {d["id"] for d in docs}

def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * p)


def main():
    base = json.load(open(BASELINE))["detail"]
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    # M2: pool baseline (50), enciende def_fragments
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True; cfg.settings.def_fragments = True

    print(f"=== FASE A: re-retrieval def_fragments=ON sobre {len(base)}q, detecta cambios ===", flush=True)
    t0 = time.time(); changed = 0
    for i, c in enumerate(base):
        newdocs = retr.retrieve(c["q"], top_k=10)
        c["docs_m1"] = newdocs
        c["changed"] = (_ids(newdocs) != _ids(c["docs"])) or c.get("err1", False)
        changed += c["changed"]
        if (i + 1) % 50 == 0:
            print(f"  retr {i+1}/{len(base)} cambiados={changed} ({time.time()-t0:.0f}s)", flush=True)
    print(f"  top-10 CAMBIO en {changed}/{len(base)} queries -> solo esos re-generan", flush=True)
    
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen_ok(c):
        golds = {tuple(g) for g in c["golds"]}
        for attempt in (1, 2):
            try:
                return _ok(generate_answer(c["q"], c["docs_m1"], llm=llm, model=MODEL), golds, c["offcorpus"])
            except Exception as ex:
                print(f"    ! gen fail ({attempt}) '{c['q'][:30]}': {type(ex).__name__}", flush=True); time.sleep(3)
        c["err_m1"] = True; return False

    print(f"=== FASE B: gen SOLO los {changed} cambiados ===", flush=True)
    t0 = time.time(); done = 0
    for c in base:
        if c["changed"]:
            c["ok_m1"] = gen_ok(c); done += 1
            if done % 20 == 0:
                print(f"  gen {done}/{changed} ({time.time()-t0:.0f}s)", flush=True)
                (OUTDIR / "result.json").write_text(json.dumps({"pool": POOL, "detail": base}, ensure_ascii=False, default=str))
        else:
            c["ok_m1"] = c["ok1"]  # top-10 identico -> reutiliza baseline
    (OUTDIR / "result.json").write_text(json.dumps({"pool": POOL, "detail": base}, ensure_ascii=False, default=str))

    # ==== reporte por categoria + McNemar ====
    print("\n=== M2 (def_fragments) vs BASELINE ===", flush=True)
    cats = {}
    for c in base:
        a = cats.setdefault(c["cat"], {"n": 0, "base": 0, "m1": 0, "b": 0, "cc": 0})
        a["n"] += 1; a["base"] += c["ok1"]; a["m1"] += c["ok_m1"]
        if c["ok1"] and not c["ok_m1"]: a["b"] += 1      # perdio
        if not c["ok1"] and c["ok_m1"]: a["cc"] += 1     # gano
    tb = tc = 0
    for cat, a in sorted(cats.items()):
        print(f"  {cat:18s} base {a['base']:3d}/{a['n']:3d} -> M1 {a['m1']:3d}/{a['n']:3d}  (gano {a['cc']}, perdio {a['b']})", flush=True)
        tb += a["b"]; tc += a["cc"]
    p = _mcnemar_p(tb, tc)
    print(f"\n  TOTAL flips: gano {tc}, perdio {tb}  -> McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p<0.05 else 'RUIDO (no adoptar)'})", flush=True)
    print("\n=== queries que GANARON (base fail -> M1 ok) ===", flush=True)
    for c in base:
        if not c["ok1"] and c["ok_m1"]:
            g = ",".join(sorted(f"{n}/{ar}" for n, ar in {tuple(x) for x in c['golds']})) or "(rechazo)"
            print(f"  [{c['cat']:16s}] {g:14s} | {c['q'][:44]}", flush=True)


if __name__ == "__main__":
    main()
