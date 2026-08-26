"""Reemplazar el contenido de una norma YA ingerida, cuando su texto cambió o estaba truncado.

`ingerir_nuevas` sólo da de ALTA: si la norma ya está en `normas`, la saltea. Eso deja dos
agujeros:

  1. **Scrapes truncados.** BCN sirve el articulado con render perezoso y a veces entrega el
     documento a medias. Hay 19 normas en el corpus con el placeholder `Loading` — 9 de ellas
     dentro del dominio. El `DECRETO 125` (Reglamento de Coordinación y Operación del SEN)
     estaba guardado con **14.919 caracteres y 4 artículos**; re-bajado con el crawler que
     hace scroll y espera 5 lecturas estables, da **226.949 caracteres**.
  2. **El monitor no puede aplicar lo que detecta.** Sabe decir "esta norma cambió" y ahí se
     queda: sin camino de actualización, el corpus sigue con el texto viejo.

**Es destructivo y por eso valida antes de borrar:** identidad (tipo y número declarados por
la norma bajada) y que el texto nuevo NO sea más corto que el guardado. Un scrape a medias se
ve igual que una derogación masiva, y sustituir un texto bueno por uno truncado es peor que no
actualizar. `--permitir-encoger` levanta esa segunda guarda para el caso legítimo en que una
norma sí se achica.

  PYTHONPATH=. venv/bin/python -m scripts.actualizar_norma 1140253 [--aplicar]
"""
import argparse
import json
import math
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.parsers.norm_structure_parser import NormStructureParser
from scripts.bajar_candidatas import identidad_ok
from scripts.marcar_fuera_dominio import _embed_4b_query

DIR = Path("data/normas_completas/nuevas")
TOLERANCIA = 0.90       # el texto nuevo no puede ser < 90% del guardado sin permiso explicito


class _D:
    """Adapta el JSON bajado a lo que espera `identidad_ok`."""
    def __init__(self, d):
        self.tipo = d.get("tipo")
        self.numero = d.get("numero")
        self.titulo = d.get("titulo")


def main(nid, aplicar=False, permitir_encoger=False):
    f = DIR / f"{nid}.json"
    if not f.exists():
        print(f"no existe {f} — bajarla primero con scripts.bajar_por_id")
        return
    d = json.loads(f.read_text())
    nuevo = d.get("texto_completo") or ""

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo, texto_completo FROM normas WHERE id_norma=%s",
                    (nid,))
        vieja = cur.fetchone()
    if not vieja:
        print(f"{nid} no esta en el corpus — esto es un ALTA, usar scripts.ingerir_nuevas")
        return

    ped = f"{vieja['tipo']}-{vieja['numero']}"
    if not identidad_ok(vieja["tipo"], vieja["numero"], _D(d)):
        print(f"RECHAZADO identidad: en corpus {ped}, el JSON dice "
              f"{d.get('tipo')} {d.get('numero')}")
        return

    largo_viejo = len(vieja["texto_completo"] or "")
    print(f"{ped} ({nid})")
    print(f"  texto guardado : {largo_viejo:>8}")
    print(f"  texto nuevo    : {len(nuevo):>8}")
    if len(nuevo) < 500:
        print("  ABORTA: el texto nuevo es demasiado corto para ser real")
        return
    if largo_viejo and len(nuevo) < largo_viejo * TOLERANCIA and not permitir_encoger:
        print(f"  ABORTA: el texto nuevo es <{TOLERANCIA:.0%} del guardado. Un scrape a medias se ve")
        print("          igual que una derogacion masiva. Usar --permitir-encoger si es real.")
        return

    arts = {k: a for k, a in
            NormStructureParser._extract_articulos(NormStructureParser(), nuevo, []).items()
            if not a.es_transcrito}
    with with_connection() as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM articulos WHERE id_norma=%s", (nid,))
        n_viejos = cur.fetchone()[0]
    print(f"  articulos      : {n_viejos} -> {len(arts)}")
    if not arts:
        print("  ABORTA: el parser no encontro articulos en el texto nuevo")
        return
    # Segunda guarda, y hace falta aparte de la del texto: el DFL 4 (la LGSE) tiene el
    # texto_completo truncado a 10.075 chars PERO 330 articulos buenos, parseados de otra
    # pasada. Ahi el texto nuevo crece —pasa la guarda de arriba— y aun asi el reemplazo
    # destruiria 330 articulos para dejar los pocos que el parser saque. Perder articulos
    # de la norma mas citada del corpus es el peor resultado posible de una "mejora".
    if n_viejos and len(arts) < n_viejos * TOLERANCIA and not permitir_encoger:
        print(f"  ABORTA: pasaria de {n_viejos} a {len(arts)} articulos (<{TOLERANCIA:.0%}).")
        print("          El texto puede crecer y el ARTICULADO encoger igual. Revisar a mano.")
        return

    if not aplicar:
        print("\n(simulacion — usar --aplicar para reemplazar)")
        return

    from src.components.chunker import HierarchicalChunker
    from src.components.embedder import Qwen3Embedder
    emb, chunker = Qwen3Embedder(), HierarchicalChunker()
    tit = vieja["titulo"] or ""

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        # Orden de borrado: primero lo que apunta a `articulos`, despues los articulos.
        cur.execute("""DELETE FROM fragmentos WHERE articulo_id IN
                       (SELECT id FROM articulos WHERE id_norma=%s)""", (nid,))
        n_frag = cur.rowcount
        cur.execute("""DELETE FROM obligacion WHERE articulo_id IN
                       (SELECT id FROM articulos WHERE id_norma=%s)""", (nid,))
        n_obl = cur.rowcount
        cur.execute("""DELETE FROM fragmentos_definicion WHERE articulo_id IN
                       (SELECT id FROM articulos WHERE id_norma=%s)""", (nid,))
        n_def = cur.rowcount
        cur.execute("""DELETE FROM referencias WHERE origen_articulo_id IN
                       (SELECT id FROM articulos WHERE id_norma=%s)""", (nid,))
        n_ref = cur.rowcount
        cur.execute("DELETE FROM articulos WHERE id_norma=%s", (nid,))
        cur.execute("UPDATE normas SET texto_completo=%s, updated_at=now() WHERE id_norma=%s",
                    (nuevo, nid))
        print(f"  borrados: {n_frag} fragmentos · {n_obl} obligaciones · {n_def} definiciones "
              f"· {n_ref} referencias", flush=True)

        n_art = 0
        for num, a in arts.items():
            cur.execute("INSERT INTO articulos (id_norma, numero, texto) VALUES (%s,%s,%s) RETURNING id",
                        (nid, num, a.texto))
            aid = cur.fetchone()["id"]
            n_art += 1
            for ch in chunker.chunk(a.texto):
                ctx = f"{tit} — Artículo {num}. {ch.text}"
                e4 = _embed_4b_query(ctx)
                s4 = (e4 or [0.0])[:1024]
                nn = math.sqrt(sum(x * x for x in s4)) or 1.0
                cur.execute("""INSERT INTO fragmentos
                    (articulo_id, chunk_index, text, contextual_text,
                     embedding, embedding_4b_1024, token_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (aid, ch.chunk_index, ch.text, ctx, emb.embed([ctx])[0],
                     [x / nn for x in s4], ch.token_count))
        c.commit()
    print(f"\nACTUALIZADA {ped}: {n_art} articulos ingestados")
    print("  ⚠️ hay que volver a correr: duplicados · derogaciones · proceso · obligaciones · citas")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("id_norma")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--permitir-encoger", action="store_true")
    a = ap.parse_args()
    main(a.id_norma, a.aplicar, a.permitir_encoger)
