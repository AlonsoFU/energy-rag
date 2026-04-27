"""Concept extraction from glosario sections of a norma's text.

Ports the regex-based glosario detection from the legacy
``src/search/concept_extractor.py`` module. The legacy module is a heavy,
multi-step pipeline (TF-IDF + sklearn, file I/O, pickle persistence) that mixes
several concerns. For the new pipelines layer we only need the *pure* part:
given the raw text of a norma, return a list of ``(nombre, definicion)``
candidates extracted from explicit glosario items such as::

    a) COMA: Costo de Operación, Mantenimiento y Administración del sistema.

Real Chilean legal glosarios use multiple formats. We support:

* ``a) NOMBRE: definición``     (letter prefix)
* ``1) NOMBRE: definición``     (numeric prefix with parenthesis)
* ``1. NOMBRE: definición``     (numeric prefix with dot)
* ``- NOMBRE: definición``      (dash prefix)
* ``NOMBRE: definición``        (bare; only when NOMBRE is all-uppercase, to
                                  avoid catching prose-embedded false positives)

The TF-IDF, coocurrencia, persistence, and query-boost features of the legacy
module are intentionally **not** ported here — they belong in higher-level
indexing/ranking layers, not in the per-document extraction step.
"""

from __future__ import annotations

import re

# Indentation in real legal texts often uses non-breaking spaces (\xa0), so the
# leading whitespace class explicitly includes them.
_LEAD_WS = r"[ \t\xa0]*"

# Items with explicit prefixes ("a)", "1)", "1.", or leading "- ").
PREFIXED_ITEM = re.compile(
    rf"""(?mx)
    ^{_LEAD_WS}
    (?:
        [a-zA-Z]\)        |  # a)
        \d+\)             |  # 1)
        \d+\.             |  # 1.
        -                    # -
    )
    {_LEAD_WS}
    (?P<nombre>[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\.\s]{{1,60}}?)
    {_LEAD_WS}:{_LEAD_WS}
    (?P<def>[^\n]{{20,500}})
    """
)

# Bare definitions ("NOMBRE: ...") with no prefix. Restricted to all-uppercase
# names to keep false positives down.
BARE_ITEM = re.compile(
    rf"""(?mx)
    ^{_LEAD_WS}
    (?P<nombre>[A-ZÁÉÍÓÚÑ\.]{{2,}}(?:\s+[A-ZÁÉÍÓÚÑ\.]+)*)
    {_LEAD_WS}:{_LEAD_WS}
    (?P<def>[^\n]{{20,500}})
    """
)

# Section headers and other tokens that should NEVER be treated as a concept
# name even if they happen to match the regex.
EXCLUDE_PREFIXES = re.compile(
    r"^(Artículo|ARTÍCULO|Art\.|Título|TÍTULO|Capítulo|CAPÍTULO|"
    r"Anexo|ANEXO|N°|Nº|Considerando|CONSIDERANDO|Visto|Vistos|"
    r"Decreto|DECRETO|Resolución|RESOLUCIÓN|Ley|LEY|"
    # Spanish legal-modifier verbs (these introduce textual amendments, not
    # definitions): "Agrégase ...", "Sustitúyese ...", etc.
    r"Agrégase|Agrégase|Agréganse|"
    r"Sustitúyese|Sustitúyase|Sustitúyense|"
    r"Reemplázase|Reemplácese|Reemplázanse|"
    r"Intercálase|Intercálese|Intercálanse|"
    r"Suprímese|Suprímanse|"
    r"Modifícase|Modifícanse|"
    r"Elimínase|Elimínanse|"
    r"Incorpórase|Incorpóranse|"
    r"Inclúyese|Inclúyense|"
    r"Derógase|Deróganse|"
    r"Refúndense|Refúndase)",
    re.IGNORECASE,
)


def _is_valid_term(nombre: str) -> bool:
    """Filter section headers and other non-definitions."""
    nombre = nombre.strip()
    if not nombre:
        return False
    if EXCLUDE_PREFIXES.match(nombre):
        return False
    if len(nombre) > 60:
        return False
    return True


def extract_concepts_from_text(text: str) -> list[dict]:
    """Extract concepts from glosario sections of a norma's text.

    Args:
        text: Raw text of a norma (or any portion containing a glosario).

    Returns:
        A list of dicts with keys ``"nombre"`` and ``"definicion"``. Both
        values are whitespace-stripped. Duplicate names are deduplicated
        (first-occurrence wins) since callers typically just want a unique
        glossary view.
    """
    if not text:
        return []

    seen: dict[str, str] = {}

    for m in PREFIXED_ITEM.finditer(text):
        nombre = re.sub(r"\s+", " ", m.group("nombre")).strip()
        definicion = m.group("def").strip()
        if not _is_valid_term(nombre) or not definicion:
            continue
        if nombre not in seen:
            seen[nombre] = definicion

    for m in BARE_ITEM.finditer(text):
        nombre = re.sub(r"\s+", " ", m.group("nombre")).strip()
        definicion = m.group("def").strip()
        if not _is_valid_term(nombre) or not definicion:
            continue
        # Restrict bare patterns to all-uppercase names (acronyms / titlecase
        # sequences in caps) to reduce false positives from prose lines.
        compact = nombre.replace(" ", "").replace(".", "")
        if not compact or not compact.isupper():
            continue
        if nombre not in seen:
            seen[nombre] = definicion

    return [{"nombre": n, "definicion": d} for n, d in seen.items()]
