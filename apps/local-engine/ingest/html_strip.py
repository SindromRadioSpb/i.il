"""ingest/html_strip.py — Strip HTML tags and decode entities."""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Remove HTML tags, decode common entities, collapse whitespace.

    Mirrors the TS stripHtml() in apps/worker/src/ingest/rss.ts:
      - Remove all <tag> elements
      - Decode &amp; &lt; &gt; &quot; and numeric entities
      - Collapse runs of whitespace to single space
      - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    # Remove tags first
    result = _TAG_RE.sub(" ", text)
    # Decode HTML entities (handles &amp; &lt; &gt; &quot; &#NNN; &#xHHH; etc.)
    result = html.unescape(result)
    # Collapse whitespace
    result = _MULTI_SPACE_RE.sub(" ", result).strip()
    return result
