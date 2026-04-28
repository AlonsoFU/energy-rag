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

    llm_default: str = "claude-sonnet-4-6"
    llm_haiku: str = "claude-haiku-4-5-20251001"
    llm_opus: str = "claude-opus-4-7"

    log_level: str = "INFO"

    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()  # singleton
