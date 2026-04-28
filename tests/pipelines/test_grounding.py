from src.pipelines.grounding import verify_citations, extract_citations


def test_extract_citations_finds_pattern():
    text = "Según [Art. 5 de DECRETO_62] y también [Art. 12 de DFL_4]..."
    cits = extract_citations(text)
    assert ("DECRETO_62", "5") in cits
    assert ("DFL_4", "12") in cits


def test_verify_citations_pass():
    docs = [
        {"id_norma": "DECRETO_62", "articulo_numero": "5", "articulo_text": "..."},
        {"id_norma": "DFL_4", "articulo_numero": "12", "articulo_text": "..."},
    ]
    response = "Según [Art. 5 de DECRETO_62] y [Art. 12 de DFL_4]..."
    assert verify_citations(response, docs) is True


def test_verify_citations_fail_invented():
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "5", "articulo_text": "..."}]
    response = "Según [Art. 99 de DECRETO_62]..."  # Art. 99 NOT in docs
    assert verify_citations(response, docs) is False


def test_verify_citations_fail_no_citations():
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "5", "articulo_text": "..."}]
    response = "Una respuesta sin ninguna cita explícita."
    assert verify_citations(response, docs) is False


def test_verify_handles_articulo_with_degree_sign():
    """Citation [Art. 5° de DECRETO_62] should match doc with articulo_numero='5°' or '5'."""
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "5°", "articulo_text": "..."}]
    response = "[Art. 5 de DECRETO_62]"
    assert verify_citations(response, docs) is True
