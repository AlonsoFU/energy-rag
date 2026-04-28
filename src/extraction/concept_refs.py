"""Concept-derived reference extraction.

Pattern 7: when a text mentions a concept name (e.g., "COMA") that exists in
the conceptos table, emit an ExtractedRef linking origen_articulo_id ->
concepto.id.
"""

import re

from src.extraction.regex_refs import ExtractedRef


def extract_concept_refs(
    text: str,
    origen_articulo_id: int,
    origen_norma_id: str,
    conceptos: list[dict],
) -> list[ExtractedRef]:
    """For each concept in `conceptos` whose nombre or alias appears in text
    (case-insensitive, whole-word), emit an ExtractedRef linking
    origen_articulo_id -> concepto.id.

    `conceptos` items: {"id": int, "nombre": str, "aliases": list[str] | None}
    """
    refs: list[ExtractedRef] = []
    seen: set[int] = set()
    for c in conceptos:
        if c["id"] in seen:
            continue
        names = [c["nombre"]] + (c.get("aliases") or [])
        for name in names:
            if not name:
                continue
            pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
            m = pattern.search(text)
            if m:
                seen.add(c["id"])
                refs.append(ExtractedRef(
                    origen_articulo_id=origen_articulo_id,
                    origen_norma_id=origen_norma_id,
                    destino_concepto_id=c["id"],
                    tipo_relacion="cita",
                    confianza=0.90,
                    metodo_extraccion="regex",
                    contexto=text[max(0, m.start() - 30):m.end() + 30],
                    metadata={"matched_term": name},
                ))
                break  # one ref per concept
    return refs
