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

def test_settings_has_model_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    s = Settings()
    assert s.qwen_embedding_model == "Qwen/Qwen3-Embedding-0.6B"
    assert s.qwen_reranker_model == "Qwen/Qwen3-Reranker-0.6B"
    assert s.llm_default == "claude-sonnet-4-6"
