"""Sync domain.primary/secondary from glossary/concepts.yaml to conceptos.metadata.

After this, retrieve.py can filter concepts by domain to avoid off-domain
matches polluting graph_boost for electrical queries.
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from src.components.vectorstore import with_connection

yaml_path = ROOT / "glossary" / "concepts.yaml"
with open(yaml_path) as f:
    data = yaml.safe_load(f)

with with_connection() as conn, conn.cursor() as cur:
    n_updated = 0
    for c in data.get("concepts", []):
        dom = c.get("domain") or {}
        primary = dom.get("primary")
        secondary = dom.get("secondary")
        if not primary:
            continue
        # Merge into existing metadata
        cur.execute(
            "UPDATE conceptos SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb WHERE nombre = %s",
            (json.dumps({"domain_primary": primary, "domain_secondary": secondary}), c["name"]),
        )
        n_updated += cur.rowcount
    conn.commit()

print(f"Updated metadata on {n_updated} concepts")
