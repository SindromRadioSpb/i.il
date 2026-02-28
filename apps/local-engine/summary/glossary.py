"""summary/glossary.py — Post-generation glossary normalization.

Exact port of apps/worker/src/summary/glossary.ts.
Enforces consistent Russian spellings of Hebrew institutions and cities.
Applied to generated text AFTER Ollama output to catch any inconsistencies.

City rules use stem-based matching so declined forms are also normalized
(e.g. хайфы → Хайфы, тель авива → Тель-Авива).
"""

from __future__ import annotations

import re
from typing import Callable

# (pattern, replacement) — all patterns are case-insensitive.
# Function replacers receive a Match object; return the corrected string.
_RULES: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    # Institutions — undeclined in Russian news style
    (re.compile(r"цахал", re.IGNORECASE), "ЦАХАЛ"),
    (re.compile(r"шабак", re.IGNORECASE), "ШАБАК"),
    # Кнессет — capture any Cyrillic case suffix (Кнессета, Кнессете, …)
    (
        re.compile(r"кнес+ет([а-яё]*)", re.IGNORECASE),
        lambda m: "Кнессет" + (m.group(1) or ""),
    ),
    # Cities — match stem + optional Cyrillic suffix so declined forms are also fixed
    (
        re.compile(r"тель[\s\-]?авив([а-яё]*)", re.IGNORECASE),
        lambda m: "Тель-Авив" + (m.group(1) or ""),
    ),
    (
        re.compile(r"иерусалим([а-яё]*)", re.IGNORECASE),
        lambda m: "Иерусалим" + (m.group(1) or ""),
    ),
    # хайф + at least one Cyrillic letter covers хайфа/хайфы/хайфе/хайфу/хайфой
    (
        re.compile(r"хайф([а-яё]+)", re.IGNORECASE),
        lambda m: "Хайф" + (m.group(1) or ""),
    ),
]


def apply_glossary(text: str) -> str:
    """Apply glossary normalization rules to a generated Russian text."""
    result = text
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)  # type: ignore[arg-type]
    return result
