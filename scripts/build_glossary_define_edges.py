"""Build `define_termino` graph edges from glossary articles.

A glossary article has the shape:

    Artículo N.- ...se entenderá por:
        a. TÉRMINO: definición;
        b. OTRO TÉRMINO: otra definición;
        ...

This script parses each `letra. TÉRMINO: definición;` item and, when TÉRMINO
matches a concept name EXACTLY (case-insensitive, trimmed), creates a
`define_termino` edge (origen_articulo_id = glossary article,
destino_concepto_id = concept).

LEGAL-SAFE: edges are created ONLY on exact term↔concept name match. No
fuzzy, no stemming, no inference. The edge is a literal fact of the text:
"this article's glossary defines this term".

graph_boost(retrieve.py) gives a +10 score boost to a candidate article that
has a `define_termino` edge to an alias-matched query concept. Without the
edge, curated aliases are inert.

Idempotent: existing (origen_articulo_id, destino_concepto_id,
'define_termino') edges are not duplicated.

Run:
    python scripts/build_glossary_define_edges.py --dry-run
    python scripts/build_glossary_define_edges.py
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage.connection import with_connection
from psycopg.rows import dict_row


# A glossary article announces its definitions with this lead-in.
_GLOSSARY_MARKER = re.compile(r"se\s+entender[áa]\s+por\s*:", re.IGNORECASE)

# One definition item:  "<letter>. <TERM>: <definition>;"
#   - letter key: 1-4 lowercase letters/roman-ish, then a dot
#   - TERM: everything up to the FIRST colon (no colon inside term)
#   - definition: up to the terminating semicolon (or end)
# We capture the TERM only; the definition is ignored (already in the corpus).
_ITEM_RE = re.compile(
    r"(?:^|\n)\s*[a-zñ]{1,4}\.\s+"   # "    a. "
    r"([^:;\n]{2,120}?)\s*:\s+",     # TERM (no colon/semicolon/newline)
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    """Lowercase + strip accents + collapse whitespace. Used ONLY for the
    exact-match key, never stored. Makes 'C.O.M.A.' == 'c.o.m.a.' and
    'Órganos' == 'organos' so legitimate same-term variants match, while
    still being an EXACT (not fuzzy) comparison."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # 1. Concept name -> id  (exact-match key on normalized name)
        cur.execute("SELECT id, nombre FROM conceptos")
        concept_by_key: dict[str, int] = {}
        collisions: set[str] = set()
        for row in cur.fetchall():
            k = _norm(row["nombre"])
            if k in concept_by_key:
                collisions.add(k)  # ambiguous name; skip to stay legal-safe
            concept_by_key[k] = row["id"]
        for k in collisions:
            concept_by_key.pop(k, None)

        # 2. Candidate glossary articles
        cur.execute("""
            SELECT id, id_norma, numero, texto
            FROM articulos
            WHERE texto ~* 'se\\s+entender[áa]\\s+por\\s*:'
        """)
        articles = cur.fetchall()

        planned: list[tuple[int, str, str, int, str]] = []
        # (articulo_id, id_norma, numero, concepto_id, term_raw)
        n_terms_seen = 0
        n_matched = 0

        for art in articles:
            text = art["texto"]
            m = _GLOSSARY_MARKER.search(text)
            if not m:
                continue
            body = text[m.end():]
            for item in _ITEM_RE.finditer(body):
                term_raw = item.group(1).strip()
                n_terms_seen += 1
                cid = concept_by_key.get(_norm(term_raw))
                if cid is None:
                    continue
                n_matched += 1
                planned.append(
                    (art["id"], art["id_norma"], art["numero"], cid, term_raw)
                )

        # 3. Filter out edges that already exist
        cur.execute("""
            SELECT origen_articulo_id, destino_concepto_id
            FROM referencias
            WHERE tipo_relacion = 'define_termino'
              AND origen_articulo_id IS NOT NULL
              AND destino_concepto_id IS NOT NULL
        """)
        existing = {
            (r["origen_articulo_id"], r["destino_concepto_id"])
            for r in cur.fetchall()
        }
        to_create = [
            p for p in planned if (p[0], p[3]) not in existing
        ]

        print(f"Glossary articles scanned:   {len(articles)}")
        print(f"Definition items parsed:     {n_terms_seen}")
        print(f"Exact concept matches:       {n_matched}")
        print(f"Edges already present:       {n_matched - len(to_create)}")
        print(f"New define_termino edges:    {len(to_create)}")
        if collisions:
            print(f"Ambiguous names skipped:     {len(collisions)}")
        print()
        for aid, norma, numero, cid, term in sorted(to_create, key=lambda x: x[4].lower()):
            print(f"  [Art. {numero} de {norma}] (art_id={aid}) "
                  f"--define--> concepto#{cid}  «{term}»")

        if args.dry_run:
            print("\n--dry-run: no edges created.")
            return

        for aid, norma, numero, cid, term in to_create:
            cur.execute("""
                INSERT INTO referencias
                    (origen_articulo_id, destino_concepto_id, tipo_relacion,
                     confianza, metodo_extraccion, contexto)
                VALUES (%s, %s, 'define_termino', 1.0, 'regex', %s)
            """, (aid, cid, f"glosario: «{term}»"))
        conn.commit()
        print(f"\nCreated {len(to_create)} define_termino edges.")


if __name__ == "__main__":
    main()
