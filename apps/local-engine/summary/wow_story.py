"""summary/wow_story.py — WOW-Story FB caption composer (Passes 2 & 3).

Takes ExtractedFacts from Pass 1 and produces a viral mini-story FB caption:
  Line 1:  Hook headline (≤90 chars, no duplication in body)
  Lines 2…N-1: 3–5 body sentences (300–900 chars total body)
             Sentence 1 — context (location/time)
             Sentences 2–3 — factual core (claims, numbers preserved)
             Sentence 4 — contrast/implication ("сообщают издания" if high-risk)
             Sentence 5 — short question to audience (no ragebait)
  Last line: "Подробнее → <story_url>"  (appended programmatically, not by LLM)

Pass 3 (Critic) validates output and rewrites (up to max_rewrites=2 times)
if any guard fails. If all rewrite attempts still fail, returns None.
The caller (generate.py) treats None as a best-effort failure — the story
is still published, the FB post falls back to the legacy format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from summary.fact_extract import ExtractedFacts
from summary.glossary import apply_glossary
from summary.guards import GuardResult
from summary.ollama import OllamaClient


# ─────────────────────────────────────────────────────────────────────────────
# WOW-Story guards
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_HEADERS: list[str] = [
    "что произошло:",
    "почему важно:",
    "что дальше:",
    "источники:",
    "заголовок:",
]

# Speculation phrases that are banned unless present in claims
_SPECULATION_PHRASES: list[str] = [
    "ожидается",
    "собираются",
    "планируют",
    "намерены",
]

_FORBIDDEN_WORDS: list[str] = ["ужас", "кошмар", "шок", "сенсация", "скандал века"]

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_HASHTAG_RE = re.compile(r"#\w+")

# Attribution phrases required for high-risk stories
_ATTRIBUTION_PHRASES: tuple[str, ...] = (
    "по данным источников",
    "сообщают издания",
    "по данным сми",
    "по информации источников",
)


def guard_wow_no_sections(text: str) -> GuardResult:
    """No section-header labels allowed in the WOW post."""
    lower = text.lower()
    for kw in _SECTION_HEADERS:
        if kw in lower:
            return GuardResult(ok=False, reason=f"section_header:{kw}")
    return GuardResult(ok=True)


def guard_wow_no_hashtags(text: str) -> GuardResult:
    """No hashtags (#word) allowed."""
    if _HASHTAG_RE.search(text):
        return GuardResult(ok=False, reason="has_hashtags")
    return GuardResult(ok=True)


def guard_wow_no_duplicate_headline(text: str) -> GuardResult:
    """First non-empty line must not appear verbatim inside the body."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return GuardResult(ok=True)
    headline = lines[0].lower()
    body = "\n".join(lines[1:]).lower()
    # Only flag meaningful headlines (>10 chars) that appear verbatim in body
    if len(headline) > 10 and headline in body:
        return GuardResult(ok=False, reason="duplicate_headline")
    return GuardResult(ok=True)


def guard_wow_hallucination(text: str, claims: list[str]) -> GuardResult:
    """Speculation phrases are banned unless explicitly present in source claims."""
    body_lower = text.lower()
    claims_lower = " ".join(claims).lower()
    for phrase in _SPECULATION_PHRASES:
        if phrase in body_lower and phrase not in claims_lower:
            return GuardResult(ok=False, reason=f"speculation_phrase:{phrase}")
    return GuardResult(ok=True)


def guard_wow_high_risk_attribution(text: str, risk_level: str) -> GuardResult:
    """High-risk stories must contain an attribution phrase."""
    if risk_level != "high":
        return GuardResult(ok=True)
    lower = text.lower()
    if any(phrase in lower for phrase in _ATTRIBUTION_PHRASES):
        return GuardResult(ok=True)
    return GuardResult(ok=False, reason="high_risk_missing_attribution")


def guard_wow_numbers(text: str, numbers: list[str]) -> GuardResult:
    """All numbers from ExtractedFacts must appear in the post.

    Tolerance: when 3+ numbers are expected, 1 may be missing (the LLM
    reliably drops rare secondary statistics while preserving key figures).
    """
    if not numbers:
        return GuardResult(ok=True)
    gen_nums = set(_NUMBER_RE.findall(text))
    missing = [n for n in numbers if n not in gen_nums]
    allowed_misses = 1 if len(numbers) >= 3 else 0
    if len(missing) > allowed_misses:
        return GuardResult(ok=False, reason=f"missing_numbers:{','.join(missing)}")
    return GuardResult(ok=True)


def guard_wow_ends_with_url(text: str, story_url: str) -> GuardResult:
    """Last non-empty line must contain story_url (when provided)."""
    if not story_url:
        return GuardResult(ok=True)
    last = text.strip().split("\n")[-1].strip()
    if story_url not in last:
        return GuardResult(ok=False, reason="missing_url_line")
    return GuardResult(ok=True)


def guard_wow_length(
    text: str,
    min_len: int = 300,
    max_len: int = 1100,
) -> GuardResult:
    """Total post character length must be within bounds."""
    n = len(text.strip())
    if n < min_len:
        return GuardResult(ok=False, reason=f"too_short:{n}<{min_len}")
    if n > max_len:
        return GuardResult(ok=False, reason=f"too_long:{n}>{max_len}")
    return GuardResult(ok=True)


def guard_wow_forbidden_words(text: str) -> GuardResult:
    """Detect forbidden sensationalist language."""
    lower = text.lower()
    for word in _FORBIDDEN_WORDS:
        if word in lower:
            return GuardResult(ok=False, reason=f"forbidden_word:{word}")
    return GuardResult(ok=True)


def run_wow_guards(text: str, facts: ExtractedFacts) -> list[GuardResult]:
    """Run all WOW-story guards and return results (both ok and failed)."""
    return [
        guard_wow_no_sections(text),
        guard_wow_no_hashtags(text),
        guard_wow_no_duplicate_headline(text),
        guard_wow_hallucination(text, facts.claims),
        guard_wow_high_risk_attribution(text, facts.risk_level),
        guard_wow_numbers(text, facts.numbers),
        guard_wow_ends_with_url(text, facts.story_url),
        guard_wow_length(text),
        guard_wow_forbidden_words(text),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# WOW counters
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class WowCounters:
    caption_ok: int = 0
    caption_fail: int = 0
    rewrite_attempts: int = 0
    guard_fail_reasons: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2: Draft composer
# ─────────────────────────────────────────────────────────────────────────────

_DRAFT_SYSTEM = """\
Ты редактор Facebook для новостей на русском языке. Напиши виральный мини-пост
на основе ТОЛЬКО предоставленного JSON с фактами.

Структура поста (строго соблюдай):
1. Строка 1: яркий заголовок-крючок (≤90 символов) — не повторяй его дословно в теле.
2. Тело: 3–5 предложений (300–900 символов суммарно):
   - Предложение 1: место/время (из location/time_ref, если есть)
   - Предложения 2–3: суть события (из claims, числа из numbers — по возможности)
   - Предложение 4 (если есть): контраст или вывод
     (при risk_level=high ОБЯЗАТЕЛЬНО включи "по данным источников" или "сообщают издания")
   - Предложение 5: короткий вопрос аудитории (не провокационный, без разжигания)

НЕЛЬЗЯ:
- Хештеги (#слово)
- Заголовки разделов (Что произошло / Почему важно / Что дальше / Источники / Заголовок:)
- Дословно повторять строку 1 в теле поста
- Использовать "ожидается/собираются/планируют/намерены", если этого нет в claims
- Изобретать факты, имена, места, числа\
"""


def _build_draft_user(facts: ExtractedFacts) -> str:
    """Build user message for Pass-2 draft generation."""
    return "Факты для поста:\n" + facts.model_dump_json(indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3: Critic / rewrite
# ─────────────────────────────────────────────────────────────────────────────

_CRITIC_SYSTEM = """\
Ты редактор-корректор. Проверь Facebook-пост и перепиши при необходимости.

Проверь наличие нарушений:
1. Хештеги (#слово)
2. Заголовки разделов (Что произошло / Почему важно / Что дальше / Источники / Заголовок:)
3. Первая строка дословно повторяется в теле
4. "ожидается/собираются/планируют/намерены" вне claims
5. Ключевые числа из JSON отсутствуют в тексте
6. risk_level="high", но нет "по данным источников" или "сообщают издания"
7. Текст слишком короткий (<300) или слишком длинный (>1100 символов)

Если нарушений нет — верни пост без изменений.
Если есть — исправь ТОЛЬКО нарушения. Не изменяй факты и числа.\
"""


def _build_critic_user(
    draft: str,
    facts: ExtractedFacts,
    violations: list[str],
) -> str:
    """Build user message for Pass-3 critic."""
    return (
        f"Нарушения: {', '.join(violations)}\n\n"
        f"JSON с фактами:\n{facts.model_dump_json(indent=2)}\n\n"
        f"Пост для исправления:\n{draft}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

_URL_LINE_RE = re.compile(r"\n\n?Подробнее\s*[→\->]+\s*\S+\s*$", re.IGNORECASE)


def _strip_and_append_url(text: str, story_url: str) -> str:
    """Remove any trailing 'Подробнее → ...' line and append the canonical one.

    This ensures the URL is always correct regardless of what the LLM produced.
    """
    # Strip trailing URL line the LLM may have added
    cleaned = _URL_LINE_RE.sub("", text).rstrip()
    return cleaned + f"\n\nПодробнее → {story_url}"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def compose_wow_post(
    ollama: OllamaClient,
    facts: ExtractedFacts,
    *,
    client: httpx.AsyncClient | None = None,
    max_rewrites: int = 2,
) -> tuple[str | None, WowCounters]:
    """Run Pass 2 (draft) + Pass 3 (critic/rewrite) and return (caption, counters).

    Returns (None, counters) on unrecoverable failure.
    The caller treats None as best-effort — story is still published,
    FB post falls back to legacy format.

    Args:
        ollama: OllamaClient instance.
        facts: Validated ExtractedFacts from Pass 1.
        client: Optional shared httpx.AsyncClient (injected in tests).
        max_rewrites: Maximum critic rewrite attempts (default 2).

    Returns:
        Tuple of (caption_text_or_None, WowCounters).
    """
    counters = WowCounters()

    # ── Pass 2: draft ────────────────────────────────────────────────────────
    try:
        raw_draft = await ollama.chat(_DRAFT_SYSTEM, _build_draft_user(facts), client=client)
        current = apply_glossary(raw_draft.strip())
    except Exception:
        counters.caption_fail += 1
        return None, counters

    # Append URL programmatically — strip any existing URL line the LLM may
    # have added, then always append the canonical "Подробнее → <url>" line.
    # This removes the largest source of guard failures (guard_wow_ends_with_url).
    if facts.story_url:
        current = _strip_and_append_url(current, facts.story_url)

    # ── Pass 3: guard → rewrite loop ────────────────────────────────────────
    for attempt in range(max_rewrites + 1):
        guard_results = run_wow_guards(current, facts)
        failed_guards = [g for g in guard_results if not g.ok]

        if not failed_guards:
            # All guards passed
            counters.caption_ok += 1
            return current, counters

        violations = [g.reason for g in failed_guards if g.reason]
        counters.guard_fail_reasons.extend(violations)

        if attempt >= max_rewrites:
            break  # exhausted rewrites

        # Critic rewrite
        try:
            counters.rewrite_attempts += 1
            raw_rewrite = await ollama.chat(
                _CRITIC_SYSTEM,
                _build_critic_user(current, facts, violations),
                client=client,
            )
            current = apply_glossary(raw_rewrite.strip())
            if facts.story_url:
                current = _strip_and_append_url(current, facts.story_url)
        except Exception:
            break

    counters.caption_fail += 1
    return None, counters
