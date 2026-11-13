"""
config.py — Central configuration loader for the Python AI service.

Reads all settings from environment variables (via python-dotenv).
No secret or connection string should ever be hard-coded here.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All fields have sensible defaults for local development.
    Override by setting the corresponding env var or placing values in .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM Provider ──────────────────────────────────────────────────────────
    llm_provider: str = "openai"           # openai | google | anthropic | ollama
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "network_knowledge"

    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "cnt_fault_diagnosis"

    # ── Service networking ────────────────────────────────────────────────────
    ai_service_host: str = "0.0.0.0"
    ai_service_port: int = 8000
    api_port: int = 4000

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Runtime ───────────────────────────────────────────────────────────────
    python_env: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
