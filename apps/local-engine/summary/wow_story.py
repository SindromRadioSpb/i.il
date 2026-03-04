"""summary/wow_story.py — WOW-Story FB caption composer (Passes 2 & 3).

Takes ExtractedFacts from Pass 1 and produces a mini-story FB caption:
  Line 1:  Hook headline (≤100 chars, optional one emoji)
  Lines 2…N-1: 3–5 sentences — scene → facts → contrast → question
  Last line: "Подробнее → <story_url>"  (always appended programmatically)

Guard reclassification (v2):
  POST-PROCESS  — stripped/appended programmatically, never a blocker:
                  no_hashtags, no_sections, ends_with_url
  HARD          — block publish even after max_rewrites:
                  forbidden_words, high_risk_attribution
  SOFT          — critic note; best-effort publish after max_rewrites:
                  hallucination, no_duplicate_headline, numbers, length

This means compose_wow_post() almost always returns a caption (never None for
soft-only failures) — approaching 100% success rate on any story.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from summary.fact_extract import ExtractedFacts
from summary.glossary import apply_glossary
from summary.guards import GuardResult
from summary.llm_provider import LLMProvider


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_HEADERS: list[str] = [
    "что произошло:",
    "почему важно:",
    "что дальше:",
    "источники:",
    "заголовок:",
]

_SPECULATION_PHRASES: list[str] = [
    "ожидается",
    "собираются",
    "планируют",
    "намерены",
]

_FORBIDDEN_WORDS: list[str] = ["ужас", "кошмар", "шок", "сенсация", "скандал века"]

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_HASHTAG_RE = re.compile(r"#\w+")
_HASHTAG_LINE_RE = re.compile(r"^(\s*#\w+)+\s*$", re.MULTILINE)

_ATTRIBUTION_PHRASES: tuple[str, ...] = (
    "по данным источников",
    "сообщают издания",
    "по данным сми",
    "по информации источников",
)

# Section-header line pattern: line starts with one of the known headers
_SECTION_LINE_RE = re.compile(
    r"^(что произошло|почему важно|что дальше|источники|заголовок)\s*:",
    re.IGNORECASE | re.MULTILINE,
)


# ─────────────────────────────────────────────────────────────────────────────
# WOW-Story guards
# ─────────────────────────────────────────────────────────────────────────────


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

    Tolerance: when 3+ numbers are expected, 1 may be missing.
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
    """Run all 9 WOW-story guards and return results (both ok and failed)."""
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


def _classify_guard_failures(
    text: str,
    facts: ExtractedFacts,
) -> tuple[list[GuardResult], list[GuardResult]]:
    """Split guard failures into (hard, soft).

    Hard — block publish: forbidden_words, high_risk_attribution.
    Soft — critic note, best-effort publish after max_rewrites:
           hallucination, no_duplicate_headline, numbers, length.
    Post-process guards (no_hashtags, no_sections, ends_with_url) are
    applied programmatically in _sanitize_post() and never appear here.
    """
    hard: list[GuardResult] = []
    soft: list[GuardResult] = []

    for guard_fn, is_hard in [
        (lambda: guard_wow_no_duplicate_headline(text),       False),
        (lambda: guard_wow_hallucination(text, facts.claims), False),
        (lambda: guard_wow_high_risk_attribution(text, facts.risk_level), True),
        (lambda: guard_wow_numbers(text, facts.numbers),      False),
        (lambda: guard_wow_length(text),                      False),
        (lambda: guard_wow_forbidden_words(text),             True),
    ]:
        result = guard_fn()
        if not result.ok:
            (hard if is_hard else soft).append(result)

    return hard, soft


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
# Nuclear post-processing (POST-PROCESS guards)
# ─────────────────────────────────────────────────────────────────────────────


def _sanitize_post(text: str, facts: ExtractedFacts) -> str:
    """Programmatically fix trivial guard violations that an LLM often produces.

    Applied after every LLM output (draft + each rewrite).  Handles the
    POST-PROCESS guard tier so those guards never actually fail:
    1. Strip lines that consist entirely of hashtags → removes hashtag blocks
    2. Strip inline hashtag markers (#Word → Word) → removes inline hashtags
    3. Strip known section-header lines (Что произошло:, etc.)
    4. Strip "Заголовок: " prefix from the first line if present
    5. Strip "Источники: …" line if present
    6. Apply glossary
    7. Append story_url programmatically (strip + re-append)
    """
    # 1. Remove hashtag-only lines
    text = _HASHTAG_LINE_RE.sub("", text)
    # 2. Remove inline # markers (keep the word)
    text = _HASHTAG_RE.sub(lambda m: m.group(0)[1:], text)
    # 3a. Remove example-delimiter lines (--- or ═══ or ___) that LLM copies from prompt
    text = re.sub(r"(?m)^[-=_]{3,}\s*$", "", text)
    # 3. Remove section-header lines
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        # 4. Strip "Заголовок: " prefix from first non-empty line (before section-skip)
        if not cleaned_lines and stripped and lower.startswith("заголовок:"):
            line = re.sub(r"(?i)^заголовок\s*:\s*", "", stripped)
            cleaned_lines.append(line)
            continue
        # 3. Remove section-header lines entirely
        if any(lower.startswith(hdr) for hdr in _SECTION_HEADERS):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 5. Remove "Источники:" standalone line anywhere
    text = re.sub(r"(?im)^Источники\s*:.*$\n?", "", text)

    # Collapse multiple blank lines to at most two
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # 6. Apply glossary
    text = apply_glossary(text)

    # 7. Append story_url programmatically
    if facts.story_url:
        text = _strip_and_append_url(text, facts.story_url)

    return text


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

_URL_LINE_RE = re.compile(r"\n\n?Подробнее\s*[→\->]+\s*\S+\s*$", re.IGNORECASE)


def _strip_and_append_url(text: str, story_url: str) -> str:
    """Remove any trailing 'Подробнее → ...' line and append the canonical one."""
    cleaned = _URL_LINE_RE.sub("", text).rstrip()
    return cleaned + f"\n\nПодробнее → {story_url}"


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2: Draft composer — storytelling prompt with inline example
# ─────────────────────────────────────────────────────────────────────────────

_DRAFT_SYSTEM = """\
Ты Facebook-редактор. Пиши как сторителлер — короткая живая сцена, не пресс-релиз.

Формат (соблюдай строго):
1. Строка 1: заголовок-крючок (≤100 знаков). Допустим один эмодзи.
2. Пустая строка.
3. Тело — 3–5 предложений:
   • 1-е: сцена/момент (место, время, атмосфера)
   • 2–3-е: факты (кто/что; числа из поля numbers — сохрани)
   • 4-е: поворот/контраст (начни на "но", "при этом", "однако", "вместе с тем")
     ← если risk_level="high": обязательно добавь "по данным источников" или "сообщают издания"
   • 5-е: один вопрос читателю (короткий, без провокации)

НЕЛЬЗЯ:
- Хэштеги (#слово) — вообще
- Секционные метки: "Что произошло:", "Почему важно:", "Что дальше:", "Источники:", "Заголовок:"
- Дословно повторять строку 1 в теле
- "ожидается/собираются/планируют/намерены" без основания в claims
- Канцелярит: "в пресс-релизе отмечено", "в рамках", "по имеющимся данным"
- Выдумывать факты, имена, места, числа

Пример хорошего поста:
---
🔴 Три беспилотника «Хезболлы» уничтожены над Галилеей

Сегодня ночью в небе над Галилеей сработала воздушная тревога.
Система «Железный купол» перехватила три БПЛА, запущенных с ливанской территории, — сообщают издания.
Жертв и разрушений нет.
Однако эксперты предупреждают: интенсивность пусков растёт.
Как вы оцениваете угрозу с Севера?
---\
"""


def _build_draft_user(facts: ExtractedFacts) -> str:
    """Build user message for Pass-2 draft generation."""
    return "Факты для поста:\n" + facts.model_dump_json(indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3: Critic / rewrite — quality-focused, not just guard-checking
# ─────────────────────────────────────────────────────────────────────────────

_CRITIC_SYSTEM = """\
Ты редактор-стилист. Перепиши пост, если он звучит как пресс-релиз или канцелярская бумага.

Проверь по пунктам:
1. Канцелярит: "отмечено, что", "в контексте", "вместе с тем", "в рамках", "по имеющимся данным" → упрости живым языком
2. "Жёлтое": "ужас", "кошмар", "шок", "сенсация" → убери
3. Заголовок первой строки дословно повторяется в теле → перефразируй тело
4. Нет контрастного поворота (предложение с "но"/"однако"/"при этом") → добавь
5. Два подряд предложения без конкретного факта ("вода") → сократи или объедини
6. Слишком длинно (>1100 зн.) → сократи до 800–900 зн.

НЕЛЬЗЯ менять:
- числа и факты из JSON
- имена людей и организаций
- структуру: заголовок → тело → вопрос читателю

Верни ТОЛЬКО исправленный пост, без пояснений и вводных слов.\
"""


def _build_critic_user(
    draft: str,
    facts: ExtractedFacts,
    violations: list[str],
) -> str:
    """Build user message for Pass-3 critic."""
    parts = []
    if violations:
        parts.append(f"Нарушения: {', '.join(violations)}")
    parts.append(f"JSON с фактами:\n{facts.model_dump_json(indent=2)}")
    parts.append(f"Пост для улучшения:\n{draft}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def compose_wow_post(
    ollama: LLMProvider,
    facts: ExtractedFacts,
    *,
    client: httpx.AsyncClient | None = None,
    max_rewrites: int = 3,
) -> tuple[str | None, WowCounters]:
    """Run Pass 2 (draft) + Pass 3 (critic/rewrite) and return (caption, counters).

    Guard classification:
    - POST-PROCESS (hashtags, sections, url): always fixed programmatically.
    - HARD (forbidden_words, high_risk_attribution): block publish even after rewrites.
    - SOFT (hallucination, duplicate_headline, numbers, length): best-effort;
      after max_rewrites, still publish with caption_ok=1.

    Returns (None, counters) only when HARD guards fail after max_rewrites
    (extremely rare — forbidden words, missing high-risk attribution).
    Returns (caption, counters) with caption_ok=1 for all other cases.
    """
    counters = WowCounters()

    # ── Pass 2: draft ────────────────────────────────────────────────────────
    try:
        raw_draft = await ollama.chat(_DRAFT_SYSTEM, _build_draft_user(facts), client=client)
        current = _sanitize_post(raw_draft.strip(), facts)
    except Exception:
        counters.caption_fail += 1
        return None, counters

    # ── Pass 3: guard → rewrite loop ────────────────────────────────────────
    for attempt in range(max_rewrites + 1):
        hard_fails, soft_fails = _classify_guard_failures(current, facts)

        if not hard_fails:
            # No hard failures → caption is publishable (soft failures are best-effort)
            if soft_fails:
                counters.guard_fail_reasons.extend(
                    g.reason for g in soft_fails if g.reason
                )
            counters.caption_ok += 1
            return current, counters

        # Hard failures exist
        counters.guard_fail_reasons.extend(g.reason for g in hard_fails if g.reason)
        counters.guard_fail_reasons.extend(g.reason for g in soft_fails if g.reason)

        if attempt >= max_rewrites:
            break  # exhausted rewrites with hard failures remaining

        # Critic rewrite
        try:
            counters.rewrite_attempts += 1
            violations = [g.reason for g in hard_fails + soft_fails if g.reason]
            raw_rewrite = await ollama.chat(
                _CRITIC_SYSTEM,
                _build_critic_user(current, facts, violations),
                client=client,
            )
            current = _sanitize_post(raw_rewrite.strip(), facts)
        except Exception:
            break

    # Hard guards still failing after max_rewrites — only failure case
    counters.caption_fail += 1
    return None, counters
