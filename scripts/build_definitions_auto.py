"""Build concepts + define_termino edges from ALL glossary articles.

Supersedes build_glossary_define_edges.py: that one only linked terms to
PRE-EXISTING concepts (27 matched). This one also CREATES the concept when
the glossary defines a term we don't have yet — closing the real gap (only
55 define_termino edges existed; ~200 terms are defined in glossaries).

A glossary item is a literal definition:
    Artículo N.- ...se entenderá por:
        a. TÉRMINO: definición;
So `(glossary_article --define_termino--> concepto)` is a fact of the text.

Legal-safe: deterministic parse, exact-normalized concept key (no fuzzy),
definition stored verbatim. Idempotent on (article, concept, define_termino)
and on concept name.

Run:  python -m scripts.build_definitions_auto --dry-run
      python -m scripts.build_definitions_auto
"""
import argparse
import re
import unicodedata
from psycopg.rows import dict_row
from src.storage.connection import with_connection

_OPENER = re.compile(r"se\s+entender[áa]\s+por\s*:", re.IGNORECASE)
# Item: "<a.|a)|1.|1)> TERM: definition" up to ';' or newline-item or end.
_ITEM = re.compile(
    r"(?:^|\n|;)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+"
    r"([^:;\n]{2,80}?)\s*:\s+"          # TERM
    r"([^\n].*?)(?=(?:\n\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s)|;|\Z)",  # DEFN
    re.IGNORECASE | re.DOTALL,
)
_MIN_ITEMS = 3      # an article needs >=3 items to count as a glossary
_MIN_DEF_LEN = 12   # definition must be substantive


def _norm(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def _looks_like_term(term: str) -> bool:
    # Reject amendment clauses caught by the parser ("reemplázase...", etc.)
    bad = ("reemplázase", "reemplazase", "agrégase", "agregase", "deróga",
           "modifícase", "modificase", "intercálase", "sustitúyese")
    low = term.lower()
    if any(b in low for b in bad):
        return False
    # A term is short-ish and doesn't end with a verb-y sentence
    return 2 <= len(term) <= 80 and not term.endswith((".",))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, nombre FROM conceptos")
        concept_by_key, collisions = {}, set()
        for r in cur.fetchall():
            k = _norm(r["nombre"])
            if k in concept_by_key:
                collisions.add(k)
            concept_by_key[k] = r["id"]
        for k in collisions:
            concept_by_key.pop(k, None)

        cur.execute("SELECT id, id_norma, numero, texto FROM articulos "
                    "WHERE texto ~* 'se\\s+entender[áa]\\s+por\\s*:'")
        arts = cur.fetchall()

        cur.execute("SELECT origen_articulo_id, destino_concepto_id FROM "
                    "referencias WHERE tipo_relacion='define_termino' "
                    "AND origen_articulo_id IS NOT NULL")
        existing_edges = {(r["origen_articulo_id"], r["destino_concepto_id"])
                          for r in cur.fetchall()}

        new_concepts = []   # (term, defn, art_id, id_norma, numero)
        new_edges = []      # (art_id, concept_key_or_id, term, defn, norma, numero)
        glossary_count = items_count = 0

        for art in arts:
            m = _OPENER.search(art["texto"])
            if not m:
                continue
            body = art["texto"][m.end():]
            items = [(t.strip(), d.strip()) for t, d in _ITEM.findall(body)]
            items = [(t, d) for t, d in items
                     if _looks_like_term(t) and len(d) >= _MIN_DEF_LEN]
            if len(items) < _MIN_ITEMS:
                continue
            glossary_count += 1
            for term, defn in items:
                items_count += 1
                key = _norm(term)
                cid = concept_by_key.get(key)
                if cid is None:
                    new_concepts.append((term, defn, art["id"],
                                         art["id_norma"], art["numero"], key))
                new_edges.append((art["id"], key, term, defn,
                                  art["id_norma"], art["numero"]))

        # Dedup new concepts by key (a term may appear in 2 glossaries).
        seen = set()
        uniq_new_concepts = []
        for nc in new_concepts:
            if nc[5] in seen:
                continue
            seen.add(nc[5])
            uniq_new_concepts.append(nc)

        print(f"Glossary articles:        {glossary_count}")
        print(f"Definition items:         {items_count}")
        print(f"Concepts already present: {items_count - len(new_concepts)}")
        print(f"NEW concepts to create:   {len(uniq_new_concepts)}")
        print(f"Edge candidates:          {len(new_edges)}")
        print()
        print("Sample NEW concepts:")
        for term, defn, _aid, norma, num, _k in uniq_new_concepts[:12]:
            print(f"  «{term}» ← [{norma}/{num}] {defn[:50]!r}")

        if args.dry_run:
            print("\n--dry-run: nothing written.")
            return

        # Create new concepts, get their ids.
        for term, defn, aid, norma, num, key in uniq_new_concepts:
            cur.execute(
                "INSERT INTO conceptos (nombre, definicion, metadata) "
                "VALUES (%s, %s, %s) RETURNING id",
                (term, defn, '{"source":"glossary_auto"}'),
            )
            concept_by_key[key] = cur.fetchone()["id"]

        # Create edges (idempotent).
        created = 0
        for aid, key, term, defn, norma, num in new_edges:
            cid = concept_by_key.get(key)
            if cid is None or (aid, cid) in existing_edges:
                continue
            cur.execute(
                "INSERT INTO referencias (origen_articulo_id, destino_concepto_id, "
                "tipo_relacion, confianza, metodo_extraccion, contexto) "
                "VALUES (%s, %s, 'define_termino', 1.0, 'regex', %s)",
                (aid, cid, f"glosario «{term}»: {defn[:160]}"),
            )
            existing_edges.add((aid, cid))
            created += 1
        conn.commit()
        print(f"\nCreated {len(uniq_new_concepts)} concepts, {created} define_termino edges.")


if __name__ == "__main__":
    main()
