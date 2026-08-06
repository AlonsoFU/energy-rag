"""M1 PAREADO: retrieval_pool_depth 50 -> 100, sobre la config VIGENTE (glossary_inject ON).

Por que un script nuevo y no exp_m1_pooldepth.py: ese compara contra el baseline en disco
data/eval/results/e0_baseline/result.json, generado con pool=50 y glossary_inject OFF. Desde
2026-08-05 glossary_inject es default ON (+16), asi que ese baseline quedo obsoleto: compararse
contra el mezclaria el efecto del pool con el del inject Y con el flicker del LLM (mismo error
que contamino M2). Aca ambos brazos se generan en LA MISMA sesion -> pares limpios.

Brazo OFF = pool 50 (config vigente). Brazo ON = pool POOL (default 100).
Ambos con glossary_inject ON, embed_4b 1024, alias_union (config adoptada).

Solo re-genera los queries cuyo top-10 CAMBIO; los identicos generan 1x y comparten resultado.
Resumible: relee result.json y saltea los pares ya hechos (clave = query).

Uso: BGE_DEVICE=cuda PYTHONPATH=. POOL=100 venv/bin/python -m scripts.exp_m1_paired
"""
import json, subprocess, time, math, os
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
SET = "data/eval/queries_balanced_v2_clean.jsonl"
OUTDIR = Path("data/eval/results/m1_paired")
POOL_OFF = 50
POOL_ON = int(os.environ.get("POOL", "100"))


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out

def _ok(res, gs):
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in gs for n, a in cits) and REFUSAL_TEXT.lower() not in res["text"].lower()

def _ids(docs): return {d["id"] for d in docs}

def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def main():
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    rows = [q for q in rows if q.get("category") == "in_domain"]
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # config VIGENTE en ambos brazos (glossary_inject ya es default ON en config.py)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    assert cfg.settings.glossary_inject, "glossary_inject deberia estar ON (config vigente)"

    retr_off = SimpleRetriever(store, e, r, top_bm25=POOL_OFF, top_vector=POOL_OFF, llm=llm)
    retr_on = SimpleRetriever(store, e, r, top_bm25=POOL_ON, top_vector=POOL_ON, llm=llm)

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("ok_on") is not None and c.get("ok_off") is not None:
                    prev[c["query"]] = (c["ok_off"], c["ok_on"])
            print(f"[RESUME] {len(prev)} pares ya generados", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo leyendo previo: {type(ex).__name__}", flush=True)

    print(f"=== FASE A: retrieval pool {POOL_OFF} vs {POOL_ON} ({len(rows)}q) ===", flush=True)
    changed = 0
    for q in rows:
        off = retr_off.retrieve(q["query"], top_k=10)
        on = retr_on.retrieve(q["query"], top_k=10)
        q["_off"] = off; q["_on"] = on; q["_chg"] = _ids(off) != _ids(on); changed += q["_chg"]
    print(f"  top-10 cambio en {changed}/{len(rows)}", flush=True)

    # libera GPU del embedder/reranker antes de la fase de generacion
    cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc
        del r, retr_off.reranker, retr_on.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen(qtext, docs, gs):
        """Devuelve (ok, err). err=True si NUNCA se pudo generar (fallo tecnico).
        OJO: antes esto devolvia False a secas y el eval contaba un timeout como
        cita_ok=False -> falso negativo. Los err se EXCLUYEN del McNemar."""
        for a in (1, 2, 3):
            try: return _ok(generate_answer(qtext, docs, llm=llm, model=MODEL), gs), False
            except Exception as ex:
                print(f"    ! fail '{qtext[:24]}' {type(ex).__name__}", flush=True); time.sleep(3)
        return False, True

    print("=== FASE B: gen pareada ===", flush=True)
    done = 0; nq = 0
    for i, q in enumerate(rows):
        gs = golds(q)
        if q["query"] in prev:
            q["ok_off"], q["ok_on"] = prev[q["query"]]
            continue
        if q["_chg"]:
            q["ok_off"], e1 = gen(q["query"], q["_off"], gs)
            q["ok_on"], e2 = gen(q["query"], q["_on"], gs)
            q["err"] = e1 or e2
            done += 1
        else:
            ok, e = gen(q["query"], q["_off"], gs)
            q["ok_off"] = q["ok_on"] = ok; q["err"] = e
        nq += 1
        if nq % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  gen nuevas={nq} (chg {done}/{changed})  [{i+1}/{len(rows)}]", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))

    errs = [q for q in rows if q.get("err")]
    valid = [q for q in rows if not q.get("err")]
    off_t = sum(q["ok_off"] for q in valid); on_t = sum(q["ok_on"] for q in valid)
    won = sum(1 for q in valid if not q["ok_off"] and q["ok_on"])
    lost = sum(1 for q in valid if q["ok_off"] and not q["ok_on"])
    p = _mcnemar_p(lost, won)
    print(f"\n=== M1 PAREADO pool {POOL_OFF} -> {POOL_ON} (balanced_v2 clean in_domain) ===", flush=True)
    if errs:
        print(f"  ⚠️ {len(errs)} queries EXCLUIDAS por fallo tecnico (no cuentan como False):", flush=True)
        for q in errs: print(f"      {q['query'][:60]}", flush=True)
    print(f"  OFF {off_t}/{len(valid)} -> ON {on_t}/{len(valid)}  (gano {won}, perdio {lost})", flush=True)
    print(f"  McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    for q in rows:
        if not q["ok_off"] and q["ok_on"]: print(f"  GANO: {q['query'][:60]}", flush=True)
    for q in rows:
        if q["ok_off"] and not q["ok_on"]: print(f"  PERDIO: {q['query'][:60]}", flush=True)


if __name__ == "__main__":
    main()
