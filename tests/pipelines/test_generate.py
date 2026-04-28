from unittest.mock import MagicMock
from src.pipelines.generate import generate_answer


def test_generate_answer_passes_grounding():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="La potencia firme se define en [Art. 1 de DECRETO_62].",
        tokens_in=100, tokens_out=20, model="claude-test",
    )
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "1",
             "articulo_text": "Se define potencia firme..."}]
    result = generate_answer("¿qué es potencia firme?", docs, llm=fake_llm)
    assert result["grounding_pass"] is True
    assert "DECRETO_62" in result["text"]


def test_generate_answer_retries_on_grounding_fail():
    fake_llm = MagicMock()
    fake_llm.generate.side_effect = [
        MagicMock(text="Según [Art. 99 de DECRETO_62]...", tokens_in=100, tokens_out=20, model="m"),
        MagicMock(text="Según [Art. 1 de DECRETO_62]...", tokens_in=110, tokens_out=22, model="m"),
    ]
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "1", "articulo_text": "..."}]
    result = generate_answer("?", docs, llm=fake_llm)
    assert result["grounding_pass"] is True
    assert fake_llm.generate.call_count == 2


def test_generate_answer_marks_failure_after_retry():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="Según [Art. 99 de DECRETO_62]...",  # always invalid
        tokens_in=100, tokens_out=20, model="m",
    )
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "1", "articulo_text": "..."}]
    result = generate_answer("?", docs, llm=fake_llm)
    assert result["grounding_pass"] is False
    # 1 initial + 1 retry = 2 calls
    assert fake_llm.generate.call_count == 2


def test_generate_answer_accumulates_tokens():
    fake_llm = MagicMock()
    fake_llm.generate.side_effect = [
        MagicMock(text="bad [Art. 99 de X]", tokens_in=10, tokens_out=5, model="m"),
        MagicMock(text="good [Art. 1 de X]", tokens_in=15, tokens_out=8, model="m"),
    ]
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "."}]
    result = generate_answer("?", docs, llm=fake_llm)
    assert result["tokens_in"] == 25
    assert result["tokens_out"] == 13
