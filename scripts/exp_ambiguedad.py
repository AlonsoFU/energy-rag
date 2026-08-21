"""D4 — `ambiguity_disclose` PAREADO: ¿declara la ambigüedad o afirma una acepción?

35 términos del glosario están definidos en MÁS DE UNA norma. Hoy `def_exact` elige una con
`ORDER BY length(texto) DESC` — criterio arbitrario — y el sistema **afirma esa acepción sin
avisar que hay otras**. Medido en `qué es la comisión` y `qué significa coordinado`: la
respuesta era correcta pero incompleta, y en materia legal eso puede inducir a error.

`cita_ok` NO sirve como métrica acá: con `also_gold` cualquier acepción cuenta como acierto,
así que da 100% en los dos brazos (exp #45 lo midió: los 4 criterios de desempate empatan).
Se mide otra cosa:

  declara      la respuesta cita >=2 de las normas que definen el término
  cobertura    fracción de las normas definitorias que aparecen citadas
  cita_ok      se sigue reportando para verificar que no se rompe nada

  PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_ambiguedad
"""
import json, math, os, time
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.core import config as cfg

MODEL = "ollama/qwen3:30b-a3b"
SET = Path(os.environ.get("SET", "data/eval/queries_ambiguos_v1.jsonl"))
NAME = os.environ.get("NAME", "ambiguedad")
OUTDIR = Path(f"data/eval/results/{NAME}")


def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def main():
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rp = OUTDIR / "result.json"
    prev = {}
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("on") and c.get("off"): prev[c["query"]] = c
            print(f"[RESUME] {len(prev)} pares ya hechos", flush=True)
        except Exception: pass

    llm = get_llm_provider()
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
    cfg.settings.glossary_lookup = True; cfg.settings.intent_gate = True
    cfg.settings.embed_4b_cpu = True
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    def arm(q, val):
        cfg.settings.ambiguity_disclose = val
        esperadas = {str(x) for x in q["_normas"]}
        for _ in (1, 2, 3):
            try:
                t0 = time.time()
                docs = retr.retrieve(q["query"], top_k=10)
                txt = generate_answer(q["query"], docs, llm=llm, model=MODEL)["text"]
                citadas = {str(n) for n, _a in extract_citations(txt)}
                aciertan = citadas & esperadas
                return {"declara": len(aciertan) >= 2,
                        "cobertura": len(aciertan) / max(1, len(esperadas)),
                        "n_normas_citadas": len(aciertan),
                        "cita_ok": bool(aciertan),
                        "inyectadas": sum(1 for d in docs if d.get("_ambiguo")),
                        "secs": round(time.time() - t0, 1), "text": txt}, False
            except Exception as ex:
                print(f"    ! fail {q['query'][:26]} {type(ex).__name__}: {ex}", flush=True)
                time.sleep(3)
        return {"declara": False, "cobertura": 0.0, "n_normas_citadas": 0, "cita_ok": False,
                "inyectadas": 0, "secs": 0.0, "text": ""}, True

    print(f"=== {NAME}: {len(rows)} pares  OFF(una acepcion) / ON(declara ambiguedad) ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            q.update({k: prev[q["query"]][k] for k in ("off", "on", "err")}); continue
        o, e1 = arm(q, False)
        n_, e2 = arm(q, True)
        q["off"], q["on"], q["err"] = o, n_, e1 or e2
        nq += 1
        rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
        if nq % 5 == 0: print(f"  pares nuevos={nq} [{i+1}/{len(rows)}]", flush=True)
    rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
    cfg.settings.ambiguity_disclose = False

    v = [q for q in rows if not q.get("err") and q.get("off")]
    n = len(v)
    won = sum(1 for q in v if not q["off"]["declara"] and q["on"]["declara"])
    lost = sum(1 for q in v if q["off"]["declara"] and not q["on"]["declara"])
    print(f"\n=== {NAME} — {n} pares ===", flush=True)
    print(f"  DECLARA ambiguedad  OFF {sum(q['off']['declara'] for q in v)}/{n}  ->  "
          f"ON {sum(q['on']['declara'] for q in v)}/{n}   [gano {won}, perdio {lost}]  "
          f"McNemar p={_mcnemar_p(lost, won):.4f}", flush=True)
    print(f"  cita_ok (no romper) OFF {sum(q['off']['cita_ok'] for q in v)}/{n}  ->  "
          f"ON {sum(q['on']['cita_ok'] for q in v)}/{n}", flush=True)
    for k, lb in (("cobertura", "cobertura normas"), ("n_normas_citadas", "normas citadas"),
                  ("inyectadas", "docs inyectados"), ("secs", "segundos")):
        a = sum(q["off"][k] for q in v) / n; b = sum(q["on"][k] for q in v) / n
        print(f"  {lb:17} OFF {a:6.2f}  ->  ON {b:6.2f}", flush=True)
    for q in v:
        if not q["off"]["declara"] and q["on"]["declara"]:
            print(f"  GANO:   ({q['_n_normas']} normas) {q['query'][:54]}", flush=True)
    for q in v:
        if q["off"]["declara"] and not q["on"]["declara"]:
            print(f"  PERDIO: ({q['_n_normas']} normas) {q['query'][:54]}", flush=True)


if __name__ == "__main__":
    main()
