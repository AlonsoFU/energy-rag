"""E1 — ingerir las candidatas descargadas, con DOS validaciones antes de tocar la DB.

`bajar_candidatas.py` resuelve tipo+numero -> idNorma con el buscador de BCN, que busca SOLO
por numero. Resultado medido: 9 de 24 descargas eran otra norma —
`DECRETO 42` devolvio `ACUERDO 42`, `DL 2763` un acta de sesion, `DFL 850` un extracto.
Ingerirlas habria metido documentos ajenos con la etiqueta equivocada.

Dos filtros, en orden:

  1. IDENTIDAD — el titulo de lo bajado tiene que empezar con el tipo y numero que se pidio.
     Si no coincide, no se ingiere (queda el JSON para revisar a mano).
  2. DOMINIO — se mide contra las funciones de la subgerencia por ARTICULADO, igual que el
     resto del corpus. Las que no pasan el corte 0.30 se ingieren MARCADAS
     `fuera_de_dominio`, no se descartan: pueden ser citadas y el grafo las necesita.

  PYTHONPATH=. venv/bin/python -m scripts.ingerir_nuevas [--dry]
"""
import glob
import json
import math
import re
import sys
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.pipelines.retrieve import _embed_4b_query
from src.parsers.norm_structure_parser import NormStructureParser
from scripts.frontera_mercados import DOMINIO

CORTE = 0.30
DIR = Path("data/normas_completas/nuevas")
EST = Path("data/eval/results/candidatas_bajadas.json")


def _v(t):
    e = _embed_4b_query(t)
    if not e:
        return None
    s = e[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def identidad_ok(pedido: str, titulo: str) -> bool:
    """El titulo bajado debe declarar el mismo tipo y numero que se pidio."""
    if "-" not in pedido:
        return False
    tb, nb = pedido.split("-", 1)
    m = re.match(r"\s*(LEY|DECRETO|DFL|DL|RESOLUCI[OÓ]N|ACUERDO)\s+([\d\.]+)", titulo or "", re.I)
    if not m:
        return False
    return (m.group(1).upper().startswith(tb[:3].upper())
            and m.group(2).replace(".", "") == nb.replace(".", ""))


def main(dry=False):
    from src.components.embedder import Qwen3Embedder
    from src.components.chunker import HierarchicalChunker

    est = json.loads(EST.read_text())
    pedido_de = {v["id_norma"]: k for k, v in est.items() if v.get("id_norma")}
    ref = _v(re.sub(r"\s+", " ", DOMINIO).strip())
    parser, chunker = NormStructureParser(), HierarchicalChunker()
    emb = None if dry else Qwen3Embedder()

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma FROM normas")
        ya = {r["id_norma"] for r in cur.fetchall()}

    n_ok = n_id = n_dom = n_art = 0
    for f in sorted(glob.glob(str(DIR / "*.json"))):
        d = json.loads(Path(f).read_text())
        nid, tit = d["id_norma"], str(d.get("titulo") or "")
        ped = pedido_de.get(nid, "?")
        if nid in ya:
            print(f"  {ped:14} ya en el corpus, salteo", flush=True); continue
        if not identidad_ok(ped, tit):
            n_id += 1
            print(f"  {ped:14} ✗ IDENTIDAD: bajo '{tit[:44]}'", flush=True); continue

        arts = {k: a for k, a in parser._extract_articulos(d.get("texto_completo") or "", []).items()
                if not a.es_transcrito}
        muestra = " ".join(a.texto for a in list(arts.values())[:3])[:1200]
        base = muestra if len(muestra) > 200 else tit[:400]
        v = _v(base)
        sim = sum(x * y for x, y in zip(ref, v)) if v else 0.0
        fuera = sim < CORTE
        if fuera:
            n_dom += 1
        n_ok += 1
        print(f"  {ped:14} sim={sim:.3f} {'FUERA' if fuera else 'dentro'}  "
              f"{len(arts)} arts  {tit[:38]}", flush=True)
        if dry:
            continue

        meta = {"url": d.get("url"), "content_hash": d.get("content_hash"),
                "estado": d.get("estado"), "versiones": d.get("versiones"),
                "origen": "descubrimiento_2026-08-23", "similitud_dominio": f"{sim:.3f}"}
        if fuera:
            meta["fuera_de_dominio"] = True
        with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
            cur.execute("""INSERT INTO normas (id_norma, tipo, numero, titulo, texto_completo, metadata)
                           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id_norma) DO NOTHING""",
                        (nid, d.get("tipo") or ped.split("-")[0], d.get("numero") or ped.split("-")[1],
                         tit, d.get("texto_completo"), json.dumps(meta)))
            for num, a in arts.items():
                cur.execute("""INSERT INTO articulos (id_norma, numero, texto)
                               VALUES (%s,%s,%s) RETURNING id""", (nid, num, a.texto))
                aid = cur.fetchone()["id"]
                n_art += 1
                for ch in chunker.chunk(a.texto):
                    ctx = f"{tit} — Artículo {num}. {ch.text}"
                    e4 = _embed_4b_query(ctx)
                    s4 = e4[:1024]
                    nn = math.sqrt(sum(x * x for x in s4)) or 1.0
                    cur.execute("""INSERT INTO fragmentos
                        (articulo_id, chunk_index, text, contextual_text,
                         embedding, embedding_4b_1024, token_count)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (aid, ch.chunk_index, ch.text, ctx, emb.embed([ctx])[0],
                         [x / nn for x in s4], ch.token_count))
            c.commit()

    print(f"\n=== validas {n_ok} · rechazadas por identidad {n_id} · "
          f"marcadas fuera de dominio {n_dom} · articulos {n_art} "
          f"{'(DRY)' if dry else 'INGESTADOS'} ===", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
