"""Re-ingest the FULL LGSE (id_norma 258171) from the BCN obtxml XML.

Why: the LGSE was only partially ingested (arts 1-8); the targets of dozens of
remissions ("artículo N de la Ley") and AVI's method (art 104/118) and the Panel
de Expertos (Título VI) were missing. The BCN page-scrape truncated it; the fix
is the structured `obtxml` endpoint + a browser User-Agent (BCN 401s without one).

This script:
  1. parses the obtxml into (numero, texto) articles,
  2. DELETES the old 258171 articulos (CASCADE drops their fragmentos+referencias),
  3. re-ingests each via the real IngestPipeline (upsert + chunk + embed → GPU) and
     extracts references (concept/positional/regex), scoped to 258171 only.

Download (no browser needed):
  UA='Mozilla/5.0 ...'; curl -A "$UA" -H 'Referer: https://www.bcn.cl/leychile' \
      'https://www.bcn.cl/leychile/Consulta/obtxml?opt=7&idNorma=258171' -o <xml>

Run:  PYTHONPATH=. ./venv/bin/python scripts/ingest_lgse.py --xml /tmp/bcn/lgse_258171.xml [--apply]
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET

from psycopg.rows import dict_row

from src.storage.connection import with_connection, close_pool

NS = {"n": "http://www.leychile.cl/esquemas"}
ID_NORMA = "258171"
_ART_RE = re.compile(r"Art[íi]culo\s+([\w°º]+(?:\s+(?:bis|ter|quáter|qu1nquies))?)\s*[.\-]", re.I)


def parse_articulos(xml_path: str) -> list[tuple[str, str]]:
    """Return [(numero, texto)] from the obtxml. The article number lives at the
    START of each EstructuraFuncional's <Texto> ("Artículo N°.- ...")."""
    root = ET.fromstring(open(xml_path, encoding="utf-8").read())
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for p in root.findall(".//n:EstructuraFuncional", NS):
        e = p.find("n:Texto", NS)
        txt = (e.text if e is not None and e.text else "").strip()
        if not txt:
            continue
        m = _ART_RE.match(txt)
        if not m:
            continue
        num = m.group(1).strip().replace("°", "").replace("º", "")
        # de-dup: same article can appear twice (consolidated + original tag)
        if num in seen:
            continue
        seen.add(num)
        out.append((num, txt))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--apply", action="store_true", help="write to DB + embed (default dry-run)")
    args = ap.parse_args()

    arts = parse_articulos(args.xml)
    print(f"parseados: {len(arts)} artículos (num {arts[0][0]}..{arts[-1][0]})")
    for tgt in ("90", "104", "108", "118"):
        hit = next((t for n, t in arts if n == tgt), None)
        print(f"  art {tgt}: {'OK ' + hit[:60] if hit else 'FALTA'}")

    close_pool()
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT count(*) c FROM articulos WHERE id_norma=%s", (ID_NORMA,))
        old = cur.fetchone()["c"]
    print(f"\nartículos 258171 actuales en DB (se borrarán): {old}")

    if not args.apply:
        print("\n--dry-run: nada escrito. Usa --apply (GPU: embebe los nuevos).")
        return

    # 1) borrar los viejos (CASCADE limpia fragmentos + referencias de esos arts)
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM articulos WHERE id_norma=%s", (ID_NORMA,))
        conn.commit()
    print(f"borrados {old} articulos viejos (+ sus fragmentos/referencias por cascade)")

    # 2) pipeline real (GPU) — sin enriquecimiento contextual (rápido, sin LLM)
    from src.components.embedder import Qwen3Embedder
    from src.pipelines.ingest import IngestPipeline
    from src.components.chunker import HierarchicalChunker
    from src.core.models import Articulo, Norma
    from scripts.embed_all import _NoOpEnricher, _build_catalogo_from_db, _fetch_conceptos, _fetch_siblings
    from src.components.vectorstore import PostgresStore

    store = PostgresStore()
    catalogo = _build_catalogo_from_db(store)
    conceptos = _fetch_conceptos()
    pipe = IngestPipeline(store=store, embedder=Qwen3Embedder(),
                          enricher=_NoOpEnricher(), chunker=HierarchicalChunker(),
                          catalogo=catalogo)
    norma = Norma(id_norma=ID_NORMA, tipo="DFL", numero="4",
                  titulo="DFL 4/20018 FIJA TEXTO REFUNDIDO, COORDINADO Y SISTEMATIZADO LGSE")

    frg = refs = 0
    for i, (num, txt) in enumerate(arts, 1):
        a = Articulo(id_norma=ID_NORMA, numero=num, texto=txt, orden=i)
        a_id = pipe.ingest_articulo(a, norma)
        frg += len(pipe.chunker.chunk(txt))
        sib = _fetch_siblings(ID_NORMA)
        refs += pipe.extract_references_for_articulo(
            articulo_id=a_id, articulo_text=txt, origen_norma_id=ID_NORMA,
            siblings=sib, conceptos=conceptos)
        if i % 50 == 0:
            print(f"  {i}/{len(arts)} … fragmentos~{frg} refs~{refs}")
    print(f"\nLISTO: {len(arts)} arts, ~{frg} fragmentos, {refs} referencias.")


if __name__ == "__main__":
    main()
