"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Website Content Auditor API."""

    app_name: str = "Website Content Auditor"
    app_version: str = "0.1.0"
    debug: bool = False
    sqlite_database_path: str = "data/auditor.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    default_max_pages: int = Field(default=8, ge=1)
    default_max_depth: int = Field(default=2, ge=0)
    cache_ttl_hours: int = Field(default=24, ge=1)
    enable_playwright_fallback: bool = False
    reports_directory: str = "reports"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()

