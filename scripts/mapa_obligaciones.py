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
             WHERE {SUJ_NORM} LIKE lower(%s)
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
             WHERE o.plazo IS NOT NULL ORDER BY o.sujeto""")
    con_fecha = [x for x in r if _FECHA.search(x["plazo"] or "")]
    print(f"\n=== obligaciones con plazo — {len(r)} ({len(con_fecha)} con fecha o duración) ===")
    for x in con_fecha[:40]:
        print(f"  {x['sujeto'][:26]:28} ⏱ {x['plazo'][:40]:42} "
              f"[{x['tipo']} {x['nnum']} art {x['art']}]")
        print(f"      {x['accion'][:96]}")


def impacto(nid):
    r = q("""SELECT count(*) n FROM obligacion o
             JOIN articulos a ON a.id = o.articulo_id WHERE a.id_norma = %s""", nid)
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
    print("\n  ⚠️ las obligaciones de esas normas pueden depender de lo que cambie.")


def resumen():
    t = q("SELECT count(*) n FROM obligacion")[0]["n"]
    cp = q("SELECT count(*) n FROM obligacion WHERE plazo IS NOT NULL")[0]["n"]
    print(f"\n=== mapa de obligaciones — {t} obligaciones, {cp} con plazo ===")
    for x in q(f"""SELECT {SUJ_NORM} AS sujeto, count(*) n, count(o.plazo) cp
                   FROM obligacion o GROUP BY 1 ORDER BY n DESC LIMIT 14"""):
        print(f"  {x['n']:>4}  ({x['cp']:>3} con plazo)  {x['sujeto'][:56]}")
    print("\n  normas que más obligaciones definen:")
    for x in q("""SELECT n.tipo, n.numero AS nnum, count(*) n FROM obligacion o
                  JOIN articulos a ON a.id=o.articulo_id JOIN normas n ON n.id_norma=a.id_norma
                  GROUP BY 1,2 ORDER BY n DESC LIMIT 8"""):
        print(f"  {x['n']:>4}  {x['tipo']} {x['nnum']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sujeto"); ap.add_argument("--plazos", action="store_true")
    ap.add_argument("--impacto")
    a = ap.parse_args()
    if a.sujeto: por_sujeto(a.sujeto)
    elif a.plazos: plazos()
    elif a.impacto: impacto(a.impacto)
    else: resumen()
