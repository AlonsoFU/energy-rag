"""Classify a norma's `clase` from its título.

Returns one of:
- "reglamento_base" — APRUEBA REGLAMENTO ...
- "fija_valores"    — FIJA ...
- "modifica"        — MODIFICA ...
- "deroga"          — DEROGA ...
- None              — no match

Patterns ported from legacy `src/search/graph_builder.py::_clasificar_norma`,
which handles real-world quirks:
  * Scrape duplicates like "DECRETO 13DECRETO 13 T FIJA ..." → strip leading
    "<TIPO> <NUM> " before matching.
  * Optional "T " prefix between tipo/número and the action verb.
  * Fallback substring search in the first 80 chars of the cleaned title.
"""
from __future__ import annotations

import re

# Primary patterns: action verb at start of cleaned title (with optional "T ").
_PRIMARY = [
    ("reglamento_base", re.compile(r"^(?:T\s+)?APRUEBA\s+REGLAMENTO\b")),
    ("fija_valores",    re.compile(r"^(?:T\s+)?FIJA\b")),
    ("modifica",        re.compile(r"^(?:T\s+)?MODIFICA\b")),
    ("deroga",          re.compile(r"^(?:T\s+)?DEROGA\b")),
]

# Fallback: substring in the first 80 chars of the cleaned, upper-cased title.
_FALLBACK = [
    ("reglamento_base", "APRUEBA REGLAMENTO"),
    ("fija_valores",    "FIJA"),
    ("modifica",        "MODIFICA"),
    ("deroga",          "DEROGA"),
]

_LEADING_TIPO_NUM = re.compile(r"^[A-Z]+\s+\d+\s*")


def classify_norma(titulo: str) -> str | None:
    """Classify a norma by its título; return clase or None if no match."""
    if not titulo:
        return None

    # Normalize: upper-case, strip leading "<TIPO> <NUM> " (scrape duplicate fix).
    t = _LEADING_TIPO_NUM.sub("", titulo.upper(), count=1).strip()

    for clase, pat in _PRIMARY:
        if pat.match(t):
            return clase

    t80 = t[:80]
    for clase, needle in _FALLBACK:
        if needle in t80:
            return clase

    return None
