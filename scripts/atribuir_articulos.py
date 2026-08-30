"""A qué norma pertenece REALMENTE cada artículo de una ley modificatoria.

El problema de fondo, y la causa raíz de las citas falsas del sistema. Una ley modificatoria
no contiene artículos propios: contiene bloques que INSERTAN articulado en otro cuerpo legal.
El ingestor los guardó como propios, y el sistema respondía `[LEY 20936 art 92°]` cuando el
artículo 92° pertenece al DFL 4 — una cita legalmente falsa.

`detectar_articulos_duplicados` tapa el caso sólo cuando el mismo artículo ya está en el
destino (55 de LEY 20936). No sirve cuando el destino **no está en el corpus** o el numeral no
coincide: los `29 ter` y `33 quinquies` de LEY 20999 quedaron sin marcar porque esa ley
modifica la **Ley de Servicios de Gas (DFL 323)**, no la LGSE.

**El texto declara el destino, no hay que adivinarlo.** Los bloques abren así:

    "Introdúcense en el decreto con fuerza de ley N° 323, de 1931, ... las siguientes
     modificaciones:"
        1. Modifícase el artículo 1 en el siguiente sentido:
            a) Sustitúyese el inciso primero, por el siguiente: "Artículo 1. El transporte..."

Todo artículo que aparece **después** de esa frase y antes de la siguiente frase-destino
pertenece a la norma anunciada. Se resuelve contra el catálogo: `_VERBOS` propone, el catálogo
dispone; una atribución sólo cuenta si el destino existe en la DB.

MARCA, no borra: `articulos.metadata.pertenece_a`.

  PYTHONPATH=. venv/bin/python -m scripts.atribuir_articulos [--aplicar]
"""
import argparse
import collections
import re

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.parsers.norm_structure_parser import NormStructureParser
from scripts.estructura_articulado import _VERBOS, limpiar

# "Introducense EN el decreto con fuerza de ley N° 323, de 1931, ... las siguientes
# modificaciones" — el destino va entre el verbo y el anuncio de modificaciones.
DESTINO = re.compile(
    r"(?P<verbo>" + _VERBOS.pattern + r")"
    r"(?P<medio>[^.;:]{0,160}?)"
    r"\b(?P<tipo>ley|decreto\s+supremo|decreto\s+con\s+fuerza\s+de\s+ley|decreto\s+ley|decreto|"
    r"resoluci[oó]n)\s*(?:n[°ºo]\.?\s*)?(?P<num>[\d\.]{1,9})",
    re.IGNORECASE)
TIPO = {"ley": "LEY", "decreto supremo": "DECRETO", "decreto": "DECRETO",
        "decreto con fuerza de ley": "DFL", "decreto ley": "DL", "resolucion": "RESOLUCION"}

# FIN del bloque insertado. Sin esto el atribuidor mandaba a la norma destino TODO lo que
# viniera despues de la frase que abre el bloque, incluidos los articulos PROPIOS que la ley
# tiene mas abajo. Caso medido: LEY 21472 art 1 modifica el DFL 4, y sus articulos 2-16 son
# suyos ("Mecanismo Transitorio de Proteccion al Cliente") -- se los llevaba al DFL 4.
#
# El articulado insertado va entrecomillado y cierra con comilla-punto:
#   "...no podra prorrogarse mas alla de ese periodo.".  TITULO II  MECANISMO TRANSITORIO...
CIERRE_BLOQUE = re.compile(r'["“”]\s*\.')


def _num(s):
    s = (s or "").replace(" ", "")
    m = re.match(r"^(\d+)\.(\d{1,2})(?!\d)", s)
    if m:
        s = m.group(1)
    return s.replace(".", "").lstrip("0") or ""


def _tipo(raw):
    return TIPO.get(re.sub(r"\s+", " ", (raw or "").lower()).replace("ó", "o"))


def main(aplicar=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo, texto_completo FROM normas")
        normas = cur.fetchall()
        cur.execute("""SELECT id, id_norma, numero FROM articulos
                       ORDER BY id_norma, id""")
        arts = cur.fetchall()
    cat = {}
    for n in normas:
        cat.setdefault((str(n["tipo"]).upper(), _num(n["numero"])), n)
    por_norma = collections.defaultdict(list)
    for a in arts:
        por_norma[a["id_norma"]].append(a)

    asign, sin_destino, sin_resolver = {}, 0, collections.Counter()
    fuera_bloque = 0
    for n in normas:
        texto = limpiar(n["texto_completo"] or "")
        if not texto:
            continue
        # tramos: (posicion, id_norma destino) en orden de aparicion
        tramos = []
        for m in DESTINO.finditer(texto):
            # el "medio" no debe cruzar otra mencion de norma: si lo hace, el destino que se
            # arma no es el que la frase anuncia.
            if re.search(r"\b(ley|decreto|reglamento|resoluci[oó]n)\b", m.group("medio"), re.I):
                continue
            tp = _tipo(m.group("tipo"))
            nu = _num(m.group("num"))
            if not tp or not nu:
                continue
            dest = cat.get((tp, nu))
            if not dest:
                sin_resolver[f"{tp} {nu}"] += 1
                continue
            if dest["id_norma"] == n["id_norma"]:
                continue                       # una norma no se modifica a si misma
            tramos.append((m.start(), dest["id_norma"], f"{tp} {nu}"))
        if not tramos:
            continue

        # posicion de cada articulo en el texto
        pos = {}
        for m in NormStructureParser.ARTICULO_PATTERN.finditer(texto):
            k = re.sub(r"[°ºª\s]+", "", (m.group(1) or "")).lower()
            pos.setdefault(k, m.start())

        for a in por_norma[n["id_norma"]]:
            k = re.sub(r"[°ºª\s]+", "", str(a["numero"] or "")).lower()
            p = pos.get(k)
            if p is None:
                continue
            previos = [t for t in tramos if t[0] < p]
            if not previos:
                sin_destino += 1
                continue                       # antes del primer bloque => articulo PROPIO
            # ¿el bloque ya cerro antes de llegar a este articulo? Entonces es PROPIO.
            ini_bloque = previos[-1][0]
            cierre = CIERRE_BLOQUE.search(texto, ini_bloque, p)
            if cierre:
                fuera_bloque += 1
                continue
            asign[a["id"]] = {"destino": previos[-1][1], "etiqueta": previos[-1][2],
                              "origen": f"{n['tipo']} {n['numero']}", "art": a["numero"]}

    print(f"articulos revisados            : {len(arts)}")
    print(f"atribuidos a OTRA norma        : {len(asign)}")
    print(f"antes del primer bloque (propios): {sin_destino}")
    print(f"despues del cierre del bloque (propios): {fuera_bloque}")
    print(f"destinos que NO estan en el corpus: {sum(sin_resolver.values())}"
          f"  ({len(sin_resolver)} distintos)")
    for k, v in sin_resolver.most_common(6):
        print(f"     {v:3}  {k}")
    por_par = collections.Counter(f"{v['origen']} -> {v['etiqueta']}" for v in asign.values())
    print("\n--- por par origen -> destino ---")
    for k, v in por_par.most_common(12):
        print(f"  {v:4}  {k}")

    if aplicar:
        with with_connection() as c, c.cursor() as cur:
            cur.execute("""UPDATE articulos SET metadata = metadata - 'pertenece_a'
                           WHERE metadata->>'pertenece_a' IS NOT NULL""")
            cur.executemany(
                """UPDATE articulos SET metadata = coalesce(metadata,'{}'::jsonb)
                   || jsonb_build_object('pertenece_a', %s::text)
                   WHERE id = %s""",
                [(v["destino"], k) for k, v in asign.items()])
            c.commit()
        print(f"\nMARCADOS {len(asign)} articulos con metadata.pertenece_a")
    else:
        print("\n(simulacion — usar --aplicar para marcar)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)
