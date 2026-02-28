"""summary/categories.py — Auto-category classification and hashtag generation via Ollama.

New functionality for the local engine (not in TS Worker).
Runs after a successful summary to enrich stories with category + hashtags.
Failures are silently swallowed — categories/hashtags are best-effort.
"""

from __future__ import annotations

import re

import httpx

from summary.ollama import OllamaClient

VALID_CATEGORIES: frozenset[str] = frozenset(
    ["politics", "security", "economy", "society", "other"]
)

_CATEGORY_SYSTEM = (
    "Ты классификатор новостей. Определи категорию новости.\n"
    "Доступные категории: politics, security, economy, society, other\n"
    "Отвечай ТОЛЬКО одним словом из этого списка."
)

_HASHTAG_SYSTEM = (
    "Ты помощник для создания хештегов для новостей в Facebook.\n"
    "Создай 3-5 хештегов на русском языке для следующей новости.\n"
    "Хештеги должны быть без пробелов, начинаться с #.\n"
    "Отвечай ТОЛЬКО хештегами, разделёнными пробелом."
)

_HASHTAG_RE = re.compile(r"#\w+")


async def classify_category(
    ollama: OllamaClient,
    title_ru: str,
    summary_ru: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Return a category string for a published story.

    Returns "other" on any error (Ollama not running, unexpected output, etc.).
    """
    try:
        user = f"Заголовок: {title_ru}\n\n{summary_ru[:300]}"
        raw = await ollama.chat(_CATEGORY_SYSTEM, user, client=client)
        category = raw.strip().lower().split()[0] if raw.strip() else "other"
        return category if category in VALID_CATEGORIES else "other"
    except Exception:
        return "other"


async def generate_hashtags(
    ollama: OllamaClient,
    title_ru: str,
    category: str,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Return 3–5 hashtag strings (including the leading #) for a story.

    Returns an empty list on any error.
    """
    try:
        user = f"Категория: {category}\nЗаголовок: {title_ru}"
        raw = await ollama.chat(_HASHTAG_SYSTEM, user, client=client)
        return _HASHTAG_RE.findall(raw)[:5]
    except Exception:
        return []
