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
import json
import re
from collections import Counter
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.parsers.norm_structure_parser import NormStructureParser

# El encabezado arranca la linea. El nombre puede venir en la MISMA linea
# ("TITULO I DISPOSICIONES GENERALES", "Capitulo I: Generalidades") o en la siguiente
# ("TITULO I" \n "DISPOSICIONES GENERALES"). Exigir linea-solo-etiqueta perdia 317 de 389
# obligaciones: DECRETO 62 y LEY 20936 escriben el nombre pegado.
#
# Se exige INICIO DE LINEA a proposito: "lo dispuesto en el Titulo II" aparece a mitad de
# parrafo todo el tiempo y no es un encabezado.
#
# La COMILLA inicial se captura, no se ignora: un encabezado entrecomillado es articulado que
# la norma TRANSCRIBE para insertarlo en OTRA norma (LEY 20936 inserta titulos completos en la
# LGSE). Atribuir ese proceso a la ley modificatoria seria la misma falsedad que el parser ya
# evita con `es_transcrito` para los articulos.
ENCABEZADO = re.compile(
    r'^[ \t]*(?P<comilla>["“«]?)[ \t]*'
    r'(?P<nivel>T[ÍI]TULO|CAP[ÍI]TULO|P[ÁA]RRAFO)[ \t]+'
    r'(?P<num>[IVXLC]+(?:[ \t]+BIS|[ \t]+TER)?|\d+)[°ºª]?'
    r'[ \t]*[:.\-]?[ \t]*(?P<nombre>[^\n]{0,150})$',
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


# El patron del parser esta ANCLADO (`^[\s.\-:]*(introducense|...)`) porque alli se aplica al
# arranque del cuerpo de un articulo. Aca hay que buscarlo a mitad de un parrafo introductorio,
# asi que se le quita el ancla y se conserva la MISMA lista de verbos: una sola fuente, para
# que las dos no se separen con el tiempo. (Con el ancla puesta y `.search()` no matcheaba
# nada: LEY 20936 dice "4) Reemplazase el Titulo III por el siguiente:" y daba 0 transcritos.)
_VERBOS = re.compile(
    NormStructureParser._VERBO_MODIFICATORIO.pattern.replace(r"^[\s\.\-–—:]*", "", 1),
    re.IGNORECASE)


def _introduce_texto_ajeno(previo):
    """¿La comilla abre articulado de OTRA norma, o el contenido propio de esta?

    Distinción medida en dos casos reales, y la decide el VERBO, no la comilla:
      DECRETO 10  "Apruébase el siguiente reglamento:"  + comilla -> el reglamento ES suyo
      LEY 20936   "Introdúcense las siguientes modif."  + comilla -> inserta en la LGSE
    Se reutiliza `_VERBO_MODIFICATORIO` del parser en vez de escribir otra lista: es el mismo
    criterio que ya usa `es_transcrito` para los artículos, y tenerlo en un solo lugar evita
    que las dos versiones se separen.
    """
    # solo la ultima linea con contenido: es la que introduce la comilla. Barrer 400 chars
    # enteros cazaria el verbo de OTRO numeral de la misma lista de modificaciones.
    lineas = [l for l in (previo or "").splitlines() if l.strip()]
    return bool(_VERBOS.search(lineas[-1])) if lineas else False


def encabezados(texto, incluir_transcritos=False):
    """[(pos, nivel, numeral, nombre, transcrito)] en orden de aparición."""
    out = []
    texto = limpiar(texto)
    for m in ENCABEZADO.finditer(texto):
        # comilla SOLA no basta: hay que mirar qué la introduce.
        transcrito = bool(m.group("comilla")) and _introduce_texto_ajeno(
            texto[max(0, m.start() - 400):m.start()])
        if transcrito and not incluir_transcritos:
            continue
        nombre = (m.group("nombre") or "").strip().strip('"“«»').strip()
        if NO_ES_NOMBRE.match(nombre):
            nombre = ""                          # "TITULO I" seguido de "Articulo 1" en la misma linea
        if not nombre:                            # el nombre va en alguna de las lineas siguientes
            for linea in texto[m.end():].splitlines()[:3]:
                t = linea.strip().strip('"“«»').strip()
                if not t:
                    continue
                if NO_ES_NOMBRE.match(t):
                    break                         # titulo sin nombre propio: se deja vacio
                nombre = t
                break
        out.append((m.start(), m.group("nivel").upper(),
                    re.sub(r"\s+", " ", m.group("num")).upper(), nombre[:180], transcrito))
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
        normas = {}
        for r in cur.fetchall():
            t = limpiar(r["texto_completo"])
            # Si `texto_completo` quedo truncado por el render perezoso de BCN pero el JSON
            # bajado tiene el documento entero, se usa ese para BUSCAR ENCABEZADOS. Los
            # articulos ya estan en la DB y no se tocan; lo unico que sale del JSON es donde
            # empieza cada TITULO/CAPITULO.
            # Caso que lo motiva: el DFL 4 (la LGSE) tiene 10.075 chars en la DB y 582.770 en
            # el JSON -> 1 encabezado contra 26, y sus 862 obligaciones quedaban sin proceso.
            j = Path(f"data/normas_completas/nuevas/{r['id_norma']}.json")
            if j.exists():
                try:
                    tj = limpiar(json.loads(j.read_text()).get("texto_completo") or "")
                    if len(tj) > len(t) * 1.5:
                        t = tj
                except Exception:
                    pass
            normas[r["id_norma"]] = t
        cur.execute("""SELECT a.id, a.id_norma, a.numero, o.id AS obl
                       FROM articulos a JOIN obligacion o ON o.articulo_id = a.id""")
        filas = cur.fetchall()

    asign, sin_estructura, sin_ubicar, transcritas = {}, 0, 0, {}
    nombres = Counter()
    for nid, texto in normas.items():
        encs = encabezados(texto)
        # Si la norma trae encabezados ENTRECOMILLADOS, esta insertando articulado en OTRA
        # norma (LEY 20936 inserta titulos completos en la LGSE). El bloque citado se abre una
        # vez y se cierra mucho despues, asi que los encabezados de adentro NO llevan comilla
        # propia y no se distinguen de los suyos. Pareando comillas tampoco sale: LEY 20936
        # tiene 381 comillas RECTAS, numero impar -- no hay apertura/cierre que emparejar.
        #
        # No se puede separar => no se asigna proceso a ESA norma. En materia legal atribuir
        # mal un proceso es peor que dejarlo vacio, y `proceso IS NULL` ya significa
        # "sin proceso conocido". Queda como frente abierto, no como dato inventado.
        if len(encabezados(texto, incluir_transcritos=True)) > len(encs):
            n_obl = sum(1 for x in filas if x["id_norma"] == nid)
            if n_obl:
                transcritas[nid] = n_obl
            continue
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
    if transcritas:
        print(f"  en normas que TRANSCRIBEN articulado: {sum(transcritas.values())}  "
              f"({len(transcritas)} normas) -- no se asigna, ver comentario")
    print(f"  procesos distintos               : {len(nombres)}")
    print("\n--- procesos con más obligaciones ---")
    for n, k in nombres.most_common(15):
        print(f"  {k:4}  {n[:72]}")

    if aplicar:
        with with_connection() as c, c.cursor() as cur:
            # limpiar ANTES: si el criterio cambia y una obligacion deja de tener proceso
            # asignable, sin este NULL se quedaria con el valor de la corrida anterior --
            # un proceso que el criterio vigente ya no le daria. Paso justo por ahi: la
            # primera version asignaba 225 obligaciones de DECRETO 10 que una version
            # intermedia descartaba.
            cur.execute("UPDATE obligacion SET proceso=NULL WHERE proceso IS NOT NULL")
            print(f"  limpiadas {cur.rowcount} asignaciones previas")
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
