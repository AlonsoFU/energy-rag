from unittest.mock import patch
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
