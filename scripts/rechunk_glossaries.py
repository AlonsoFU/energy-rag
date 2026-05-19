"""Re-chunk glossary articles: 1 definition = 1 atomic fragment.

A glossary article ("...se entenderá por:" + enumerated items
`a. TÉRMINO: definición;`) is today stored as a few ~2.5k-char mega-chunks
that each blend ~8 definitions. The per-term embedding/BM25 signal is diluted,
so the defining article never enters the retrieval pool (root cause found
2026-05-16, see handoff).

This script splits each glossary article by its OWN legal divisions
(`a.`, `b.`, `c.`, ... that the norm already has) into one fragment per
definition. LEGAL-SAFE: uses the divisions the text already defines; invents
nothing. Trazabilidad preserved (fragmento.articulo_id unchanged).

Per glossary article:
  chunk 0      = header ("Artículo N.- ... se entenderá por:")
  chunk 1..K   = one definition each, contextual_text repeats the term so
                 BM25/vector get a strong per-term signal.

Idempotent-ish: re-running DELETEs the article's fragments and rebuilds them.

Run:
    python scripts/rechunk_glossaries.py --dry-run            # parse only
    python scripts/rechunk_glossaries.py --dry-run --show 5   # + preview art 5
    python scripts/rechunk_glossaries.py                      # apply + embed
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.connection import with_connection
from psycopg.rows import dict_row

_GLOSSARY_MARKER = re.compile(r"se\s+entender[áa]\s+por\s*:", re.IGNORECASE)

# An enumeration marker: 1-2 lowercase letters OR 1-2 digits, followed by
# `.` or `)`, at start / after newline / after `;`. Covers the legal styles
# seen in the corpus: "a. TÉRMINO" (Decreto 10), "a) TÉRMINO" (PMGD),
# "1) TÉRMINO" / "1. TÉRMINO" (numeric glossaries). Excludes "art." (3
# letters) and "Ley." (uppercase).
_MARKER = re.compile(r"(?:^|\n|;)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+")

# Safety threshold: only re-chunk an article if at least this many clean
# definitions were parsed. Below it, the article is LEFT UNTOUCHED (keeps its
# current fragments) — never destroy content we cannot re-chunk reliably.
MIN_DEFS = 4
# A parsed definition is "clean" if the term is short (a real term, not a
# run-on sentence) and the definition is non-empty.
MAX_TERM_CHARS = 90


def parse_glossary(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (header, items) where items = [(term, definition)].

    header = everything up to and including "se entenderá por:".
    Each item spans from one marker to the next (or end-of-text), so a
    definition with internal commas/numbers/«artículo 105°» stays intact.

    Only items with a real term (has a colon, term ≤ MAX_TERM_CHARS, non-empty
    definition) are kept — this filters run-on prose that isn't a definition.
    """
    m = _GLOSSARY_MARKER.search(text)
    if not m:
        return text, []
    header = text[: m.end()].strip()
    body = text[m.end():]

    markers = list(_MARKER.finditer(body))
    items: list[tuple[str, str]] = []
    for idx, mk in enumerate(markers):
        start = mk.end()
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(body)
        chunk = body[start:end].strip().rstrip(";").strip()
        # term = up to first colon; definition = rest
        if ":" not in chunk:
            continue
        term, definition = chunk.split(":", 1)
        term, definition = term.strip(), definition.strip()
        if term and definition and len(term) <= MAX_TERM_CHARS:
            items.append((term, definition))
    return header, items


def build_fragments(art: dict) -> list[tuple[int, str, str]]:
    """Return [(chunk_index, raw_text, contextual_text)] for one glossary art.

    contextual_text repeats the TERM up front so a query like "qué es COMA"
    gets a strong BM25 + vector match against this specific fragment instead
    of being averaged across ~70 definitions.
    """
    header, items = parse_glossary(art["texto"])
    preamble = f"[Artículo {art['numero']} de {art['id_norma']}]"
    frags: list[tuple[int, str, str]] = []
    # chunk 0 — header (keeps the "for the purposes of this reglamento" framing)
    frags.append((0, header, f"{preamble} {header}"))
    for i, (term, definition) in enumerate(items, start=1):
        raw = f"{term}: {definition}".strip().rstrip(":").strip()
        ctx = (
            f"{preamble} Definición en el glosario: «{term}». "
            f"{term}: {definition}"
        ).strip()
        frags.append((i, raw, ctx))
    return frags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=None,
                    help="articulo_id to preview parsed items")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, id_norma, numero, texto
            FROM articulos
            WHERE texto ~* 'se\\s+entender[áa]\\s+por\\s*:'
            ORDER BY id
        """)
        arts = cur.fetchall()

    plan = []
    skipped = []
    for art in arts:
        frags = build_fragments(art)
        n_defs = len(frags) - 1  # minus header
        if n_defs < MIN_DEFS:
            skipped.append((art, n_defs))
            print(f"  art_id={art['id']:>4} [{art['id_norma']}/{art['numero']}] "
                  f"texto={len(art['texto']):>5}c → {n_defs} defs  SKIP "
                  f"(<{MIN_DEFS}, queda intacto)")
            continue
        plan.append((art, frags))
        print(f"  art_id={art['id']:>4} [{art['id_norma']}/{art['numero']}] "
              f"texto={len(art['texto']):>5}c → {n_defs} definiciones + header")

    total_frags = sum(len(f) for _, f in plan)
    total_defs = total_frags - len(plan)
    print(f"\nGlossary articles re-chunked: {len(plan)}  "
          f"(skipped, left intact: {len(skipped)})")
    print(f"Total fragments to create: {total_frags} "
          f"({total_defs} definiciones + {len(plan)} headers)")

    if args.show is not None:
        art, frags = next((p for p in plan if p[0]["id"] == args.show), (None, None))
        if frags:
            print(f"\n--- Preview art_id={args.show} (primeros 8 fragmentos) ---")
            for ci, raw, ctx in frags[:8]:
                print(f"\n  [chunk {ci}] raw: {raw[:100]!r}")
                print(f"            ctx: {ctx[:140]!r}")

    if args.dry_run:
        print("\n--dry-run: no DB changes, no embedding.")
        return

    print("\nLoading Qwen3-Embedding (CPU FP32)...")
    from src.components.embedder import Qwen3Embedder
    embedder = Qwen3Embedder()

    t0 = time.time()
    created = 0
    for n, (art, frags) in enumerate(plan, 1):
        ctx_texts = [c for _, _, c in frags]
        embeddings = embedder.embed(ctx_texts)
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fragmentos WHERE articulo_id = %s", (art["id"],))
            for (ci, raw, ctx), emb in zip(frags, embeddings):
                cur.execute("""
                    INSERT INTO fragmentos
                        (articulo_id, chunk_index, text, contextual_text,
                         embedding, token_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (art["id"], ci, raw, ctx, emb, len(raw.split())))
            conn.commit()
        created += len(frags)
        print(f"  [{n}/{len(plan)}] art_id={art['id']} → {len(frags)} fragmentos "
              f"| elapsed {time.time()-t0:.0f}s")

    print(f"\nDone in {time.time()-t0:.0f}s. Created {created} fragments.")


if __name__ == "__main__":
    main()
