"""E4.3 — consultar el mapa de obligaciones. Es la pregunta que el RAG no puede responder.

Un RAG legal contesta *"¿qué dice el artículo X?"*. Esto contesta:

  --sujeto "Coordinador"   ¿qué me obliga a hacer, y cuándo?
  --plazos                 ¿qué vence y en qué fecha?
  --impacto <id_norma>     si esa norma cambia, ¿qué obligaciones se caen?

Se apoya en `obligacion` (E4.2, extraída y validada contra el texto) y en el grafo de citas
(`referencias.tipo_relacion='remite'`, B3.4).

  PYTHONPATH=. venv/bin/python -m scripts.mapa_obligaciones [--sujeto X] [--plazos] [--impacto ID]
"""
import argparse
import re

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

# fecha explicita vs periodicidad: separarlas cambia si algo se agenda o se vigila
_FECHA = re.compile(r"\b(\d{1,2}\s+de\s+\w+|\d{1,2}/\d{1,2}|d[íi]as?\s+h[áa]biles?|"
                    r"d[íi]as?\s+corridos?|meses?|a[ñn]os?)\b", re.I)


# El sujeto viene literal del articulo, asi que "La Comisión" y "la Comisión" llegan como dos
# entidades distintas. Se normaliza en la CONSULTA (no en la tabla) para no perder el literal,
# que es lo que sostiene la validacion contra el texto.
# Obligaciones que viven en articulos DUPLICADOS (una ley modificatoria guardo como suyos los
# articulos que inserta en otro cuerpo). Mostrarlas las atribuye a la norma equivocada: 128 de
# las 1178, 127 de ellas de LEY 20936, que en realidad son del DFL 4.
# Ver `scripts/detectar_articulos_duplicados.py`.
NO_DUP = " AND (a.metadata->>'duplicado_de') IS NULL"

SUJ_NORM = """regexp_replace(lower(btrim(o.sujeto)),
                             '^(el|la|los|las)\\s+', '', 'g')"""


def q(sql, *a):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, a)
        return cur.fetchall()


def por_sujeto(sujeto):
    r = q(f"""SELECT o.sujeto, o.accion, o.plazo, n.tipo, n.numero AS nnum, a.numero AS art
             FROM obligacion o
             JOIN articulos a ON a.id = o.articulo_id
             JOIN normas n ON n.id_norma = a.id_norma
             WHERE {SUJ_NORM} LIKE lower(%s){NO_DUP}
             ORDER BY (o.plazo IS NULL), n.tipo, n.numero""", f"%{sujeto}%")
    print(f"\n=== obligaciones de «{sujeto}» — {len(r)} ===")
    for x in r[:40]:
        pl = f"  ⏱ {x['plazo'][:52]}" if x["plazo"] else ""
        print(f"  [{x['tipo']} {x['nnum']} art {x['art']}] {x['accion'][:74]}{pl}")


def plazos():
    r = q(f"""SELECT o.sujeto, o.accion, o.plazo, n.tipo, n.numero AS nnum, a.numero AS art
             FROM obligacion o
             JOIN articulos a ON a.id = o.articulo_id
             JOIN normas n ON n.id_norma = a.id_norma
             WHERE o.plazo IS NOT NULL{NO_DUP} ORDER BY o.sujeto""")
    con_fecha = [x for x in r if _FECHA.search(x["plazo"] or "")]
    print(f"\n=== obligaciones con plazo — {len(r)} ({len(con_fecha)} con fecha o duración) ===")
    for x in con_fecha[:40]:
        print(f"  {x['sujeto'][:26]:28} ⏱ {x['plazo'][:40]:42} "
              f"[{x['tipo']} {x['nnum']} art {x['art']}]")
        print(f"      {x['accion'][:96]}")


def impacto(nid):
    r = q(f"""SELECT count(*) n FROM obligacion o
              JOIN articulos a ON a.id = o.articulo_id
              WHERE a.id_norma = %s{NO_DUP}""", nid)
    prop = r[0]["n"]
    cit = q("""SELECT DISTINCT a2.id_norma, n2.tipo, n2.numero AS nnum, count(*) OVER () tot
               FROM referencias r
               JOIN articulos a2 ON a2.id = r.origen_articulo_id
               JOIN normas n2 ON n2.id_norma = a2.id_norma
               WHERE r.tipo_relacion = 'remite' AND r.destino_norma_id = %s""", nid)
    n = q("SELECT tipo, numero, titulo FROM normas WHERE id_norma=%s", nid)
    nom = f"{n[0]['tipo']} {n[0]['numero']}" if n else nid
    print(f"\n=== si cambia {nom} ({nid}) ===")
    print(f"  obligaciones que define directamente : {prop}")
    print(f"  normas del corpus que la citan       : {len(cit)}")
    for x in cit[:12]:
        print(f"      {x['tipo']} {x['nnum']}")
    # FASE 4.2: el proceso viene del encabezado del propio articulado (TÍTULO / CAPÍTULO /
    # PÁRRAFO), no de una taxonomía inventada. Es lo que convierte "cambió la norma X" en
    # "se rompe el proceso Y", que es la pregunta que justifica tener el foso.
    pr = q(f"""SELECT o.proceso, count(*) n FROM obligacion o
               JOIN articulos a ON a.id = o.articulo_id
               WHERE a.id_norma = %s AND o.proceso IS NOT NULL{NO_DUP}
               GROUP BY 1 ORDER BY n DESC""", nid)
    if pr:
        print(f"\n  procesos que toca ({sum(x['n'] for x in pr)} obligaciones):")
        for x in pr[:12]:
            print(f"      {x['n']:>3}  {x['proceso'][:70]}")
    sin = prop - sum(x["n"] for x in pr)
    if sin > 0:
        # sin proceso CONOCIDO no es lo mismo que sin proceso. Dos causas distintas: la
        # norma no trae estructura de títulos, o el artículo no se pudo ubicar en el texto.
        # Decir "la norma no trae títulos" seria mentir en el segundo caso.
        print(f"\n  ({sin} sin proceso conocido — sin títulos en la norma, o artículo no ubicado)")
    print("\n  ⚠️ las obligaciones de esas normas pueden depender de lo que cambie.")


def procesos():
    """Qué procesos existen y en qué normas viven."""
    r = q(f"""SELECT o.proceso, count(*) n, count(o.plazo) cp,
                    count(DISTINCT a.id_norma) normas
             FROM obligacion o JOIN articulos a ON a.id = o.articulo_id
             WHERE o.proceso IS NOT NULL{NO_DUP} GROUP BY 1 ORDER BY n DESC""")
    tot = q(f"""SELECT count(*) n FROM obligacion o
                JOIN articulos a ON a.id = o.articulo_id WHERE true{NO_DUP}""")[0]["n"]
    con = sum(x["n"] for x in r)
    print(f"\n=== {len(r)} procesos — {con}/{tot} obligaciones ubicadas ===")
    print("  el nombre lo escribió el legislador en el encabezado del articulado\n")
    for x in r[:25]:
        print(f"  {x['n']:>4}  ({x['cp']:>3} con plazo, {x['normas']} norma/s)  {x['proceso'][:64]}")
    print(f"\n  {tot - con} sin proceso conocido — sin títulos en la norma, o artículo no ubicado")


def resumen():
    t = q(f"""SELECT count(*) n FROM obligacion o
               JOIN articulos a ON a.id = o.articulo_id WHERE true{NO_DUP}""")[0]["n"]
    cp = q(f"""SELECT count(*) n FROM obligacion o
                JOIN articulos a ON a.id = o.articulo_id
                WHERE o.plazo IS NOT NULL{NO_DUP}""")[0]["n"]
    print(f"\n=== mapa de obligaciones — {t} obligaciones, {cp} con plazo ===")
    for x in q(f"""SELECT {SUJ_NORM} AS sujeto, count(*) n, count(o.plazo) cp
                   FROM obligacion o JOIN articulos a ON a.id = o.articulo_id
                   WHERE true{NO_DUP} GROUP BY 1 ORDER BY n DESC LIMIT 14"""):
        print(f"  {x['n']:>4}  ({x['cp']:>3} con plazo)  {x['sujeto'][:56]}")
    print("\n  normas que más obligaciones definen:")
    for x in q(f"""SELECT n.tipo, n.numero AS nnum, count(*) n FROM obligacion o
                  JOIN articulos a ON a.id=o.articulo_id JOIN normas n ON n.id_norma=a.id_norma
                  WHERE true{NO_DUP} GROUP BY 1,2 ORDER BY n DESC LIMIT 8"""):
        print(f"  {x['n']:>4}  {x['tipo']} {x['nnum']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sujeto"); ap.add_argument("--plazos", action="store_true")
    ap.add_argument("--procesos", action="store_true")
    ap.add_argument("--impacto")
    a = ap.parse_args()
    if a.procesos: procesos()
    elif a.sujeto: por_sujeto(a.sujeto)
    elif a.plazos: plazos()
    elif a.impacto: impacto(a.impacto)
    else: resumen()
