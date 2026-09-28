"""DRY-RUN (read-only) for canonical-name extraction rule A.

Does NOT touch the DB. For each concept whose DEFINITION reopens with the
concept name extended into a longer noun phrase, derive the canonical name
(verbatim span up to the first clause/predicate/punctuation boundary) and
classify high / low confidence / no-fire. Prints the distribution + examples
so we can validate the design before committing the spec.
"""
from __future__ import annotations

from collections import Counter

# Single source of truth for rule A (was inlined here; now imported so the
# dry-run and the production runner can never diverge).
from src.extraction.canonical_names import _na, extract_canonical
from src.storage.connection import with_connection


def main() -> None:
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, definicion FROM conceptos ORDER BY nombre")
        rows = cur.fetchall()
        names = {_na(n) for n, _ in rows}

    buckets: Counter = Counter()
    examples = {"high": [], "low": [], "no-fire": []}
    collisions = []
    for nombre, definicion in rows:
        canonical, conf = extract_canonical(nombre, definicion)
        buckets[conf] += 1
        if conf in ("high", "low") and canonical and _na(canonical) in names:
            collisions.append((nombre, canonical))
        if len(examples[conf]) < 12:
            examples[conf].append((nombre, canonical))

    total = sum(buckets.values())
    print(f"=== {total} conceptos ===")
    for k in ("high", "low", "no-fire"):
        print(f"  {k:8}: {buckets[k]}")
    print(f"  colisiones (canónico ya existe → merge a revisión): {len(collisions)}")

    print("\n--- HIGH (auto-aplica) ---")
    for n, c in examples["high"]:
        print(f"  '{n}'  →  '{c}'")
    print("\n--- LOW (revisión) ---")
    for n, c in examples["low"]:
        print(f"  '{n}'  →  {c!r}")
    print("\n--- NO-FIRE (queda igual) ---")
    for n, _ in examples["no-fire"]:
        print(f"  '{n}'")
    if collisions:
        print("\n--- colisiones ---")
        for n, c in collisions[:10]:
            print(f"  '{n}'  →  '{c}' (ya existe)")


if __name__ == "__main__":
    main()
