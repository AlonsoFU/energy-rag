"""Resolve the authoritative defining norm for multi-defined concepts (B1).

A term defined in >1 norma is resolved by RANK → FECHA → conflict (see
src/extraction/authority.py). Rank comes from the TITLE, not the unreliable
`tipo` (src/extraction/norm_rank.py). Writes per concept:
  - resolved → metadata.authoritative = {id_norma, articulo}
  - conflict → metadata.authority_conflict = [{id_norma, articulo}, ...]
plus metadata.authority_resolved provenance (idempotency marker).

Runs in ingestion AFTER canonicalize_concepts.py. Idempotent: re-running
recomputes from current edges and rewrites the same result; a concept whose
candidates are unchanged yields no diff. Default DRY-RUN; --apply writes.

Run:  PYTHONPATH=. ./venv/bin/python scripts/resolve_authority.py
      PYTHONPATH=. ./venv/bin/python scripts/resolve_authority.py --apply
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from psycopg.rows import dict_row

from src.extraction.authority import select_authoritative
from src.extraction.norm_rank import derive_rank
from src.storage.connection import with_connection

SQL = """
SELECT c.id AS concepto_id, c.nombre,
       a.id_norma, a.numero AS articulo,
       n.tipo, n.titulo, n.fecha_publicacion
FROM conceptos c
JOIN referencias r ON r.destino_concepto_id = c.id
                  AND r.tipo_relacion = 'define_termino'
JOIN articulos a ON a.id = r.origen_articulo_id
JOIN normas n ON n.id_norma = a.id_norma
ORDER BY c.id, a.id_norma, a.numero
"""


def build_candidates(rows: list[dict]) -> list[dict]:
    """One candidate per distinct norma (first defining article), with rank.

    Collapsing per norma avoids spurious conflicts when a single norma defines
    the term in more than one article (same rank + same fecha would otherwise
    look like a tie between two articles of the same source).
    """
    seen: dict[str, dict] = {}
    for r in rows:
        if r["id_norma"] in seen:
            continue
        rank, _flag = derive_rank(r["tipo"], r["titulo"])
        fecha = r["fecha_publicacion"]
        seen[r["id_norma"]] = {
            "id_norma": r["id_norma"],
            "articulo": r["articulo"],
            "rank": rank,
            "fecha": fecha.isoformat() if fecha else None,
        }
    return list(seen.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write metadata to DB (default: dry-run)")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL)
        by_concept: dict[tuple, list[dict]] = defaultdict(list)
        for row in cur.fetchall():
            by_concept[(row["concepto_id"], row["nombre"])].append(row)

        resolved: list[dict] = []
        conflicts: list[dict] = []
        for (cid, nombre), rows in by_concept.items():
            cands = build_candidates(rows)
            if len(cands) < 2:
                continue  # single-norma: trivial, inject already handles it
            result = select_authoritative(cands)
            if result["status"] == "resolved":
                resolved.append({"id": cid, "nombre": nombre,
                                 "id_norma": result["id_norma"],
                                 "articulo": result["articulo"]})
            elif result["status"] == "conflict":
                conflicts.append({"id": cid, "nombre": nombre,
                                  "candidates": result["candidates"]})

        print(f"multi-defined concepts: {len(resolved)+len(conflicts)} "
              f"| resolved: {len(resolved)} | conflict: {len(conflicts)}")
        for x in resolved:
            print(f"  ✓ {x['nombre']!r} → norma {x['id_norma']} art {x['articulo']}")
        for x in conflicts:
            print(f"  ⚠ CONFLICT {x['nombre']!r} → {x['candidates']}")

        if not args.apply:
            print("\n--dry-run: nothing written. Use --apply.")
            return

        for x in resolved:
            cur.execute(
                "UPDATE conceptos SET metadata = "
                "coalesce(metadata,'{}'::jsonb) || %(meta)s::jsonb WHERE id = %(id)s",
                {"id": x["id"], "meta": json.dumps({
                    "authoritative": {"id_norma": x["id_norma"], "articulo": x["articulo"]},
                    "authority_conflict": None,
                    "authority_resolved": {"metodo": "rank_fecha", "regla": "B1"}})},
            )
        for x in conflicts:
            cur.execute(
                "UPDATE conceptos SET metadata = "
                "coalesce(metadata,'{}'::jsonb) || %(meta)s::jsonb WHERE id = %(id)s",
                {"id": x["id"], "meta": json.dumps({
                    "authoritative": None,
                    "authority_conflict": x["candidates"],
                    "authority_resolved": {"metodo": "rank_fecha", "regla": "B1"}})},
            )
        conn.commit()
        print(f"\nApplied: {len(resolved)} authoritative + {len(conflicts)} conflict markers.")


if __name__ == "__main__":
    main()
