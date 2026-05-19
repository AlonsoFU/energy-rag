"""Find the REAL define_termino articles for each validated concept.

Searches the 12 articulos that contain `se entenderá por:` (regulatory
definition articles) and checks if each validated concept (or its aliases)
appears textually in that article. Only emits an edge when there's
evidence the article actually defines the concept.

Run:
    python scripts/find_real_define_termino.py --dry-run
    python scripts/find_real_define_termino.py
"""
import argparse
import re
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

    # Collect validated concepts in electricidad
    concepts = []
    for c in data.get("concepts", []):
        if (c.get("domain") or {}).get("primary") != "electricidad":
            continue
        if c.get("status") not in {"ok", "corrected"}:
            continue
        aliases = [a["alias"] for a in (c.get("aliases") or []) if a.get("validated")]
        if not aliases:
            continue
        concepts.append({"name": c["name"], "aliases": aliases})

    print(f"Validated electricidad concepts: {len(concepts)}")

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Get the 12 definition-articles
        cur.execute("""
            SELECT id, id_norma, numero, texto FROM articulos
            WHERE texto ILIKE '%se entenderá por:%'
            ORDER BY id
        """)
        def_articles = cur.fetchall()
        print(f"Definition-articles found: {len(def_articles)}\n")

        # Map concept_name → concepto_id
        cur.execute("SELECT id, nombre FROM conceptos")
        name_to_id = {r["nombre"]: r["id"] for r in cur.fetchall()}

    # For each concept, find articles that define it
    plan = []
    not_found = []
    for c in concepts:
        # Build search patterns: name + aliases, word-bounded, case-insensitive
        patterns = [c["name"]] + c["aliases"]
        # Look for definition pattern: "<term>:" or "Por <term> se entenderá"
        # within the definition section. Simplest heuristic: search for
        # word-bounded match of the term name (or alias) inside the article text.
        matches = []
        for art in def_articles:
            text = art["texto"]
            for p in patterns:
                # Strict patterns that signal a DEFINITION entry, not a mention:
                #   1. "<term>:"  (glossary-style entry)
                #   2. "se entenderá por <term>"
                #   3. "se denomina <term>"
                #   4. "Por <term> se entenderá"
                strict_pats = [
                    r"\b" + re.escape(p) + r"\s*:",
                    r"se\s+entender[áa]\s+por\s+" + re.escape(p) + r"\b",
                    r"se\s+denomina[r]?[áa]?\s+" + re.escape(p) + r"\b",
                    r"\bPor\s+" + re.escape(p) + r"\s+se\s+entender",
                ]
                if any(re.search(sp, text, re.IGNORECASE) for sp in strict_pats):
                    matches.append((art["id"], art["id_norma"], art["numero"], p))
                    break
        if matches:
            for m in matches:
                plan.append({
                    "concept_name": c["name"],
                    "concepto_id": name_to_id.get(c["name"]),
                    "articulo_id": m[0],
                    "id_norma": m[1],
                    "numero": m[2],
                    "matched_term": m[3],
                })
        else:
            not_found.append(c["name"])

    print(f"Edges to generate: {len(plan)}")
    for p in plan:
        print(f"  art_id={p['articulo_id']:<5} norm={p['id_norma']:<10} art={p['numero']:<10} concepto={p['concept_name']:<35} via='{p['matched_term']}'")

    if not_found:
        print(f"\nNo definition-article match (skipped, {len(not_found)}):")
        for n in not_found:
            print(f"  - {n}")

    if args.dry_run:
        print("\n--dry-run: no writes.")
        return

    inserted = 0
    skipped = 0
    with with_connection() as conn, conn.cursor() as cur:
        for p in plan:
            if not p["concepto_id"]:
                skipped += 1
                continue
            cur.execute(
                """
                SELECT 1 FROM referencias
                WHERE origen_articulo_id = %s
                  AND destino_concepto_id = %s
                  AND tipo_relacion = 'define_termino'
                """,
                (p["articulo_id"], p["concepto_id"]),
            )
            if cur.fetchone():
                skipped += 1
                continue
            cur.execute(
                """
                INSERT INTO referencias (
                    origen_articulo_id, destino_concepto_id,
                    tipo_relacion, confianza, metodo_extraccion
                ) VALUES (%s, %s, 'define_termino', 0.85, 'manual')
                """,
                (p["articulo_id"], p["concepto_id"]),
            )
            inserted += 1
        conn.commit()
    print(f"\nInserted: {inserted}, skipped: {skipped}")


if __name__ == "__main__":
    main()
