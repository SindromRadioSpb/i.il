"""cluster/tokens.py — Hebrew title tokenizer and Jaccard similarity.

Exact port of apps/worker/src/normalize/title_tokens.ts.
The tokenizer regex, stopwords, and Jaccard formula MUST remain identical
to the TypeScript implementation for story clustering to produce
equivalent groupings across both the local engine and the Worker.
"""

from __future__ import annotations

import re

# Common Hebrew function words that carry no topic signal.
# Exact 73 unique stopwords — same Set as title_tokens.ts (duplicates deduplicated).
HE_STOPWORDS: frozenset[str] = frozenset(
    [
        "של", "את", "אל", "עם", "כי", "על", "זה", "זו", "זאת",
        "הם", "הן", "היה", "היו", "הוא", "היא", "לא", "גם", "אבל",
        "כן", "אם", "כבר", "רק", "עוד", "כל", "כלל", "אחד", "אחת",
        "שני", "שתי", "מה", "מי", "לו", "לה", "להם", "לנו", "לי",
        "כך", "אז", "יש", "אין", "אחרי", "לפני", "בין", "תחת",
        "מתוך", "כנגד", "בגלל", "כדי", "כמו", "אחרת", "או", "שוב",
        "עכשיו", "יותר", "פחות", "הכל", "ממנו", "ממנה", "אלה", "אלו",
        "בה", "בהם", "בנו", "בי", "ומה",
        "ועל", "ואל", "ועם", "ולא", "וגם", "אנחנו", "אתם", "אתן",
    ]
)

# Split on non-Hebrew non-ASCII-alphanumeric chars — identical to TS regex.
_SPLIT_RE = re.compile(r"[^\u05D0-\u05EAa-zA-Z0-9]+")


def tokenize(title: str) -> frozenset[str]:
    """Tokenize a Hebrew (or mixed) title into a set of meaningful tokens.

    - Splits on whitespace and punctuation (Unicode-safe).
    - Lowercases (primarily affects mixed Hebrew+Latin titles).
    - Drops tokens shorter than 2 characters.
    - Drops Hebrew stopwords.

    Returns a frozenset (identical semantics to the TS Set<string>).
    """
    parts = _SPLIT_RE.split(title)
    tokens: set[str] = set()
    for raw in parts:
        t = raw.strip().lower()
        if len(t) < 2:
            continue
        if t in HE_STOPWORDS:
            continue
        tokens.add(t)
    return frozenset(tokens)


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity: |A∩B| / |A∪B|.

    Returns 0 when one set is empty; returns 1 when both are empty.
    Identical formula to TS jaccardSimilarity().
    """
    if len(a) == 0 and len(b) == 0:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0

    intersection = len(a & b)
    union = len(a) + len(b) - intersection
    return intersection / union
