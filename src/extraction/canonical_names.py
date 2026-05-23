"""Deterministic canonical concept-name extraction (rule A).

When a glossary DEFINITION reopens by restating the concept name and
extending it into a longer noun phrase ("Comité: Comité de adjudicación y
supervisión…"), the real canonical name is that longer phrase and the bare
word is an alias. Legal-safe: the canonical name is a VERBATIM span of the
definition text (not invented, not re-accented); only orthographic
normalization is used to compare the prefix. No fuzzy, no thresholds beyond
the explicit word-count gate.

See spec docs/superpowers/specs/2026-05-22-canonical-concept-names-design.md.
"""
from __future__ import annotations

import re
import unicodedata

# Max words the canonical phrase may add over the bare name before it is
# considered too long to auto-apply (sent to review instead).
MAX_EXTRA_WORDS = 8

# Where the canonical noun phrase ends — cut BEFORE the first match.
BOUNDARY = re.compile(
    r"(?:[.;:,]"
    r"|\b(?:a\s+que|al\s+que|a\s+los\s+que|a\s+las\s+que|a\s+la\s+que"
    r"|que\s+se\s+refiere|que\s+establece|que\s+fija|que\s+indica"
    r"|que\s+se\s+\w+|en\s+adelante|seg[uú]n|conforme)\b"
    r"|\b(?:establecid[oa]s?|definid[oa]s?|constituid[oa]s?|conformad[oa]s?"
    r"|integrad[oa]s?|denominad[oa]s?|es|son|ser[aá]n?|consiste|corresponde"
    r"|comprende|contemplad[oa]s?|se\s+entender[aá])\b)",
    re.IGNORECASE,
)


def _na(s: str) -> str:
    """Lowercase + strip accents (orthographic normalization only)."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def extract_canonical(nombre: str, definicion: str) -> tuple[str | None, str]:
    """Return (canonical|None, confidence) where confidence is one of
    'high', 'low', 'no-fire'.

    - no-fire: definition does not restate+extend the name → leave concept.
    - high:    clean boundary, 1..MAX_EXTRA_WORDS added → auto-apply.
    - low:     boundary but too long, OR no clean cut → review queue.
    """
    if not definicion:
        return None, "no-fire"
    defi = definicion.strip()
    if not _na(defi).startswith(_na(nombre).strip()):
        return None, "no-fire"
    after = defi[len(nombre):]
    if not after[:1].isspace():            # must EXTEND with more words
        return None, "no-fire"
    m = BOUNDARY.search(after)
    if not m:
        return None, "low"                 # no clean cut → review, no proposal
    canonical = (nombre + after[: m.start()]).strip().rstrip(" ,;:.")
    extra_words = len(canonical.split()) - len(nombre.split())
    if extra_words <= 0:
        return None, "no-fire"             # boundary right after name
    conf = "high" if extra_words <= MAX_EXTRA_WORDS else "low"
    return canonical, conf


def decide_action(nombre: str, definicion: str, metadata: dict | None,
                  other_names: set[str]) -> dict:
    """Decide what to do with one concept. Pure (no DB).

    `other_names` is the set of `_na`-normalized names of all OTHER concepts,
    used to detect a rename that would collide with an existing concept (a
    merge — routed to review, never auto-applied).

    Returns a dict with 'action' in {'skip','rename','review'} plus
    'canonical' and 'reason' where relevant.
    """
    if metadata and metadata.get("canonical_source"):
        return {"action": "skip", "reason": "already_canonicalized"}
    canonical, conf = extract_canonical(nombre, definicion)
    if conf == "no-fire":
        return {"action": "skip", "reason": "no-fire"}
    if conf == "low":
        kind = "no_boundary" if canonical is None else "too_long"
        return {"action": "review", "canonical": canonical,
                "reason": f"low_confidence: {kind}"}
    # high
    if _na(canonical) in other_names:
        return {"action": "review", "canonical": canonical, "reason": "collision"}
    return {"action": "rename", "canonical": canonical, "reason": "high"}
