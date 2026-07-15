"""Application configuration.

Loaded once as a module-level singleton (`settings`). All values are
overridable via environment variables / a .env file — see .env.example.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Tri9T CT-200 Document Intelligence API"

    # SQLAlchemy / SQLite — the relational store for documents, versions, nodes, selections.
    database_url: str = f"sqlite:///{BASE_DIR / 'app.db'}"

    # JSON-file store for generated LLM output (see APPROACH.md for why not MongoDB by default).
    generations_dir: Path = BASE_DIR / "data" / "generations"

    # LLM provider config. Groq is used by default (OpenAI-compatible schema, free tier).
    llm_provider: str = "groq"
    llm_api_key: str | None = None
    llm_model: str = "llama-3.3-70b-versatile"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: float = 30.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
