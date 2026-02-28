"""config/settings.py — Centralised configuration via pydantic-settings.

All settings are loaded from environment variables (or .env file).
Secrets (FB_PAGE_ACCESS_TOKEN, CF_SYNC_TOKEN) must never appear in logs.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_path: str = Field(default="data/news_hub.db")

    # --- Scheduler ---
    scheduler_interval_sec: int = Field(default=600, ge=60)
    scheduler_jitter_sec: int = Field(default=60, ge=0)

    # --- Sources ---
    sources_registry_path: str = Field(default="../../sources/registry.yaml")

    # --- Ollama ---
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:7b-instruct")
    ollama_timeout_sec: int = Field(default=30, ge=5)
    ollama_max_retries: int = Field(default=2, ge=0)

    # --- Summary ---
    summary_target_min: int = Field(default=400, ge=100)
    summary_target_max: int = Field(default=700, ge=200)
    max_summaries_per_run: int = Field(default=50, ge=1)

    # --- Facebook (secrets — never log) ---
    fb_posting_enabled: bool = Field(default=False)
    fb_page_id: str = Field(default="")
    fb_page_access_token: str = Field(default="")
    fb_max_per_hour: int = Field(default=8, ge=1)
    fb_max_per_day: int = Field(default=40, ge=1)
    fb_min_interval_sec: int = Field(default=180, ge=0)

    # --- Image Cache ---
    image_cache_dir: str = Field(default="data/images")
    image_max_size_mb: int = Field(default=5, ge=1)
    image_fetch_timeout_sec: int = Field(default=15, ge=5)

    # --- Cloudflare Sync (token is a secret) ---
    cf_sync_enabled: bool = Field(default=False)
    cf_sync_url: str = Field(default="")
    cf_sync_token: str = Field(default="")

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")  # json | text
    log_file: str = Field(default="data/logs/engine.jsonl")

    # --- Environment ---
    service_env: str = Field(default="dev")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        if v not in ("json", "text"):
            raise ValueError("log_format must be 'json' or 'text'")
        return v

    @field_validator("service_env")
    @classmethod
    def validate_service_env(cls, v: str) -> str:
        if v not in ("dev", "prod"):
            raise ValueError("service_env must be 'dev' or 'prod'")
        return v

    def safe_repr(self) -> dict[str, object]:
        """Return settings dict with secrets redacted — safe to log."""
        d = self.model_dump()
        for secret_key in ("fb_page_access_token", "cf_sync_token"):
            if d.get(secret_key):
                d[secret_key] = "***REDACTED***"
        return d
