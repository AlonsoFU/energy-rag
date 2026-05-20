from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "energy_rag"
    postgres_user: str = "energy_rag"
    postgres_password: str

    anthropic_api_key: str

    qwen_embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    qwen_reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    embedder_device: str = "auto"  # "auto" | "cuda" | "cpu" — set "cpu" when LLM occupies GPU
    reranker_device: str = "auto"  # same semantics as embedder_device

    llm_default: str = "claude-sonnet-4-6"
    llm_haiku: str = "claude-haiku-4-5-20251001"
    llm_opus: str = "claude-opus-4-7"

    log_level: str = "INFO"

    # Hybrid citation pattern: when False, generate plain (no JSON schema)
    # and validate citations post-hoc with verify_citations + retry-on-fail.
    # Set False by default because Ollama's JSON-schema constrained decoding
    # deadlocks on qwen3.5 (upstream issues #15540, #15260, #15502 — combined
    # with our think=false makes the format constraint silently fail or hang).
    # Switch True only with a runtime that implements constrained decoding
    # correctly (vLLM, llama.cpp direct, API providers like Anthropic/OpenAI).
    use_constrained_decoding: bool = False

    # Char budget for the article block in the generation prompt. Tail-trims
    # docs (lowest rank dropped first) so prompt fits in num_ctx and the
    # JSON-schema-constrained sampler doesn't deadlock. Default 45000 chars
    # ≈ 13k tokens (Spanish + qwen BPE ≈ 3.5 chars/token), leaving room for
    # system (~1.5k tokens) + query + response in 16k ctx. 0 disables.
    prompt_doc_char_budget: int = 45000

    # Ollama context window. MUST exceed the largest prompt (10 docs with full
    # article text + Contextual enrichment ≈ 15k tokens). At 8192 the prompt
    # overflows and the JSON-schema-constrained sampler DEADLOCKS (0 tokens,
    # connection held forever) — the root cause of the "deterministic Ollama
    # hang". 16384 fits the prompt; plain generation degraded gracefully but
    # constrained decoding does not.
    ollama_num_ctx: int = 16384

    # Candidate-pool depth fed into RRF fusion (BM25 + vector each retrieve
    # this many before fusion/rerank). Default 50 = unchanged behavior. Raise
    # via env (RETRIEVAL_POOL_DEPTH) to test whether grounding is recall-limited
    # (right norma missed by shallow retrieval) vs generation-limited (LLM
    # ceiling). Pure deterministic recall lever — no fuzzy, no thresholds.
    retrieval_pool_depth: int = 50

    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()  # singleton
