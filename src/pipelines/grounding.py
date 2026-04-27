"""Citation extraction and grounding verification.

A response passes grounding iff every [Art. X de NORMA_ID] cite points to an
(id_norma, articulo_numero) actually present in the retrieved docs. Empty
citations also fail (the system prompt mandates citing).
"""
import re

CITATION_PATTERN = re.compile(r"\[Art\.\s*(?P<art>\d+°?[a-z]?)\s+de\s+(?P<norma>[A-Z_0-9]+)\]")


def extract_citations(text: str) -> list[tuple[str, str]]:
    """Returns list of (norma_id, articulo_numero_normalized) found in text.

    Strips the degree sign from the article number for normalization.
    """
    return [
        (m.group("norma"), m.group("art").rstrip("°"))
        for m in CITATION_PATTERN.finditer(text)
    ]


def verify_citations(response: str, docs: list[dict]) -> bool:
    """Every citation in `response` must point to an (id_norma, articulo_numero) in docs.

    Articulo numbers are compared with degree sign stripped (so "5" and "5°" match).
    A response with no citations fails grounding (rule from spec).
    """
    cits = extract_citations(response)
    if not cits:
        return False
    valid = {
        (d["id_norma"], str(d["articulo_numero"]).rstrip("°"))
        for d in docs
    }
    return all(c in valid for c in cits)
