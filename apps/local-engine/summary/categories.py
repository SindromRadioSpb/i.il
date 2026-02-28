"""summary/categories.py — Auto-category classification and hashtag generation via Ollama.

New functionality for the local engine (not in TS Worker).
Runs after a successful summary to enrich stories with category + hashtags.
Failures are silently swallowed — categories/hashtags are best-effort.
"""

from __future__ import annotations

import json
import re

import httpx

from summary.ollama import OllamaClient

VALID_CATEGORIES: frozenset[str] = frozenset(
    ["politics", "security", "economy", "society", "other"]
)

_HASHTAG_RE = re.compile(r"#\w+")

_COMBINED_SYSTEM = (
    "Ты помощник-редактор новостей. По заголовку и тексту определи категорию и создай хештеги.\n"
    "Доступные категории: politics, security, economy, society, other\n"
    "Верни ТОЛЬКО JSON без пояснений:\n"
    '{"category": "...", "hashtags": ["#хештег1", "#хештег2", "#хештег3"]}'
)


async def classify_and_tag(
    ollama: OllamaClient,
    title_ru: str,
    summary_ru: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, list[str]]:
    """Return (category, hashtags) for a published story in one Ollama call.

    Returns ("other", []) on any error.
    """
    try:
        user = f"Заголовок: {title_ru}\n\n{summary_ru[:300]}"
        raw = await ollama.chat(_COMBINED_SYSTEM, user, client=client, format="json")
        data = json.loads(raw)
        category = str(data.get("category", "other")).lower().strip()
        if category not in VALID_CATEGORIES:
            category = "other"
        hashtags_raw = data.get("hashtags", [])
        if isinstance(hashtags_raw, list):
            hashtags = [h for h in hashtags_raw if isinstance(h, str) and h.startswith("#")][:5]
        else:
            hashtags = _HASHTAG_RE.findall(str(hashtags_raw))[:5]
        return category, hashtags
    except Exception:
        return "other", []


async def classify_category(
    ollama: OllamaClient,
    title_ru: str,
    summary_ru: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Return a category string for a published story.

    Thin wrapper around classify_and_tag() for backward compatibility.
    Returns "other" on any error.
    """
    category, _ = await classify_and_tag(ollama, title_ru, summary_ru, client=client)
    return category


async def generate_hashtags(
    ollama: OllamaClient,
    title_ru: str,
    category: str,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Return 3–5 hashtag strings (including the leading #) for a story.

    Thin wrapper — category param is ignored (classify_and_tag does both).
    Returns an empty list on any error.
    """
    _, hashtags = await classify_and_tag(ollama, title_ru, "", client=client)
    return hashtags
