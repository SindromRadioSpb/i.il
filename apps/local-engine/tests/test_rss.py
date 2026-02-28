"""tests/test_rss.py — RSS/Atom parser tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.rss import NormalizedEntry, fetch_rss
from sources.models import Source, Throttle

FIXTURES = Path(__file__).parent / "fixtures"


def _make_source(url: str = "https://example.com/rss") -> Source:
    return Source(
        id="test_source",
        name="Test",
        type="rss",
        url=url,
        enabled=True,
        throttle=Throttle(min_interval_sec=10, max_items_per_run=25),
    )


def _mock_client(content: str, status: int = 200) -> httpx.AsyncClient:
    """Create a mock httpx.AsyncClient that returns fixed content."""
    response = MagicMock(spec=httpx.Response)
    response.text = content
    response.status_code = status
    response.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    return client


async def test_parse_rss2_fixture():
    xml = (FIXTURES / "ynet_main.xml").read_text(encoding="utf-8")
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert len(entries) >= 1
    e = entries[0]
    assert e.item_key  # sha256 hex
    assert len(e.item_key) == 64
    assert e.title_he
    assert e.normalized_url.startswith("http")
    assert e.source_url.startswith("http")


async def test_parse_atom_fixture():
    xml = (FIXTURES / "atom_sample.xml").read_text(encoding="utf-8")
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert len(entries) == 2
    assert entries[0].title_he  # first entry has Hebrew title


async def test_max_items_respected():
    xml = (FIXTURES / "atom_sample.xml").read_text(encoding="utf-8")
    source = Source(
        id="s", name="s", type="rss", url="https://example.com/",
        enabled=True,
        throttle=Throttle(min_interval_sec=10, max_items_per_run=1),
    )
    client = _mock_client(xml)
    entries = await fetch_rss(source, client, max_items=1)
    assert len(entries) == 1


async def test_item_key_is_sha256_of_normalized_url():
    from ingest.normalize import hash_hex, normalize_url
    xml = (FIXTURES / "ynet_main.xml").read_text(encoding="utf-8")
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    for e in entries:
        expected_key = hash_hex(normalize_url(e.source_url))
        assert e.item_key == expected_key


async def test_ssrf_guard_blocks_private_ip():
    source = _make_source(url="http://192.168.1.1/rss")
    client = AsyncMock(spec=httpx.AsyncClient)
    with pytest.raises(ValueError, match="Disallowed private IP"):
        await fetch_rss(source, client)


async def test_utm_stripped_from_article_links():
    """Links in RSS items with UTM params get normalized."""
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>כותרת בדיקה</title>
        <link>https://example.com/news?utm_source=rss&amp;id=42</link>
        <pubDate>Thu, 28 Feb 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert len(entries) == 1
    assert "utm_source" not in entries[0].normalized_url
    assert "id=42" in entries[0].normalized_url


async def test_html_stripped_from_title():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title><![CDATA[<b>כותרת</b> עם HTML]]></title>
        <link>https://example.com/article/1</link>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert "<b>" not in entries[0].title_he
    assert "כותרת" in entries[0].title_he


async def test_enclosure_url_extracted():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>כותרת עם תמונה</title>
        <link>https://example.com/article/img</link>
        <enclosure url="https://cdn.example.com/img.jpg" type="image/jpeg" length="12345"/>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert len(entries) == 1
    assert entries[0].enclosure_url == "https://cdn.example.com/img.jpg"


async def test_missing_link_skipped():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>כותרת ללא קישור</title>
      </item>
      <item>
        <title>כותרת עם קישור</title>
        <link>https://example.com/valid</link>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert len(entries) == 1
    assert entries[0].title_he == "כותרת עם קישור"


async def test_date_confidence_high_when_pubdate_present():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>כותרת</title>
        <link>https://example.com/a</link>
        <pubDate>Thu, 28 Feb 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert entries[0].date_confidence == "high"
    assert entries[0].published_at is not None


async def test_date_confidence_low_when_no_pubdate():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>כותרת</title>
        <link>https://example.com/b</link>
      </item>
    </channel></rss>"""
    source = _make_source()
    client = _mock_client(xml)
    entries = await fetch_rss(source, client)
    assert entries[0].date_confidence == "low"
    assert entries[0].published_at is None
