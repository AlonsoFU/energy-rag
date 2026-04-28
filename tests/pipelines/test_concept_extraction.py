"""Tests for src.pipelines.concept_extraction."""

from src.pipelines.concept_extraction import extract_concepts_from_text


def test_extracts_glosario_definitions():
    text = """
    Artículo 2°.- Para los efectos del presente reglamento, se entenderá por:

    a) COMA: Costo de Operación, Mantenimiento y Administración del sistema.
    b) VATT: Valor Anual de Transmisión Troncal.
    c) AVI: Anualidad del Valor de Inversión.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "COMA" in names
    assert "VATT" in names
    assert "AVI" in names
    coma = next(c for c in concepts if c["nombre"] == "COMA")
    assert "Costo de Operación" in coma["definicion"]


def test_returns_empty_list_when_no_glosario():
    text = "Este artículo no contiene glosario alguno, solo prosa común."
    assert extract_concepts_from_text(text) == []


def test_handles_numbered_glosario():
    text = """
    Definiciones:
    1) SEN: Sistema Eléctrico Nacional, definido por la ley.
    2) CEN: Coordinador Eléctrico Nacional encargado de la operación.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "SEN" in names
    assert "CEN" in names


def test_filters_too_short_definitions():
    # Definitions shorter than 20 chars should be skipped
    text = """
    a) FOO: corto.
    b) BAR: Esta definición es suficientemente larga para superar el umbral.
    """
    concepts = extract_concepts_from_text(text)
    names = {c["nombre"] for c in concepts}
    assert "FOO" not in names
    assert "BAR" in names


def test_strips_whitespace():
    text = "a)   COMA   :   Costo de Operación, Mantenimiento y Administración del sistema.   "
    concepts = extract_concepts_from_text(text)
    assert any(c["nombre"] == "COMA" for c in concepts)
    coma = next(c for c in concepts if c["nombre"] == "COMA")
    assert coma["nombre"] == "COMA"
    assert not coma["definicion"].startswith(" ")
