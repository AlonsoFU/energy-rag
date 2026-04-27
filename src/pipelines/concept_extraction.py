"""Concept extraction from glosario sections of a norma's text.

Ports the regex-based glosario detection from the legacy
``src/search/concept_extractor.py`` module. The legacy module is a heavy,
multi-step pipeline (TF-IDF + sklearn, file I/O, pickle persistence) that mixes
several concerns. For the new pipelines layer we only need the *pure* part:
given the raw text of a norma, return a list of ``(nombre, definicion)``
candidates extracted from explicit glosario items such as::

    a) COMA: Costo de Operación, Mantenimiento y Administración del sistema.

The TF-IDF, coocurrencia, persistence, and query-boost features of the legacy
module are intentionally **not** ported here — they belong in higher-level
indexing/ranking layers, not in the per-document extraction step.
"""

from __future__ import annotations

import re

# Match a glosario item like:
#   "a) NOMBRE: definición"
#   "1) NOMBRE: definición"
#   "1. NOMBRE: definición"
# where NOMBRE is an uppercase token (acronym or short uppercase phrase) and
# definición is at least 20 characters of inline text on the same line.
GLOSARIO_ITEM = re.compile(
    r"""(?mx)
    ^\s*
    (?:[a-zA-Z]\)|\d+[\.\)])      # bullet: "a)" / "1)" / "1."
    \s*
    (?P<nombre>[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{1,40}?)
    \s*:\s*
    (?P<def>[^\n]{20,500})
    """
)


def extract_concepts_from_text(text: str) -> list[dict]:
    """Extract concepts (nombre, definicion) from glosario sections.

    Args:
        text: Raw text of a norma (or any portion containing a glosario).

    Returns:
        A list of dicts with keys ``"nombre"`` and ``"definicion"``. Both
        values are whitespace-stripped. Duplicates are not removed — callers
        decide how to deduplicate / merge with other concept sources.
    """
    if not text:
        return []

    concepts: list[dict] = []
    for m in GLOSARIO_ITEM.finditer(text):
        nombre = re.sub(r"\s+", " ", m.group("nombre")).strip()
        definicion = m.group("def").strip()
        if not nombre or not definicion:
            continue
        concepts.append({"nombre": nombre, "definicion": definicion})
    return concepts
