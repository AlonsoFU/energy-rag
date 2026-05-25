"""Apply human-confirmed definition sources to the DB (CPU-only, no GPU/LLM).

Reads glossary/confirmed_definition_sources.yaml and writes each concept's
metadata.definition_source with needs_review=false (high confidence). Idempotent.
Use after a fresh DB load or any --apply run to re-assert the human decisions
(the big resolver also honors the file, but this lets you re-apply cheaply).

Run:  PYTHONPATH=. ./venv/bin/python scripts/apply_confirmed_sources.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json

from scripts.resolve_definition_sources import load_confirmed
from src.storage.connection import with_connection


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    confirmed = load_confirmed()
    if not confirmed:
        print("No hay confirmaciones en glossary/confirmed_definition_sources.yaml")
        return

    with with_connection() as conn, conn.cursor() as cur:
        for cid, cf in confirmed.items():
            ds = {"id_norma": str(cf["id_norma"]), "articulo": str(cf["articulo"]),
                  "criterio": "confirmado_humano", "confianza": "alta",
                  "needs_review": False}
            print(f"  {cid} {cf.get('nombre','')[:32]:32} -> {ds['id_norma']} art {ds['articulo']}")
            if args.dry_run:
                continue
            cur.execute(
                "UPDATE conceptos SET metadata = coalesce(metadata,'{}'::jsonb) "
                "|| %(m)s::jsonb WHERE id = %(id)s",
                {"id": cid, "m": json.dumps({"definition_source": ds})})
        if not args.dry_run:
            conn.commit()
            print(f"Aplicadas {len(confirmed)} confirmaciones.")
        else:
            print("--dry-run: nada escrito.")


if __name__ == "__main__":
    main()
