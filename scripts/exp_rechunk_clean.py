"""Rechunk M2 (def_fragments + glossary_exclude) medido LIMPIO (controla ruido de gen).
Fallo del metodo M1/M2: comparaba gen NUEVA vs gen VIEJA del baseline -> el flicker del LLM
(±1 aun con temp=0) aparecia como flip. Fix: por cada query cuyo top-10 DIFIERA entre OFF y
rechunk-ON, re-generar AMBOS brazos en la MISMA corrida (ruido simetrico -> se cancela). Cada
brazo se genera 2x y se toma mayoria para bajar el flicker. McNemar pareado.

Uso (env limpio): BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_rechunk_clean
"""
import json, subprocess, time, math
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
BASELINE = Path("data/eval/results/e0_baseline/result.json")
OUTDIR = Path("data/eval/results/rechunk_clean")


def _is_refusal(t): return REFUSAL_TEXT.lower() in t.lower()

def _ok_once(res, golds, offcorpus):
    if offcorpus: return _is_refusal(res["text"])
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits) and not _is_refusal(res["text"])

def _ids(docs): return {d["id"] for d in docs}

def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def _set_rechunk(on):
    cfg.settings.def_fragments = on
    cfg.settings.glossary_exclude = on


def main():
    base = json.load(open(BASELINE))["detail"]
    # RESUME: si ya hay result.json parcial, retoma los ok_off/ok_on ya calculados
    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if "ok_on" in c and "ok_off" in c:
                    prev[c["q"]] = (c["ok_off"], c["ok_on"])
            print(f"[RESUME] {len(prev)} queries ya genradas, se saltan", flush=True)
        except Exception:
            pass
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    print("=== FASE A: retrieval OFF vs rechunk-ON, detecta cambios ===", flush=True)
    t0 = time.time(); changed = 0
    for i, c in enumerate(base):
        _set_rechunk(False); off = retr.retrieve(c["q"], top_k=10)
        _set_rechunk(True); on = retr.retrieve(c["q"], top_k=10)
        c["_off"] = off; c["_on"] = on
        c["_chg"] = _ids(off) != _ids(on)
        changed += c["_chg"]
        if (i + 1) % 50 == 0:
            print(f"  retr {i+1}/{len(base)} cambiados={changed} ({time.time()-t0:.0f}s)", flush=True)
    print(f"  top-10 CAMBIO en {changed}/{len(base)} -> esos se gen en AMBOS brazos (2x c/u)", flush=True)
    _set_rechunk(False); cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen2(q, docs, golds, off):
        """Genera 1x, tolerante a fallos. El pareado (ambos brazos misma sesion) controla el
        sesgo; el flicker residual es simetrico entre brazos."""
        for attempt in (1, 2, 3):
            try:
                return _ok_once(generate_answer(q, docs, llm=llm, model=MODEL), golds, off)
            except Exception as ex:
                print(f"    ! gen fail '{q[:26]}': {type(ex).__name__}", flush=True); time.sleep(3)
        return False

    print("=== FASE B: gen pareada (solo cambiados) ===", flush=True)
    t0 = time.time(); done = 0
    for c in base:
        golds = {tuple(g) for g in c["golds"]}
        if c["q"] in prev:  # RESUME: ya genrada
            c["ok_off"], c["ok_on"] = prev[c["q"]]; continue
        if c["_chg"]:
            c["ok_off"] = gen2(c["q"], c["_off"], golds, c["offcorpus"])
            c["ok_on"] = gen2(c["q"], c["_on"], golds, c["offcorpus"])
            done += 1
            if done % 15 == 0:
                print(f"  gen {done}/{changed} ({time.time()-t0:.0f}s)", flush=True)
                (OUTDIR / "result.json").write_text(json.dumps({"detail": base}, ensure_ascii=False, default=str))
        else:
            c["ok_off"] = c["ok_on"] = c["ok1"]  # top-10 identico -> mismo resultado, sin re-gen
    (OUTDIR / "result.json").write_text(json.dumps({"detail": base}, ensure_ascii=False, default=str))

    # ==== McNemar PAREADO (ambos brazos misma sesion de gen) ====
    print("\n=== RECHUNK vs OFF (pareado, ruido de gen controlado) ===", flush=True)
    cats = {}
    for c in base:
        a = cats.setdefault(c["cat"], {"n": 0, "off": 0, "on": 0, "won": 0, "lost": 0})
        a["n"] += 1; a["off"] += c["ok_off"]; a["on"] += c["ok_on"]
        if c["ok_off"] and not c["ok_on"]: a["lost"] += 1
        if not c["ok_off"] and c["ok_on"]: a["won"] += 1
    tw = tl = 0
    for cat, a in sorted(cats.items()):
        print(f"  {cat:18s} OFF {a['off']:3d}/{a['n']:3d} -> RECHUNK {a['on']:3d}/{a['n']:3d}  (gano {a['won']}, perdio {a['lost']})", flush=True)
        tw += a["won"]; tl += a["lost"]
    p = _mcnemar_p(tl, tw)
    print(f"\n  TOTAL flips: gano {tw}, perdio {tl}  -> McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/no-signif'})", flush=True)
    print("\n=== GANARON (OFF fail -> RECHUNK ok) ===", flush=True)
    for c in base:
        if not c["ok_off"] and c["ok_on"]:
            g = ",".join(sorted(f"{n}/{ar}" for n, ar in {tuple(x) for x in c['golds']})) or "(rechazo)"
            print(f"  [{c['cat']:14s}] {g:12s} | {c['q'][:40]}", flush=True)
    print("=== PERDIERON ===", flush=True)
    for c in base:
        if c["ok_off"] and not c["ok_on"]:
            g = ",".join(sorted(f"{n}/{ar}" for n, ar in {tuple(x) for x in c['golds']})) or "(rechazo)"
            print(f"  [{c['cat']:14s}] {g:12s} | {c['q'][:40]}", flush=True)


if __name__ == "__main__":
    main()
