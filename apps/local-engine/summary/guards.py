"""summary/guards.py — Pre-publication guards for generated Russian summaries.

Exact port of apps/worker/src/summary/guards.ts.
Each guard returns a GuardResult(ok, reason).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class GuardResult:
    ok: bool
    reason: str | None = field(default=None)


_FORBIDDEN_WORDS: list[str] = ["ужас", "кошмар", "шок", "сенсация", "скандал века"]

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")


def guard_length(body: str, min_len: int, max_len: int) -> GuardResult:
    """Verify the summary body length is within the allowed character range."""
    n = len(body)
    if n < min_len:
        return GuardResult(ok=False, reason=f"too_short:{n}<{min_len}")
    if n > max_len:
        return GuardResult(ok=False, reason=f"too_long:{n}>{max_len}")
    return GuardResult(ok=True)


def guard_forbidden_words(text: str) -> GuardResult:
    """Detect forbidden sensational language."""
    lower = text.lower()
    for word in _FORBIDDEN_WORDS:
        if word in lower:
            return GuardResult(ok=False, reason=f"forbidden_word:{word}")
    return GuardResult(ok=True)


def _extract_numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text)


def guard_numbers(source_titles: list[str], generated_text: str) -> GuardResult:
    """Verify that every number from source Hebrew titles appears in the generated text."""
    source_nums: set[str] = set()
    for title in source_titles:
        source_nums.update(_extract_numbers(title))

    if not source_nums:
        return GuardResult(ok=True)

    gen_nums = set(_extract_numbers(generated_text))
    missing = [n for n in source_nums if n not in gen_nums]
    if missing:
        return GuardResult(ok=False, reason=f"missing_numbers:{','.join(missing)}")
    return GuardResult(ok=True)


def guard_high_risk(body: str, risk_level: str) -> GuardResult:
    """For high-risk stories, body must contain the attribution phrase."""
    if risk_level != "high":
        return GuardResult(ok=True)
    if "по данным источников" not in body.lower():
        return GuardResult(ok=False, reason="high_risk_requires_attribution")
    return GuardResult(ok=True)
