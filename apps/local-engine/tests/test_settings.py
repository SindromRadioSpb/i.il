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
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.summary_target_min == 400
    assert s.summary_target_max == 700
    assert s.max_summaries_per_run == 50
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
