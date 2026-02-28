"""images/og_parser.py — Extract og:image URL from article HTML."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup


async def extract_og_image(
    url: str,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Fetch article HTML and extract the og:image meta tag content.

    Returns the image URL string, or None if not found or on any error.
    Errors are silently swallowed — this is best-effort enrichment.
    """
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                return await _fetch_og(c, url)
        return await _fetch_og(client, url)
    except Exception:
        return None


async def _fetch_og(client: httpx.AsyncClient, url: str) -> str | None:
    resp = await client.get(url, headers={"User-Agent": "NewsHubBot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("meta", attrs={"property": "og:image"})
    if tag:
        content = tag.get("content", "")
        stripped = str(content).strip()
        return stripped if stripped else None
    return None
