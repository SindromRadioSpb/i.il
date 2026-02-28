"""tests/test_guards.py — Summary guard tests.

Port of apps/worker/test/summary_guards.test.ts.
"""

from __future__ import annotations

import pytest

from summary.guards import (
    guard_forbidden_words,
    guard_high_risk,
    guard_length,
    guard_numbers,
)


# ─────────────────────────────────────────────────────────────────────────────
# guard_length
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_length_ok_within_range():
    assert guard_length("А" * 500, 400, 700).ok is True


def test_guard_length_ok_at_exact_minimum():
    assert guard_length("А" * 400, 400, 700).ok is True


def test_guard_length_ok_at_exact_maximum():
    assert guard_length("А" * 700, 400, 700).ok is True


def test_guard_length_fails_too_short():
    result = guard_length("А" * 100, 400, 700)
    assert result.ok is False
    assert result.reason is not None
    assert "too_short" in result.reason


def test_guard_length_fails_too_long():
    result = guard_length("А" * 800, 400, 700)
    assert result.ok is False
    assert result.reason is not None
    assert "too_long" in result.reason


def test_guard_length_reason_contains_actual_length():
    result = guard_length("А" * 100, 400, 700)
    assert "100" in (result.reason or "")


# ─────────────────────────────────────────────────────────────────────────────
# guard_forbidden_words
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_forbidden_ok_clean_text():
    assert guard_forbidden_words("Правительство обсудило бюджет.").ok is True


def test_guard_forbidden_fails_ужас():
    result = guard_forbidden_words("Это настоящий ужас для города.")
    assert result.ok is False
    assert result.reason is not None
    assert "ужас" in result.reason


def test_guard_forbidden_fails_кошмар():
    assert guard_forbidden_words("Настоящий кошмар.").ok is False


def test_guard_forbidden_fails_шок():
    assert guard_forbidden_words("Рынки в шоке.").ok is False


def test_guard_forbidden_fails_сенсация():
    assert guard_forbidden_words("Это сенсация!").ok is False


def test_guard_forbidden_case_insensitive():
    assert guard_forbidden_words("УЖАС").ok is False


# ─────────────────────────────────────────────────────────────────────────────
# guard_numbers
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_numbers_ok_all_present():
    titles = ["3 ракеты выпущены", "50% граждан"]
    generated = "ЦАХАЛ сообщил о 3 ракетах. Поддержка составила 50%."
    assert guard_numbers(titles, generated).ok is True


def test_guard_numbers_fails_missing_number():
    titles = ["100 пострадавших"]
    generated = "Пострадало несколько человек."
    result = guard_numbers(titles, generated)
    assert result.ok is False
    assert result.reason is not None
    assert "100" in result.reason


def test_guard_numbers_ok_no_numbers_in_source():
    titles = ["Переговоры продолжаются", "Ситуация сложная"]
    generated = "Стороны продолжают переговоры."
    assert guard_numbers(titles, generated).ok is True


def test_guard_numbers_handles_percentage():
    titles = ["Рост 3.5%"]
    generated = "Экономика выросла на 3.5%."
    assert guard_numbers(titles, generated).ok is True


def test_guard_numbers_ok_empty_titles():
    assert guard_numbers([], "Что-то произошло.").ok is True


# ─────────────────────────────────────────────────────────────────────────────
# guard_high_risk
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_high_risk_ok_low_risk():
    assert guard_high_risk("Правительство обсудило бюджет.", "low").ok is True


def test_guard_high_risk_ok_medium_risk():
    assert guard_high_risk("Суд рассмотрел дело.", "medium").ok is True


def test_guard_high_risk_fails_missing_attribution():
    result = guard_high_risk("Произошёл теракт в центре города.", "high")
    assert result.ok is False
    assert result.reason == "high_risk_requires_attribution"


def test_guard_high_risk_ok_with_attribution():
    body = "По данным источников, произошёл теракт в центре города."
    assert guard_high_risk(body, "high").ok is True


def test_guard_high_risk_attribution_case_insensitive():
    body = "По Данным Источников, в городе введён комендантский час."
    assert guard_high_risk(body, "high").ok is True
