"""glossary_inject (inyeccion determinista termino-glosario) sobre balanced_v2 clean.
Hipotesis: dev es glosario PURO (sin articulos funcionales compitiendo como Coordinador) ->
def_fragments podria CONVERTIR aca aunque en balanced_v2 (mixto) fue flat. El gap dev es GEN
(258171/225 ya entra al top-10 pero el LLM no lo cita en el glosario gigante) -> la definicion
focalizada podria ayudar a citar. Pareado (ambos brazos misma sesion), McNemar. Resumible.

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_deffrag_dev
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
SET = "data/eval/queries_balanced_v2_clean.jsonl"
OUTDIR = Path("data/eval/results/glossary_inject")


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

def _set(on):
    cfg.settings.glossary_inject = on


def main():
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    rows = [q for q in rows if q.get('category')=='in_domain']
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("ok_on") is not None and c.get("ok_off") is not None:
                    prev[c["query"]] = (c["ok_off"], c["ok_on"])
            print(f"[RESUME] {len(prev)} ya genradas", flush=True)
        except Exception: pass

    print(f"=== FASE A: retrieval OFF vs ON ({len(rows)}q) ===", flush=True)
    changed = 0
    for q in rows:
        _set(False); off = retr.retrieve(q["query"], top_k=10)
        _set(True); on = retr.retrieve(q["query"], top_k=10)
        q["_off"] = off; q["_on"] = on; q["_chg"] = _ids(off) != _ids(on); changed += q["_chg"]
    print(f"  top-10 cambio en {changed}/{len(rows)}", flush=True)
    _set(False); cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen(qtext, docs, gs):
        for a in (1, 2, 3):
            try: return _ok(generate_answer(qtext, docs, llm=llm, model=MODEL), gs)
            except Exception as ex:
                print(f"    ! fail '{qtext[:24]}' {type(ex).__name__}", flush=True); time.sleep(3)
        return False

    print("=== FASE B: gen pareada (cambiados) ===", flush=True)
    done = 0; nq = 0
    for i, q in enumerate(rows):
        gs = golds(q)
        if q["query"] in prev:
            q["ok_off"], q["ok_on"] = prev[q["query"]]
            continue
        if q["_chg"]:
            q["ok_off"] = gen(q["query"], q["_off"], gs); q["ok_on"] = gen(q["query"], q["_on"], gs); done += 1
        else:
            # top-10 identico -> gen 1x (mismo resultado ambos)
            ok = gen(q["query"], q["_off"], gs); q["ok_off"] = q["ok_on"] = ok
        nq += 1
        if nq % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  gen nuevas={nq} (chg {done}/{changed})  [{i+1}/{len(rows)}]", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))

    off_t = sum(q["ok_off"] for q in rows); on_t = sum(q["ok_on"] for q in rows)
    won = sum(1 for q in rows if not q["ok_off"] and q["ok_on"])
    lost = sum(1 for q in rows if q["ok_off"] and not q["ok_on"])
    print(f"\n=== GLOSSARY_INJECT en balanced_v2 clean ===", flush=True)
    print(f"  OFF {off_t}/{len(rows)} -> ON {on_t}/{len(rows)}  (gano {won}, perdio {lost})", flush=True)
    print(f"  McNemar p={_mcnemar_p(lost, won):.4f}  ({'SIGNIFICATIVO' if _mcnemar_p(lost,won)<0.05 else 'ruido/flat'})", flush=True)
    for q in rows:
        if not q["ok_off"] and q["ok_on"]: print(f"  GANO: {q['query'][:50]}", flush=True)
    for q in rows:
        if q["ok_off"] and not q["ok_on"]: print(f"  PERDIO: {q['query'][:50]}", flush=True)


if __name__ == "__main__":
    main()
