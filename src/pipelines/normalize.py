"""Deterministic query/term normalization for concept matching.

LEGAL-SAFE by design: this is NOT fuzzy matching. There is no similarity
threshold, no edit distance, no embeddings. It only canonicalizes
*orthographic* variants of the SAME term so an exact post-normalization
match still succeeds:

  - case:            "VATT"      == "vatt"
  - accents:         "energética" == "energetica"
  - acronym dots:    "V.A.T.T."  == "VATT"   ("C.O.M.A." == "COMA")
  - whitespace runs: collapsed

After normalization the comparison is still EXACT and word-bounded. A query
term that isn't literally the same term (modulo the above) will NOT match.
This avoids the "potencia inicial ≈ potencia firme" class of legal errors
that fuzzy matching would introduce.
"""
import re
import unicodedata

# A run of single letters separated by dots, e.g. "V.A.T.T." or "C.O.M.A."
# (optionally a trailing dot). Used to collapse acronym punctuation.
_ACRONYM_DOTS = re.compile(r"\b(?:[a-zñ]\.){2,}[a-zñ]?\.?", re.IGNORECASE)


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _collapse_acronym(m: re.Match) -> str:
    return m.group(0).replace(".", "")


def normalize_for_match(s: str) -> str:
    """Canonicalize a string for EXACT post-normalization comparison.

    Deterministic and reversible-in-spirit: same input → same output, and
    only orthographic noise is removed. Never collapses two different terms.
    """
    if not s:
        return ""
    s = s.lower()
    # Collapse acronym dots only inside acronym-shaped runs (won't touch a
    # sentence-final period or "art." because those aren't letter.letter.).
    s = _ACRONYM_DOTS.sub(_collapse_acronym, s)
    s = _strip_accents(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_term_in_query(term: str, normalized_query: str) -> bool:
    """True if `term` occurs in `normalized_query` as a whole word, comparing
    under normalization. `normalized_query` must already be normalized via
    normalize_for_match (caller normalizes once, reuses for all terms).
    """
    nt = normalize_for_match(term)
    if not nt:
        return False
    return re.search(rf"\b{re.escape(nt)}\b", normalized_query) is not None
