"""Edge cases in entity grounding observed in legal citations."""
from src.pipelines.grounding import verify_citations, extract_citations


def test_citation_with_letter_suffix():
    """Citation like [Art. 5b de X] should still be parsed."""
    text = "[Art. 5b de DECRETO_62]"
    cits = extract_citations(text)
    assert len(cits) == 1
    assert cits[0][0] == "DECRETO_62"


def test_citation_at_end_of_sentence():
    text = "La regulación lo establece [Art. 1 de DFL_4]."
    cits = extract_citations(text)
    assert ("DFL_4", "1") in cits


def test_citation_inside_parenthesis():
    """Citations sometimes appear inside parens (Chilean drafting style)."""
    text = "Lo dispuesto ([Art. 5 de DECRETO_62]) implica que..."
    cits = extract_citations(text)
    assert ("DECRETO_62", "5") in cits


def test_verify_with_no_citations_in_response():
    """A response without any citation must fail grounding."""
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}]
    assert verify_citations("Una afirmación sin citas.", docs) is False


def test_verify_citation_to_unknown_norma_fails():
    """Even if articulo_numero matches, an unknown norma must fail."""
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "1", "articulo_text": "..."}]
    assert verify_citations("[Art. 1 de OTRA_NORMA]", docs) is False
