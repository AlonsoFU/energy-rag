"""exp #82 -- ¿un juez detecta la cita REAL pero del articulo EQUIVOCADO?

quote-only verifica que la cita EXISTE (substring exacto), no que RESPONDE la pregunta. dev: 29
de 103 respuestas con cita apuntan a un articulo que no es el gold, con formato perfecto.
Esto mide, sobre respuestas YA guardadas (no genera nada), si un juez local separa ambas clases.
Las etiquetas del eval hacen de control: cita_ok=True debe salir RESPONDE, cita_ok=False no.

CRITERIO FIJADO ANTES (plan v35), sobre respuestas con >= 1 cita y sin rechazo:
  detecta >= 50 % de las equivocadas (dev)  Y  falsa alarma <= 10 % de las correctas (dev Y held-out)
  -> vale la pena llevarlo al pipeline como AVISO (no rechazo) y medirlo completo.
  Si no -> descartado; no se toca el pipeline.
CAVEATS: juez == generador (qwen3 local), circular; el gold es del asistente, y un cita_ok=False
puede responder de verdad (articulo alternativo valido) -> la deteccion medida es un piso ruidoso.

Uso: env PYTHONPATH=. RES=data/eval/results/repet0_a/result.json NAME=juez_resp_dev \
         venv/bin/python -m scripts.experimentos.exp_juez_responde
"""
import json, os, time
from pathlib import Path

RES = os.environ["RES"]                       # exp_fidelidad tambien lo lee al importarse
NAME = os.environ.get("NAME", "juez_resp")
from scripts.experimentos.exp_fidelidad import texto_articulo   # noqa: E402  (misma eleccion de fila, v2.2)
from src.components.llm import get_llm_provider    # noqa: E402
from src.pipelines.generate import REFUSAL_TEXT    # noqa: E402
from src.pipelines.grounding import extract_citations, _normalize_art  # noqa: E402
from src.storage.connection import with_connection  # noqa: E402
from src.core import config as cfg                 # noqa: E402

SYS = (
    "Eres un revisor juridico. Te dan una PREGUNTA y el TEXTO de los articulos que una respuesta "
    "cito. Decide si esos articulos contienen lo necesario para responder ESA pregunta. "
    "RESPONDE = el texto trata el asunto preguntado y permite contestarlo. "
    "NO_RESPONDE = el texto trata otro asunto, otro sujeto u otro procedimiento, aunque comparta "
    "palabras con la pregunta. Ignora notas de modificacion (Decreto N, D.O. fecha). "
    "Responde SOLO una palabra: RESPONDE o NO_RESPONDE."
)


def juzgar(llm, pregunta, textos):
    ctx = "\n\n".join(f"[ARTICULO {i+1}]\n{t[:6000]}" for i, t in enumerate(textos))
    r = llm.generate(f"PREGUNTA:\n{pregunta}\n\nTEXTO:\n{ctx}\n\nVeredicto (una palabra):",
                     system=SYS, temperature=0.0, max_tokens=20).text.strip().upper().replace(" ", "_")
    return "NO_RESPONDE" if "NO_RESPONDE" in r else "RESPONDE" if "RESPONDE" in r else "ILEGIBLE:" + r[:40]


def main():
    cfg.settings.ollama_think = True
    llm = get_llm_provider()
    out = Path(f"data/eval/results/{NAME}.json")
    hechas = {r["query"]: r for r in json.load(open(out))} if out.exists() else {}
    rows, t0 = [], time.time()
    with with_connection() as conn:
        cur = conn.cursor()
        for rec in json.load(open(RES))["detail"]:
            on = rec["on"]
            txt = on.get("text") or ""
            cits = extract_citations(txt)
            if not cits or REFUSAL_TEXT.lower() in txt.lower() or not rec.get("expected_articulo"):
                continue
            if rec["query"] in hechas:
                rows.append(hechas[rec["query"]]); continue
            textos = [t for nid, art in dict.fromkeys(cits)
                      if (t := texto_articulo(cur, str(nid), _normalize_art(str(art))))]
            if not textos:
                continue
            rows.append({"query": rec["query"], "category": rec["category"], "cita_ok": bool(on["cita_ok"]),
                         "veredicto": juzgar(llm, rec["query"], textos)})
            json.dump(rows, open(out, "w"), ensure_ascii=False, indent=1)
            print(f"{len(rows):3d} {time.time()-t0:6.0f}s ok={rows[-1]['cita_ok']!s:5} {rows[-1]['veredicto']}", flush=True)
    bien = [r for r in rows if r["cita_ok"]]; mal = [r for r in rows if not r["cita_ok"]]
    det = sum(r["veredicto"] == "NO_RESPONDE" for r in mal); fa = sum(r["veredicto"] == "NO_RESPONDE" for r in bien)
    ileg = sum(r["veredicto"].startswith("ILEGIBLE") for r in rows)
    print(f"\n{NAME}: equivocadas detectadas {det}/{len(mal)}   falsa alarma {fa}/{len(bien)}   ilegibles {ileg}")


if __name__ == "__main__":
    main()
