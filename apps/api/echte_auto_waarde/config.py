"""Application configuration.

All settings have local-first defaults so the API runs with no .env file at all.
Everything that could differ per machine (database location, Ollama endpoint,
model name) is overridable through environment variables prefixed with EAW_.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/echte_auto_waarde/config.py -> repository root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EAW_",
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Echte Auto Waarde API"
    environment: str = "local"
    debug: bool = True

    # Database — SQLite file inside the repository's data/ directory.
    database_path: Path = REPO_ROOT / "data" / "automotive.db"

    # Frontend origins allowed to call this API during local development.
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Local AI (Ollama). AI is optional: the core valuation never depends on it.
    ai_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    # A 7B model on CPU spends the first request loading several gigabytes
    # before it emits a token; 60 seconds expires during that cold start.
    ollama_timeout_seconds: float = 180.0

    # Optional RDW open-data enrichment (added in a later phase).
    rdw_enabled: bool = False
    rdw_base_url: str = "https://opendata.rdw.nl/resource"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
