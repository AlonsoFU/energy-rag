"""Apply canonical-name extraction (rule A) over the concepts table.

Default is DRY-RUN (prints what it would do). With --apply it writes:
  - high confidence  → UPDATE conceptos (nombre=canónico, aliases += bare word,
                       metadata.canonical_source provenance). Idempotent.
  - low / collision  → glossary/incoming/canonical_review.yaml (human review).

Runs after build_definitions_auto.py in the ingestion flow. Idempotent: a
concept with metadata.canonical_source is skipped.

Run:  PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py
      PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py --apply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from psycopg.rows import dict_row

from src.extraction.canonical_names import _na, decide_action
from src.storage.connection import with_connection

REVIEW_PATH = Path("glossary/incoming/canonical_review.yaml")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write changes to DB + review file (default: dry-run)")
    args = ap.parse_args()

    renames: list[dict] = []
    reviews: list[dict] = []

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, nombre, definicion, aliases, metadata "
                    "FROM conceptos ORDER BY nombre")
        rows = cur.fetchall()
        all_names = {_na(r["nombre"]) for r in rows}

        for r in rows:
            other = all_names - {_na(r["nombre"])}
            act = decide_action(r["nombre"], r["definicion"] or "",
                                r["metadata"], other)
            if act["action"] == "skip":
                continue
            if act["action"] == "review":
                reviews.append({
                    "concepto_id": r["id"],
                    "original_nombre": r["nombre"],
                    "canonical_propuesto": act.get("canonical"),
                    "motivo": act["reason"],
                    "definicion_inicio": (r["definicion"] or "")[:120],
                })
                continue
            renames.append({"id": r["id"], "bare": r["nombre"],
                            "canonical": act["canonical"]})

        print(f"renames (high): {len(renames)} | reviews: {len(reviews)}")
        for x in renames:
            print(f"  '{x['bare']}' → '{x['canonical']}'")
        for x in reviews:
            print(f"  [review] '{x['original_nombre']}' → "
                  f"{x['canonical_propuesto']!r} ({x['motivo']})")

        if not args.apply:
            print("\n--dry-run: nothing written. Use --apply.")
            return

        for x in renames:
            cur.execute(
                """
                UPDATE conceptos
                   SET nombre = %(canonical)s,
                       aliases = (SELECT array_agg(DISTINCT a)
                                    FROM unnest(coalesce(aliases,'{}') || %(bare)s::text) a),
                       metadata = coalesce(metadata,'{}'::jsonb) || %(meta)s::jsonb
                 WHERE id = %(id)s
                """,
                {"canonical": x["canonical"], "bare": x["bare"], "id": x["id"],
                 "meta": json.dumps({
                     "canonical_source": "definition_opening",
                     "original_nombre": x["bare"],
                     "canonical_span": x["canonical"],
                     "confianza": 1.0,
                     "metodo": "regex_def_opening"})},
            )
        conn.commit()
        print(f"\nApplied {len(renames)} renames.")

    if args.apply:
        REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        REVIEW_PATH.write_text(
            yaml.safe_dump(reviews, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        print(f"Wrote {len(reviews)} review candidates → {REVIEW_PATH}")


if __name__ == "__main__":
    main()
