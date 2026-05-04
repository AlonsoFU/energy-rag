"""Bootstrap a glossary template from a single BCN norm.

Reads articles for the given norm_id, finds article 1 (or the article that
defines terms — usually titled 'Definiciones' or 'Para los efectos de...'),
extracts each defined term + its definition, and writes a YAML file at
glossary/incoming/<norm_id>.yaml for human review.

Usage:
    python scripts/extract_glossary_template.py 1146553
    # → glossary/incoming/1146553.yaml

The output file uses the same schema as concepts.yaml. Review, mark
status: ok / corrected / needs_research, validate aliases, then merge
into concepts.yaml manually (or via merge script — TODO).
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.components.vectorstore import with_connection
from psycopg.rows import dict_row


# Pattern: " 1) Concept Name: definition text"  or "Concept Name: definition"
# Common in Chilean legal definitions sections (Art. 1 Definiciones).
DEFINITION_PATTERNS = [
    # "1) Term: definition." or "a) Term: definition"
    re.compile(
        r"(?:^|\n)\s*(?:\d+|[a-z])[\)\.]\s*(?P<term>[A-ZÁÉÍÓÚÑa-záéíóúñ][^:\n]{2,80}):\s*(?P<def>[^\n]+(?:\n(?!\s*(?:\d+|[a-z])[\)\.])[^\n]+)*)",
        re.MULTILINE,
    ),
    # "Term: definition" at start of line, no leading enumerator
    re.compile(
        r"(?:^|\n)(?P<term>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\s\.]{2,60}):\s*(?P<def>[^\n]{20,400})",
        re.MULTILINE,
    ),
]


def find_definitions_article(cur, norm_id: str) -> dict | None:
    """Find the article in this norma that contains term definitions.

    Looks for articles with titles like 'Definiciones', 'Para los efectos de...',
    or article 1 / 2 of the norm.
    """
    cur.execute(
        """
        SELECT id, numero, titulo, texto, orden
        FROM articulos
        WHERE id_norma = %s
        ORDER BY orden ASC
        """,
        (norm_id,),
    )
    rows = cur.fetchall()

    # Look for a definitions article by title
    for r in rows:
        titulo = (r.get("titulo") or "").lower()
        texto_start = (r.get("texto") or "")[:300].lower()
        if any(kw in titulo for kw in ["definicion", "definicion", "glosario"]):
            return r
        if "para los efectos" in texto_start or "se entender" in texto_start:
            return r

    # Fall back to article 1
    if rows:
        return rows[0]
    return None


def extract_terms_from_text(text: str) -> list[tuple[str, str]]:
    """Run patterns over text, return [(term, definition)] deduped by term."""
    seen = {}
    for pat in DEFINITION_PATTERNS:
        for m in pat.finditer(text):
            term = m.group("term").strip().rstrip(".")
            defn = m.group("def").strip()
            if 2 < len(term) < 80 and len(defn) > 15:
                if term not in seen or len(defn) > len(seen[term]):
                    seen[term] = defn
    return list(seen.items())


def yaml_str(s: str) -> str:
    if s is None:
        return '""'
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("norm_id", help="BCN idNorma (e.g. 1146553)")
    args = ap.parse_args()

    norm_id = args.norm_id
    today = date.today().isoformat()
    out_path = Path("glossary") / "incoming" / f"{norm_id}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo FROM normas WHERE id_norma = %s", (norm_id,))
        norma = cur.fetchone()
        if not norma:
            print(f"ERROR: norma {norm_id} not found in DB")
            sys.exit(1)

        norm_label = f"{norma['tipo']} {norma['numero']}"
        print(f"Bootstrapping glossary for {norm_label} (idNorma={norm_id})...")

        defs_article = find_definitions_article(cur, norm_id)
        if not defs_article:
            print(f"ERROR: no articles found for {norm_id}")
            sys.exit(1)

        article_label = f"Art. {defs_article['numero']}"
        if defs_article.get("titulo"):
            article_label += f" ({defs_article['titulo']})"
        print(f"Definitions source: {article_label}")
        print()

        terms = extract_terms_from_text(defs_article.get("texto") or "")
        print(f"Extracted {len(terms)} candidate terms.")

    # Write YAML
    lines = []
    lines.append(f"# Auto-extracted glossary template from {norm_label} (idNorma={norm_id})")
    lines.append(f"# Source article: {article_label}")
    lines.append("# ")
    lines.append("# REVIEW WORKFLOW:")
    lines.append("# 1. For each entry: validate definition, propose aliases, mark status")
    lines.append("# 2. Set status: ok | corrected | needs_research")
    lines.append("# 3. Merge approved entries into glossary/concepts.yaml")
    lines.append(f"# Generated: {today}")
    lines.append("")
    lines.append("schema_version: 1")
    lines.append(f"source_norm_id: {yaml_str(norm_id)}")
    lines.append(f"source_norm_label: {yaml_str(norm_label)}")
    lines.append(f"source_article: {yaml_str(defs_article['numero'])}")
    lines.append(f"generated_at: \"{today}\"")
    lines.append(f"total_candidates: {len(terms)}")
    lines.append("")
    lines.append("concepts:")

    if not terms:
        lines.append("  []")
    else:
        for term, defn in terms:
            short = defn if len(defn) <= 400 else defn[:397] + "..."
            url = f"https://www.bcn.cl/leychile/navegar?idNorma={norm_id}"
            lines.append(f"  - id: null  # not yet in conceptos table")
            lines.append(f"    name: {yaml_str(term)}")
            lines.append(f"    definition: {yaml_str(short)}")
            lines.append("    aliases: []  # propose aliases here, set validated: true after review")
            lines.append("    source:")
            lines.append(f"      norm_id: {yaml_str(norm_id)}")
            lines.append(f"      norm_label: {yaml_str(norm_label)}")
            lines.append(f"      article: {yaml_str(defs_article['numero'])}")
            lines.append(f"      url: {yaml_str(url)}")
            lines.append("    domain_context: general  # adjust if specific")
            lines.append("    status: not_reviewed")
            lines.append("    relations:")
            lines.append("      related: []")
            lines.append("      broader: []")
            lines.append("      narrower: []")
            lines.append("    notes: \"\"")
            lines.append("    extraction_difficulty: \"\"")
            lines.append("    metadata:")
            lines.append("      refs_count: 0  # populated after merge to conceptos table")
            lines.append("      last_reviewed_by: auto")
            lines.append(f"      last_reviewed_date: \"{today}\"")
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
