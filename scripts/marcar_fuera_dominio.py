"""B3.1 — marcar las normas fuera del dominio de la Subgerencia de Mercados.

Corte fijado por el usuario (2026-08-22): **similitud < 0.30** contra las funciones de la
subgerencia (ver `scripts/frontera_mercados.py`).

**MARCA, no borra.** Poner `metadata.fuera_de_dominio = true` es reversible; un DELETE de
normas + articulos + fragmentos no lo es, y el criterio es semantico (puede fallar en un
titulo mal escrito). El retrieval filtra por la marca.

  PYTHONPATH=. venv/bin/python -m scripts.marcar_fuera_dominio [--aplicar]
"""
import math
import re
import sys

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.pipelines.retrieve import _embed_4b_query
from scripts.frontera_mercados import DOMINIO

CORTE = 0.30

# Un titulo que solo repite "{tipo} {numero}" no describe nada: puntua bajo por FALTA DE DATO,
# no por ser ajeno. Marcarlo seria podar una norma del dominio por un scrape incompleto.
# Detectado en LEY 21647, DECRETO 130, LEY 20999, LEY 21527.
_TITULO_VACIO = re.compile(r"^\s*(ley|decreto|dfl|dl|resoluci[oó]n)\s*n?[°ºo]?\s*[\d\.]+\s*$", re.I)


def _v(t):
    e = _embed_4b_query(t)
    if not e:
        return None
    s = e[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def main(aplicar=False):
    ref = _v(re.sub(r"\s+", " ", DOMINIO).strip())
    # Se clasifica por el ARTICULADO, no por el titulo. El titulo legal chileno arranca con
    # una formula burocratica identica entre normas de materias distintas ("FIJA TEXTO
    # REFUNDIDO, COORDINADO Y SISTEMATIZADO DE..."), y esa formula DOMINA el embedding.
    # Medido: DFL 1 (Ley de TRANSITO) daba 0.316 por titulo -- dentro del corte -- y da 0.197
    # por articulado; DFL 4 (LGSE) sube de 0.409 a 0.549. Por titulo caian del mismo lado.
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.id_norma, n.tipo, n.numero, n.titulo,
                   (SELECT string_agg(a.texto, ' ')
                      FROM (SELECT texto FROM articulos
                             WHERE id_norma = n.id_norma ORDER BY id LIMIT 3) a) AS muestra
            FROM normas n""")
        normas = cur.fetchall()

    fuera, sin_titulo, puntuadas = [], [], []
    for n in normas:
        t = str(n["titulo"] or "").strip()
        if (not t or _TITULO_VACIO.match(t)) and len((n.get("muestra") or "")) < 200:
            sin_titulo.append(n)          # sin titulo NI articulado: no hay evidencia
            continue
        muestra = (n.get("muestra") or "").strip()
        base = muestra[:1200] if len(muestra) > 200 else t[:400]   # articulado si lo hay
        v = _v(base)
        sim = sum(x * y for x, y in zip(ref, v)) if v else 0.0
        puntuadas.append((sim, n))          # se guarda el puntaje de TODAS, no solo las que salen
        if sim < CORTE:
            fuera.append((sim, n))
    fuera.sort()
    if sin_titulo:
        print(f"⚠️ {len(sin_titulo)} normas SIN titulo descriptivo -> NO se clasifican "
              f"(puntuarian bajo por falta de dato, no por ser ajenas):")
        for n in sin_titulo:
            print(f"     {n['id_norma']:>9} {n['tipo']} {n['numero']}")
        print()
    print(f"corte {CORTE} -> {len(fuera)} de {len(normas)} normas quedan FUERA del dominio\n")
    for s, n in fuera:
        print(f"   {s:.3f}  {n['tipo']:<10} {str(n['numero']):>6}  {str(n['titulo'])[:60]}")

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        ids = tuple(n["id_norma"] for _s, n in fuera)
        cur.execute("""SELECT count(*) a FROM articulos WHERE id_norma = ANY(%s)""", (list(ids),))
        na = cur.fetchone()["a"]
        cur.execute("""SELECT count(*) f FROM fragmentos fr JOIN articulos a ON a.id=fr.articulo_id
                       WHERE a.id_norma = ANY(%s)""", (list(ids),))
        nf = cur.fetchone()["f"]
    print(f"\n  arrastran {na} articulos y {nf} fragmentos")

    if not aplicar:
        print("\n(DRY — nada escrito. Correr con --aplicar)")
        return 0

    with with_connection() as c, c.cursor() as cur:
        # El puntaje se guarda para TODAS las clasificadas, no solo para las que quedan fuera.
        # Sin esto solo 60 de 122 normas tenian `similitud_dominio` y no se podia auditar la
        # decision, ni probar otro corte sin volver a embeber el corpus entero.
        for s, n in puntuadas:
            cur.execute("""UPDATE normas SET metadata = coalesce(metadata,'{}'::jsonb)
                           || jsonb_build_object('similitud_dominio', %s::text)
                           WHERE id_norma = %s""", (f"{s:.3f}", n["id_norma"]))
        for s, n in fuera:
            cur.execute("""UPDATE normas SET metadata = coalesce(metadata,'{}'::jsonb)
                             || jsonb_build_object('fuera_de_dominio', true)
                             || jsonb_build_object('similitud_dominio', %s::text)
                             || jsonb_build_object('marcado_en','2026-08-22')
                           WHERE id_norma = %s""", (f"{s:.3f}", n["id_norma"]))
        c.commit()
    print(f"\nMARCADAS {len(fuera)} normas con metadata.fuera_de_dominio = true (reversible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(aplicar="--aplicar" in sys.argv))
