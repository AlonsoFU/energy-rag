"""EXP #63 (grande) — `ollama_think` OFF vs ON sobre el set operativo. EL PAREADO QUE DECIDE.

Por que existe este archivo y no se reusa `exp_selfcons_n1`: encolé ese script para decidir
`think` y **togglea `self_consistency_n`, no `ollama_think`**. Corrió ~6 h y lo que devolvió
fue una repeticion del exp #54 (n=1 vs n=3), que no decide nada de esto. Este script cambia
UNA variable: `cfg.settings.ollama_think`.

Criterio FIJADO ANTES de correr (docs/plan-operacion.md, exp #63):

    adoptar think=True si   cita_ok cae <= 3   Y   cita_limpia NO cae

`cita_limpia` no puede caer porque think=True existe justamente para que el modelo deje de
rociar citas mientras delibera: si la precision no sube o se mantiene, no esta haciendo lo que
promete.

Antecedente EN CONTRA (GEN8, exp #35): think=True perdia 16 golds, casi siempre por RECHAZAR.
Se midio sobre `queries_balanced_v2_clean`, que es casi todo `rule-recall`. Este set trae 50
coloquiales + 5 multihop + 5 temporales + 5 cuantitativos, que son los tipos donde el
diagnostico chico (exp #63) vio 6/6 arreglados. La pregunta es si el saldo cierra.

El retrieval NO cambia entre brazos (la intervencion es solo de generacion), asi que se
recupera UNA vez por query y se reusa en los dos brazos: la mitad del costo, y ademas elimina
el ruido de retrieval entre brazos.

  env PYTHONPATH=. SET=data/eval/queries_operativas_v1.jsonl NAME=think_paired \
      venv/bin/python -m scripts.exp_think_paired

Env: SET, NAME, LIMIT. Resumible (releé `result.json` y saltea los pares ya hechos).
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
SET = Path(os.environ.get("SET", "data/eval/queries_operativas_v1.jsonl"))
NAME = os.environ.get("NAME", "think_paired")
# Que variable se togglea. OFF = valor bajo/apagado, ON = valor alto/prendido.
VAR = os.environ.get("VAR", "answer_think")
LIMIT = int(os.environ.get("LIMIT", "0"))
OUTDIR = Path(f"data/eval/results/{NAME}")


def es_offcorpus(q):
    """Fuera del corpus => RECHAZAR es el acierto, no un fallo.

    REGLA #2: todo scorer declara como puntua el RECHAZO antes de correrse. Aca importa el
    doble: la acusacion contra think=True es que RECHAZA de mas. Si los 4 `hold_offcorpus` se
    contaran como fallo, think saldria castigado por hacer lo correcto en ellos.

    Se decide por CATEGORIA, no por `gold=None`: los `hold_ambiguo` tambien vienen sin gold,
    pero ahi el termino SI esta en el corpus y lo esperado es PREGUNTAR, no rechazar.
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


def resumen(rows, parcial=False):
    valid = [q for q in rows if not q.get("err") and q.get("off") and q.get("on")]
    n = len(valid)
    if not n:
        print("  (sin pares validos todavia)", flush=True); return
    ok_off = sum(q["off"]["cita_ok"] for q in valid)
    ok_on = sum(q["on"]["cita_ok"] for q in valid)
    li_off = sum(bool(q["off"]["cita_limpia"]) for q in valid)
    li_on = sum(bool(q["on"]["cita_limpia"]) for q in valid)
    won = sum(1 for q in valid if not q["off"]["cita_ok"] and q["on"]["cita_ok"])
    lost = sum(1 for q in valid if q["off"]["cita_ok"] and not q["on"]["cita_ok"])
    p = _mcnemar_p(lost, won)
    tag = "PARCIAL" if parcial else "FINAL"
    print(f"\n=== {NAME} [{tag}] — {n} pares validos   VAR={VAR}  OFF=bajo / ON=alto ===", flush=True)
    print(f"  cita_ok      OFF {ok_off}/{n}  ->  ON {ok_on}/{n}   [gano {won}, perdio {lost}]  "
          f"McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    print(f"  cita_limpia  OFF {li_off}/{n}  ->  ON {li_on}/{n}", flush=True)
    print(f"  rechazos     OFF {sum(q['off']['refuso'] for q in valid)}/{n}  ->  "
          f"ON {sum(q['on']['refuso'] for q in valid)}/{n}", flush=True)
    for k, lb in (("precision", "precision"), ("n_cits", "citas totales"),
                  ("n_uniq", "citas unicas"), ("secs", "segundos")):
        a = sum(q["off"][k] for q in valid) / n; b = sum(q["on"][k] for q in valid) / n
        print(f"  {lb:14} OFF {a:6.2f}  ->  ON {b:6.2f}", flush=True)

    # Por categoria: el saldo global puede esconder que se arreglan los multihop y se rompen
    # los coloquiales, que son 50 de 114. El criterio se decide con el global, pero si el
    # veredicto queda al filo esta tabla es la que dice si vale la pena un flag por tipo.
    cats = sorted({q.get("category", "?") for q in valid})
    print("  --- por categoria (cita_ok) ---", flush=True)
    for c in cats:
        g = [q for q in valid if q.get("category") == c]
        print(f"    {c:16} {sum(q['off']['cita_ok'] for q in g):3}/{len(g):<3} -> "
              f"{sum(q['on']['cita_ok'] for q in g):3}/{len(g)}", flush=True)

    if not parcial:
        # VEREDICTO automatico contra el criterio escrito ANTES de correr. Se imprime aca para
        # que no quede a interpretacion mia despues de ver el numero.
        # El criterio depende de QUE se esta midiendo, y esta fijado en
        # docs/plan-operacion.md ANTES de correr. Si el veredicto se imprimiera siempre con la
        # regla del exp #63, una corrida de #64 diria "NO ADOPTAR" por un criterio que no es
        # el suyo -- y ya perdimos 6 h una vez por leer un log que medía otra cosa.
        #   #63 answer_think        cita_ok <= 3  Y  cita_limpia NO cae
        #   #64 self_consistency_n  cita_ok <= 3  Y  cita_limpia cae <= 2  (compra 3x de
        #       velocidad sobre el bloqueante declarado, no un punto de precision)
        # OJO: en #64 el brazo OFF es n=1, o sea ADOPTAR = quedarse con el brazo OFF.
        tope_limpia = 2 if VAR == "self_consistency_n" else 0
        cae_ok = ok_off - ok_on
        cae_limpia = li_off - li_on
        if VAR == "self_consistency_n":
            cae_ok, cae_limpia = -cae_ok, -cae_limpia   # se evalua la caida DE n=1 (OFF)
        adoptar = (cae_ok <= 3) and (cae_limpia <= tope_limpia)
        print(f"\n  CRITERIO ({VAR}): cita_ok cae <= 3  Y  cita_limpia cae <= {tope_limpia}", flush=True)
        print(f"  cita_ok cae {cae_ok}   cita_limpia cae {cae_limpia}", flush=True)
        cual = "n=1 (brazo OFF)" if VAR == "self_consistency_n" else "answer_think=True (brazo ON)"
        print(f"  => {'ADOPTAR ' + cual if adoptar else 'NO ADOPTAR ' + cual}", flush=True)
        for q in valid:
            if q["off"]["cita_ok"] and not q["on"]["cita_ok"]:
                print(f"  PERDIO: [{q.get('category','?')}] {q['query'][:62]}", flush=True)
        for q in valid:
            if not q["off"]["cita_ok"] and q["on"]["cita_ok"]:
                print(f"  GANO:   [{q.get('category','?')}] {q['query'][:62]}", flush=True)


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
    # Config ADOPTADA, identica en los dos brazos. Lo unico que se togglea es `ollama_think`.
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
    cfg.settings.glossary_lookup = True; cfg.settings.intent_gate = True
    cfg.settings.ambiguity_disclose = True; cfg.settings.filtrar_fuera_dominio = True
    cfg.settings.self_consistency_n = 3
    cfg.settings.answer_think = True
    # think_hybrid MUTA `ollama_think` por intento (GEN12). Si quedara prendido pisaria la
    # variable del experimento en el reintento y los dos brazos convergerian. Se midio y se
    # descarto (exp #36: 260->250, p=0.0063 NEGATIVO), pero se apaga explicito.
    cfg.settings.think_hybrid = False
    # embed_4b_cpu: el embedder va a CPU para NO pelear VRAM con el LLM. Medido: el 30b-a3b
    # ocupa 20.5 de 20.8 GiB, cada embed desalojaba el LLM y habia que recargar 17 GiB ->
    # 186 recargas en 3 h y el ritmo cayendo de 150 s/par a 888 s/par.
    cfg.settings.embed_4b_cpu = True
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    def arm(qtext, docs, gs, val, q_row):
        # VAR elige QUE se togglea. Existe porque el 03-09 se encolo `exp_selfcons_n1` para
        # decidir `think` y ese script togglea `self_consistency_n`: 6 h de GPU midiendo otra
        # cosa. Un solo script, la variable explicita, y el banner la imprime.
        if VAR == "self_consistency_n":
            cfg.settings.self_consistency_n = 3 if val else 1
        else:
            cfg.settings.answer_think = val
        for _ in (1, 2, 3):
            try:
                t0 = time.time()
                txt = generate_answer(qtext, docs, llm=llm, model=MODEL)["text"]
                s = score_answer(txt, gs)
                if es_offcorpus(q_row):
                    s["cita_ok"] = bool(s.get("refuso"))   # rechazar ES el acierto
                    s["cita_limpia"] = s["cita_ok"]
                s.update(secs=round(time.time() - t0, 1), text=txt)
                return s, False
            except Exception as ex:
                print(f"    ! fail '{qtext[:30]}' {VAR}={val} {type(ex).__name__}: {ex}", flush=True)
                time.sleep(3)
        return {"cita_ok": False, "cita_limpia": False, "precision": 0.0, "n_uniq": 0,
                "n_cits": 0, "refuso": False, "secs": 0.0, "text": ""}, True

    pend = [q for q in rows if q["query"] not in prev]
    print(f"=== {NAME}: {len(rows)} queries ({len(pend)} pendientes)  "
          f"togglea VAR={VAR}  OFF=bajo / ON=alto ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            q.update({k: prev[q["query"]][k] for k in ("off", "on", "err")})
            continue
        gs = golds(q)
        docs = retr.retrieve(q["query"], top_k=10)   # UNA vez, los dos brazos ven lo mismo
        o, e1 = arm(q["query"], docs, gs, False, q)
        n_, e2 = arm(q["query"], docs, gs, True, q)
        q["off"], q["on"], q["err"] = o, n_, e1 or e2
        nq += 1
        rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
        if nq % 10 == 0:
            print(f"  pares nuevos={nq}  [{i+1}/{len(rows)}]", flush=True)
            resumen(rows, parcial=True)
    rp.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
    resumen(rows)


if __name__ == "__main__":
    main()
