"""Load validated aliases from glossary/concepts.yaml into Postgres conceptos.aliases.

Only loads aliases marked validated: true on entries with status: ok | corrected.

Usage:
    python scripts/load_glossary_to_db.py --dry-run    # show planned changes
    python scripts/load_glossary_to_db.py              # apply
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.components.vectorstore import with_connection
from psycopg.rows import dict_row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print plan, don't write")
    args = ap.parse_args()

    yaml_path = Path(__file__).resolve().parent.parent / "glossary" / "concepts.yaml"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    eligible = []  # list of (id, name, [alias strings])
    for c in data.get("concepts", []):
        if c.get("status") not in {"ok", "corrected"}:
            continue
        validated = [a["alias"] for a in (c.get("aliases") or []) if a.get("validated")]
        if not validated:
            continue
        eligible.append((c["id"], c["name"], validated))

    if not eligible:
        print("No entries with status=ok|corrected and validated aliases. Nothing to do.")
        return

    print(f"Eligible entries: {len(eligible)}")
    print()
    for cid, name, aliases in eligible:
        print(f"  [{cid}] {name}")
        for a in aliases:
            print(f"      + {a}")
    print()

    if args.dry_run:
        print("--dry-run: no changes applied.")
        return

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        for cid, name, aliases in eligible:
            cur.execute(
                "UPDATE conceptos SET aliases = %s, updated_at = now() WHERE id = %s",
                (aliases, cid),
            )
        conn.commit()
    print(f"Applied to {len(eligible)} concepts.")


if __name__ == "__main__":
    main()
