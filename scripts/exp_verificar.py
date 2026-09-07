"""exp #72 -- VERIFICAR-Y-FILTRAR sobre respuestas GUARDADAS (post-hoc, sin regenerar).

Estandar (CoVe / "verify then edit"): cada frase con cita se juzga contra el texto real del
articulo citado; la que no esta SOPORTADA se borra. Si no queda ninguna, la respuesta pasa a
ser el rechazo. Corre sobre el result.json de una corrida (brazo `on`) y escribe otra corrida
con  off = original,  on = filtrada,  asi que `resumen`/`comparar_corridas` sirven igual.

CIRCULARIDAD (caveat escrito antes de correr): el filtro usa el MISMO juez que mide fidelidad
en #68. Medir fidelidad del resultado con ese juez es trivial (sube por construccion). Por eso
el criterio de #72 NO usa fidelidad del mismo juez, sino:
  - cita_ok / cita_limpia recalculados sobre el texto filtrado (si borra la frase con el gold,
    cita_ok cae: senal independiente)
  - cobertura = frases conservadas / frases con cita (si borra la mitad, no sirve)
  - fidelidad con el juez DISTINTO (#73b, qwen3.6:27b) sobre lo que queda
Calibracion #73 (docs/calibracion-juez-68.md): el juez 30b marca PARCIAL ~la mitad de las
veces en frases que si estan soportadas -> este filtro puede borrar de mas. MODO=laxo conserva
tambien PARCIAL (borra solo NO_SOPORTADA y CITA_INEXISTENTE).

Uso:
  env PYTHONPATH=. RES=data/eval/results/limpio_dev/result.json SET=data/eval/queries_operativas_v1.jsonl \
      NAME=verificar_dev MODO=estricto venv/bin/python -m scripts.exp_verificar
Env: RES, SET, NAME, MODO (estricto|laxo), THINK, JUEZ, LIMIT. Resumible.
"""
import json, os, time
from pathlib import Path

os.environ.setdefault("RES", "")
from scripts.exp_fidelidad import frases_con_cita, texto_articulo, juzgar, JUEZ, THINK
from scripts.exp_think_paired import golds, es_offcorpus, resumen
from scripts.eval_metrics import score_answer
from src.pipelines.grounding import extract_citations
from src.pipelines.off_topic import REFUSAL_TEXT
from src.components.llm import get_llm_provider
from src.storage.connection import with_connection
from src.core import config as cfg
import scripts.exp_think_paired as _tp

RES = os.environ["RES"]
SET = Path(os.environ["SET"])
NAME = os.environ.get("NAME", "verificar")
MODO = os.environ.get("MODO", "estricto")
LIMIT = int(os.environ.get("LIMIT", "0") or 0)
OUTDIR = Path(f"data/eval/results/{NAME}"); OUTDIR.mkdir(parents=True, exist_ok=True)
RP = OUTDIR / "result.json"
_tp.NAME, _tp.VAR = NAME, f"verificar:{MODO}"


def filtrar(cur, llm, text):
    """Devuelve (texto_filtrado, conservadas, total)."""
    keep, tot, kept = [], 0, 0
    for linea in text.split("\n"):
        frs = frases_con_cita(linea)
        if not frs:
            keep.append(linea); continue
        nuevas = []
        for fr in frs:
            tot += 1
            textos = [t for t in (texto_articulo(cur, n, a) for n, a in extract_citations(fr)) if t]
            v = juzgar(llm, fr, textos) if textos else "CITA_INEXISTENTE"
            ok = v == "SOPORTADA" or (MODO == "laxo" and v == "PARCIAL")
            if ok:
                nuevas.append(fr); kept += 1
        if nuevas:
            keep.append(" ".join(nuevas))
    out = "\n".join(l for l in keep if l.strip())
    if kept == 0 and tot > 0:
        out = REFUSAL_TEXT
    return out, kept, tot


def main():
    cfg.settings.ollama_think = THINK
    if JUEZ:
        cfg.settings.llm_default = JUEZ
    llm = get_llm_provider()
    src = {r["query"]: r for r in json.load(open(RES))["detail"]}
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    if LIMIT:
        rows = rows[:LIMIT]
    prev = {r["query"]: r for r in json.load(open(RP))["detail"]} if RP.exists() else {}
    print(f"=== {NAME}: {len(rows)} queries  RES={RES} MODO={MODO} juez={JUEZ or cfg.settings.llm_default} think={THINK}", flush=True)
    t0 = time.time(); n = 0
    with with_connection() as conn:
        cur = conn.cursor()
        for i, q in enumerate(rows):
            if q["query"] in prev:
                q.update({k: prev[q["query"]][k] for k in ("off", "on", "err")}); continue
            o = src.get(q["query"], {}).get("on")
            if not o:
                q["off"] = q["on"] = None; q["err"] = True; continue
            txt, kept, tot = filtrar(cur, llm, o.get("text") or "")
            s = score_answer(txt, golds(q))
            if es_offcorpus(q):
                s["cita_ok"] = bool(s.get("refuso")); s["cita_limpia"] = s["cita_ok"]
            s.update(secs=0.0, text=txt, conservadas=kept, frases=tot)
            q["off"], q["on"], q["err"] = dict(o), s, False
            n += 1
            RP.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            if n % 10 == 0:
                print(f"  {i+1}/{len(rows)}  {time.time()-t0:.0f}s", flush=True)
    RP.write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
    valid = [q for q in rows if not q.get("err")]
    k = sum(q["on"]["conservadas"] for q in valid); t = sum(q["on"]["frases"] for q in valid) or 1
    print(f"\n  cobertura: {k}/{t} frases conservadas ({100*k//t} %)  "
          f"rechazos nuevos: {sum(1 for q in valid if q['on']['refuso'] and not q['off']['refuso'])}", flush=True)
    resumen(rows)


if __name__ == "__main__":
    main()
