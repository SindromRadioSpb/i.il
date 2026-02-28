"""summary/format.py — Parse and format the mandatory 5-section Russian summary.

Exact port of apps/worker/src/summary/format.ts.

Expected LLM output format:
  Заголовок: <headline>
  Что произошло: <1–2 sentences>
  Почему важно: <1 sentence>
  Что дальше: <1 sentence>
  Источники: <source names>
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedSummary:
    title: str
    what_happened: str
    why_important: str
    whats_next: str
    sources: str


# Section keys in mandatory order — identical to TS SECTIONS array.
_SECTIONS = [
    ("Заголовок", "title"),
    ("Что произошло", "what_happened"),
    ("Почему важно", "why_important"),
    ("Что дальше", "whats_next"),
    ("Источники", "sources"),
]


def parse_sections(text: str) -> ParsedSummary | None:
    """Parse LLM output into structured sections.

    Each section starts with "Key: value" on its own line.
    Multi-line continuation is supported for section content.
    Returns None if any required section is missing or has an empty value.
    """
    lines = text.split("\n")
    result: dict[str, str] = {}

    for s_idx, (key, field_name) in enumerate(_SECTIONS):
        next_key = _SECTIONS[s_idx + 1][0] if s_idx + 1 < len(_SECTIONS) else None

        # Find the line that begins this section
        start_idx = next(
            (i for i, line in enumerate(lines) if line.strip().startswith(key + ":")),
            -1,
        )
        if start_idx == -1:
            return None

        # Find where this section ends (start of next section or EOF)
        end_idx = len(lines)
        if next_key is not None:
            ni = next(
                (
                    i
                    for i, line in enumerate(lines)
                    if i > start_idx and line.strip().startswith(next_key + ":")
                ),
                -1,
            )
            if ni != -1:
                end_idx = ni

        # Collect value: inline text after "Key:" + any continuation lines
        first_line = lines[start_idx].strip()[len(key) + 1 :].strip()
        continuations = " ".join(
            line.strip()
            for line in lines[start_idx + 1 : end_idx]
            if line.strip()
        )
        value = (f"{first_line} {continuations}".strip() if continuations else first_line)
        if not value:
            return None

        result[field_name] = value

    return ParsedSummary(
        title=result["title"],
        what_happened=result["what_happened"],
        why_important=result["why_important"],
        whats_next=result["whats_next"],
        sources=result["sources"],
    )


def format_body(parsed: ParsedSummary) -> str:
    """Body text used for character-length checks (excludes Источники and title)."""
    return "\n".join(
        [
            f"Что произошло: {parsed.what_happened}",
            f"Почему важно: {parsed.why_important}",
            f"Что дальше: {parsed.whats_next}",
        ]
    )


def format_full(parsed: ParsedSummary) -> str:
    """Full display text stored in summary_ru (title + body + sources)."""
    return "\n".join(
        [
            parsed.title,
            "",
            f"Что произошло: {parsed.what_happened}",
            f"Почему важно: {parsed.why_important}",
            f"Что дальше: {parsed.whats_next}",
            f"Источники: {parsed.sources}",
        ]
    )
