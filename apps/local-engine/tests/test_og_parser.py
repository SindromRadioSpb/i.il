"""tests/test_og_parser.py — og:image extraction tests with mocked httpx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from images.og_parser import extract_og_image


def _mock_client(html: str, status: int = 200) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.text = html
    response.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    return client


_HTML_WITH_OG = (
    "<html><head>"
    '<meta property="og:image" content="https://cdn.ynet.co.il/img/news.jpg"/>'
    "</head></html>"
)

_HTML_WITHOUT_OG = "<html><head><title>No image here</title></head></html>"

_HTML_EMPTY_OG = (
    "<html><head>"
    '<meta property="og:image" content=""/>'
    "</head></html>"
)

_HTML_WHITESPACE_OG = (
    "<html><head>"
    '<meta property="og:image" content="  https://cdn.example.com/img.jpg  "/>'
    "</head></html>"
)


async def test_extracts_og_image_url():
    client = _mock_client(_HTML_WITH_OG)
    result = await extract_og_image("https://example.com", client=client)
    assert result == "https://cdn.ynet.co.il/img/news.jpg"


async def test_returns_none_when_no_og_tag():
    client = _mock_client(_HTML_WITHOUT_OG)
    result = await extract_og_image("https://example.com", client=client)
    assert result is None


async def test_returns_none_for_empty_og_content():
    client = _mock_client(_HTML_EMPTY_OG)
    result = await extract_og_image("https://example.com", client=client)
    assert result is None


async def test_strips_whitespace_from_og_url():
    client = _mock_client(_HTML_WHITESPACE_OG)
    result = await extract_og_image("https://example.com", client=client)
    assert result == "https://cdn.example.com/img.jpg"


async def test_returns_none_on_http_error():
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "404", request=MagicMock(), response=response
        )
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    result = await extract_og_image("https://example.com", client=client)
    assert result is None


async def test_returns_none_on_connection_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    result = await extract_og_image("https://example.com", client=client)
    assert result is None


async def test_calls_get_with_user_agent_header():
    client = _mock_client(_HTML_WITH_OG)
    await extract_og_image("https://example.com/article", client=client)
    call_kwargs = client.get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert "User-Agent" in headers


async def test_returns_none_for_malformed_html():
    client = _mock_client("<<<not html at all>>>")
    # BeautifulSoup is lenient — should not raise, just return None
    result = await extract_og_image("https://example.com", client=client)
    assert result is None
