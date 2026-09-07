"""exp #68 -- FIDELIDAD: ¿la prosa dice lo que dice el articulo que cita?

Todo el eval hasta hoy mide CUAL articulo cito (cita_ok / cita_limpia). Nunca midio si la
afirmacion se sigue del articulo. Puede citar el correcto y caracterizarlo mal (plazo, sujeto,
excepcion omitida) y contar como acierto perfecto. Esto lo mide sobre respuestas YA guardadas:
no genera nada nuevo, solo juzga.

Unidad = frase con cita. Para cada frase:
  - se busca en `articulos` el texto de cada [Art. X de Y] citado en ESA frase
  - juez local (mismo qwen3, think=True, temp 0) responde SOPORTADA / PARCIAL / NO_SOPORTADA
  - CONTROL NEG: la misma frase contra un articulo AL AZAR de la misma norma. Si el juez dice
    SOPORTADA ahi, regala. Ese % es el piso de la metrica.
  - CONTROL POS: una oracion TEXTUAL del articulo citado, juzgada contra ese articulo. Si el
    juez NO dice SOPORTADA ahi, es demasiado estricto. (Agregado tras spot-check a 30/114 en
    v1: una frase casi textual del Art. 8 de 250604 salio NO_SOPORTADA. v1 descartada.)

Salida: data/eval/results/{NAME}.json  y resumen por pantalla.
Criterio FIJADO ANTES (docs/plan-operacion.md exp #68), sobre las respuestas con cita_ok:
  fiel_estricto (todas las frases SOPORTADA) >= 90 %  -> "responder" == "buscar"
  < 80 %                                              -> solo buscador
  control_neg > 20 %  o  control_pos < 80 %            -> el juez no sirve, no se concluye nada

Uso:
  env PYTHONPATH=. RES=data/eval/results/think_real/result.json ARM=on NAME=fidelidad_dev \
      venv/bin/python -m scripts.exp_fidelidad
Env: RES, ARM (on|off), NAME, LIMIT, CONTROL (1|0), JUEZ (modelo juez, #73b). Resumible.
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
# #73b: juez DISTINTO del que redacto (rompe la circularidad juez == generador). Ej:
# JUEZ=ollama/qwen3.6:27b (denso 27B, local). Vacio = cfg.settings.llm_default.
JUEZ = os.environ.get("JUEZ", "")
# THINK=0: juez sin razonamiento. Medido 2026-09-07: qwen3.6:27b con think tarda 161 s por
# veredicto (21 h el set dev); sin think entra en horas. Los controles POS/NEG validan igual.
THINK = os.environ.get("THINK", "1") == "1"
OUT = Path(f"data/eval/results/{NAME}.json")
random.seed(7)

JUEZ_SYS = (
    "Eres un revisor juridico. Te dan una AFIRMACION y el TEXTO de uno o mas articulos. "
    "Decide si la afirmacion se sigue del texto. Reglas: SOPORTADA = lo que afirma esta en el "
    "texto; vale parafrasear, resumir u omitir detalles mientras no cambie el sentido. "
    "PARCIAL = cambia un detalle (plazo, sujeto, monto, condicion) o afirma algo que el texto "
    "no dice ademas de algo que si. NO_SOPORTADA = el texto no dice eso o dice lo contrario. "
    "El texto puede traer notas de modificacion intercaladas (Decreto N, D.O. fecha): ignoralas. "
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
    # v2.2: la LGSE (258171) tiene 2 filas por articulo: '118º' (13 chars, basura de una
    # transcripcion) y '118°' (2211 chars, el real). Con LIMIT 1 el juez leia la basura y
    # decia NO_SOPORTADA por una respuesta correcta. Se toma la fila mas larga no marcada
    # duplicado_de. 163 pares (norma, art) duplicados; 34/291 frases de dev afectadas.
    cur.execute(
        "SELECT texto FROM articulos WHERE id_norma=%s "
        "AND replace(replace(numero,'°',''),'º','')=%s "
        "AND COALESCE(NOT (metadata ? 'duplicado_de'), true) "
        "AND COALESCE(NOT (metadata ? 'fantasma'), true) "  # #69b
        "ORDER BY length(texto) DESC LIMIT 1", (norma, art))
    r = cur.fetchone()
    return r[0] if r else None


def claves_duplicadas(cur):
    cur.execute("SELECT id_norma, replace(replace(numero,'°',''),'º','') FROM articulos "
                "GROUP BY 1,2 HAVING count(*)>1")
    return set(cur.fetchall())


def articulo_azar(cur, norma, evitar):
    cur.execute(
        "SELECT replace(replace(numero,'°',''),'º',''), texto FROM articulos "
        "WHERE id_norma=%s AND length(texto) > 200 ORDER BY random() LIMIT 5", (norma,))
    for num, txt in cur.fetchall():
        if num not in evitar:
            return num, txt
    return None, None


def oracion_textual(texto):
    """Primera oracion del articulo con >= 80 chars, sin las notas de modificacion."""
    limpio = " ".join(l for l in texto.split("\n") if len(l.strip()) > 40)
    for o in re.split(r"(?<=[\.;])\s+", limpio):
        # v2.1: antes cortaba a 400 chars a mitad de oracion ("...suspension o in") y el juez
        # decia PARCIAL con razon: 8 de 75 positivos fallaban por eso. Oracion completa.
        if 80 <= len(o) <= 1500:
            return o
    return None


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
          f"juez={JUEZ or cfg.settings.llm_default} think={THINK}", flush=True)
    cfg.settings.ollama_think = THINK
    if JUEZ:
        cfg.settings.llm_default = JUEZ
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
        dup = claves_duplicadas(cur)
        n_rej = [0]
        for i, rec in enumerate(detail):
            if rec["query"] in hechas:
                h = hechas[rec["query"]]
                for f in h["frases"]:
                    # repara positivos truncados de v2.0 (len == 400 era el corte)
                    pf = f.get("control_pos_frase")
                    if pf and len(pf) == 400:
                        t = texto_articulo(cur, *f["citas"][0])
                        pos = oracion_textual(t) if t else None
                        f["control_pos_frase"] = pos
                        f["control_pos"] = juzgar(llm, pos, [t]) if pos else None
                    # v2.2: re-juzga frases cuyo articulo citado tiene fila duplicada
                    if not f.get("v22") and any(tuple(c) in dup for c in f["citas"]):
                        textos = [t for t in (texto_articulo(cur, *c) for c in f["citas"]) if t]
                        f["veredicto_v21"] = f["veredicto"]
                        f["veredicto"] = juzgar(llm, f["frase"], textos) if textos else "CITA_INEXISTENTE"
                        if textos and CONTROL:
                            pos = oracion_textual(textos[0])
                            f["control_pos_frase"] = pos
                            f["control_pos"] = juzgar(llm, pos, [textos[0]]) if pos else None
                        f["v22"] = True
                        n_rej[0] += 1
                resto = [hechas[r["query"]] for r in detail[i+1:] if r["query"] in hechas]
                OUT.write_text(json.dumps({"detail": rows + [h] + resto}, ensure_ascii=False, indent=1))
                rows.append(h); continue
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
                        pos = oracion_textual(textos[0])
                        f["control_pos_frase"] = pos
                        f["control_pos"] = juzgar(llm, pos, [textos[0]]) if pos else None
                else:
                    f["veredicto"] = "CITA_INEXISTENTE"
                row["frases"].append(f)
            rows.append(row)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps({"detail": rows}, ensure_ascii=False, indent=1))
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(detail)}  {time.time()-t0:.0f}s", flush=True)
                resumen(rows)
    if n_rej[0]:
        print(f"  v2.2: re-juzgadas {n_rej[0]} frases con articulo duplicado", flush=True)
    resumen(rows, final=True)


def resumen(rows, final=False):
    def agg(sub):
        fr = [f for r in sub for f in r["frases"]]
        v = [f["veredicto"] for f in fr]
        c = [f.get("control") for f in fr if f.get("control")]
        cp = [f.get("control_pos") for f in fr if f.get("control_pos")]
        n = len(v) or 1
        estricto = sum(1 for r in sub
                       if r["frases"] and all(f["veredicto"] == "SOPORTADA" for f in r["frases"]))
        return dict(resp=len(sub), frases=len(v),
                    sop=round(100*v.count("SOPORTADA")/n), par=round(100*v.count("PARCIAL")/n),
                    no=round(100*v.count("NO_SOPORTADA")/n),
                    inex=v.count("CITA_INEXISTENTE"),
                    fiel_estricto=round(100*estricto/(len(sub) or 1)),
                    control_neg=round(100*c.count("SOPORTADA")/(len(c) or 1)),
                    control_pos=round(100*cp.count("SOPORTADA")/(len(cp) or 1)))
    con = [r for r in rows if r["frases"]]
    ok = [r for r in con if r["cita_ok"]]
    print("  cita_ok  ", agg(ok))
    print("  todas    ", agg(con))
    if final:
        a = agg(ok)
        print("\nVEREDICTO (criterio exp #68, sobre cita_ok):")
        if a["control_neg"] > 20 or a["control_pos"] < 80:
            print(f"  JUEZ NO SIRVE: control_neg={a['control_neg']}% (tope 20) "
                  f"control_pos={a['control_pos']}% (piso 80). No se concluye.")
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
