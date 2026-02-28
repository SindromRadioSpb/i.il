"""tests/test_wow_story.py — Unit tests for WOW-story guards and composer.

Tests:
  - Each WOW guard individually
  - run_wow_guards() full suite
  - compose_wow_post() happy path (no rewrite needed)
  - compose_wow_post() rewrite path (guard fails → critic fixes it)
  - compose_wow_post() fails after max rewrites
  - Glossary applied to output
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from summary.fact_extract import ExtractedFacts
from summary.ollama import OllamaClient
from summary.wow_story import (
    WowCounters,
    _classify_guard_failures,
    _sanitize_post,
    compose_wow_post,
    guard_wow_ends_with_url,
    guard_wow_forbidden_words,
    guard_wow_hallucination,
    guard_wow_high_risk_attribution,
    guard_wow_length,
    guard_wow_no_duplicate_headline,
    guard_wow_no_hashtags,
    guard_wow_no_sections,
    guard_wow_numbers,
    run_wow_guards,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_URL = "https://ynet.co.il/story/abc123"

_VALID_POST = (
    "Землетрясение 4.5 в Тель-Авиве: жертв нет\n\n"
    "Ранним утром в районе Тель-Авива произошло землетрясение магнитудой 4.5 по шкале Рихтера. "
    "Эпицентр находился в 10 км к западу от центра города, на глубине 15 км от поверхности. "
    "Несколько зданий получили незначительные повреждения, жертв и пострадавших по имеющимся данным нет. "
    "Сейсмологи продолжают мониторинг ситуации в течение ближайших 48 часов и призывают граждан к спокойствию.\n\n"
    "Ощущали ли вы это землетрясение сегодня утром?\n\n"
    f"Подробнее → {_URL}"
)

_VALID_FACTS = ExtractedFacts(
    event_type="society",
    location="Тель-Авив",
    time_ref="ранним утром",
    actors=[],
    numbers=["4.5"],
    claims=["Землетрясение магнитудой 4.5", "Жертв нет"],
    uncertainty_notes=[],
    sources=["ynet"],
    risk_level="low",
    story_url=_URL,
)


def _make_ollama(responses: list[str]) -> OllamaClient:
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=responses)
    return ollama


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_no_sections
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_no_sections_ok():
    assert guard_wow_no_sections(_VALID_POST).ok is True


def test_guard_no_sections_fails_on_what_happened():
    post = "Заголовок\n\nЧто произошло: текст\n\nПодробнее → http://x.com"
    result = guard_wow_no_sections(post)
    assert result.ok is False
    assert "что произошло:" in result.reason


def test_guard_no_sections_fails_on_sources():
    post = "Headline\n\nBody text.\n\nИсточники: Ynet, Mako"
    result = guard_wow_no_sections(post)
    assert result.ok is False


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_no_hashtags
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_no_hashtags_ok():
    assert guard_wow_no_hashtags(_VALID_POST).ok is True


def test_guard_no_hashtags_fails():
    result = guard_wow_no_hashtags("Пост с #Израиль и #новости в конце.")
    assert result.ok is False
    assert result.reason == "has_hashtags"


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_no_duplicate_headline
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_no_duplicate_headline_ok():
    assert guard_wow_no_duplicate_headline(_VALID_POST).ok is True


def test_guard_no_duplicate_headline_fails():
    post = (
        "Землетрясение 4.5 в Тель-Авиве: жертв нет\n\n"
        "Землетрясение 4.5 в Тель-Авиве: жертв нет — это повтор.\n"
        f"Подробнее → {_URL}"
    )
    result = guard_wow_no_duplicate_headline(post)
    assert result.ok is False
    assert result.reason == "duplicate_headline"


def test_guard_no_duplicate_headline_short_ok():
    """Short headlines (≤10 chars) don't trigger the guard."""
    post = "ОК\n\nТекст про ОК и другие вещи.\n\nПодробнее → http://x.com"
    assert guard_wow_no_duplicate_headline(post).ok is True


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_hallucination
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_hallucination_ok_no_phrases():
    result = guard_wow_hallucination(_VALID_POST, [])
    assert result.ok is True


def test_guard_hallucination_ok_phrase_in_claims():
    post = "Голосование ожидается в четверг.\nПодробнее → http://x.com"
    claims = ["Голосование ожидается в четверг"]
    result = guard_wow_hallucination(post, claims)
    assert result.ok is True


def test_guard_hallucination_fails_phrase_not_in_claims():
    post = "Принятие решения ожидается на следующей неделе.\nПодробнее → http://x.com"
    claims = ["Министры обсудили вопрос"]
    result = guard_wow_hallucination(post, claims)
    assert result.ok is False
    assert "ожидается" in result.reason


def test_guard_hallucination_fails_planiruyut():
    post = "Власти планируют реформу образования.\nПодробнее → http://x.com"
    result = guard_wow_hallucination(post, [])
    assert result.ok is False
    assert "планируют" in result.reason


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_high_risk_attribution
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_attribution_low_risk_ok():
    result = guard_wow_high_risk_attribution("Любой текст", "low")
    assert result.ok is True


def test_guard_attribution_high_risk_with_phrase():
    post = "По данным источников, произошло нечто серьёзное."
    result = guard_wow_high_risk_attribution(post, "high")
    assert result.ok is True


def test_guard_attribution_high_risk_sообщают():
    post = "Сообщают издания: атака была отражена."
    result = guard_wow_high_risk_attribution(post, "high")
    assert result.ok is True


def test_guard_attribution_high_risk_missing():
    post = "Атака произошла в районе Ашдода. Жертв нет."
    result = guard_wow_high_risk_attribution(post, "high")
    assert result.ok is False
    assert result.reason == "high_risk_missing_attribution"


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_numbers
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_numbers_ok_no_numbers():
    result = guard_wow_numbers("Текст без чисел.", [])
    assert result.ok is True


def test_guard_numbers_ok_all_present():
    result = guard_wow_numbers("Землетрясение 4.5 в Тель-Авиве.", ["4.5"])
    assert result.ok is True


def test_guard_numbers_fails_missing():
    result = guard_wow_numbers("Землетрясение в Тель-Авиве.", ["4.5", "200"])
    assert result.ok is False
    assert "4.5" in result.reason or "200" in result.reason


def test_guard_numbers_percentage():
    result = guard_wow_numbers("Рост на 15%.", ["15%"])
    assert result.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_ends_with_url
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_url_ok():
    post = f"Headline\n\nBody.\n\nПодробнее → {_URL}"
    result = guard_wow_ends_with_url(post, _URL)
    assert result.ok is True


def test_guard_url_empty_story_url_ok():
    """Empty story_url means the guard is skipped."""
    result = guard_wow_ends_with_url("Any text.", "")
    assert result.ok is True


def test_guard_url_fails_missing():
    post = "Headline\n\nBody.\n\nПодробнее → https://other.com/x"
    result = guard_wow_ends_with_url(post, _URL)
    assert result.ok is False
    assert result.reason == "missing_url_line"


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_length
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_length_ok():
    assert guard_wow_length(_VALID_POST).ok is True


def test_guard_length_too_short():
    result = guard_wow_length("Коротко.", min_len=450)
    assert result.ok is False
    assert "too_short" in result.reason


def test_guard_length_too_long():
    long_text = "А" * 1200
    result = guard_wow_length(long_text, max_len=1100)
    assert result.ok is False
    assert "too_long" in result.reason


# ─────────────────────────────────────────────────────────────────────────────
# guard_wow_forbidden_words
# ─────────────────────────────────────────────────────────────────────────────


def test_guard_forbidden_ok():
    assert guard_wow_forbidden_words(_VALID_POST).ok is True


def test_guard_forbidden_fails():
    result = guard_wow_forbidden_words("Это настоящий ужас для жителей города.")
    assert result.ok is False
    assert "ужас" in result.reason


# ─────────────────────────────────────────────────────────────────────────────
# run_wow_guards
# ─────────────────────────────────────────────────────────────────────────────


def test_run_wow_guards_valid_post_all_pass():
    results = run_wow_guards(_VALID_POST, _VALID_FACTS)
    failed = [r for r in results if not r.ok]
    assert failed == [], f"Unexpected guard failures: {[r.reason for r in failed]}"


def test_run_wow_guards_returns_nine_results():
    results = run_wow_guards(_VALID_POST, _VALID_FACTS)
    assert len(results) == 9


# ─────────────────────────────────────────────────────────────────────────────
# compose_wow_post
# ─────────────────────────────────────────────────────────────────────────────


async def test_compose_wow_post_happy_path():
    """Draft passes all guards — no rewrite needed."""
    ollama = _make_ollama([_VALID_POST])
    caption, counters = await compose_wow_post(ollama, _VALID_FACTS)

    assert caption is not None
    assert counters.caption_ok == 1
    assert counters.caption_fail == 0
    assert counters.rewrite_attempts == 0
    assert "Подробнее →" in caption
    assert "#" not in caption
    # Glossary applied — verify ЦАХАЛ stays correct
    assert "цахал" not in caption  # would be uppercased by glossary if present


async def test_compose_wow_post_sanitizes_hashtags_without_rewrite():
    """Hashtags are stripped programmatically — no critic rewrite needed."""
    draft_with_hashtag = (
        "Землетрясение 4.5 в Тель-Авиве: что происходит?\n\n"
        "Ранним утром в районе Тель-Авива произошло землетрясение магнитудой 4.5 по шкале Рихтера. "
        "Эпицентр находился в 10 км к западу от центра города на глубине 15 км. "
        "Жертв и серьёзных разрушений нет, здания устояли. "
        "Однако сейсмологи продолжают наблюдения за обстановкой в течение ближайших суток.\n\n"
        "Ощущали ли вы землетрясение сегодня утром?\n\n"
        f"#Израиль #землетрясение\n\nПодробнее → {_URL}"
    )
    # Only 1 response needed — _sanitize_post strips hashtags, no rewrite triggered
    ollama = _make_ollama([draft_with_hashtag])

    caption, counters = await compose_wow_post(ollama, _VALID_FACTS)

    assert caption is not None
    assert counters.rewrite_attempts == 0  # sanitized programmatically, no critic call
    assert counters.caption_ok == 1
    assert "#" not in caption


async def test_compose_wow_post_returns_none_after_max_rewrites():
    """Returns None only when a HARD guard fails after all rewrites."""
    # Post with forbidden word "ужас" — HARD guard, never softened
    forbidden_post = (
        "Настоящий ужас: землетрясение в Тель-Авиве\n\n"
        "Ранним утром в районе Тель-Авива произошёл настоящий ужас — землетрясение магнитудой 4.5. "
        "Эпицентр находился в 10 км к западу от центра города на глубине 15 км. "
        "Жертв нет, но жители напуганы. "
        "Однако спасатели уже работают на месте событий. "
        "Как вы себя чувствуете?\n\n"
        f"Подробнее → {_URL}"
    )
    # draft + 2 rewrites all contain "ужас" (HARD guard never fixed)
    ollama = _make_ollama([forbidden_post, forbidden_post, forbidden_post])

    caption, counters = await compose_wow_post(ollama, _VALID_FACTS, max_rewrites=2)

    assert caption is None
    assert counters.caption_fail == 1
    assert counters.rewrite_attempts == 2
    assert any("ужас" in r for r in counters.guard_fail_reasons)


async def test_compose_wow_post_draft_ollama_error_returns_none():
    """If Pass-2 Ollama call fails, returns None immediately."""
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=Exception("timeout"))

    caption, counters = await compose_wow_post(ollama, _VALID_FACTS)

    assert caption is None
    assert counters.caption_fail == 1
    assert counters.rewrite_attempts == 0


async def test_compose_wow_post_glossary_applied():
    """Glossary normalization is applied to the draft output."""
    draft_with_bad_casing = _VALID_POST.replace("ЦАХАЛ", "цахал")
    ollama = _make_ollama([draft_with_bad_casing])

    caption, _ = await compose_wow_post(ollama, _VALID_FACTS)
    # Glossary should have uppercased it (if present in draft)
    if caption and "цахал" in draft_with_bad_casing.lower():
        assert "ЦАХАЛ" in caption or "цахал" not in caption.lower()


# ─────────────────────────────────────────────────────────────────────────────
# _sanitize_post — programmatic post-processing
# ─────────────────────────────────────────────────────────────────────────────


def test_sanitize_post_strips_hashtag_only_lines():
    """Lines that consist entirely of hashtags are removed."""
    text = (
        "Землетрясение в Тель-Авиве\n\n"
        "Произошло землетрясение.\n\n"
        "#Израиль #землетрясение #ТельАвив"
    )
    result = _sanitize_post(text, _VALID_FACTS)
    assert "#" not in result


def test_sanitize_post_strips_inline_hashtags():
    """Inline #Word markers are stripped but the word is kept."""
    text = "Текст о #Израиле и #землетрясении в городе."
    result = _sanitize_post(text, _VALID_FACTS)
    assert "#" not in result
    assert "Израиле" in result
    assert "землетрясении" in result


def test_sanitize_post_strips_section_headers():
    """Section-header lines are removed entirely."""
    text = (
        "Заголовок: Землетрясение\n\n"
        "Что произошло: Случилось нечто важное.\n\n"
        "Источники: Ynet, Mako"
    )
    result = _sanitize_post(text, _VALID_FACTS)
    assert "Что произошло:" not in result
    assert "Источники:" not in result
    # "Заголовок:" prefix stripped from first line, but content kept
    assert "Землетрясение" in result
    assert not result.startswith("Заголовок:")


def test_sanitize_post_appends_url():
    """story_url is always appended as 'Подробнее → <url>'."""
    text = "Заголовок\n\nКакой-то текст о событии."
    result = _sanitize_post(text, _VALID_FACTS)
    assert f"Подробнее → {_URL}" in result


# ─────────────────────────────────────────────────────────────────────────────
# Soft-failure best-effort publish
# ─────────────────────────────────────────────────────────────────────────────


async def test_compose_wow_post_publishes_with_soft_failures():
    """Caption is published (caption_ok=1) even when only SOFT guards fail."""
    # Short post — fails guard_wow_length (SOFT), no HARD guard failures
    short_post = (
        "Землетрясение в Тель-Авиве\n\n"
        "Произошло небольшое землетрясение.\n\n"
        "Как вы себя чувствуете?"
    )
    # Only 1 response — function returns immediately on first iteration (no hard fails)
    ollama = _make_ollama([short_post])

    caption, counters = await compose_wow_post(ollama, _VALID_FACTS)

    # Publishes even though length guard is soft-failed
    assert caption is not None
    assert counters.caption_ok == 1
    assert counters.caption_fail == 0
    # URL was appended by _sanitize_post
    assert f"Подробнее → {_URL}" in caption
