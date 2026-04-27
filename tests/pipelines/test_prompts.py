from src.pipelines.prompts import build_answer_prompt, get_answer_system


def test_build_answer_prompt_includes_articulos():
    docs = [
        {"id_norma": "DECRETO_62", "articulo_numero": "1°", "articulo_text": "TEXTO 1"},
        {"id_norma": "DFL_4", "articulo_numero": "2°", "articulo_text": "TEXTO 2"},
    ]
    prompt = build_answer_prompt("¿qué es COMA?", docs)
    assert "TEXTO 1" in prompt
    assert "TEXTO 2" in prompt
    assert "DECRETO_62" in prompt
    assert "1°" in prompt
    assert "¿qué es COMA?" in prompt


def test_get_answer_system_has_citation_rules():
    sys = get_answer_system()
    assert "[Art." in sys or "verbatim" in sys.lower()
