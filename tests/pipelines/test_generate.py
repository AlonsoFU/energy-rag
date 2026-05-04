from unittest.mock import MagicMock
from src.pipelines.generate import generate_answer


def test_generate_answer_passes_grounding():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        # JSON because response_format is active for any docs+model combo
        text='{"answer": "La potencia firme se define en", "citations": ["[Art. 1 de DECRETO_62]"]}',
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
        MagicMock(text='{"answer": "Según", "citations": ["[Art. 99 de DECRETO_62]"]}',
                  tokens_in=100, tokens_out=20, model="m"),
        MagicMock(text='{"answer": "Según", "citations": ["[Art. 1 de DECRETO_62]"]}',
                  tokens_in=110, tokens_out=22, model="m"),
    ]
    docs = [{"id_norma": "DECRETO_62", "articulo_numero": "1", "articulo_text": "..."}]
    result = generate_answer("?", docs, llm=fake_llm)
    assert result["grounding_pass"] is True
    assert fake_llm.generate.call_count == 2


def test_generate_answer_marks_failure_after_retry():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text='{"answer": "Según", "citations": ["[Art. 99 de DECRETO_62]"]}',
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
        MagicMock(text='{"answer": "bad", "citations": ["[Art. 99 de X]"]}',
                  tokens_in=10, tokens_out=5, model="m"),
        MagicMock(text='{"answer": "good", "citations": ["[Art. 1 de X]"]}',
                  tokens_in=15, tokens_out=8, model="m"),
    ]
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "."}]
    result = generate_answer("?", docs, llm=fake_llm)
    assert result["tokens_in"] == 25
    assert result["tokens_out"] == 13


def test_generate_passes_response_format_when_docs_present():
    """generate_answer must build a JSON schema from docs and pass it as response_format."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text='{"answer": "ok", "citations": ["[Art. 1 de X]"]}',
        tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}]
    generate_answer("?", docs, llm=fake_llm, model="ollama/qwen2.5:7b")
    call_kwargs = fake_llm.generate.call_args.kwargs
    assert call_kwargs.get("response_format") is not None
    schema = call_kwargs["response_format"]
    enum = schema["properties"]["citations"]["items"]["enum"]
    assert "[Art. 1 de X]" in enum


def test_generate_skips_response_format_when_no_docs():
    """Empty docs → no valid citations → no response_format (avoid empty enum)."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="No info.", tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    generate_answer("?", [], llm=fake_llm, model="ollama/qwen2.5:7b")
    call_kwargs = fake_llm.generate.call_args.kwargs
    assert call_kwargs.get("response_format") is None


def test_generate_handles_plain_text_when_no_format():
    """Without response_format, plain text path still works (regression check)."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="No info.", tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    result = generate_answer("?", [], llm=fake_llm, model="ollama/qwen2.5:7b")
    assert result["text"] == "No info."


def test_generate_falls_back_when_json_parse_fails():
    """If model emits non-JSON despite response_format, treat as plain text."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(
        text="not valid json [Art. 1 de X]",
        tokens_in=10, tokens_out=5, model="ollama/qwen2.5:7b",
    )
    docs = [{"id_norma": "X", "articulo_numero": "1", "articulo_text": "."}]
    result = generate_answer("?", docs, llm=fake_llm, model="ollama/qwen2.5:7b")
    # Verifier still finds the inline citation and grounds it
    assert result["grounding_pass"] is True
