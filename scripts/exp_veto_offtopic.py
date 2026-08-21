"""B4 — offtopic_glossary_veto PAREADO: el diccionario vetando el gate off-topic.

OFF = hoy (concepto por regex de prefijo)   ON = concepto por diccionario del glosario.
Mismo set, misma query en ambos brazos, misma sesion. El retrieval CAMBIA entre brazos
(esa es la intervencion), asi que se corre completo en los dos — no hay cache.

  PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_lookup_paired

Env: SET (default queries_fraseos_v1.jsonl), NAME, LIMIT. Resumible.
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
SET = Path(os.environ.get("SET", "data/eval/queries_fraseos_v1.jsonl"))
NAME = os.environ.get("NAME", "veto_offtopic")
LIMIT = int(os.environ.get("LIMIT", "0"))
OUTDIR = Path(f"data/eval/results/{NAME}")


def es_offcorpus(q):
    """Fuera del corpus => RECHAZAR es el acierto, no un fallo.

    REGLA #2 del proyecto: todo scorer declara como puntua el RECHAZO antes de correrse.
    Fallada 3 veces ya. `queries_operativas_v1` trae 4 `hold_offcorpus` ("capital de
    Australia", "queque de zanahoria"...) que se contaban como fallo aunque el sistema las
    rechazara CORRECTAMENTE -> el resultado operativo salia 4 puntos bajo.

    Se decide por CATEGORIA y no por `gold=None`: los `hold_ambiguo` tambien vienen sin gold,
    pero ahi el termino SI esta en el corpus y lo esperado es PREGUNTAR, no rechazar (frente D4).
    """
    return str(q.get("category", "")).lower() == "hold_offcorpus"


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
    rows = [q for q in rows if not q.get("unanswerable")]
    if LIMIT: rows = rows[:LIMIT]
    OUTDIR.mkdir(parents=True, exist_ok=True)

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("off") and c.get("on"):
                    prev[c["query"]] = c
            print(f"[RESUME] {len(prev)} pares ya hechos", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo: {type(ex).__name__}", flush=True)

    llm = get_llm_provider()
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
    # embed_4b_cpu: el embedder va a CPU para NO pelear VRAM con el LLM.
    # Medido en gate_fraseos: el 30b-a3b ocupa 20.5 GiB de las 20.8 GiB disponibles, asi que
    # cada llamada al embedder desalojaba el LLM y habia que recargar 17 GiB. Resultado: 186
    # recargas de modelo en 3 h y el ritmo cayendo de 150 s/par a 888 s/par (5x mas lento).
    # El embed en CPU cuesta 0.3 s en caliente y devuelve el MISMO vector.
    cfg.settings.embed_4b_cpu = True
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    def arm(qtext, gs, val, q_row=None):
        # ON = lookup por diccionario + gate de intencion (los dos van juntos: el diccionario
        # sin gate contamina lo operativo, medido 20/51 en complex_v3).
        # lookup+gate quedan SIEMPRE ON (ya adoptados); lo que se togglea es el veto.
        cfg.settings.glossary_lookup = True
        cfg.settings.intent_gate = True
        cfg.settings.offtopic_glossary_veto = val
        for _ in (1, 2, 3):
            try:
                t0 = time.time()
                docs = retr.retrieve(qtext, top_k=10)
                inject = any((d or {}).get("_rol") == "DEFINICION" for d in docs)
                txt = generate_answer(qtext, docs, llm=llm, model=MODEL)["text"]
                s = score_answer(txt, gs)
                if es_offcorpus(q_row):
                    s["cita_ok"] = bool(s.get("refuso"))   # rechazar ES el acierto
                    s["cita_limpia"] = s["cita_ok"]
                s.update(inject=inject, secs=round(time.time() - t0, 1), text=txt)
                return s, False
            except Exception as ex:
                print(f"    ! fail '{qtext[:30]}' lookup={val} {type(ex).__name__}: {ex}", flush=True)
                time.sleep(3)
        return {"cita_ok": False, "cita_limpia": False, "precision": 0.0, "n_uniq": 0,
                "n_cits": 0, "refuso": False, "inject": False, "secs": 0.0, "text": ""}, True

    print(f"=== {NAME}: {len(rows)} pares  OFF(sin veto) / ON(veto del glosario) ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            q.update({k: prev[q["query"]][k] for k in ("off", "on", "err")})
            continue
        gs = golds(q)
        o, e1 = arm(q["query"], gs, False, q)
        n_, e2 = arm(q["query"], gs, True, q)
        q["off"], q["on"], q["err"] = o, n_, e1 or e2
        nq += 1
        rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
        if nq % 5 == 0:
            print(f"  pares nuevos={nq}  [{i+1}/{len(rows)}]", flush=True)
    rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
    cfg.settings.offtopic_glossary_veto = False

    valid = [q for q in rows if not q.get("err") and q.get("off")]
    n = len(valid)
    won = sum(1 for q in valid if not q["off"]["cita_ok"] and q["on"]["cita_ok"])
    lost = sum(1 for q in valid if q["off"]["cita_ok"] and not q["on"]["cita_ok"])
    p = _mcnemar_p(lost, won)
    print(f"\n=== {NAME} — {n} pares validos ===", flush=True)
    print(f"  cita_ok      OFF {sum(q['off']['cita_ok'] for q in valid)}/{n}  ->  "
          f"ON {sum(q['on']['cita_ok'] for q in valid)}/{n}   [gano {won}, perdio {lost}]  "
          f"McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    print(f"  cita_limpia  OFF {sum(bool(q['off']['cita_limpia']) for q in valid)}/{n}  ->  "
          f"ON {sum(bool(q['on']['cita_limpia']) for q in valid)}/{n}", flush=True)
    print(f"  inject       OFF {sum(q['off']['inject'] for q in valid)}/{n}  ->  "
          f"ON {sum(q['on']['inject'] for q in valid)}/{n}", flush=True)
    print(f"  rechazos     OFF {sum(q['off']['refuso'] for q in valid)}/{n}  ->  "
          f"ON {sum(q['on']['refuso'] for q in valid)}/{n}", flush=True)
    for k, lb in (("precision", "precision"), ("n_uniq", "citas unicas"), ("secs", "segundos")):
        a = sum(q["off"][k] for q in valid) / n; b = sum(q["on"][k] for q in valid) / n
        print(f"  {lb:13} OFF {a:6.2f}  ->  ON {b:6.2f}", flush=True)
    for q in valid:
        if not q["off"]["cita_ok"] and q["on"]["cita_ok"]:
            print(f"  GANO:   [{q.get('_grupo','?')}] {q['query'][:62]}", flush=True)
    for q in valid:
        if q["off"]["cita_ok"] and not q["on"]["cita_ok"]:
            print(f"  PERDIO: [{q.get('_grupo','?')}] {q['query'][:62]}", flush=True)


if __name__ == "__main__":
    main()
