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


def test_generate_passes_grammar_for_ollama_model():
    """When model is ollama/*, generate_answer must build grammar and pass it."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="[Art. 1 de X]", tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}]
    generate_answer("?", docs, llm=fake_llm, model="ollama/qwen2.5:7b")
    # Grammar must be passed
    call_kwargs = fake_llm.generate.call_args.kwargs
    assert "grammar" in call_kwargs
    assert call_kwargs["grammar"] != ""
    assert '"[Art. 1 de X]"' in call_kwargs["grammar"]


def test_generate_no_grammar_for_api_model():
    """When model is non-Ollama (Claude/OpenAI), grammar param should be None."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="[Art. 1 de X]", tokens_in=10, tokens_out=5, model="claude-haiku-4-5",
    )
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}]
    generate_answer("?", docs, llm=fake_llm, model="claude-haiku-4-5-20251001")
    call_kwargs = fake_llm.generate.call_args.kwargs
    # Grammar either absent or None — both acceptable
    assert call_kwargs.get("grammar") is None


def test_generate_skips_grammar_when_no_docs():
    """Empty docs → no valid citations → no grammar (would be invalid anyway)."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="No info.", tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    generate_answer("?", [], llm=fake_llm, model="ollama/qwen2.5:7b")
    call_kwargs = fake_llm.generate.call_args.kwargs
    assert call_kwargs.get("grammar") in (None, "")
