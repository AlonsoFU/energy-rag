"""Generate `define_termino` edges from concepts.yaml source fields.

For every validated concept in the electricidad domain, look up the
articulo whose (id_norma, numero) matches concept.source.{norm_id, article}
and insert a referencia row:
    origen_articulo_id = articulo.id
    destino_concepto_id = concepto.id
    tipo_relacion = 'define_termino'
    metodo_extraccion = 'glossary_yaml'

This gives the graph_boost step a 2.0× factor on the defining article so
it can outrank generic 'cita' edges (1.3×). Without this, all candidates
mentioning the concept get the same uniform boost and the alias detection
has no effect on ranking.

Run:
    python scripts/load_define_termino_edges.py --dry-run
    python scripts/load_define_termino_edges.py
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.components.vectorstore import with_connection
from psycopg.rows import dict_row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(ROOT / "glossary" / "concepts.yaml") as f:
        data = yaml.safe_load(f)

    plan = []  # (articulo_id, concepto_id, concept_name, norm_id, article)
    skipped_no_source = []
    skipped_no_articulo = []
    skipped_no_concepto = []

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        for c in data.get("concepts", []):
            dom = (c.get("domain") or {}).get("primary")
            if dom != "electricidad":
                continue
            if c.get("status") not in {"ok", "corrected"}:
                continue
            src = c.get("source") or {}
            norm_id = src.get("norm_id")
            article = src.get("article")
            name = c.get("name")
            if not norm_id or norm_id == "unknown" or not article:
                skipped_no_source.append(name)
                continue

            cur.execute(
                "SELECT id FROM articulos WHERE id_norma = %s AND numero = %s",
                (norm_id, article),
            )
            row = cur.fetchone()
            if not row:
                skipped_no_articulo.append((name, norm_id, article))
                continue
            articulo_id = row["id"]

            cur.execute("SELECT id FROM conceptos WHERE nombre = %s", (name,))
            row = cur.fetchone()
            if not row:
                skipped_no_concepto.append(name)
                continue
            concepto_id = row["id"]

            plan.append((articulo_id, concepto_id, name, norm_id, article))

    print(f"Plan: {len(plan)} define_termino edges to upsert")
    for articulo_id, concepto_id, name, norm_id, article in plan:
        print(f"  art_id={articulo_id} concepto_id={concepto_id} norm={norm_id} art={article} → {name}")

    if skipped_no_source:
        print(f"\nSkipped (no source.norm_id/article): {len(skipped_no_source)}")
    if skipped_no_articulo:
        print(f"\nSkipped (norm/article not in DB): {len(skipped_no_articulo)}")
        for s in skipped_no_articulo[:10]:
            print(f"  {s}")
    if skipped_no_concepto:
        print(f"\nSkipped (concepto not in DB): {len(skipped_no_concepto)}")

    if args.dry_run:
        print("\n--dry-run: no writes.")
        return

    inserted = 0
    skipped_dup = 0
    with with_connection() as conn, conn.cursor() as cur:
        for articulo_id, concepto_id, name, norm_id, _ in plan:
            # Check if edge already exists (idempotent)
            cur.execute(
                """
                SELECT 1 FROM referencias
                WHERE origen_articulo_id = %s
                  AND destino_concepto_id = %s
                  AND tipo_relacion = 'define_termino'
                """,
                (articulo_id, concepto_id),
            )
            if cur.fetchone():
                skipped_dup += 1
                continue
            cur.execute(
                """
                INSERT INTO referencias (
                    origen_articulo_id, destino_concepto_id,
                    tipo_relacion, confianza, metodo_extraccion
                ) VALUES (%s, %s, 'define_termino', 1.0, 'manual')
                """,
                (articulo_id, concepto_id),
            )
            inserted += 1
        conn.commit()
    print(f"\nInserted: {inserted}, skipped (already existed): {skipped_dup}")


if __name__ == "__main__":
    main()
