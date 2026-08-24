"""Qué normativa usa REALMENTE el sector, según sus propias discrepancias ante el Panel.

Dos problemas que ataca a la vez, y por eso vale la pena:

1. **Descubrimiento** (frente bloqueado: 10 vías probadas, los sitios bloquean). En vez de
   preguntarle a un buscador qué normas existen, se mira qué normas **cita la gente que está
   litigando**. Una norma que aparece en una discrepancia real es normativa viva del sector,
   no un resultado de búsqueda. Primera medición: de 3 normas citadas en la discrepancia de
   Betel, sólo el DFL 4 estaba en el corpus — faltaban el DS 88 y el DS 44.

2. **Preguntas reales con gold** (FASE 3.2). Los sets de evaluación los escribí yo mirando el
   corpus, y eso ya falló una vez. Una discrepancia trae las dos mitades juntas: el
   planteamiento en lenguaje del sector, y **el artículo exacto en que se apoya**, citado por
   el abogado que lo redactó. El gold no lo invento yo.

Sobre el regex (regla del proyecto): igual que en `resolver_citas_normas`, acá **propone**
candidatos y **el catálogo dispone** — una cita cuenta como resuelta sólo si (tipo, número)
existe en la DB. No hay lista de normas escrita a mano.

  PYTHONPATH=. venv/bin/python -m scripts.extraer_de_discrepancias
"""
import collections
import re
import subprocess
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

FUENTE = Path("data/discrepancias")
SALIDA = Path("docs/normativa-usada-en-discrepancias.md")

# "articulo 124 del Decreto Supremo N°88" / "articulo 208 ... Decreto con Fuerza de Ley N°4"
CITA = re.compile(
    r"art[íi]culos?\s+(?P<art>\d{1,3}[°ºª]?(?:\s*(?:bis|ter|quater))?)"
    r"(?P<medio>.{0,120}?)"
    r"(?P<tipo>ley|decreto\s+supremo|decreto\s+con\s+fuerza\s+de\s+ley|decreto\s+ley|decreto|"
    r"resoluci[oó]n\s+exenta|resoluci[oó]n)\s*(?:n[°ºo]\.?\s*)?(?P<num>[\d\.]{1,9})",
    re.IGNORECASE | re.DOTALL)
TIPO = {"ley": "LEY", "decreto supremo": "DECRETO", "decreto": "DECRETO",
        "decreto con fuerza de ley": "DFL", "decreto ley": "DL",
        "resolucion": "RESOLUCION", "resolucion exenta": "RESOLUCION"}


def _num(s):
    """Número de la norma, tolerando cómo el PDF pega dígitos ajenos.

    El `-layout` de pdftotext arrastra numeraciones de linea al número de la norma:
    "Decreto N°44." + "1 15. El articulo 32..." salia como DECRETO 441, y "Decreto Supremo
    Nº88" + "10" como DECRETO 8810. El punto se corta sólo cuando lo que sigue NO son tres
    dígitos: el separador de miles chileno agrupa siempre de a 3, así que "20.936" es 20936
    pero "44.1" es 44.
    """
    s = (s or "").replace(" ", "")
    m = re.match(r"^(\d+)\.(\d{1,2})(?!\d)", s)
    if m:
        s = m.group(1)
    return s.replace(".", "").lstrip("0") or ""


def _tipo(raw):
    k = re.sub(r"\s+", " ", (raw or "").lower()).replace("ó", "o")
    return TIPO.get(k)


def texto_de(pdf):
    try:
        r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                           capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", "ignore")
    except Exception:
        return ""


def main():
    pdfs = sorted(FUENTE.glob("*.pdf"))
    if not pdfs:
        print(f"sin PDFs en {FUENTE}/ — bajar discrepancias o dictamenes ahi")
        return

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo FROM normas")
        normas = cur.fetchall()
        cur.execute("""SELECT n.tipo, n.numero,
                              replace(replace(a.numero,'°',''),'º','') AS art
                       FROM articulos a JOIN normas n ON n.id_norma = a.id_norma""")
        arts = {(str(r["tipo"]).upper(), _num(r["numero"]), (r["art"] or "").lower().strip())
                for r in cur.fetchall()}
    cat = {}
    for n in normas:
        cat.setdefault((str(n["tipo"]).upper(), _num(n["numero"])), n)

    en_corpus = collections.Counter()
    faltan = collections.defaultdict(lambda: {"n": 0, "ejemplo": "", "docs": set()})
    con_art, sin_art, pares = 0, 0, []
    for pdf in pdfs:
        t = texto_de(pdf)
        for m in CITA.finditer(t):
            # el "medio" no debe cruzar otra mencion de articulo: si lo hace, el par
            # articulo-norma que se arma es falso.
            if re.search(r"art[íi]culo", m.group("medio"), re.I):
                continue
            tp = _tipo(m.group("tipo"))
            if not tp:
                continue
            nu = _num(m.group("num"))
            if not nu:
                continue        # "artículo 72-1 de la Ley." -- sin número no se resuelve
            k = (tp, nu)
            art = re.sub(r"[°ºª\s]+", "", m.group("art")).lower()
            if k in cat:
                en_corpus[k] += 1
                if (k[0], k[1], art) in arts:
                    con_art += 1
                    pares.append((cat[k]["id_norma"], cat[k]["tipo"], cat[k]["numero"],
                                  art, pdf.name))
                else:
                    sin_art += 1
            else:
                e = faltan[k]
                e["n"] += 1
                e["docs"].add(pdf.name)
                if not e["ejemplo"]:
                    e["ejemplo"] = re.sub(r"\s+", " ", m.group(0))[:110]

    tot = sum(en_corpus.values()) + sum(v["n"] for v in faltan.values())
    print(f"documentos leidos            : {len(pdfs)}")
    print(f"citas articulo->norma        : {tot}")
    print(f"  a normas DEL corpus        : {sum(en_corpus.values())}  ({len(en_corpus)} normas)")
    print(f"     ...y el ARTICULO existe : {con_art}   <- sirven como gold")
    print(f"     ...articulo NO esta     : {sin_art}")
    print(f"  a normas que FALTAN        : {sum(v['n'] for v in faltan.values())}"
          f"  ({len(faltan)} normas)")

    # Un numero que no esta en el catalogo pero cuyo PREFIJO si esta es, casi siempre, el
    # mismo defecto de layout con un digito de mas. Se SEÑALA, no se corrige solo: resolverlo
    # por truncamiento sesgaria el reporte hacia "ya lo tenemos", que es justo lo contrario
    # de lo que este reporte tiene que detectar.
    for (tp, nu), v in faltan.items():
        # solo prefijos PLAUSIBLES: se quitan 1-2 digitos y quedan al menos 2. Sin este
        # limite sugeria "DECRETO 4" para el DECRETO 44 -- que existe en el catalogo pero es
        # otra norma, y el DECRETO 44 es un faltante REAL (Reglamento del Panel de Expertos).
        v["quiza"] = next((f"{tp} {nu[:i]}" for i in (len(nu) - 1, len(nu) - 2)
                           if i >= 2 and (tp, nu[:i]) in cat), "")

    orden = sorted(faltan.items(), key=lambda kv: -kv[1]["n"])
    print("\n--- normas citadas por el sector que NO estan en el corpus ---")
    for (tp, nu), v in orden[:15]:
        q = f"  (¿será {v['quiza']}? numero pegado por el PDF)" if v["quiza"] else ""
        print(f"  {v['n']:3}  {tp} {nu:<8} {v['ejemplo'][:52]}{q}")

    L = ["# Normativa que el sector cita en sus discrepancias",
         "",
         "Generado por `scripts/extraer_de_discrepancias.py` sobre los PDF de",
         "`data/discrepancias/`. **Es descubrimiento por USO, no por búsqueda**: una norma que",
         "aparece en una discrepancia real ante el Panel de Expertos es normativa viva del",
         "sector. El frente de descubrimiento prospectivo estaba bloqueado porque los sitios",
         "bloquean el scraping; esta vía no depende de ellos.",
         "",
         f"- documentos leídos: **{len(pdfs)}**",
         f"- citas artículo→norma detectadas: **{tot}**",
         f"- resueltas a normas del corpus: **{sum(en_corpus.values())}**"
         f" ({con_art} con el artículo también presente — sirven de gold para evaluar)",
         f"- apuntan a normas que **faltan**: **{sum(v['n'] for v in faltan.values())}**",
         "",
         "## Normas citadas que NO están en el corpus",
         "",
         "⚠️ Un `quizá` señala que el número no existe pero un prefijo suyo sí: casi siempre",
         "es el `-layout` de pdftotext pegando una numeración de línea. **No se corrige solo** —",
         "resolverlo por truncamiento sesgaría el reporte hacia *\"ya lo tenemos\"*.",
         "",
         "| tipo | número | veces | quizá | ejemplo de la cita |",
         "|---|---|---|---|---|"]
    for (tp, nu), v in orden:
        L.append(f"| {tp} | {nu} | {v['n']} | {v['quiza'] or '—'} | {v['ejemplo'][:70]} |")
    L += ["", "## Pares artículo–norma utilizables como gold", "",
          "| norma | artículo | documento |", "|---|---|---|"]
    for nid, tp, nu, art, doc in sorted(set(pares))[:80]:
        L.append(f"| {tp} {nu} (`{nid}`) | {art} | {doc} |")
    SALIDA.write_text("\n".join(L) + "\n")
    print(f"\nescrito {SALIDA}")


if __name__ == "__main__":
    main()
