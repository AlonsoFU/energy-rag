"""Real-data and edge-case tests for concept extraction.

Verifies that the extractor works against the actual 103-norma corpus and
also covers each glosario format (letter, numeric, dash, bare, multi-format)
and the section-header false-positive filter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipelines.concept_extraction import extract_concepts_from_text

NORMAS_DIR = Path(__file__).parent.parent.parent / "data" / "normas_completas"


@pytest.mark.integration
def test_concept_extraction_yields_at_least_20_unique_concepts_across_corpus():
    if not NORMAS_DIR.exists() or not list(NORMAS_DIR.rglob("*.json")):
        pytest.skip("No real corpus")
    seen: set[str] = set()
    for f in NORMAS_DIR.rglob("*.json"):
        if f.name.endswith(".bak"):
            continue
        try:
            d = json.load(open(f))
        except Exception:
            continue
        texto = d.get("texto_completo") or ""
        for c in extract_concepts_from_text(texto):
            seen.add(c["nombre"])
    # The original (pre-rewrite) system extracted 29; we accept >=20 as a
    # reasonable threshold to allow for different normalisations.
    assert (
        len(seen) >= 20
    ), f"only {len(seen)} unique concepts found: {sorted(seen)[:30]}"


def test_extracts_dash_prefix():
    text = "- COMA: Costo de Operación, Mantenimiento y Administración del sistema."
    concepts = extract_concepts_from_text(text)
    assert any(c["nombre"] == "COMA" for c in concepts)


def test_extracts_bare_uppercase():
    text = """
    Para los efectos del presente reglamento se entenderá lo siguiente:

    COMA: Costo de Operación, Mantenimiento y Administración.
    VATT: Valor Anual de Transmisión Troncal.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "COMA" in names
    assert "VATT" in names


def test_does_not_match_section_headers():
    text = """
    Artículo 5°: Las empresas deberán cumplir con la obligación.
    Título II: De las Concesiones eléctricas en el sistema interconectado.
    Capítulo 1: Disposiciones generales del presente reglamento de servicios.
    Anexo A: Listado de instalaciones y empresas eléctricas reguladas.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "Artículo" not in names
    assert "Título" not in names
    assert "Capítulo" not in names
    assert "Anexo" not in names


def test_filters_legal_modifier_verbs():
    """Patterns like 'a) Agrégase ... :' must not be treated as concepts."""
    text = """
    a) Agrégase la siguiente oración final: "esto es un texto modificatorio."
    b) Sustitúyese la frase X por Y: "este es el reemplazo correspondiente."
    c) COMA: Costo de Operación, Mantenimiento y Administración.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "COMA" in names
    assert not any("Agrégase" in n for n in names)
    assert not any("Sustitúyese" in n for n in names)


def test_supports_nbsp_indented_lines():
    """Real legal texts often indent with non-breaking spaces (\\xa0)."""
    text = (
        "\xa0 \xa0 a) Biomasa: la materia orgánica sólida, biodegradable.\n"
        "\xa0 \xa0 b) Biocombustibles sólidos: los combustibles elaborados a partir de biomasa.\n"
    )
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "Biomasa" in names
    assert "Biocombustibles sólidos" in names


def test_deduplicates_repeated_names():
    text = """
    a) COMA: primera definición que es suficientemente larga para pasar.
    b) COMA: segunda mención del mismo término que también pasa el filtro.
    """
    concepts = extract_concepts_from_text(text)
    coma = [c for c in concepts if c["nombre"] == "COMA"]
    # First-occurrence wins.
    assert len(coma) == 1
    assert coma[0]["definicion"].startswith("primera")
