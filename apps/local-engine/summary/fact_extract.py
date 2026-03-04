"""summary/fact_extract.py — Pass 1: Extract structured facts from Hebrew titles.

Calls LLM provider and returns a validated ExtractedFacts pydantic model.
Returns None on failure — callers treat this as best-effort.

The model is the single source of truth passed to the WOW-story composer:
no prose is invented, every field is grounded in source input.
"""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field, ValidationError

from summary.json_utils import build_json_retry_instruction, parse_json_output
from summary.llm_provider import LLMProvider


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema
# ─────────────────────────────────────────────────────────────────────────────


class ExtractedFacts(BaseModel):
    """Structured fact extraction from Hebrew news titles.

    All fields are grounded in source input. Nothing is invented.
    story_url and risk_level are always injected by the caller
    (not trusted from LLM output).
    """

    event_type: str = "other"        # security|politics|economy|society|sport|other
    location: str | None = None      # city/country or null
    time_ref: str | None = None      # time/date reference or null
    actors: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)   # every numeric token from input
    claims: list[str] = Field(default_factory=list)    # facts explicitly in titles
    uncertainty_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    risk_level: str = "low"          # low|medium|high (caller-controlled)
    story_url: str = ""              # caller-controlled — passed verbatim to post


_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    ["security", "politics", "economy", "society", "sport", "other"]
)
_VALID_RISK_LEVELS: frozenset[str] = frozenset(["low", "medium", "high"])


_JSON_RETRY_SUFFIX = build_json_retry_instruction()


def _coerce_facts(data: dict, story_url: str, risk_level: str) -> ExtractedFacts:
    """Validate and coerce raw dict into ExtractedFacts, clamping enum values."""
    # Normalise event_type
    et = str(data.get("event_type", "other")).lower()
    data["event_type"] = et if et in _VALID_EVENT_TYPES else "other"

    # Always use caller-supplied values — never trust LLM output for these
    rl = str(risk_level).lower()
    data["story_url"] = story_url
    data["risk_level"] = rl if rl in _VALID_RISK_LEVELS else "low"

    # Ensure list fields are actual lists
    for key in ("actors", "numbers", "claims", "uncertainty_notes", "sources"):
        val = data.get(key)
        if not isinstance(val, list):
            data[key] = [str(val)] if val else []

    # Ensure string-or-null fields
    for key in ("location", "time_ref"):
        val = data.get(key)
        data[key] = str(val).strip() if val else None

    return ExtractedFacts.model_validate(data)


# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

_FACT_SYSTEM = """\
Ты аналитик новостей. ТОЛЬКО извлекай факты из заголовков на иврите.
Отвечай ИСКЛЮЧИТЕЛЬНО в формате JSON — без вводного текста, без пояснений.

Схема JSON (все поля обязательны):
{
  "event_type": "security|politics|economy|society|sport|other",
  "location": "город/страна или null",
  "time_ref": "время/дата или null",
  "actors": ["список задействованных лиц/организаций"],
  "numbers": ["ВСЕ числа, проценты, суммы из заголовков"],
  "claims": ["факты, ЯВНО указанные в заголовках"],
  "uncertainty_notes": ["что неясно или не подтверждено"],
  "sources": ["названия источников"],
  "risk_level": "low|medium|high",
  "story_url": "передаётся без изменений"
}

Правила:
- numbers: включи КАЖДОЕ число, процент, сумму из заголовков
- claims: только то, что ЯВНО написано; без интерпретаций
- uncertainty_notes: если что-то спорно или отсутствует — запиши сюда
- Не выдумывай факты, имена, места, числа\
"""


# ─────────────────────────────────────────────────────────────────────────────
# User message builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_fact_user(items: list, story_url: str, risk_level: str) -> str:
    """Build user message for Pass-1 fact extraction."""
    lines = [f"{i + 1}. [{it.source_id}] {it.title_he}" for i, it in enumerate(items)]
    parts = ["Заголовки на иврите:"] + lines

    # Include RSS snippets when available (extra context, no obligation for LLM)
    snippets = [
        f"   (сниппет: {it.snippet_he})"
        for it in items
        if getattr(it, "snippet_he", None)
    ]
    if snippets:
        parts.append("\nСниппеты:")
        parts.extend(snippets)

    parts.append(f'\nstory_url: "{story_url}"')
    parts.append(f'risk_level: "{risk_level}"')
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helper (public for tests)
# ─────────────────────────────────────────────────────────────────────────────


def extract_json_from_text(raw: str) -> dict:
    """Extract the first JSON object from raw LLM output.

    Handles bare JSON, fenced JSON, and leading/trailing prose.
    """
    data = parse_json_output(raw, allow_extractor=True)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def extract_facts(
    llm: LLMProvider,
    items: list,
    story_url: str,
    risk_level: str = "low",
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int = 2,
    json_mode: str = "strict",
) -> ExtractedFacts | None:
    """Return validated ExtractedFacts, or None on failure.

    Retry strategy:
      1) direct parse (json.loads)
      2) extractor fallback (best_effort, or last attempt in strict mode)
      3) pydantic validation; retry with stronger JSON instruction on failure
    """
    user = _build_fact_user(items, story_url, risk_level)
    attempts = max(0, int(max_retries)) + 1
    mode = json_mode.strip().lower()
    best_effort = mode == "best_effort"

    for attempt in range(attempts):
        system = _FACT_SYSTEM
        if attempt > 0:
            system = f"{_FACT_SYSTEM}\n\n{_JSON_RETRY_SUFFIX}"

        try:
            raw = await llm.chat(system, user, client=client, format="json")
        except Exception:
            continue

        allow_extractor = best_effort or (attempt == attempts - 1)
        try:
            parsed = parse_json_output(raw, allow_extractor=allow_extractor)
        except (ValueError, json.JSONDecodeError):
            continue

        if not isinstance(parsed, dict):
            continue

        try:
            return _coerce_facts(parsed, story_url, risk_level)
        except ValidationError:
            continue
        except Exception:
            continue

    return None
