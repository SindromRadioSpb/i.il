"""summary/categories.py — Auto-category classification and hashtag generation.

Runs after a successful summary to enrich stories with category + hashtags.
Failures are best-effort and never block publish.
"""

from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from summary.json_utils import build_json_retry_instruction, parse_json_output
from summary.llm_provider import LLMProvider

VALID_CATEGORIES: frozenset[str] = frozenset(
    ["politics", "security", "economy", "society", "other"]
)

_HASHTAG_RE = re.compile(r"#\w+")
_JSON_RETRY_SUFFIX = build_json_retry_instruction()

_COMBINED_SYSTEM = (
    "Ты помощник-редактор новостей. По заголовку и тексту определи категорию и создай хештеги.\n"
    "Доступные категории: politics, security, economy, society, other\n"
    "Верни ТОЛЬКО JSON без пояснений:\n"
    '{"category": "...", "hashtags": ["#хештег1", "#хештег2", "#хештег3"]}'
)


class _CategoryTagResponse(BaseModel):
    category: str = "other"
    hashtags: list[str] = Field(default_factory=list)


def _coerce_category_and_tags(data: dict) -> tuple[str, list[str]]:
    """Validate and normalize LLM JSON payload."""
    payload = _CategoryTagResponse.model_validate(data)

    category = payload.category.lower().strip()
    if category not in VALID_CATEGORIES:
        category = "other"

    hashtags: list[str] = []
    for raw in payload.hashtags:
        txt = str(raw).strip()
        if not txt:
            continue
        if not txt.startswith("#"):
            txt = f"#{txt.lstrip('#')}"
        if _HASHTAG_RE.fullmatch(txt):
            hashtags.append(txt)

    # Keep only first 5 tags; preserve order and uniqueness.
    deduped: list[str] = []
    for h in hashtags:
        if h not in deduped:
            deduped.append(h)
        if len(deduped) >= 5:
            break

    return category, deduped


async def classify_and_tag(
    llm: LLMProvider,
    title_ru: str,
    summary_ru: str,
    client: httpx.AsyncClient | None = None,
    *,
    max_retries: int = 2,
    json_mode: str = "strict",
) -> tuple[str, list[str]]:
    """Return (category, hashtags) via a single LLM call.

    Parsing strategy mirrors fact_extract:
      - direct JSON parse first
      - extractor fallback (best_effort, or final strict attempt)
      - pydantic validation
    """
    user = f"Заголовок: {title_ru}\n\n{summary_ru[:300]}"
    attempts = max(0, int(max_retries)) + 1
    mode = json_mode.strip().lower()
    best_effort = mode == "best_effort"

    for attempt in range(attempts):
        system = _COMBINED_SYSTEM
        if attempt > 0:
            system = f"{_COMBINED_SYSTEM}\n\n{_JSON_RETRY_SUFFIX}"

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
            return _coerce_category_and_tags(parsed)
        except ValidationError:
            continue
        except Exception:
            continue

    return "other", []


async def classify_category(
    llm: LLMProvider,
    title_ru: str,
    summary_ru: str,
    client: httpx.AsyncClient | None = None,
    *,
    max_retries: int = 2,
    json_mode: str = "strict",
) -> str:
    """Return category only (wrapper around classify_and_tag)."""
    category, _ = await classify_and_tag(
        llm,
        title_ru,
        summary_ru,
        client=client,
        max_retries=max_retries,
        json_mode=json_mode,
    )
    return category


async def generate_hashtags(
    llm: LLMProvider,
    title_ru: str,
    category: str,
    client: httpx.AsyncClient | None = None,
    *,
    max_retries: int = 2,
    json_mode: str = "strict",
) -> list[str]:
    """Return hashtags only (wrapper around classify_and_tag)."""
    _ = category  # category is ignored: classify_and_tag already returns both.
    _, hashtags = await classify_and_tag(
        llm,
        title_ru,
        "",
        client=client,
        max_retries=max_retries,
        json_mode=json_mode,
    )
    return hashtags
