"""LLM provider abstraction.

Two implementations:
- LiteLLMProvider: real API via litellm (Claude, OpenAI, etc.). Used in production.
- MockLLMProvider: deterministic, network-free. Used by default in dev and tests.

Use `get_llm_provider()` to get the right one based on environment.
"""
from dataclasses import dataclass, field
from typing import Protocol
import litellm
from src.core import config as _config


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


class LLMProvider(Protocol):
    """Common interface. Both LiteLLM and Mock implement this."""
    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        cache_control: bool = False,
    ) -> LLMResponse: ...


class LiteLLMProvider:
    """Real LLM provider backed by litellm."""

    def __init__(self):
        litellm.api_key = _config.settings.anthropic_api_key

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        cache_control: bool = False,
    ) -> LLMResponse:
        model = model or _config.settings.llm_default
        messages = []
        if system:
            if cache_control:
                messages.append({
                    "role": "system",
                    "content": [
                        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
                    ],
                })
            else:
                messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Ollama bug: max_tokens (num_predict) competes with num_ctx and truncates
        # output for prompts > 1k tokens. Drop max_tokens for ollama and bump
        # num_ctx via litellm extra params instead.
        if model.startswith("ollama/"):
            kwargs.pop("max_tokens", None)
            # 8k context fits our largest prompts (Contextual Retrieval + 10 docs)
            kwargs["num_ctx"] = 8192

        resp = litellm.completion(**kwargs)
        return LLMResponse(
            text=resp.choices[0].message.content,
            model=resp.model,
            tokens_in=resp.usage.prompt_tokens,
            tokens_out=resp.usage.completion_tokens,
        )


@dataclass
class MockLLMProvider:
    """Deterministic LLM provider for dev and tests. No network access.

    Returns canned responses keyed by substring matching in the prompt.
    Falls back to a generic 'Mock response: <prefix of prompt>' if no key matches.
    """
    canned_responses: dict[str, str] = field(default_factory=dict)

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        cache_control: bool = False,
    ) -> LLMResponse:
        text = self._pick_response(prompt)
        # Token approximation: 1 token ~= 4 chars
        tokens_in = max(1, len(prompt) // 4)
        tokens_out = max(1, len(text) // 4)
        return LLMResponse(text=text, model="mock", tokens_in=tokens_in, tokens_out=tokens_out)

    def _pick_response(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        for keyword, response in self.canned_responses.items():
            if keyword.lower() in prompt_lower:
                return response
        return f"Mock response: {prompt[:60]}{'...' if len(prompt) > 60 else ''}"


def _is_real_api_key(key: str) -> bool:
    """Heuristic: real keys start with 'sk-ant-api' and have substantive length."""
    return key.startswith("sk-ant-api") and len(key) > 30


def get_llm_provider() -> LLMProvider:
    """Return the appropriate provider based on settings.

    - If ANTHROPIC_API_KEY looks real -> LiteLLMProvider
    - Otherwise (placeholder/missing) -> MockLLMProvider with default canned responses
    """
    if _is_real_api_key(_config.settings.anthropic_api_key):
        return LiteLLMProvider()
    return MockLLMProvider(canned_responses={
        "contextual": "Este fragmento describe disposiciones tecnicas de la norma referida.",
        "hyde": "La regulacion define este concepto como una capacidad tecnica establecida en el reglamento.",
        "multi-query": "1. Como se define el termino?\n2. Cual es su aplicacion practica?\n3. Que norma lo regula?",
        "step-back": "Cual es la regulacion general aplicable?",
        "respuesta": "La normativa establece [Art. 1 de DECRETO_X] que se trata de un concepto regulado.",
    })
