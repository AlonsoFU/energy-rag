"""Citation extraction and grounding verification.

A response passes grounding iff every [Art. X de NORMA_ID] cite points to an
(id_norma, articulo_numero) actually present in the retrieved docs. Empty
citations also fail (the system prompt mandates citing).
"""
import re

# Citation parser. Accepts several natural variants the LLM produces:
#   [Art. 5 de 1146553]            ← canonical
#   [Art. 5° de 1146553]           ← with degree sign
#   [Artículo 5 de 1146553]        ← full word
#   [Artículo 5° de 1146553]
#   [art. 5° de 1146553]           ← lowercase
#   [Art. 5 bis de 1146553]        ← bis/ter
#   [Art. 36 D de 1146553]         ← letter suffix
CITATION_PATTERN = re.compile(
    r"\["
    r"(?:art[íi]culos?\.?|arts?\.)"                          # Art / Art. / Artículo / Artículos
    r"\s*"
    r"(?P<art>\d+\s*[°º]?(?:\s*(?:bis|ter|quater|quinquies))?(?:\s*[A-Z])?)"
    r"\s+(?:de|del)\s+"                                      # 'de' or 'del'
    r"(?P<norma>[A-Z_0-9]+)"
    r"\]",
    re.IGNORECASE,
)


def _normalize_art(s: str) -> str:
    """Drop degree signs and collapse whitespace so '5°' and '5' match."""
    s = s.replace("°", "").replace("º", "")
    return re.sub(r"\s+", " ", s).strip()


def extract_citations(text: str) -> list[tuple[str, str]]:
    """Returns list of (norma_id, articulo_numero_normalized) found in text."""
    return [
        (m.group("norma"), _normalize_art(m.group("art")))
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
        (d["id_norma"], _normalize_art(str(d["articulo_numero"])))
        for d in docs
    }
    return all(c in valid for c in cits)
