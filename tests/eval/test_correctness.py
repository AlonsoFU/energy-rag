from src.eval.correctness import (
    cited_expected,
    content_tokens,
    definition_recall,
)


def test_content_tokens_drops_stopwords_and_accents():
    toks = content_tokens("Aquellos Sistemas de Transmisión radiales")
    # "de" dropped (stopword); accents normalized; len>=3 kept.
    assert "transmision" in toks
    assert "radiales" in toks
    assert "sistemas" in toks
    assert "de" not in toks


def test_definition_recall_full_overlap():
    d = "líneas y subestaciones eléctricas radiales"
    assert definition_recall(d, d) == 1.0


def test_definition_recall_partial():
    definition = "líneas subestaciones radiales interconectadas"
    answer = "Son líneas y subestaciones radiales."  # 3 of 4 content words
    r = definition_recall(answer, definition)
    assert 0.7 <= r < 1.0


def test_definition_recall_zero_when_unrelated():
    assert definition_recall("la receta del pisco sour", "subestaciones radiales") == 0.0


def test_definition_recall_empty_definition_is_zero():
    assert definition_recall("cualquier cosa", "") == 0.0


def test_cited_expected_exact_match():
    cits = [["1160108", "2"], ["1146553", "23"]]
    assert cited_expected(cits, "1160108", "2") is True


def test_cited_expected_degree_sign_normalized():
    cits = [["1146553", "5"]]
    assert cited_expected(cits, "1146553", "5°") is True


def test_cited_expected_miss():
    cits = [["1146553", "23"]]
    assert cited_expected(cits, "1160108", "2") is False


def test_cited_expected_none_norma_is_false():
    assert cited_expected([["X", "1"]], None, None) is False


def test_cited_expected_empty_citations():
    assert cited_expected([], "1160108", "2") is False
