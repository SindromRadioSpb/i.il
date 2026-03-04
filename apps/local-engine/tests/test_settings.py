"""tests/test_settings.py — Settings model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_defaults():
    s = Settings(_env_file=None)  # ignore local .env so we test pure defaults
    assert s.database_path == "data/news_hub.db"
    assert s.scheduler_interval_sec == 600
    assert s.scheduler_jitter_sec == 60
    assert s.llm_provider == "ollama"
    assert s.llm_base_url == "http://localhost:11434"
    assert s.llm_model == "qwen2.5:7b-instruct"
    assert s.llm_timeout_sec == 30
    assert s.llm_max_retries == 2
    assert s.llm_json_mode == "strict"
    # legacy aliases remain readable for backward compatibility
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.summary_target_min == 400
    assert s.summary_target_max == 700
    assert s.max_summaries_per_run == 10
    assert s.fb_posting_enabled is False
    assert s.cf_sync_enabled is False
    assert s.log_level == "INFO"
    assert s.log_format == "json"
    assert s.service_env == "dev"


def test_log_level_normalised(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings()
    assert s.log_level == "DEBUG"


def test_invalid_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_log_format(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "xml")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_service_env(monkeypatch):
    monkeypatch.setenv("SERVICE_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_llm_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_llm_json_mode(monkeypatch):
    monkeypatch.setenv("LLM_JSON_MODE", "raw")
    with pytest.raises(ValidationError):
        Settings()


def test_llamacpp_default_base_url_when_not_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llamacpp")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_provider == "llamacpp"
    assert s.llm_base_url == "http://localhost:8001/v1"


def test_llamacpp_explicit_base_url_preserved(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llamacpp")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:18001/v1")
    s = Settings(_env_file=None)
    assert s.llm_base_url == "http://localhost:18001/v1"


def test_legacy_ollama_aliases_map_to_llm_when_llm_not_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen-legacy")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SEC", "55")
    monkeypatch.setenv("OLLAMA_MAX_RETRIES", "7")

    s = Settings(_env_file=None)

    assert s.llm_base_url == "http://127.0.0.1:11434"
    assert s.llm_model == "qwen-legacy"
    assert s.llm_timeout_sec == 55
    assert s.llm_max_retries == 7


def test_safe_repr_redacts_secrets(monkeypatch):
    monkeypatch.setenv("FB_PAGE_ACCESS_TOKEN", "super_secret_token")
    monkeypatch.setenv("CF_SYNC_TOKEN", "another_secret")
    s = Settings()
    safe = s.safe_repr()
    assert safe["fb_page_access_token"] == "***REDACTED***"
    assert safe["cf_sync_token"] == "***REDACTED***"
    # Non-secret fields remain
    assert safe["log_level"] == "INFO"


def test_safe_repr_empty_secrets_not_redacted():
    """Empty secrets should not be redacted (they're empty, not secret)."""
    s = Settings(_env_file=None)  # ignore local .env so tokens are empty
    safe = s.safe_repr()
    assert safe["fb_page_access_token"] == ""
    assert safe["cf_sync_token"] == ""


def test_scheduler_interval_min_bound(monkeypatch):
    monkeypatch.setenv("SCHEDULER_INTERVAL_SEC", "30")
    with pytest.raises(ValidationError):
        Settings()


def test_prod_env(monkeypatch):
    monkeypatch.setenv("SERVICE_ENV", "prod")
    s = Settings()
    assert s.service_env == "prod"
