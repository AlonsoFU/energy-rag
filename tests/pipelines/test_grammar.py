"""Tests for src/pipelines/grammar.py — citation extraction + GBNF builder.

The grammar module is LLM-agnostic: it consumes retrieved docs and produces
either a GBNF grammar (for Ollama constrained decoding) or a JSON schema
(for API-based structured output). Both consume the same citation list.
"""
from src.pipelines.grammar import (
    extract_valid_citations,
    build_gbnf_grammar,
    build_json_schema,
)


def test_extract_valid_citations_basic():
    docs = [
        {"id_norma": "1146553", "articulo_numero": "5", "articulo_text": "..."},
        {"id_norma": "250604", "articulo_numero": "28", "articulo_text": "..."},
    ]
    cits = extract_valid_citations(docs)
    assert ("5", "1146553") in cits
    assert ("28", "250604") in cits


def test_extract_valid_citations_dedupes():
    docs = [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "a"},
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "b"},  # dup
    ]
    assert len(extract_valid_citations(docs)) == 1


def test_extract_valid_citations_preserves_format():
    """Articulo with degree sign / bis suffix stays literal — grammar is verbatim."""
    docs = [
        {"id_norma": "X", "articulo_numero": "5°", "articulo_text": "."},
        {"id_norma": "X", "articulo_numero": "12 bis", "articulo_text": "."},
    ]
    cits = extract_valid_citations(docs)
    assert ("5°", "X") in cits
    assert ("12 bis", "X") in cits


def test_extract_valid_citations_empty():
    assert extract_valid_citations([]) == []


def test_build_gbnf_grammar_includes_all_citations():
    citations = [("1", "ABC"), ("2", "ABC"), ("5°", "DEF")]
    grammar = build_gbnf_grammar(citations)
    # Each literal citation must appear in grammar text
    assert '"[Art. 1 de ABC]"' in grammar
    assert '"[Art. 2 de ABC]"' in grammar
    assert '"[Art. 5° de DEF]"' in grammar
    # Must define a root rule
    assert "root" in grammar


def test_build_gbnf_grammar_empty_returns_empty():
    """No valid citations means no constraint — caller decides what to do."""
    assert build_gbnf_grammar([]) == ""


def test_build_gbnf_grammar_structure_allows_text_and_citations():
    """Grammar must allow free text plus enforced citations (not citations-only)."""
    citations = [("1", "ABC")]
    grammar = build_gbnf_grammar(citations)
    # Root should reference both a text element and a citation element
    # Implementation detail: text chars are "anything except '['"
    assert "citation" in grammar
    # Should include negated bracket char class — \x5b is '['
    assert "\\x5b" in grammar or "[^[]" in grammar or '[^\\[]' in grammar


def test_build_json_schema_basic():
    citations = [("5", "1146553"), ("28", "250604")]
    schema = build_json_schema(citations)
    assert schema["type"] == "object"
    assert "answer" in schema["properties"]
    assert "citations" in schema["properties"]
    enum = schema["properties"]["citations"]["items"]["enum"]
    assert "[Art. 5 de 1146553]" in enum
    assert "[Art. 28 de 250604]" in enum


def test_build_json_schema_empty():
    """No citations → schema with empty enum (caller decides)."""
    schema = build_json_schema([])
    assert schema["properties"]["citations"]["items"]["enum"] == []


def test_gbnf_escapes_special_chars_in_norma_id():
    """Norma IDs are typically alphanumeric but be defensive."""
    citations = [("1", "DECRETO_62")]
    grammar = build_gbnf_grammar(citations)
    assert '"[Art. 1 de DECRETO_62]"' in grammar
