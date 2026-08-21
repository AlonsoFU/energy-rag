"""B3 — ingerir normas cuya parte dispositiva NO viene en artículos.

Los decretos tarifarios (precios de nudo, peajes) no tienen articulado: son un preámbulo
(Visto / Considerando) seguido de una parte dispositiva única con tablas de valores. El parser
de artículos no los ve, así que quedaban con 0 artículos y el retrieval nunca los alcanzaba —
justo el material que usa Transferencias de Mercado.

Se ingiere la PARTE DISPOSITIVA (lo que va después de "DECRETO:"), no el preámbulo: los
"Visto" son citas a otras normas, ruido para el retrieval. Se guarda como artículo `único`,
que es la convención para una norma sin articulado formal; la cita queda
"[Art. único de DECRETO 1]", honesta y verificable.

  PYTHONPATH=. venv/bin/python -m scripts.ingest_sin_articulado [--dry]
"""
import json
import math
import re
import sys
import urllib.request
from glob import glob
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

DISPOSITIVO = re.compile(r"\n\s*(?:DECRETO|RESUELVO|RESUELVE|ORDENO)\s*:?\s*\n", re.I)
OLLAMA = "http://localhost:11434/api/embed"


def _embed_4b(t):
    data = json.dumps({"model": "qwen3-embedding:4b", "input": [t]}).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        v = json.loads(r.read())["embeddings"][0]
    s = v[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def main(dry=False):
    from src.components.embedder import Qwen3Embedder
    from src.components.chunker import HierarchicalChunker

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT n.id_norma, n.tipo, n.numero, n.titulo FROM normas n
                       WHERE (SELECT count(*) FROM articulos a WHERE a.id_norma=n.id_norma)=0""")
        objetivo = {r["id_norma"]: r for r in cur.fetchall()}
    print(f"normas con 0 articulos: {len(objetivo)}", flush=True)

    textos = {}
    for f in glob("data/normas_completas/**/*.json", recursive=True):
        if f.endswith(".bak"):
            continue
        d = json.loads(Path(f).read_text())
        i = str(d.get("id_norma") or "")
        if i in objetivo:
            textos[i] = d.get("texto_completo") or ""

    chunker = HierarchicalChunker()
    emb = None if dry else Qwen3Embedder()
    n_art = n_frag = 0
    for nid, meta in objetivo.items():
        t = textos.get(nid, "")
        m = DISPOSITIVO.search(t)
        if not m:
            print(f"  {nid} {meta['tipo']} {meta['numero']}: sin parte dispositiva, salteo", flush=True)
            continue
        cuerpo = t[m.end():].strip()
        if len(cuerpo) < 300:
            print(f"  {nid}: dispositivo de {len(cuerpo)} chars, muy corto, salteo", flush=True)
            continue
        print(f"  {nid} {meta['tipo']} {meta['numero']}: dispositivo {len(cuerpo)} chars", flush=True)
        if dry:
            n_art += 1
            continue
        with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
            cur.execute("""INSERT INTO articulos (id_norma, numero, texto)
                           VALUES (%s,'único',%s) RETURNING id""", (nid, cuerpo))
            art_id = cur.fetchone()["id"]
            n_art += 1
            for ch in chunker.chunk(cuerpo):
                ctx = f"{meta['titulo']} — Artículo único. {ch.text}"
                cur.execute("""INSERT INTO fragmentos
                    (articulo_id, chunk_index, text, contextual_text,
                     embedding, embedding_4b_1024, token_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (art_id, ch.chunk_index, ch.text, ctx,
                     emb.embed([ctx])[0], _embed_4b(ctx), ch.token_count))
                n_frag += 1
            c.commit()
    print(f"\n=== articulos {n_art} · fragmentos {n_frag} "
          f"{'(DRY)' if dry else 'INGESTADOS'} ===", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
