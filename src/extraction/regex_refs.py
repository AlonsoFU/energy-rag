"""Regex-based reference extraction for Spanish legal text.

Returns lightweight ExtractedRef dataclasses (NOT Referencia) so the caller
can fill in origen_articulo_id / origen_norma_id from its own context before
persisting. This avoids the XOR-validator on Referencia at extraction time.
"""

import re
from dataclasses import dataclass, field

from src.core.catalogo import Catalogo


@dataclass
class ExtractedRef:
    """Reference extracted from text. Caller fills origen_* before persisting as Referencia."""
    destino_articulo_id: int | None = None
    destino_norma_id: str | None = None
    destino_concepto_id: int | None = None
    tipo_relacion: str = "cita"
    confianza: float = 0.0
    metodo_extraccion: str = "regex"
    destino_subdivision: str | None = None
    contexto: str | None = None
    metadata: dict = field(default_factory=dict)


# Optional subdivision token that may appear before "artículo X" — e.g.
# "la letra b) del artículo 5 del DFL 4". Used as a look-behind via finditer
# on a wrapper pattern.
_SUB_PRE = r"(?:letra\s*[a-z]\)?|inciso\s*\w+|n[úu]mero\s*\d+)"
_SUB_POST = r"(?:letra\s*[a-z]\)?|inciso\s*\w+|n[úu]mero\s*\d+)"

# Pattern: [<sub> del]? artículo N° [<sub>]? del NORMA NUMERO
PATTERN_ART_NORMA = re.compile(rf"""
    (?:(?P<sub_pre>{_SUB_PRE})\s*(?:de\s*la|del?)\s*)?
    (?:art(?:[íi]culo)?s?\.?|art°)\s*
    (?P<art_num>\d+)°?
    (?:\s*(?P<sub_post>{_SUB_POST}))?
    \s*(?:de\s*la|del?)\s*
    (?P<tipo>D\.?S\.?\s*N?°?|Decreto\s*Supremo|Decreto|Ley|DFL|D\.F\.L\.|
        Resoluci[óo]n(?:\s+Exenta)?|Res\.?\s*Ex\.?)
    \s*N?°?\s*
    (?P<num>\d+(?:[\.\,]\d+)?)
""", re.VERBOSE | re.IGNORECASE)

# Pattern: NORMA NUMERO solo (sin artículo)
PATTERN_NORMA = re.compile(r"""
    \b
    (?P<tipo>D\.?S\.?\s*N?°?|Decreto\s*Supremo|Decreto|Ley|DFL|D\.F\.L\.|
        Resoluci[óo]n(?:\s+Exenta)?|Res\.?\s*Ex\.?)
    \s*N?°?\s*
    (?P<num>\d+(?:[\.\,]\d+)?)
    \b
""", re.VERBOSE | re.IGNORECASE)


def extract_regex_refs(text: str, catalogo: Catalogo) -> list[ExtractedRef]:
    """Extract legal references from `text` resolved against `catalogo`.

    Returns ExtractedRef instances; origen_* fields are left for the caller
    (ingest pipeline) to fill in based on which articulo the text came from.
    """
    refs: list[ExtractedRef] = []
    seen: set[tuple] = set()  # avoid dupes (canonico, art_num, sub)
    spans_with_art: list[tuple[int, int, str]] = []  # (start, end, canonico)

    for m in PATTERN_ART_NORMA.finditer(text):
        norma_text = f"{m.group('tipo').strip()} {m.group('num')}"
        canonico = catalogo.resolve(norma_text)
        if not canonico:
            continue
        art_num = m.group("art_num")
        sub = m.group("sub_pre") or m.group("sub_post")
        key = (canonico, art_num, sub)
        if key in seen:
            continue
        seen.add(key)
        spans_with_art.append((m.start(), m.end(), canonico))
        refs.append(ExtractedRef(
            destino_norma_id=canonico,
            destino_subdivision=sub,
            tipo_relacion="cita",
            confianza=0.90,
            metodo_extraccion="regex",
            contexto=text[max(0, m.start() - 50):m.end() + 50],
            metadata={"articulo_numero": art_num},
        ))

    for m in PATTERN_NORMA.finditer(text):
        # Skip if this match is inside an already-captured ART_NORMA span
        if any(s <= m.start() and m.end() <= e for s, e, _ in spans_with_art):
            continue
        norma_text = f"{m.group('tipo').strip()} {m.group('num')}"
        canonico = catalogo.resolve(norma_text)
        if not canonico:
            continue
        key = (canonico, None, None)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ExtractedRef(
            destino_norma_id=canonico,
            tipo_relacion="cita",
            confianza=0.85,
            metodo_extraccion="regex",
            contexto=text[max(0, m.start() - 50):m.end() + 50],
            metadata={},
        ))
    return refs
