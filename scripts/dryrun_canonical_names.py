"""DRY-RUN (read-only) for canonical-name extraction rule A.

Does NOT touch the DB. For each concept whose DEFINITION reopens with the
concept name extended into a longer noun phrase, derive the canonical name
(verbatim span up to the first clause/predicate/punctuation boundary) and
classify high / low confidence / no-fire. Prints the distribution + examples
so we can validate the design before committing the spec.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from src.storage.connection import with_connection


def _na(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Boundaries where the canonical noun phrase ends (cut BEFORE the match).
_BOUNDARY = re.compile(
    r"(?:[.;:,]"
    r"|\b(?:a\s+que|al\s+que|a\s+los\s+que|a\s+las\s+que|a\s+la\s+que"
    r"|que\s+se\s+refiere|que\s+establece|que\s+fija|que\s+indica"
    r"|que\s+se\s+\w+|en\s+adelante|seg[uú]n|conforme)\b"
    r"|\b(?:establecid[oa]s?|definid[oa]s?|constituid[oa]s?|conformad[oa]s?"
    r"|integrad[oa]s?|denominad[oa]s?|es|son|ser[aá]n?|consiste|corresponde"
    r"|comprende|contemplad[oa]s?|se\s+entender[aá])\b)",
    re.IGNORECASE,
)


def extract_canonical(nombre: str, definicion: str):
    """Return (canonical, confidence) or (None, 'no-fire')."""
    if not definicion:
        return None, "no-fire"
    defi = definicion.strip()
    n_na = _na(nombre).strip()
    # Definition must START with the concept name (word-aligned).
    if not _na(defi).startswith(n_na):
        return None, "no-fire"
    # Must EXTEND: the char right after the name is a space + more words.
    after = defi[len(nombre):]
    if not after[:1].isspace():
        return None, "no-fire"
    # Find the first boundary in the part after the name.
    m = _BOUNDARY.search(after)
    if not m:
        return None, "low"  # no clean cut within the definition → review
    canonical = (nombre + after[: m.start()]).strip().rstrip(" ,;:.")
    extra_words = len(canonical.split()) - len(nombre.split())
    if extra_words <= 0:
        return None, "no-fire"  # boundary right after name → already canonical
    conf = "high" if 1 <= extra_words <= 8 else "low"
    return canonical, conf


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
