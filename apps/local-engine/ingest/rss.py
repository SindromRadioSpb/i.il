"""ingest/rss.py — RSS 2.0 and Atom feed fetcher + parser.

Uses feedparser (handles both RSS 2.0 and Atom natively).
Mirrors the logic of apps/worker/src/ingest/rss.ts.

Key difference from TS:
- feedparser replaces fast-xml-parser (simpler, handles encoding)
- SHA-256 is synchronous (hashlib vs Web Crypto subtle)
- enclosure_url is extracted (new field, not in TS version)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import feedparser
import httpx

from ingest.html_strip import strip_html
from ingest.normalize import hash_hex, normalize_url, validate_url_for_fetch
from sources.models import Source

# Max snippet length — matches TS constant
_SNIPPET_MAX = 500


@dataclass
class NormalizedEntry:
    source_url: str
    normalized_url: str
    item_key: str            # sha256(normalized_url) — must match TS hash_hex
    title_he: str
    published_at: str | None  # ISO 8601 UTC or None
    snippet_he: str | None
    title_hash: str
    date_confidence: Literal["high", "low"]
    enclosure_url: str | None = None  # from <enclosure url="..."> (new vs TS)


def _parse_date(raw: str | None) -> str | None:
    """Parse RFC 2822 or ISO 8601 date to ISO 8601 UTC. Returns None on failure."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    # Try email-utils RFC 2822 (pubDate format from RSS)
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    # Try ISO 8601 (Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def _extract_enclosure_url(entry: feedparser.FeedParserDict) -> str | None:
    """Extract <enclosure url="..."> image URL if present."""
    enclosures = getattr(entry, "enclosures", None) or []
    for enc in enclosures:
        url = enc.get("href") or enc.get("url", "")
        mime = enc.get("type", "")
        if url and mime.startswith("image/"):
            return url
    # Some feeds use media:content
    media = getattr(entry, "media_content", None) or []
    for m in media:
        url = m.get("url", "")
        mime = m.get("type", "")
        if url and mime.startswith("image/"):
            return url
    return None


async def fetch_rss(
    source: Source,
    client: httpx.AsyncClient,
    max_items: int | None = None,
) -> list[NormalizedEntry]:
    """Fetch and parse an RSS 2.0 or Atom feed.

    SSRF-guarded: validate_url_for_fetch() raises ValueError for unsafe URLs.
    Returns up to max_items (default: source.throttle.max_items_per_run) entries.
    """
    limit = max_items if max_items is not None else source.throttle.max_items_per_run
    validate_url_for_fetch(source.url)

    resp = await client.get(
        source.url,
        headers={"User-Agent": "NewsHub/0.1"},
        follow_redirects=True,
    )
    resp.raise_for_status()

    # feedparser can parse from string directly
    feed = feedparser.parse(resp.text)

    entries: list[NormalizedEntry] = []

    for raw in feed.entries[:limit]:
        # Extract link
        link = getattr(raw, "link", "") or ""
        if not link or not (link.startswith("http://") or link.startswith("https://")):
            # Try id as fallback (Atom)
            link = getattr(raw, "id", "") or ""
        if not link:
            continue

        # Apply source-level URL exclusion patterns
        if any(pat in link for pat in source.exclude_url_patterns):
            continue

        # Extract title
        title_raw = getattr(raw, "title", "") or ""
        title = strip_html(title_raw)
        if not title:
            continue

        # Extract snippet
        snippet_raw = (
            getattr(raw, "summary", "")
            or getattr(raw, "description", "")
            or ""
        )
        snippet = strip_html(snippet_raw)[:_SNIPPET_MAX] or None

        # Parse date
        published_struct = getattr(raw, "published_parsed", None)
        updated_struct = getattr(raw, "updated_parsed", None)
        date_str: str | None = None
        for struct in (published_struct, updated_struct):
            if struct:
                try:
                    dt = datetime(*struct[:6], tzinfo=UTC)
                    date_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    break
                except Exception:
                    pass
        if not date_str:
            # Fallback: try raw string
            pub_raw = getattr(raw, "published", None) or getattr(raw, "updated", None)
            date_str = _parse_date(pub_raw)

        normalized = normalize_url(link)
        item_key = hash_hex(normalized)
        title_hash = hash_hex(title)
        enclosure_url = _extract_enclosure_url(raw)

        entries.append(
            NormalizedEntry(
                source_url=link,
                normalized_url=normalized,
                item_key=item_key,
                title_he=title,
                published_at=date_str,
                snippet_he=snippet,
                title_hash=title_hash,
                date_confidence="high" if date_str else "low",
                enclosure_url=enclosure_url,
            )
        )

    return entries
