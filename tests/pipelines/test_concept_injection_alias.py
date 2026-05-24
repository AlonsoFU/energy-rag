"""Alias-aware injection: when a user queries by an ALIAS/acronym (e.g. "qué es
SEC"), the injected doc must contain the alias token explicitly linked to its
canonical name + definition. Otherwise the article defines only the expansion,
the literal acronym is absent from the context, and the LLM refuses (it cannot
ground the query token). Root-caused 2026-05-23.
"""
from src.pipelines import concept_injection as ci


def test_alias_query_injects_alias_link_doc(monkeypatch):
    # Query term "SEC" is an ALIAS of canonical "Superintendencia de Electricidad
    # y Combustibles" (defined at 1160108/2). The injected doc must surface "SEC".
    monkeypatch.setattr(
        ci, "find_subject_concept",
        lambda q: ("1160108", "2", "Superintendencia de Electricidad y Combustibles.",
                   "Superintendencia de Electricidad y Combustibles", "SEC"))
    docs = [{"id_norma": "1160108", "articulo_numero": "2",
             "articulo_text": "X" * 9000}]  # the buried full glossary
    out = ci.inject_definition("qué es SEC", docs)
    top = out[0]["articulo_text"]
    assert "SEC" in top                       # the literal alias token is present
    assert "Superintendencia de Electricidad y Combustibles" in top
    assert out[0]["id_norma"] == "1160108" and out[0]["articulo_numero"] == "2"
    # full glossary copy replaced (one doc for that article, the alias chunk)
    assert sum(1 for d in out if d["articulo_numero"] == "2") == 1


def test_canonical_query_is_not_treated_as_alias(monkeypatch):
    # Query term equals the canonical name (modulo orthography) → NOT an alias →
    # no synthetic alias-link doc; existing behaviour applies.
    monkeypatch.setattr(
        ci, "find_subject_concept",
        lambda q: ("1160108", "2", "def.",
                   "Superintendencia de Electricidad y Combustibles", None))
    from src.core import config as cfg
    monkeypatch.setattr(cfg.settings, "inject_focused_definition", False, raising=False)
    docs = [{"id_norma": "1160108", "articulo_numero": "2", "articulo_text": "FULL"}]
    out = ci.inject_definition("qué es la Superintendencia de Electricidad y Combustibles", docs)
    assert out[0]["articulo_text"] == "FULL"          # legacy path, not alias chunk
    assert "_alias_link" not in out[0]


def test_no_alias_link_when_definition_blank(monkeypatch):
    monkeypatch.setattr(
        ci, "find_subject_concept",
        lambda q: ("1160108", "2", "  ",
                   "Superintendencia de Electricidad y Combustibles", "SEC"))
    from src.core import config as cfg
    monkeypatch.setattr(cfg.settings, "inject_focused_definition", False, raising=False)
    docs = [{"id_norma": "1160108", "articulo_numero": "2", "articulo_text": "FULL"}]
    out = ci.inject_definition("qué es SEC", docs)
    # No usable definition → fall back to existing behaviour (no alias chunk).
    assert out[0]["articulo_text"] == "FULL"
