"""B4.5 — qué está DEROGADO, para no citarlo como vigente.

El peor error posible en un sistema legal es responder con un artículo derogado sin decirlo.
Hoy el sistema puede hacerlo: `articulos.derogado` está en **2 de 3455**, y las vinculaciones
que BCN entrega sólo traen `modifica` (204 filas), ni una derogación.

La fuente real es el propio articulado: las normas derogatorias lo dicen con todas las letras
—*"Derógase el decreto supremo Nº 181, de 2004"*—. Eso es un hecho escrito por el legislador,
no una inferencia.

**El verbo propone, el catálogo dispone.** El patrón reconoce la frase derogatoria y extrae el
objeto; una derogación sólo cuenta si el objeto existe en la DB. No hay lista de normas
derogadas escrita a mano, y lo que no resuelve queda reportado, no adivinado.

Dos alcances, que hay que distinguir o se borra de más:
  NORMA    "Derógase el decreto supremo Nº 181"            -> la norma entera
  ARTICULO "Derógase el artículo 5º de la ley Nº 18.410"   -> sólo ese artículo

⚠️ Una derogación puede ser PARCIAL ("derógase el inciso segundo del artículo 5"). Esos casos se
detectan y se reportan APARTE: marcar el artículo entero como derogado sería falso, y esconder
un artículo vigente es tan grave como citar uno muerto.

  PYTHONPATH=. venv/bin/python -m scripts.detectar_derogaciones [--aplicar]
"""
import argparse
import collections
import re

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

# La frase derogatoria chilena: "Derógase/Deróganse" + objeto. Se exige el verbo al inicio de
# la oracion; "no se deroga" o "la derogacion del articulo X" no son actos derogatorios.
VERBO = r"der[óo]g(?:ase|uese|anse|uense)"
# alcance ARTICULO: "Derogase el articulo 5º de la ley N°18.410"
DEROGA_ART = re.compile(
    VERBO + r"\s+(?:el\s+|los\s+)?art[íi]culos?\s+(?P<art>\d{1,3}[°ºª]?(?:\s*bis|\s*ter)?)"
    r"(?P<medio>[^.;]{0,90}?)"
    r"(?P<tipo>ley|decreto\s+supremo|decreto\s+con\s+fuerza\s+de\s+ley|decreto\s+ley|decreto|"
    r"resoluci[oó]n)\s*(?:n[°ºo]\.?\s*)?(?P<num>[\d\.]{1,9})",
    re.IGNORECASE)
# alcance NORMA: "Derogase el decreto supremo N°181, de 2004"
DEROGA_NORMA = re.compile(
    VERBO + r"\s+(?:el\s+|la\s+|los\s+)?"
    r"(?P<tipo>ley|decreto\s+supremo|decreto\s+con\s+fuerza\s+de\s+ley|decreto\s+ley|decreto|"
    r"resoluci[oó]n)\s*(?:n[°ºo]\.?\s*)?(?P<num>[\d\.]{1,9})",
    re.IGNORECASE)
# El articulo cuyo CUERPO es la marca: BCN deja "Artículo 20.- Derogado." en el lugar del
# texto. Es la via que importa de verdad -- son articulos DENTRO de normas vigentes, cargados
# como articulos normales: DECRETO 88 tiene seis (20, 21, 22, 23, 25, 26) y el DFL 4 tiene el
# 146 quáter "Suprimido".
# Se exige que la marca sea PRACTICAMENTE TODO el cuerpo. LEY 21472 art 3 menciona derogacion
# dentro de 5.541 caracteres de texto vigente; marcarlo por mencionarla seria esconder un
# articulo vivo, que es tan grave como citar uno muerto.
CUERPO_DEROGADO = re.compile(
    r'^[\s\-–—.:"“]*(?:art[íi]culo[^.\n]{0,26}[.\-–—]+\s*)?'
    r"(derogad[oa]s?|suprimid[oa]s?|eliminad[oa]s?)\s*[.\-–—]*\s*$", re.IGNORECASE)
LARGO_MARCA = 60          # por encima de esto ya hay texto dispositivo, no una marca

# derogacion PARCIAL: no toca el articulo entero
PARCIAL = re.compile(r"\b(inciso|letra|numeral|p[áa]rrafo|frase|expresi[óo]n|oraci[óo]n)\b", re.I)

TIPO = {"ley": "LEY", "decreto supremo": "DECRETO", "decreto": "DECRETO",
        "decreto con fuerza de ley": "DFL", "decreto ley": "DL",
        "resolucion": "RESOLUCION"}


def _num(s):
    return (s or "").replace(".", "").replace(" ", "").lstrip("0") or ""


def _tipo(raw):
    return TIPO.get(re.sub(r"\s+", " ", (raw or "").lower()).replace("ó", "o"))


def _art(s):
    return re.sub(r"[°ºª\s]+", "", (s or "")).lower()


def main(aplicar=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero FROM normas")
        normas = cur.fetchall()
        cur.execute("""SELECT a.id, a.id_norma, a.numero, coalesce(a.texto,'') texto,
                              n.tipo, n.numero AS nnum
                       FROM articulos a JOIN normas n ON n.id_norma = a.id_norma
                       ORDER BY a.id_norma, a.id""")
        arts = cur.fetchall()

    cat = {}
    for n in normas:
        cat.setdefault((str(n["tipo"]).upper(), _num(n["numero"])), n["id_norma"])
    por_norma_art = collections.defaultdict(dict)
    for a in arts:
        por_norma_art[a["id_norma"]][_art(a["numero"])] = a["id"]

    der_norma, der_art, parciales, sin_resolver = {}, {}, [], collections.Counter()
    cuerpo_marca = {}

    for a in arts:
        # se corta en el primer salto doble: BCN a veces pega el encabezado del capitulo
        # siguiente al cuerpo del articulo derogado (visto en DECRETO 88 art 26).
        cuerpo = re.split(r"\n\s*\n", (a["texto"] or "").strip())[0].strip()
        if len(cuerpo) <= LARGO_MARCA and CUERPO_DEROGADO.match(cuerpo):
            cuerpo_marca[a["id"]] = {"por": "el propio texto del articulo",
                                     "frase": re.sub(r"\s+", " ", cuerpo)[:60],
                                     "ref": f"{a['tipo']} {a['nnum']} art {a['numero']}"}

    for a in arts:
        # una oracion por vez: el objeto derogado tiene que estar en la MISMA oracion que el verbo
        for frase in re.split(r"(?<=[.;])\s+", a["texto"]):
            if not re.search(VERBO, frase, re.I):
                continue
            es_parcial = bool(PARCIAL.search(frase))

            m = DEROGA_ART.search(frase)
            if m and not re.search(r"art[íi]culo", m.group("medio") or "", re.I):
                k = (_tipo(m.group("tipo")), _num(m.group("num")))
                nid = cat.get(k)
                if not nid:
                    sin_resolver[f"{k[0]} {k[1]}"] += 1
                    continue
                aid = por_norma_art.get(nid, {}).get(_art(m.group("art")))
                if not aid:
                    sin_resolver[f"{k[0]} {k[1]} art {m.group('art')}"] += 1
                    continue
                reg = {"por": f"{a['tipo']} {a['nnum']} art {a['numero']}",
                       "frase": re.sub(r"\s+", " ", frase)[:130]}
                if es_parcial:
                    parciales.append({"articulo_id": aid, **reg})
                else:
                    der_art.setdefault(aid, reg)
                continue

            m = DEROGA_NORMA.search(frase)
            if m:
                k = (_tipo(m.group("tipo")), _num(m.group("num")))
                nid = cat.get(k)
                if not nid:
                    sin_resolver[f"{k[0]} {k[1]}"] += 1
                    continue
                if nid == a["id_norma"]:
                    continue                    # una norma no se deroga a si misma
                reg = {"por": f"{a['tipo']} {a['nnum']} art {a['numero']}",
                       "frase": re.sub(r"\s+", " ", frase)[:130]}
                if es_parcial:
                    parciales.append({"id_norma": nid, **reg})
                else:
                    der_norma.setdefault(nid, reg)

    print(f"articulos revisados            : {len(arts)}")
    print(f"NORMAS derogadas por completo  : {len(der_norma)}")
    for nid, v in list(der_norma.items())[:10]:
        n = next((x for x in normas if x["id_norma"] == nid), None)
        print(f"   {n['tipo']} {n['numero']:<8} ({nid})  por {v['por']}")
    print(f"ARTICULOS derogados (por otra norma) : {len(der_art)}")
    print(f"ARTICULOS cuyo CUERPO es la marca     : {len(cuerpo_marca)}")
    for v in list(cuerpo_marca.values())[:8]:
        print(f"   {v['ref']:<26} {v['frase']!r}")
    print(f"derogaciones PARCIALES (no se marcan): {len(parciales)}")
    print(f"objetos que NO estan en el corpus    : {sum(sin_resolver.values())}"
          f"  ({len(sin_resolver)} distintos)")
    for k, n in sin_resolver.most_common(6):
        print(f"   {n:3}  {k}")

    if aplicar:
        with with_connection() as c, c.cursor() as cur:
            todos = set(der_art) | set(cuerpo_marca)
            if todos:
                cur.executemany("UPDATE articulos SET derogado = true WHERE id = %s",
                                [(k,) for k in todos])
            if der_norma:
                cur.executemany(
                    """UPDATE normas SET metadata = coalesce(metadata,'{}'::jsonb)
                       || jsonb_build_object('derogada', 'true', 'derogada_por', %s::text)
                       WHERE id_norma = %s""",
                    [(v["por"], k) for k, v in der_norma.items()])
                # los articulos de una norma derogada quedan derogados con ella
                cur.executemany("UPDATE articulos SET derogado = true WHERE id_norma = %s",
                                [(k,) for k in der_norma])
            c.commit()
        print(f"\nMARCADAS {len(der_norma)} normas y "
              f"{len(set(der_art) | set(cuerpo_marca))} articulos como derogados")
    else:
        print("\n(simulacion — usar --aplicar para marcar)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)
