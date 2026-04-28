"""Positional self-reference extraction.

Resolves phrases like "el artículo precedente" / "el artículo siguiente"
inside an article by looking at the article's `orden` and finding the
sibling at `orden ± 1` within the same norma.
"""

import re

from src.extraction.regex_refs import ExtractedRef

PRECEDENTE = re.compile(r"\bart[íi]culo\s+(precedente|anterior)\b", re.IGNORECASE)
SIGUIENTE = re.compile(r"\bart[íi]culo\s+(siguiente|posterior|próximo)\b", re.IGNORECASE)


def extract_positional_refs(
    text: str,
    origen_articulo_id: int,
    origen_norma_id: str,
    siblings: list[dict],
) -> list[ExtractedRef]:
    """Resolve 'artículo precedente/siguiente' to specific sibling articulo_ids.

    siblings: list of {'id', 'orden', 'numero'} for all articulos in the same norma.
    """
    refs: list[ExtractedRef] = []
    by_orden = {s["orden"]: s for s in siblings}
    current = next((s for s in siblings if s["id"] == origen_articulo_id), None)
    if not current:
        return refs
    cur_orden = current["orden"]

    if PRECEDENTE.search(text):
        prev = by_orden.get(cur_orden - 1)
        if prev:
            refs.append(ExtractedRef(
                origen_articulo_id=origen_articulo_id,
                destino_articulo_id=prev["id"],
                tipo_relacion="referencia_implicita",
                confianza=0.70,
                metodo_extraccion="regex",
                contexto="(posicional: precedente)",
            ))
    if SIGUIENTE.search(text):
        nxt = by_orden.get(cur_orden + 1)
        if nxt:
            refs.append(ExtractedRef(
                origen_articulo_id=origen_articulo_id,
                destino_articulo_id=nxt["id"],
                tipo_relacion="referencia_implicita",
                confianza=0.70,
                metodo_extraccion="regex",
                contexto="(posicional: siguiente)",
            ))
    return refs
