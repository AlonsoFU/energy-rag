"""exp #68 -- FIDELIDAD: ¿la prosa dice lo que dice el articulo que cita?

Todo el eval hasta hoy mide CUAL articulo cito (cita_ok / cita_limpia). Nunca midio si la
afirmacion se sigue del articulo. Puede citar el correcto y caracterizarlo mal (plazo, sujeto,
excepcion omitida) y contar como acierto perfecto. Esto lo mide sobre respuestas YA guardadas:
no genera nada nuevo, solo juzga.

Unidad = frase con cita. Para cada frase:
  - se busca en `articulos` el texto de cada [Art. X de Y] citado en ESA frase
  - juez local (mismo qwen3, think=True, temp 0) responde SOPORTADA / PARCIAL / NO_SOPORTADA
  - CONTROL: la misma frase contra un articulo AL AZAR de la misma norma. Si el juez dice
    SOPORTADA ahi, es sesgo del juez, no fidelidad. Ese % es el piso de la metrica.

Salida: data/eval/results/{NAME}.json  y resumen por pantalla.
Criterio FIJADO ANTES (docs/plan-operacion.md exp #68), sobre las respuestas con cita_ok:
  fiel_estricto (todas las frases SOPORTADA) >= 90 %  -> "responder" == "buscar"
  < 80 %                                              -> solo buscador
  piso de control > 20 %                              -> el juez no sirve, no se concluye nada

Uso:
  env PYTHONPATH=. RES=data/eval/results/think_real/result.json ARM=on NAME=fidelidad_dev \
      venv/bin/python -m scripts.exp_fidelidad
Env: RES, ARM (on|off), NAME, LIMIT, CONTROL (1|0). Resumible.
"""
import json, os, random, re, time
from pathlib import Path
from src.components.llm import get_llm_provider
from src.pipelines.grounding import extract_citations, CITATION_PATTERN
from src.storage.connection import with_connection
from src.core import config as cfg

RES = os.environ["RES"]
ARM = os.environ.get("ARM", "on")
NAME = os.environ.get("NAME", "fidelidad")
LIMIT = int(os.environ.get("LIMIT", "0") or 0)
CONTROL = os.environ.get("CONTROL", "1") == "1"
OUT = Path(f"data/eval/results/{NAME}.json")
random.seed(7)

JUEZ_SYS = (
    "Eres un revisor juridico. Te dan una AFIRMACION y el TEXTO de uno o mas articulos. "
    "Decide si la afirmacion se sigue del texto. Reglas: SOPORTADA = todo lo que afirma esta "
    "en el texto (parafrasis vale). PARCIAL = una parte esta y otra no, o cambia un detalle "
    "(plazo, sujeto, monto, condicion). NO_SOPORTADA = el texto no dice eso o dice lo contrario. "
    "Responde SOLO una palabra: SOPORTADA, PARCIAL o NO_SOPORTADA."
)


def frases_con_cita(text):
    """Frases (lineas o puntos) que contienen al menos una cita."""
    out = []
    for linea in re.split(r"\n+", text):
        for fr in re.split(r"(?<=[\.\]])\s+(?=[A-ZÁÉÍÓÚ¿])", linea.strip()):
            if CITATION_PATTERN.search(fr):
                out.append(fr.strip())
    return out


def texto_articulo(cur, norma, art):
    cur.execute(
        "SELECT texto FROM articulos WHERE id_norma=%s "
        "AND replace(replace(numero,'°',''),'º','')=%s LIMIT 1", (norma, art))
    r = cur.fetchone()
    return r[0] if r else None


def articulo_azar(cur, norma, evitar):
    cur.execute(
        "SELECT replace(replace(numero,'°',''),'º',''), texto FROM articulos "
        "WHERE id_norma=%s AND length(texto) > 200 ORDER BY random() LIMIT 5", (norma,))
    for num, txt in cur.fetchall():
        if num not in evitar:
            return num, txt
    return None, None


def juzgar(llm, frase, textos):
    ctx = "\n\n".join(f"[ARTICULO {i+1}]\n{t[:6000]}" for i, t in enumerate(textos))
    p = f"AFIRMACION:\n{frase}\n\nTEXTO:\n{ctx}\n\nVeredicto (una palabra):"
    r = llm.generate(p, system=JUEZ_SYS, temperature=0.0, max_tokens=20).text
    r = r.strip().upper()
    for v in ("NO_SOPORTADA", "PARCIAL", "SOPORTADA"):
        if v in r.replace(" ", "_"):
            return v
    return "ILEGIBLE:" + r[:40]


def main():
    print(f"exp_fidelidad  RES={RES} ARM={ARM} NAME={NAME} CONTROL={CONTROL}  "
          f"juez={cfg.settings.llm_default} think=True", flush=True)
    cfg.settings.ollama_think = True
    llm = get_llm_provider()
    detail = json.load(open(RES))["detail"]
    if LIMIT:
        detail = detail[:LIMIT]
    hechas = {}
    if OUT.exists():
        hechas = {r["query"]: r for r in json.load(open(OUT))["detail"]}
    rows = []
    t0 = time.time()
    with with_connection() as conn:
        cur = conn.cursor()
        for i, rec in enumerate(detail):
            if rec["query"] in hechas:
                rows.append(hechas[rec["query"]]); continue
            arm = rec.get(ARM) or {}
            text = arm.get("text") or ""
            row = {"query": rec["query"], "category": rec["category"],
                   "cita_ok": bool(arm.get("cita_ok")), "refuso": bool(arm.get("refuso")),
                   "frases": []}
            for fr in frases_con_cita(text):
                cits = extract_citations(fr)
                textos, faltan = [], []
                for norma, art in cits:
                    t = texto_articulo(cur, norma, art)
                    (textos if t else faltan).append(t or f"{art} de {norma}")
                f = {"frase": fr, "citas": cits, "inexistentes": faltan}
                if textos:
                    f["veredicto"] = juzgar(llm, fr, textos)
                    if CONTROL:
                        n0, a0 = cits[0]
                        num, txt = articulo_azar(cur, n0, {a for _, a in cits})
                        f["control_art"] = num
                        f["control"] = juzgar(llm, fr, [txt]) if txt else None
                else:
                    f["veredicto"] = "CITA_INEXISTENTE"
                row["frases"].append(f)
            rows.append(row)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps({"detail": rows}, ensure_ascii=False, indent=1))
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(detail)}  {time.time()-t0:.0f}s", flush=True)
                resumen(rows)
    resumen(rows, final=True)


def resumen(rows, final=False):
    def agg(sub):
        fr = [f for r in sub for f in r["frases"]]
        v = [f["veredicto"] for f in fr]
        c = [f.get("control") for f in fr if f.get("control")]
        n = len(v) or 1
        estricto = sum(all(f["veredicto"] == "SOPORTADA" for f in r["frases"]) and r["frases"]
                       for r in sub)
        return dict(resp=len(sub), frases=len(v),
                    sop=round(100*v.count("SOPORTADA")/n), par=round(100*v.count("PARCIAL")/n),
                    no=round(100*v.count("NO_SOPORTADA")/n),
                    inex=v.count("CITA_INEXISTENTE"),
                    fiel_estricto=round(100*estricto/(len(sub) or 1)),
                    control_sop=round(100*c.count("SOPORTADA")/(len(c) or 1)))
    con = [r for r in rows if r["frases"]]
    ok = [r for r in con if r["cita_ok"]]
    print("  cita_ok  ", agg(ok))
    print("  todas    ", agg(con))
    if final:
        a = agg(ok)
        print("\nVEREDICTO (criterio exp #68, sobre cita_ok):")
        if a["control_sop"] > 20:
            print(f"  JUEZ NO SIRVE: control_sop={a['control_sop']}% > 20. No se concluye.")
        elif a["fiel_estricto"] >= 90:
            print(f"  fiel_estricto={a['fiel_estricto']}% >= 90 -> responder == buscar")
        elif a["fiel_estricto"] < 80:
            print(f"  fiel_estricto={a['fiel_estricto']}% < 80 -> SOLO BUSCADOR")
        else:
            print(f"  fiel_estricto={a['fiel_estricto']}% zona gris 80-90")
        print("  por categoria (fiel_estricto %):")
        for c in sorted({r["category"] for r in ok}):
            print(f"    {c:16s}", agg([r for r in ok if r["category"] == c])["fiel_estricto"])


if __name__ == "__main__":
    main()
