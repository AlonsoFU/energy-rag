"""FASE 4.2 — de qué PROCESO habla cada obligación, según el propio articulado.

El campo `obligacion.proceso` está vacío en las 1178 filas. Sin él no se puede responder la
pregunta que justifica el foso: *"cambió la norma X → ¿qué proceso se rompe?"*.

**El nombre del proceso no se inventa ni se infiere: lo escribió el legislador.** Toda norma
larga viene dividida en TÍTULO / CAPÍTULO / PÁRRAFO, y el encabezado dice de qué trata lo que
sigue ("TÍTULO III · DEL PROCEDIMIENTO APLICABLE A LAS AUTORIZACIONES SECTORIALES"). Eso es un
agrupamiento **hecho por la autoridad que dictó la norma** — mejor fuente que cualquier
clustering que yo arme por parecido semántico, y auditable línea por línea.

Sobre el regex (regla del proyecto): acá no clasifica ni interpreta nada. Reconoce un
encabezado LITERAL y copia el nombre que viene escrito debajo, igual que `ARTICULO_PATTERN`
reconoce dónde empieza un artículo. Quien decide el nombre del proceso es el texto.

Cobertura medida: 790 de 1178 obligaciones (67 %) viven en normas con estructura de títulos.
Las otras 388 quedan con `proceso = NULL` — **sin proceso conocido, que no es lo mismo que
"sin proceso"**. Completarlas pide otro mecanismo (LLM sobre el texto) y es trabajo aparte.

  PYTHONPATH=. venv/bin/python -m scripts.estructura_articulado [--aplicar]
"""
import argparse
import re
from collections import Counter

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.parsers.norm_structure_parser import NormStructureParser

# encabezado = la linea es SOLO la etiqueta y su numeral. El nombre va en la linea siguiente.
# Se exige linea completa a proposito: "lo dispuesto en el Título II" aparece a mitad de
# parrafo todo el tiempo y no es un encabezado.
ENCABEZADO = re.compile(
    r'^[ \t]*(T[ÍI]TULO|CAP[ÍI]TULO|P[ÁA]RRAFO)[ \t]+([IVXLC]+|\d+)[°ºª]?\.?[ \t]*$',
    re.MULTILINE | re.IGNORECASE)
# un nombre valido no es otro encabezado ni el arranque de un articulo
NO_ES_NOMBRE = re.compile(r'^[ \t]*(art[íi]culo|t[ÍIíi]tulo|cap[ÍIíi]tulo|p[ÁAáa]rrafo)\b', re.I)


# BCN sirve el articulado con espacios duros U+00A0 (y afines). Un encabezado llega como
# '\xa0 \xa0 TÍTULO I', asi que `[ \t]*` no lo reconoce y la deteccion daba 0 de 1178.
# Se normalizan ANTES de parsear, y con reemplazo 1:1 para que las POSICIONES no se muevan
# (de eso depende asignar cada articulo al encabezado que lo precede).
ESPACIOS_DUROS = {0xA0: " ", 0x2007: " ", 0x202F: " ", 0xFEFF: " "}


def limpiar(texto):
    return (texto or "").translate(ESPACIOS_DUROS)


def encabezados(texto):
    """[(pos, etiqueta, numeral, nombre)] en orden de aparición."""
    out = []
    texto = limpiar(texto)
    for m in ENCABEZADO.finditer(texto):
        resto = texto[m.end():].splitlines()
        nombre = ""
        for linea in resto[:3]:                 # el nombre puede venir tras una linea vacia
            s = linea.strip()
            if not s:
                continue
            if NO_ES_NOMBRE.match(s):
                break                            # titulo sin nombre propio: se deja vacio
            nombre = s
            break
        out.append((m.start(), m.group(1).upper(), m.group(2).upper(), nombre[:180]))
    return out


def proceso_de(pos_art, encs):
    """El último encabezado que PRECEDE al artículo. Prefiere el más específico con nombre."""
    previos = [e for e in encs if e[0] < pos_art]
    if not previos:
        return None
    con_nombre = [e for e in previos if e[3]]
    e = (con_nombre or previos)[-1]
    return {"nivel": e[1], "numeral": e[2], "nombre": e[3]}


def main(aplicar=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT n.id_norma, n.texto_completo FROM normas n
                       WHERE n.texto_completo IS NOT NULL
                         AND n.metadata->>'fuera_de_dominio' IS DISTINCT FROM 'true'""")
        normas = {r["id_norma"]: limpiar(r["texto_completo"]) for r in cur.fetchall()}
        cur.execute("""SELECT a.id, a.id_norma, a.numero, o.id AS obl
                       FROM articulos a JOIN obligacion o ON o.articulo_id = a.id""")
        filas = cur.fetchall()

    asign, sin_estructura, sin_ubicar = {}, 0, 0
    nombres = Counter()
    for nid, texto in normas.items():
        encs = encabezados(texto)
        arts = list(NormStructureParser.ARTICULO_PATTERN.finditer(texto))
        # numero del articulo -> posicion de su PRIMERA aparicion en el texto
        pos = {}
        for m in arts:
            k = re.sub(r"[°ºª\s]+", "", (m.group(1) or "")).lower()
            pos.setdefault(k, m.start())
        for f in [x for x in filas if x["id_norma"] == nid]:
            if len(encs) < 2:
                sin_estructura += 1
                continue
            k = re.sub(r"[°ºª\s]+", "", str(f["numero"] or "")).lower()
            p = pos.get(k)
            if p is None:
                sin_ubicar += 1
                continue
            pr = proceso_de(p, encs)
            if pr and pr["nombre"]:
                asign[f["obl"]] = pr
                nombres[pr["nombre"]] += 1

    tot = len(filas)
    print(f"obligaciones                       : {tot}")
    print(f"  con proceso del articulado       : {len(asign)}  ({100 * len(asign) // max(tot, 1)} %)")
    print(f"  en normas SIN estructura         : {sin_estructura}")
    print(f"  articulo no ubicado en el texto  : {sin_ubicar}")
    print(f"  procesos distintos               : {len(nombres)}")
    print("\n--- procesos con más obligaciones ---")
    for n, k in nombres.most_common(15):
        print(f"  {k:4}  {n[:72]}")

    if aplicar:
        with with_connection() as c, c.cursor() as cur:
            cur.executemany("UPDATE obligacion SET proceso=%s WHERE id=%s",
                            [(f"{v['nivel']} {v['numeral']} — {v['nombre']}", k)
                             for k, v in asign.items()])
            c.commit()
        print(f"\nESCRITAS {len(asign)} filas de `obligacion.proceso`")
    else:
        print("\n(simulacion — usar --aplicar para escribir)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)
