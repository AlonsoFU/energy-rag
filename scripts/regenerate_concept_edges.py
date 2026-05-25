"""Add the concept→cita edges that the dotted-acronym fix now matches (CPU-only).

The old `\\b..\\b` matcher missed acronyms ending/starting in punctuation
(A.V.I., V.A.T.T., V.I., C.O.M.A., A.E.I.R.), so those concepts had no `cita`
edges to the articles that use them — making their substantive article
unreachable to the definition resolver. This re-runs `extract_concept_refs`
(now using whole_term_pattern) over every articulo and inserts ONLY the edges
that don't already exist. Purely additive: no embeddings, no deletes, no dups.

Run:  PYTHONPATH=. ./venv/bin/python scripts/regenerate_concept_edges.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import re

from psycopg.rows import dict_row

from src.extraction.concept_refs import extract_concept_refs
from src.storage.connection import with_connection


def _broken_under_old_matcher(term: str) -> bool:
    """True iff the OLD `\\b..\\b` matcher couldn't even match the term inside its
    own padded text — i.e. exactly the terms the dotted-acronym bug silenced
    (A.V.I., V.A.T.T., …). Generic words like 'Ley' match fine → excluded, so we
    only add the edges the fix was meant to recover. General, not a hardcoded list.
    """
    if not term:
        return False
    old = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    return old.search(f" {term} ") is None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write missing edges (default dry-run)")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, nombre, aliases FROM conceptos")
        # Only concepts the dotted-acronym bug actually broke: keep a name/alias
        # iff the old matcher failed on it (so 'Ley' & co. are excluded → no noise).
        conceptos = []
        for r in cur.fetchall():
            names = [r["nombre"]] + (r.get("aliases") or [])
            broken = [n for n in names if n and _broken_under_old_matcher(n)]
            if broken:
                # match ONLY the broken forms (not a normal nombre with a dotted alias)
                conceptos.append({"id": r["id"], "nombre": broken[0], "aliases": broken[1:]})
        print(f"conceptos afectados por el bug de acrónimo: {len(conceptos)}")
        cur.execute("SELECT id, id_norma, texto FROM articulos WHERE texto IS NOT NULL")
        articulos = cur.fetchall()
        cur.execute("SELECT origen_articulo_id, destino_concepto_id FROM referencias "
                    "WHERE tipo_relacion='cita' AND destino_concepto_id IS NOT NULL")
        existing = {(r["origen_articulo_id"], r["destino_concepto_id"]) for r in cur.fetchall()}

        new_edges = []
        for a in articulos:
            for er in extract_concept_refs(a["texto"], a["id"], a["id_norma"], conceptos):
                key = (a["id"], er.destino_concepto_id)
                if key in existing:
                    continue
                existing.add(key)  # avoid dup within this run
                new_edges.append(er)

        by_concept: dict[int, int] = {}
        for er in new_edges:
            by_concept[er.destino_concepto_id] = by_concept.get(er.destino_concepto_id, 0) + 1
        # name lookup for reporting
        names = {c["id"]: c["nombre"] for c in conceptos}
        print(f"aristas concepto→cita NUEVAS: {len(new_edges)} "
              f"(sobre {len(by_concept)} conceptos)")
        for cid, n in sorted(by_concept.items(), key=lambda x: -x[1])[:15]:
            print(f"  +{n:3}  {names.get(cid,'?')[:40]} (id {cid})")

        if not args.apply:
            print("\n--dry-run: nada escrito. Usa --apply.")
            return

        for er in new_edges:
            # origen_norma_id must be NULL when origen_articulo_id is set (CHECK:
            # exactly one origin). The norma is derived via JOIN in the view.
            cur.execute(
                "INSERT INTO referencias (origen_articulo_id, origen_norma_id, "
                "destino_concepto_id, tipo_relacion, confianza, metodo_extraccion, "
                "contexto, metadata) VALUES (%s,NULL,%s,'cita',%s,'regex',%s,%s::jsonb)",
                (er.origen_articulo_id, er.destino_concepto_id,
                 er.confianza, er.contexto, json.dumps(er.metadata)))
        conn.commit()
        print(f"\nInsertadas {len(new_edges)} aristas nuevas.")


if __name__ == "__main__":
    main()
