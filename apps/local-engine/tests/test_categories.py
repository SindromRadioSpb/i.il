"""tests/test_categories.py — classify_and_tag JSON robustness tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from summary.categories import classify_and_tag
from summary.ollama import OllamaClient


_VALID = '{"category":"security","hashtags":["#alpha","beta"]}'


def _make_llm(responses: list[str]) -> OllamaClient:
    llm = MagicMock(spec=OllamaClient)
    llm.chat = AsyncMock(side_effect=responses)
    return llm


async def test_classify_and_tag_retries_after_invalid_json_strict_mode():
    llm = _make_llm(["not-json", _VALID])

    category, tags = await classify_and_tag(
        llm,
        "Title",
        "Summary",
        max_retries=1,
        json_mode="strict",
    )

    assert category == "security"
    assert tags == ["#alpha", "#beta"]
    assert llm.chat.await_count == 2
    assert "Return ONLY valid JSON" in llm.chat.await_args_list[1].args[0]


async def test_classify_and_tag_best_effort_parses_json_with_prose_first_try():
    llm = _make_llm([f"prefix\\n{_VALID}\\nsuffix"])

    category, tags = await classify_and_tag(
        llm,
        "Title",
        "Summary",
        max_retries=2,
        json_mode="best_effort",
    )

    assert category == "security"
    assert tags == ["#alpha", "#beta"]
    assert llm.chat.await_count == 1


async def test_classify_and_tag_returns_other_when_all_attempts_fail():
    llm = _make_llm(["bad", "still bad", "bad again"])

    category, tags = await classify_and_tag(
        llm,
        "Title",
        "Summary",
        max_retries=2,
        json_mode="strict",
    )

    assert category == "other"
    assert tags == []
    assert llm.chat.await_count == 3
