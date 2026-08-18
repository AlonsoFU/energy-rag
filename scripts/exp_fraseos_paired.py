"""B1.2 - Cuanto del 98.9% sobrevive a fraseos que el regex NO cubre.

PAREADO POR TERMINO, ambos brazos en la MISMA sesion (regla #4):
  brazo CONTROL   "qué es <T>"        <- fraseo cubierto por _DEF_INTENT
  brazo FRASEO    fraseo natural      <- data/eval/queries_fraseos_v1.jsonl

El retrieval NO se cachea ni se comparte: la diferencia entre brazos ES el
retrieval (glossary_inject dispara o no). Se corre completo en los dos.

Registra si glossary_inject efectivamente disparo (doc con _rol=DEFINICION),
para separar "fallo el gate" de "fallo el modelo".

  PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_fraseos_paired

Env: LIMIT (recorta el set), NAME (subcarpeta de resultados).
Resumible: relee result.json y saltea pares ya hechos.
"""
import json, math, os, time
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import _normalize_art
from src.core import config as cfg
from scripts.eval_metrics import score_answer

MODEL = "ollama/qwen3:30b-a3b"
SET = Path("data/eval/queries_fraseos_v1.jsonl")
NAME = os.environ.get("NAME", "fraseos_v1")
LIMIT = int(os.environ.get("LIMIT", "0"))
OUTDIR = Path(f"data/eval/results/{NAME}")


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def main():
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    if LIMIT: rows = rows[:LIMIT]
    OUTDIR.mkdir(parents=True, exist_ok=True)

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("ctrl") and c.get("fras"):
                    prev[c["query"]] = c
            print(f"[RESUME] {len(prev)} pares ya hechos", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo: {type(ex).__name__}", flush=True)

    llm = get_llm_provider()
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)

    def arm(qtext, gs):
        """retrieval + gen + score de UN brazo. (dict, err)"""
        for _ in (1, 2, 3):
            try:
                t0 = time.time()
                docs = retr.retrieve(qtext, top_k=10)
                inject = any((d or {}).get("_rol") == "DEFINICION" for d in docs)
                txt = generate_answer(qtext, docs, llm=llm, model=MODEL)["text"]
                s = score_answer(txt, gs)
                s.update(inject=inject, secs=round(time.time() - t0, 1), text=txt)
                return s, False
            except Exception as ex:
                print(f"    ! fail '{qtext[:30]}' {type(ex).__name__}: {ex}", flush=True)
                time.sleep(3)
        return {"cita_ok": False, "cita_limpia": False, "precision": 0.0, "n_uniq": 0,
                "n_cits": 0, "refuso": False, "inject": False, "secs": 0.0, "text": ""}, True

    print(f"=== {NAME}: {len(rows)} pares (control vs fraseo) ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            q.update({k: prev[q["query"]][k] for k in ("ctrl", "fras", "err")})
            continue
        gs = golds(q)
        c, e1 = arm(q["_control_query"], gs)
        f, e2 = arm(q["query"], gs)
        q["ctrl"], q["fras"], q["err"] = c, f, e1 or e2
        nq += 1
        if nq % 1 == 0:
            rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  pares nuevos={nq}  [{i+1}/{len(rows)}]", flush=True)
    rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))

    valid = [q for q in rows if not q.get("err") and q.get("ctrl")]
    print(f"\n=== RESULTADO {NAME} — {len(valid)} pares validos ===", flush=True)

    def bloque(sub, lbl):
        if not sub: return
        co = sum(q["ctrl"]["cita_ok"] for q in sub); fo = sum(q["fras"]["cita_ok"] for q in sub)
        won = sum(1 for q in sub if not q["ctrl"]["cita_ok"] and q["fras"]["cita_ok"])
        lost = sum(1 for q in sub if q["ctrl"]["cita_ok"] and not q["fras"]["cita_ok"])
        p = _mcnemar_p(lost, won)
        n = len(sub)
        print(f"\n-- {lbl}  (n={n})", flush=True)
        print(f"  cita_ok      control {co}/{n} ({100*co/n:.1f}%)  ->  fraseo {fo}/{n} ({100*fo/n:.1f}%)"
              f"   [gano {won}, perdio {lost}]  McNemar p={p:.4f}", flush=True)
        cl = sum(bool(q["ctrl"]["cita_limpia"]) for q in sub)
        fl = sum(bool(q["fras"]["cita_limpia"]) for q in sub)
        print(f"  cita_limpia  control {cl}/{n}  ->  fraseo {fl}/{n}", flush=True)
        ci = sum(q["ctrl"]["inject"] for q in sub); fi = sum(q["fras"]["inject"] for q in sub)
        print(f"  inject disparo  control {ci}/{n}  ->  fraseo {fi}/{n}", flush=True)
        for k, lb in (("precision", "precision"), ("n_uniq", "citas unicas"), ("secs", "segundos")):
            a = sum(q["ctrl"][k] for q in sub) / n; b = sum(q["fras"][k] for q in sub) / n
            print(f"  {lb:13} control {a:6.2f}  ->  fraseo {b:6.2f}", flush=True)

    bloque(valid, "TOTAL")
    bloque([q for q in valid if q["_grupo"] == "A"], "GRUPO A — el gate NO dispara")
    bloque([q for q in valid if q["_grupo"] == "B"], "GRUPO B — gate si, extraccion del concepto rota")

    print("\n-- por plantilla (cita_ok fraseo / n)", flush=True)
    tpls = {}
    for q in valid:
        tpls.setdefault(q["_plantilla"], []).append(q)
    for t, sub in sorted(tpls.items(), key=lambda kv: sum(x["fras"]["cita_ok"] for x in kv[1]) / len(kv[1])):
        ok = sum(x["fras"]["cita_ok"] for x in sub)
        inj = sum(x["fras"]["inject"] for x in sub)
        print(f"  {ok}/{len(sub)}  inject {inj}/{len(sub)}  {t}", flush=True)

    print("\n-- PERDIDAS (control acierta, fraseo falla)", flush=True)
    for q in valid:
        if q["ctrl"]["cita_ok"] and not q["fras"]["cita_ok"]:
            print(f"  [{q['_grupo']}] {q['query'][:70]}", flush=True)


if __name__ == "__main__":
    main()
