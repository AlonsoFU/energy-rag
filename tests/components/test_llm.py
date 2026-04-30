from unittest.mock import patch, MagicMock
from src.components.llm import LLMProvider, LiteLLMProvider, MockLLMProvider, LLMResponse, get_llm_provider


def test_litellm_provider_calls_litellm():
    """LiteLLMProvider should delegate to litellm.completion and parse the response."""
    with patch("src.components.llm.litellm.completion") as mock:
        mock.return_value = type("X", (), {
            "choices": [type("Y", (), {"message": type("Z", (), {"content": "hello"})})()],
            "usage": type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})(),
            "model": "claude-haiku-4-5",
        })()
        provider = LiteLLMProvider()
        resp = provider.generate("hi", model="claude-haiku-4-5-20251001")
        assert resp.text == "hello"
        assert resp.tokens_in == 10
        assert resp.tokens_out == 5


def test_mock_provider_returns_canned_response():
    """MockLLMProvider returns deterministic responses without network."""
    provider = MockLLMProvider()
    resp = provider.generate("any prompt", model="any-model")
    assert isinstance(resp, LLMResponse)
    assert resp.text  # non-empty
    assert resp.tokens_in > 0
    assert resp.tokens_out > 0
    assert resp.model == "mock"


def test_mock_provider_canned_per_keyword():
    """MockLLMProvider can return different canned responses based on keyword in prompt."""
    canned = {"contextual": "Mock contextual snippet.", "hyde": "Mock hyde answer."}
    provider = MockLLMProvider(canned_responses=canned)
    r1 = provider.generate("Generate contextual context for fragment", model="m")
    r2 = provider.generate("Generate hyde hypothetical answer", model="m")
    r3 = provider.generate("something else", model="m")
    assert r1.text == "Mock contextual snippet."
    assert r2.text == "Mock hyde answer."
    assert "Mock response" in r3.text  # default fallback


def test_get_llm_provider_default_is_mock(monkeypatch):
    """By default (no real API key), get_llm_provider returns MockLLMProvider."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-placeholder-not-real")
    from src.core import config as cfg
    cfg.settings = cfg.Settings()
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_real_when_key_real(monkeypatch):
    """When ANTHROPIC_API_KEY looks real, returns LiteLLMProvider."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-something-real-looking")
    # Force re-read of settings
    from src.core import config as cfg
    cfg.settings = cfg.Settings()
    provider = get_llm_provider()
    assert isinstance(provider, LiteLLMProvider)


def test_litellm_uses_ollama_grammar_when_provided():
    """When model is ollama/* and grammar is given, bypass litellm and call Ollama API directly."""
    grammar = 'root ::= "[Art. 1 de X]"\n'
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "response": "[Art. 1 de X]",
        "prompt_eval_count": 50,
        "eval_count": 10,
    }
    with patch("src.components.llm.requests.post", return_value=fake_resp) as mock_post:
        provider = LiteLLMProvider()
        resp = provider.generate(
            "test prompt",
            model="ollama/qwen2.5:7b",
            grammar=grammar,
        )
        assert resp.text == "[Art. 1 de X]"
        assert resp.tokens_in == 50
        assert resp.tokens_out == 10
        mock_post.assert_called_once()
        # Grammar must be in the request body
        body = mock_post.call_args.kwargs["json"]
        assert body["grammar"] == grammar
        assert body["model"] == "qwen2.5:7b"


def test_litellm_ignores_grammar_for_non_ollama_model():
    """For Claude/OpenAI models, grammar param is ignored (doesn't break call)."""
    with patch("src.components.llm.litellm.completion") as mock:
        mock.return_value = type("X", (), {
            "choices": [type("Y", (), {"message": type("Z", (), {"content": "ok"})})()],
            "usage": type("U", (), {"prompt_tokens": 5, "completion_tokens": 2})(),
            "model": "claude-haiku-4-5",
        })()
        provider = LiteLLMProvider()
        # Pass grammar — should be ignored, normal litellm call should proceed
        resp = provider.generate(
            "hi",
            model="claude-haiku-4-5-20251001",
            grammar="root ::= anything",
        )
        assert resp.text == "ok"
        # Grammar should NOT have been added to litellm kwargs
        kwargs_passed = mock.call_args.kwargs
        assert "grammar" not in kwargs_passed


def test_litellm_no_grammar_uses_default_litellm_path_for_ollama():
    """For Ollama without grammar, use the existing litellm flow (regression check)."""
    with patch("src.components.llm.litellm.completion") as mock:
        mock.return_value = type("X", (), {
            "choices": [type("Y", (), {"message": type("Z", (), {"content": "regular ollama"})})()],
            "usage": type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})(),
            "model": "ollama/qwen2.5:7b",
        })()
        provider = LiteLLMProvider()
        resp = provider.generate("hi", model="ollama/qwen2.5:7b")
        assert resp.text == "regular ollama"
        # max_tokens dropped, num_ctx set (existing Ollama behavior)
        kwargs_passed = mock.call_args.kwargs
        assert "max_tokens" not in kwargs_passed
        assert kwargs_passed.get("num_ctx") == 8192


def test_mock_provider_accepts_grammar_param():
    """MockLLMProvider must accept grammar kwarg so test code stays uniform."""
    provider = MockLLMProvider()
    resp = provider.generate("any prompt", grammar="root ::= 'x'")
    assert isinstance(resp, LLMResponse)
