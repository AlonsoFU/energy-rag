"""Alias-based reference extraction (Pattern 5).

Looks up informal names from each NormaEntry.aliases (e.g., "LGSE" -> DFL_4)
inside the input text and emits ExtractedRef per match.
"""

import re

from src.core.catalogo import Catalogo
from src.extraction.regex_refs import ExtractedRef


def extract_alias_refs(text: str, catalogo: Catalogo) -> list[ExtractedRef]:
    """Find informal aliases (e.g., 'LGSE') in text and emit ExtractedRef per match.

    Uses each NormaEntry.aliases. Case-insensitive whole-word match.
    Deduplicates by canonical id (one ref per norma per text).
    """
    refs: list[ExtractedRef] = []
    seen: set[str] = set()
    for entry in catalogo.all_entries():
        if entry.id_canonico in seen:
            continue
        for alias in entry.aliases:
            if not alias:
                continue
            pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
            m = pattern.search(text)
            if m:
                seen.add(entry.id_canonico)
                refs.append(ExtractedRef(
                    destino_norma_id=entry.id_canonico,
                    tipo_relacion="cita",
                    confianza=0.85,
                    metodo_extraccion="regex",
                    contexto=text[max(0, m.start() - 30):m.end() + 30],
                    metadata={"alias_used": alias},
                ))
                break  # one ref per entry
    return refs
