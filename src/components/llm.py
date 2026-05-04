"""LLM provider abstraction.

Two implementations:
- LiteLLMProvider: real API via litellm (Claude, OpenAI, etc.). Used in production.
- MockLLMProvider: deterministic, network-free. Used by default in dev and tests.

Use `get_llm_provider()` to get the right one based on environment.
"""
from dataclasses import dataclass, field
from typing import Protocol
import litellm
import requests
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
        response_format: dict | None = None,
    ) -> LLMResponse: ...


class LiteLLMProvider:
    """Real LLM provider backed by litellm.

    For Ollama with structured-output (`response_format` JSON schema), bypasses
    litellm and posts directly to /api/generate — litellm doesn't pass through
    Ollama's `format` parameter. Non-Ollama models receive the schema as
    litellm's `response_format` (Anthropic / OpenAI native support).
    """

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
        response_format: dict | None = None,
    ) -> LLMResponse:
        model = model or _config.settings.llm_default

        # Constrained-decoding path for Ollama: bypass litellm so we can
        # set Ollama's `format` parameter (JSON schema enforced at sampler).
        if response_format and model.startswith("ollama/"):
            return self._ollama_with_schema(
                prompt=prompt, model=model, system=system,
                temperature=temperature, schema=response_format,
            )

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

        # Pass JSON schema through to API providers (Anthropic/OpenAI handle natively).
        if response_format and not model.startswith("ollama/"):
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"schema": response_format}}

        resp = litellm.completion(**kwargs)
        return LLMResponse(
            text=resp.choices[0].message.content,
            model=resp.model,
            tokens_in=resp.usage.prompt_tokens,
            tokens_out=resp.usage.completion_tokens,
        )

    def _ollama_with_schema(
        self,
        prompt: str,
        model: str,
        system: str | None,
        temperature: float,
        schema: dict,
    ) -> LLMResponse:
        """Direct call to Ollama's /api/generate with `format` JSON schema.

        Ollama 0.5+ supports JSON schema-constrained output: the response is
        forced to match the schema at the sampler level (similar to GBNF).
        Enum-restricted fields effectively give us constrained decoding for
        citations.
        """
        model_name = model.replace("ollama/", "")
        body = {
            "model": model_name,
            "prompt": prompt,
            "format": schema,
            # Disable reasoning/thinking mode (Qwen3+ series). Without this,
            # the structured JSON ends up in `thinking` instead of `response`.
            "think": False,
            "stream": False,
            "options": {
                "num_ctx": 8192,
                "temperature": temperature,
            },
        }
        if system:
            body["system"] = system
        host = getattr(_config.settings, "ollama_host", "http://localhost:11434")
        # 300s instead of 180: qwen3.5:9b in tight VRAM occasionally needs >180s
        # for long prompts; the prior 180 limit caused 14% query loss in eval.
        resp = requests.post(f"{host}/api/generate", json=body, timeout=300)
        data = resp.json()
        return LLMResponse(
            text=data.get("response", ""),
            model=model,
            tokens_in=data.get("prompt_eval_count", 0),
            tokens_out=data.get("eval_count", 0),
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
        response_format: dict | None = None,
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
