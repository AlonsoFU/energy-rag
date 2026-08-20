"""B3 — re-ingerir el articulado de las normas que quedaron con 0 artículos.

Origen (exp #46): 17 normas del catálogo tienen 0 artículos ingestados, 12 de ellas del
dominio eléctrico. El retrieval NUNCA puede citarlas. Causa (exp #47): `ARTICULO_PATTERN`
no aceptaba encabezados precedidos de comilla ('"Artículo único.- Introdúcense…'), que es
como las leyes modificatorias transcriben su articulado.

Ingiere SOLO el articulado PROPIO. Los artículos `es_transcrito` se descartan a propósito:
son texto que la ley inserta en OTRA norma, y atribuírselos produciría una cita legalmente
falsa ("[Art. 20 de LEY 20701]" cuando ese artículo es de la LGSE).

Puebla las tres cosas que necesita el retrieval vigente:
  articulos · fragmentos(embedding 0.6B + tsv) · fragmentos.embedding_4b_1024 (MRL, HNSW)

  PYTHONPATH=. venv/bin/python -m scripts.reingest_faltantes [--dry]
"""
import json
import math
import sys
import urllib.request
from glob import glob
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

OLLAMA = "http://localhost:11434/api/embed"
MODELO_4B = "qwen3-embedding:4b"


def _embed_4b(textos):
    data = json.dumps({"model": MODELO_4B, "input": textos}).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["embeddings"]


def _mrl_1024(v):
    """Trunca a 1024 y renormaliza — igual que hace el retrieval (`embed_4b_dim=1024`)."""
    s = v[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def normas_sin_articulos():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.id_norma, n.tipo, n.numero, n.titulo
            FROM normas n
            WHERE (SELECT count(*) FROM articulos a WHERE a.id_norma = n.id_norma) = 0
            ORDER BY n.id_norma
        """)
        return cur.fetchall()


def main(dry=False):
    from src.components.embedder import Qwen3Embedder
    from src.components.chunker import HierarchicalChunker
    from src.parsers.norm_structure_parser import NormStructureParser

    objetivo = {r["id_norma"]: r for r in normas_sin_articulos()}
    print(f"normas con 0 articulos: {len(objetivo)}", flush=True)

    textos = {}
    for f in glob("data/normas_completas/**/*.json", recursive=True):
        if f.endswith(".bak"):
            continue
        d = json.loads(Path(f).read_text())
        i = str(d.get("id_norma") or "")
        if i in objetivo:
            textos[i] = d.get("texto_completo") or ""
    print(f"con JSON en disco: {len(textos)}", flush=True)

    parser = NormStructureParser()
    chunker = HierarchicalChunker()
    emb = None if dry else Qwen3Embedder()

    total_art = total_frag = 0
    for nid, meta in objetivo.items():
        t = textos.get(nid)
        if not t:
            print(f"  {nid}: SIN JSON, salteo", flush=True)
            continue
        arts = parser._extract_articulos(t, [])
        propios = {k: a for k, a in arts.items() if not a.es_transcrito}
        desc = len(arts) - len(propios)
        if not propios:
            print(f"  {nid} {meta['tipo']} {meta['numero']}: 0 propios "
                  f"({desc} transcritos) -- sin articulado propio", flush=True)
            continue
        print(f"  {nid} {meta['tipo']} {meta['numero']}: {len(propios)} propios, "
              f"{desc} transcritos descartados", flush=True)
        if dry:
            total_art += len(propios)
            continue

        with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
            for num, a in propios.items():
                cur.execute("""INSERT INTO articulos (id_norma, numero, texto)
                               VALUES (%s,%s,%s) RETURNING id""", (nid, num, a.texto))
                art_id = cur.fetchone()["id"]
                total_art += 1
                for ch in chunker.chunk(a.texto):
                    ctx = f"{meta['titulo']} — Artículo {num}. {ch.text}"
                    v06 = emb.embed([ctx])[0]
                    v4b = _mrl_1024(_embed_4b([ctx])[0])
                    cur.execute("""
                        INSERT INTO fragmentos
                          (articulo_id, chunk_index, text, contextual_text,
                           embedding, embedding_4b_1024, token_count)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (art_id, ch.chunk_index, ch.text, ctx, v06, v4b, ch.token_count))
                    total_frag += 1
            c.commit()

    print(f"\n=== articulos {total_art} · fragmentos {total_frag} "
          f"{'(DRY, nada escrito)' if dry else 'INGESTADOS'} ===", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
