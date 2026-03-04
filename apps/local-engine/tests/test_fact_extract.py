"""tests/test_fact_extract.py — Unit tests for Pass-1 fact extraction.

Tests:
  - JSON extraction helper (bare JSON, fenced block, invalid)
  - ExtractedFacts model coercion
  - extract_facts() happy path and failure modes
  - story_url / risk_level always come from caller, not LLM
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from summary.fact_extract import (
    ExtractedFacts,
    _build_fact_user,
    _coerce_facts,
    extract_facts,
    extract_json_from_text,
)
from summary.ollama import OllamaClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_FACTS_DICT = {
    "event_type": "security",
    "location": "Тель-Авив",
    "time_ref": "утром",
    "actors": ["ЦАХАЛ"],
    "numbers": ["3", "200"],
    "claims": ["Три ракеты перехвачены системой Железный купол"],
    "uncertainty_notes": [],
    "sources": ["ynet"],
    "risk_level": "high",
    "story_url": "https://ynet.co.il/abc",
}

_VALID_FACTS_JSON = json.dumps(_VALID_FACTS_DICT)


def _make_item(title_he: str, source_id: str = "ynet", snippet_he: str | None = None):
    obj = MagicMock()
    obj.title_he = title_he
    obj.source_id = source_id
    obj.snippet_he = snippet_he
    return obj


def _make_ollama(response: str) -> OllamaClient:
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(return_value=response)
    return ollama


# ─────────────────────────────────────────────────────────────────────────────
# extract_json_from_text
# ─────────────────────────────────────────────────────────────────────────────


def test_extract_json_bare():
    raw = '{"event_type": "other", "location": null}'
    result = extract_json_from_text(raw)
    assert result["event_type"] == "other"
    assert result["location"] is None


def test_extract_json_fenced_block():
    raw = '```json\n{"event_type": "security"}\n```'
    result = extract_json_from_text(raw)
    assert result["event_type"] == "security"


def test_extract_json_fenced_no_lang_label():
    raw = "```\n{\"key\": \"value\"}\n```"
    result = extract_json_from_text(raw)
    assert result["key"] == "value"


def test_extract_json_with_prose_before():
    raw = 'Here is the JSON:\n{"event_type": "politics"}\nDone.'
    result = extract_json_from_text(raw)
    assert result["event_type"] == "politics"


def test_extract_json_invalid_raises():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        extract_json_from_text("This is just plain text, no JSON here.")


def test_extract_json_empty_raises():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        extract_json_from_text("")


# ─────────────────────────────────────────────────────────────────────────────
# _coerce_facts
# ─────────────────────────────────────────────────────────────────────────────


def test_coerce_facts_valid():
    facts = _coerce_facts(dict(_VALID_FACTS_DICT), "https://example.com/s1", "high")
    assert facts.event_type == "security"
    assert facts.location == "Тель-Авив"
    assert "3" in facts.numbers
    assert facts.story_url == "https://example.com/s1"  # caller value wins
    assert facts.risk_level == "high"


def test_coerce_facts_caller_url_overrides_llm():
    """story_url from LLM must be overridden with caller-provided value."""
    data = dict(_VALID_FACTS_DICT)
    data["story_url"] = "https://llm-invented-url.com"
    facts = _coerce_facts(data, "https://real-caller-url.com", "low")
    assert facts.story_url == "https://real-caller-url.com"


def test_coerce_facts_caller_risk_overrides_llm():
    """risk_level from LLM must be overridden with caller-provided value."""
    data = dict(_VALID_FACTS_DICT)
    data["risk_level"] = "high"
    facts = _coerce_facts(data, "https://example.com", "low")
    assert facts.risk_level == "low"


def test_coerce_facts_invalid_event_type_becomes_other():
    data = {"event_type": "weather", "story_url": "", "risk_level": "low"}
    facts = _coerce_facts(data, "", "low")
    assert facts.event_type == "other"


def test_coerce_facts_non_list_fields_coerced():
    data = {
        "event_type": "other",
        "actors": "ЦАХАЛ",       # string instead of list
        "numbers": None,          # None instead of list
        "claims": "Ракета",       # string
        "story_url": "",
        "risk_level": "low",
    }
    facts = _coerce_facts(data, "", "low")
    assert isinstance(facts.actors, list)
    assert isinstance(facts.numbers, list)
    assert isinstance(facts.claims, list)


def test_coerce_facts_null_location_and_time():
    data = {
        "event_type": "other",
        "location": None,
        "time_ref": None,
        "story_url": "",
        "risk_level": "low",
    }
    facts = _coerce_facts(data, "", "low")
    assert facts.location is None
    assert facts.time_ref is None


# ─────────────────────────────────────────────────────────────────────────────
# _build_fact_user
# ─────────────────────────────────────────────────────────────────────────────


def test_build_fact_user_includes_titles():
    items = [_make_item("כותרת ראשונה", "ynet"), _make_item("כותרת שנייה", "mako")]
    msg = _build_fact_user(items, "https://example.com/s1", "low")
    assert "[ynet] כותרת ראשונה" in msg
    assert "[mako] כותרת שנייה" in msg
    assert "story_url" in msg
    assert "risk_level" in msg


def test_build_fact_user_includes_snippets():
    items = [_make_item("כותרת", "ynet", snippet_he="פרטי ידיעה")]
    msg = _build_fact_user(items, "", "low")
    assert "פרטי ידיעה" in msg


def test_build_fact_user_no_snippets_when_none():
    items = [_make_item("כותרת", "ynet", snippet_he=None)]
    msg = _build_fact_user(items, "", "low")
    assert "סניפ" not in msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# extract_facts — integration (mocked Ollama)
# ─────────────────────────────────────────────────────────────────────────────


async def test_extract_facts_happy_path():
    items = [_make_item("ירי קטיושות על גליל", "ynet")]
    ollama = _make_ollama(_VALID_FACTS_JSON)
    facts = await extract_facts(ollama, items, "https://ynet.co.il/s1", "high")
    assert facts is not None
    assert facts.event_type == "security"
    assert facts.story_url == "https://ynet.co.il/s1"  # caller value used
    assert facts.risk_level == "high"


async def test_extract_facts_story_url_always_caller_value():
    """Even if LLM returns a different URL, caller's URL wins."""
    data = dict(_VALID_FACTS_DICT)
    data["story_url"] = "https://llm-made-this-up.com"
    items = [_make_item("כותרת")]
    ollama = _make_ollama(json.dumps(data))
    facts = await extract_facts(ollama, items, "https://real-caller.com/s1", "low")
    assert facts is not None
    assert facts.story_url == "https://real-caller.com/s1"


async def test_extract_facts_invalid_json_returns_none():
    items = [_make_item("כותרת")]
    ollama = _make_ollama("This is just plain prose, no JSON.")
    facts = await extract_facts(ollama, items, "", "low")
    assert facts is None


async def test_extract_facts_ollama_error_returns_none():
    items = [_make_item("כותרת")]
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=Exception("Connection refused"))
    facts = await extract_facts(ollama, items, "", "low")
    assert facts is None


async def test_extract_facts_fenced_json_block():
    """Handles LLM wrapping JSON in a code fence."""
    items = [_make_item("כותרת")]
    fenced = f"```json\n{_VALID_FACTS_JSON}\n```"
    ollama = _make_ollama(fenced)
    facts = await extract_facts(ollama, items, "https://example.com", "low")
    assert facts is not None
    assert facts.event_type == "security"


async def test_extract_facts_minimal_json():
    """Minimal JSON (just event_type) still returns a valid model."""
    items = [_make_item("כותרת")]
    minimal = json.dumps({"event_type": "other"})
    ollama = _make_ollama(minimal)
    facts = await extract_facts(ollama, items, "https://example.com/s1", "medium")
    assert facts is not None
    assert facts.event_type == "other"
    assert facts.numbers == []
    assert facts.story_url == "https://example.com/s1"
    assert facts.risk_level == "medium"

async def test_extract_facts_retries_with_strict_json_instruction_on_invalid_json():
    items = [_make_item("?????")]
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=["not-json", _VALID_FACTS_JSON])

    facts = await extract_facts(
        ollama,
        items,
        "https://example.com/s1",
        "low",
        max_retries=1,
        json_mode="strict",
    )

    assert facts is not None
    assert facts.story_url == "https://example.com/s1"
    assert ollama.chat.await_count == 2

    first_call = ollama.chat.await_args_list[0]
    second_call = ollama.chat.await_args_list[1]
    assert "Return ONLY valid JSON" not in first_call.args[0]
    assert "Return ONLY valid JSON" in second_call.args[0]


async def test_extract_facts_best_effort_accepts_json_with_prose_without_retry():
    items = [_make_item("?????")]
    mixed = f"before\n{_VALID_FACTS_JSON}\nafter"
    ollama = _make_ollama(mixed)

    facts = await extract_facts(
        ollama,
        items,
        "https://example.com/s1",
        "low",
        max_retries=2,
        json_mode="best_effort",
    )

    assert facts is not None
    assert ollama.chat.await_count == 1


async def test_extract_facts_strict_uses_extractor_on_last_attempt_only():
    items = [_make_item("?????")]
    mixed = f"before\n{_VALID_FACTS_JSON}\nafter"
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=[mixed, mixed])

    facts = await extract_facts(
        ollama,
        items,
        "https://example.com/s1",
        "low",
        max_retries=1,
        json_mode="strict",
    )

    assert facts is not None
    assert ollama.chat.await_count == 2

