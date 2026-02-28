"""tests/test_format.py — Summary section parsing and formatting tests.

Port of apps/worker/test/summary_format.test.ts.
"""

from __future__ import annotations

import pytest

from summary.format import ParsedSummary, format_body, format_full, parse_sections

VALID_TEXT = (
    "Заголовок: В Тель-Авиве произошло землетрясение\n"
    "Что произошло: Землетрясение магнитудой 4.5 произошло ранним утром.\n"
    "Почему важно: Это первое ощутимое землетрясение за последнее десятилетие.\n"
    "Что дальше: Сейсмологи продолжают мониторинг ситуации.\n"
    "Источники: Ynet, Mako"
)


# ─────────────────────────────────────────────────────────────────────────────
# parse_sections — valid input
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_valid_text_returns_parsed_summary():
    result = parse_sections(VALID_TEXT)
    assert result is not None
    assert result.title == "В Тель-Авиве произошло землетрясение"
    assert "4.5" in result.what_happened
    assert "десятилетие" in result.why_important
    assert "мониторинг" in result.whats_next
    assert result.sources == "Ynet, Mako"


def test_parse_strips_whitespace_in_section_values():
    text = (
        "Заголовок:   Заголовок с пробелами\n"
        "Что произошло: Событие.\n"
        "Почему важно: Важность.\n"
        "Что дальше: Ожидается обновление.\n"
        "Источники: Haaretz"
    )
    result = parse_sections(text)
    assert result is not None
    assert result.title == "Заголовок с пробелами"


def test_parse_joins_multi_line_section_content():
    text = (
        "Заголовок: Заголовок\n"
        "Что произошло: Первое предложение.\n"
        "Второе предложение той же секции.\n"
        "Почему важно: Важность.\n"
        "Что дальше: Ожидается обновление.\n"
        "Источники: Ynet"
    )
    result = parse_sections(text)
    assert result is not None
    assert "Первое предложение" in result.what_happened
    assert "Второе предложение" in result.what_happened


# ─────────────────────────────────────────────────────────────────────────────
# parse_sections — invalid input
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_returns_none_when_заголовок_missing():
    text = (
        "Что произошло: Событие.\n"
        "Почему важно: Важность.\n"
        "Что дальше: Ожидается обновление.\n"
        "Источники: Ynet"
    )
    assert parse_sections(text) is None


def test_parse_returns_none_when_что_произошло_missing():
    text = (
        "Заголовок: Заголовок\n"
        "Почему важно: Важность.\n"
        "Что дальше: Ожидается обновление.\n"
        "Источники: Ynet"
    )
    assert parse_sections(text) is None


def test_parse_returns_none_when_section_value_empty():
    text = (
        "Заголовок:\n"
        "Что произошло: Событие.\n"
        "Почему важно: Важность.\n"
        "Что дальше: Ожидается обновление.\n"
        "Источники: Ynet"
    )
    assert parse_sections(text) is None


def test_parse_returns_none_for_empty_string():
    assert parse_sections("") is None


def test_parse_returns_none_for_partial_sections():
    assert parse_sections("Заголовок: Только заголовок") is None


# ─────────────────────────────────────────────────────────────────────────────
# format_body
# ─────────────────────────────────────────────────────────────────────────────


def test_format_body_contains_three_sections():
    parsed = parse_sections(VALID_TEXT)
    assert parsed is not None
    body = format_body(parsed)
    assert "Что произошло:" in body
    assert "Почему важно:" in body
    assert "Что дальше:" in body


def test_format_body_excludes_источники():
    parsed = parse_sections(VALID_TEXT)
    assert parsed is not None
    body = format_body(parsed)
    assert "Источники:" not in body


def test_format_body_excludes_title():
    parsed = parse_sections(VALID_TEXT)
    assert parsed is not None
    body = format_body(parsed)
    assert parsed.title not in body


# ─────────────────────────────────────────────────────────────────────────────
# format_full
# ─────────────────────────────────────────────────────────────────────────────


def test_format_full_title_is_first_line():
    parsed = parse_sections(VALID_TEXT)
    assert parsed is not None
    full = format_full(parsed)
    lines = full.split("\n")
    assert lines[0] == parsed.title


def test_format_full_contains_all_five_sections():
    parsed = parse_sections(VALID_TEXT)
    assert parsed is not None
    full = format_full(parsed)
    assert "Что произошло:" in full
    assert "Почему важно:" in full
    assert "Что дальше:" in full
    assert "Источники:" in full
    assert parsed.title in full
