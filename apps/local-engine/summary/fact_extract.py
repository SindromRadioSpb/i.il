"""summary/fact_extract.py — Pass 1: Extract structured facts from Hebrew titles.

Calls Ollama once and returns a validated ExtractedFacts pydantic model.
Returns None on any failure — callers treat this as best-effort.

The model is the single source of truth passed to the WOW-story composer:
no prose is invented, every field is grounded in source input.
"""

from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel, Field

from summary.ollama import OllamaClient


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
    risk_level: str = "low"          # low|medium|high  (caller-controlled)
    story_url: str = ""              # caller-controlled — passed verbatim to post


_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    ["security", "politics", "economy", "society", "sport", "other"]
)
_VALID_RISK_LEVELS: frozenset[str] = frozenset(["low", "medium", "high"])


def _coerce_facts(data: dict, story_url: str, risk_level: str) -> ExtractedFacts:
    """Validate and coerce raw dict into ExtractedFacts, clamping enum values."""
    # Normalise event_type
    et = str(data.get("event_type", "other")).lower()
    data["event_type"] = et if et in _VALID_EVENT_TYPES else "other"
    # Always use caller-supplied values — never trust LLM output for these
    data["story_url"] = story_url
    data["risk_level"] = risk_level
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
# JSON extraction helper
# ─────────────────────────────────────────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def extract_json_from_text(raw: str) -> dict:
    """Extract the first JSON object from raw LLM output.

    Handles both bare JSON and ```json ... ``` fenced blocks.
    Raises ValueError if no valid JSON object is found.
    """
    # Try fenced code block first
    m = _JSON_BLOCK_RE.search(raw)
    if m:
        return json.loads(m.group(1))

    # Try bare JSON: find outermost { ... }
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(raw[start:end])

    raise ValueError(f"No JSON object found in LLM output: {raw[:200]!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def extract_facts(
    ollama: OllamaClient,
    items: list,
    story_url: str,
    risk_level: str = "low",
    *,
    client: httpx.AsyncClient | None = None,
) -> ExtractedFacts | None:
    """Call Ollama Pass-1 and return validated ExtractedFacts, or None on failure.

    Never raises — failures are silently absorbed.
    story_url and risk_level are always set from caller, not from LLM output.
    """
    user = _build_fact_user(items, story_url, risk_level)
    try:
        raw = await ollama.chat(_FACT_SYSTEM, user, client=client)
        data = extract_json_from_text(raw)
        return _coerce_facts(data, story_url, risk_level)
    except Exception:
        return None
