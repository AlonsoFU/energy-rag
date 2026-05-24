"""Capa 0 — detect a WEAK marked definition (route it to the resolver).

These are cheap, topic-neutral SUSPICION signals; they only decide what to
look at, never the legal answer. A definition is suspect when it is empty, a
circular label (it mostly restates the concept's own name), too short to carry
substance, or a remission (it points elsewhere instead of defining).
"""
from __future__ import annotations

import re
import unicodedata

# A definition that, after removing the concept's own words, has at least this
# many remaining content words is considered substantive.
_MIN_CONTENT_WORDS = 4
_STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o", "a",
         "que", "se", "en", "al", "lo", "su", "sus", "para", "por", "con"}
_REMISSION = re.compile(
    r"\b(a que se refiere|se refiere|señalad[oa] en|definid[oa] en|"
    r"establecid[oa] en|en los t[ée]rminos de|conforme a lo dispuesto)\b",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-záéíóúñ]{2,}", _norm(text))
    return [w for w in words if w not in _STOP]


def is_label(nombre: str, definicion: str) -> bool:
    """True if the definition's content words are essentially just the name's."""
    name_words = set(_content_words(nombre))
    extra = [w for w in _content_words(definicion) if w not in name_words]
    return len(extra) < _MIN_CONTENT_WORDS


def is_remission(definicion: str) -> bool:
    return bool(_REMISSION.search(definicion or ""))


def suspect_definition(nombre: str, definicion: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not (definicion or "").strip():
        reasons.append("empty")
        return True, reasons
    if is_remission(definicion):
        reasons.append("remission")
    if is_label(nombre, definicion):
        reasons.append("label")
    return (len(reasons) > 0, reasons)
