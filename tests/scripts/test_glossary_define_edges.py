"""Structural detection of definition articles (glossary_define_edges).

The LGSE had 0 `define_termino` edges after ingestion (the reference extractor
only emits `cita`). These tests pin the two STRUCTURAL patterns we detect — no
hardcoded per-concept text:

  A) glossary article: a lettered/numbered list of `Término: definición` entries
     (LGSE art 225, "se entiende por: a) Sistema eléctrico: ...").
  B) titled definition article: "Artículo N°.- Definición de <Término>." — the
     law's own marker. The source XML wraps lines mid-title, so the term must
     survive whitespace normalization.
"""
from scripts.glossary_define_edges import extract_defined_terms


def test_glossary_list_yields_entries():
    txt = (
        "Artículo 225.- Para los efectos de esta ley se entiende por:\n"
        "  a) Sistema eléctrico: conjunto de instalaciones...\n"
        "  b) Autoproductor: todo propietario...\n"
        "  c) Curva de carga: gráfico que representa...\n"
    )
    terms = extract_defined_terms(txt)
    heads = {t for t, p in terms if p == "glossary"}
    assert {"Sistema eléctrico", "Autoproductor", "Curva de carga"} <= heads


def test_glossary_needs_minimum_entries():
    # A single "Term: def" line is not a glossary (could be any sentence).
    txt = "Artículo 5.- El plazo: será de treinta días."
    assert all(p != "glossary" for _, p in extract_defined_terms(txt))


def test_titled_definition_article_full_term():
    # No line wrap: the whole term up to the closing period.
    txt = ("Artículo 74°.- Definición de Sistema de Transmisión Nacional. "
           "El sistema de transmisión nacional es aquel sistema que...")
    terms = extract_defined_terms(txt)
    assert ("Sistema de Transmisión Nacional", "def_article") in terms


def test_titled_definition_article_survives_line_wrap():
    # The obtxml wraps lines mid-title; the term must NOT be truncated at "\n".
    txt = ("Artículo 74°.- Definición de Sistema de Transmisión\n"
           "Nacional. El sistema de transmisión nacional es aquel...")
    terms = extract_defined_terms(txt)
    assert ("Sistema de Transmisión Nacional", "def_article") in terms


def test_plain_article_yields_nothing():
    txt = ("Artículo 117°.- Repartición de Ingresos. Dentro de cada sistema de "
           "transmisión nacional, zonal y dedicado se repartirán los ingresos...")
    assert extract_defined_terms(txt) == []
