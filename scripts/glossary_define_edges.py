"""Create `define_termino` edges from a norm's GLOSSARY article (structural).

Why: `ingest_lgse.py` only ran the reference extractor, which emits `cita`
(mentions), never `define_termino`. So the LGSE — whose art 225 is the
authoritative glossary of the electricity law — had 0 `define_termino` edges,
and the authority resolver (Capa 1 trusts ONLY `define_termino`) could not
prefer the LAW by rank. This script closes that gap.

General, NOT hardcoded. `find_real_define_termino.py` gated articles on the
exact phrase "se entenderá por:", so it missed the LGSE entirely. The LGSE uses
TWO structural definition conventions, and we detect both by their SHAPE, not
by per-concept text rules — so this works on any norm:

  A) Glossary article: a lettered/numbered list of `Término: definición`
     entries (the LGSE art 225, "se entiende por: a) Sistema eléctrico: ...").
  B) Titled definition article: an article whose own title is
     "Artículo N°.- Definición de <Término>." (LGSE art 73/74/75/77/79/103…).
     This is the law's own structural marker for a definition; the <Término>
     is matched to our concepts by their own name/aliases.

The only inputs are these structural shapes + the concepts' names/aliases.

Run:
    PYTHONPATH=. ./venv/bin/python scripts/glossary_define_edges.py --norma 258171 --dry-run
    PYTHONPATH=. ./venv/bin/python scripts/glossary_define_edges.py --norma 258171
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.components.vectorstore import with_connection  # noqa: E402

# Pattern A — glossary entry head: a list marker (a) / ñ) / 1) / 1.- ) followed
# by a short term, ended by the FIRST colon. The term must not span a newline
# and is bounded in length (terms are short; definitions are long).
_ENTRY_RE = re.compile(
    r"^\s*(?:[a-zñA-ZÑ]{1,2}|\d{1,2})[\)\.\-]+\s+([^:\n]{2,80}?)\s*:",
    re.MULTILINE,
)
# Structural gate: an article is a glossary if it lists at least this many
# `Term: definition` entries.
_MIN_ENTRIES = 3

# Pattern B — titled definition article: "Artículo N°.- Definición de <Término>."
# The term runs up to the period that closes the title (before the definition
# sentence, which starts with a capital/quote). Whitespace is collapsed first
# because the source XML wraps lines mid-title.
_DEFART_RE = re.compile(
    r"^\s*Art[íi]culo\s+\S+\s*\.?-?\s*Definici[óo]n\s+de\s+(.+?)\.\s+[A-ZÁÉÍÓÚ\"“«]",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    """Lowercase + strip accents/punctuation for accent-insensitive matching."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def extract_defined_terms(texto: str) -> list[tuple[str, str]]:
    """Return (term, pattern) for every term this article defines.

    pattern is "glossary" (A) or "def_article" (B). Empty if neither matches.
    """
    out: list[tuple[str, str]] = []
    # Pattern A: glossary list (only counts as one if it has >= _MIN_ENTRIES).
    heads = [m.group(1).strip() for m in _ENTRY_RE.finditer(texto)]
    if len(heads) >= _MIN_ENTRIES:
        out += [(h, "glossary") for h in heads]
    # Pattern B: titled definition article. Collapse line wraps first.
    flat = re.sub(r"\s+", " ", texto or "")
    m = _DEFART_RE.match(flat)
    if m:
        out.append((m.group(1).strip(), "def_article"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--norma", help="restrict to one id_norma (e.g. 258171). Default: all.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Concept population: same as the rest of the curation — validated
    # electricidad concepts (name + their validated aliases).
    with open(ROOT / "glossary" / "concepts.yaml") as f:
        data = yaml.safe_load(f)
    term_to_concept: dict[str, str] = {}  # normalized term/alias -> concept name
    for c in data.get("concepts", []):
        if (c.get("domain") or {}).get("primary") != "electricidad":
            continue
        if c.get("status") not in {"ok", "corrected"}:
            continue
        names = [c["name"]] + [a["alias"] for a in (c.get("aliases") or []) if a.get("validated")]
        for n in names:
            term_to_concept.setdefault(_norm(n), c["name"])
    print(f"Validated electricidad concepts (name+alias keys): {len(term_to_concept)}")

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        q = "SELECT id, id_norma, numero, texto FROM articulos"
        params: tuple = ()
        if args.norma:
            q += " WHERE id_norma = %s"
            params = (args.norma,)
        cur.execute(q, params)
        articulos = cur.fetchall()
        cur.execute("SELECT id, nombre FROM conceptos")
        name_to_id = {r["nombre"]: r["id"] for r in cur.fetchall()}

    # Detect definition articles structurally, then match terms -> concepts.
    plan = []  # (articulo_id, concepto_id, concept_name, id_norma, numero, term, pat)
    seen_edge: set[tuple[int, str]] = set()
    n_gloss = n_defart = 0
    for art in articulos:
        terms = extract_defined_terms(art["texto"] or "")
        if any(p == "glossary" for _, p in terms):
            n_gloss += 1
        if any(p == "def_article" for _, p in terms):
            n_defart += 1
        for term, pat in terms:
            cn = term_to_concept.get(_norm(term))
            if not cn:
                continue
            cid = name_to_id.get(cn)
            if not cid or (art["id"], cn) in seen_edge:
                continue
            seen_edge.add((art["id"], cn))
            plan.append((art["id"], cid, cn, art["id_norma"], art["numero"], term, pat))

    print(f"Glossary articles (A): {n_gloss} | titled definition articles (B): {n_defart}")
    print(f"define_termino edges to create: {len(plan)}\n")
    for aid, cid, cn, idn, num, term, pat in plan:
        print(f"  [{pat:11}] art_id={aid:<5} norm={idn:<10} art={num:<8} concepto={cn:<38} via='{term}'")

    if args.dry_run:
        print("\n--dry-run: no writes.")
        return

    inserted = skipped = 0
    with with_connection() as conn, conn.cursor() as cur:
        for aid, cid, cn, idn, num, term, pat in plan:
            cur.execute(
                """SELECT 1 FROM referencias WHERE origen_articulo_id=%s
                   AND destino_concepto_id=%s AND tipo_relacion='define_termino'""",
                (aid, cid),
            )
            if cur.fetchone():
                skipped += 1
                continue
            # metodo_extraccion is CHECK-constrained to regex/llm/manual; these
            # are structurally-derived curations → 'manual' (like the sibling
            # curation scripts). The pattern (A/B) is reported to stdout only.
            cur.execute(
                """INSERT INTO referencias (origen_articulo_id, destino_concepto_id,
                   tipo_relacion, confianza, metodo_extraccion)
                   VALUES (%s, %s, 'define_termino', 0.9, 'manual')""",
                (aid, cid),
            )
            inserted += 1
        conn.commit()
    print(f"\nInserted: {inserted}, skipped (already existed): {skipped}")


if __name__ == "__main__":
    main()
