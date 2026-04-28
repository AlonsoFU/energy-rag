import os
from src.core.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "myhost")
    monkeypatch.setenv("POSTGRES_PORT", "1234")
    monkeypatch.setenv("POSTGRES_DB", "mydb")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = Settings()
    assert s.postgres_host == "myhost"
    assert s.postgres_port == 1234
    assert s.dsn() == "postgresql://u:p@myhost:1234/mydb"

def test_settings_has_model_defaults(monkeypatch, tmp_path):
    """When no env or .env override exists, the field defaults must hold.
    We point Settings at a non-existent .env so a developer's local overrides
    don't break the test."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    # Make sure no LLM_*/QWEN_* env vars leak in
    for var in ("LLM_DEFAULT", "LLM_HAIKU", "LLM_OPUS",
                "QWEN_EMBEDDING_MODEL", "QWEN_RERANKER_MODEL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=str(tmp_path / "nonexistent.env"))
    assert s.qwen_embedding_model == "Qwen/Qwen3-Embedding-0.6B"
    assert s.qwen_reranker_model == "Qwen/Qwen3-Reranker-0.6B"
    assert s.llm_default == "claude-sonnet-4-6"
