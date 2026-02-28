"""tests/test_ollama.py — OllamaClient unit tests with mocked httpx."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from summary.ollama import OllamaClient


def _mock_client(content: str, status: int = 200) -> httpx.AsyncClient:
    """Return a mock httpx.AsyncClient that returns a fixed Ollama /api/chat response."""
    body = {"message": {"role": "assistant", "content": content}}
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json = MagicMock(return_value=body)
    response.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


async def test_chat_returns_content():
    ollama = OllamaClient(model="test-model")
    client = _mock_client("Тестовый ответ Ollama")
    result = await ollama.chat("system", "user", client=client)
    assert result == "Тестовый ответ Ollama"


async def test_chat_sends_correct_payload():
    ollama = OllamaClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client = _mock_client("ok")
    await ollama.chat("sys prompt", "user prompt", client=client)

    client.post.assert_awaited_once()
    call_args = client.post.call_args
    assert call_args.args[0] == "http://localhost:11434/api/chat"
    payload = call_args.kwargs["json"]
    assert payload["model"] == "qwen2.5:7b"
    assert payload["stream"] is False
    messages = payload["messages"]
    assert messages[0] == {"role": "system", "content": "sys prompt"}
    assert messages[1] == {"role": "user", "content": "user prompt"}


async def test_chat_raises_on_http_error():
    response = MagicMock(spec=httpx.Response)
    response.status_code = 500
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=response)
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)

    ollama = OllamaClient()
    with pytest.raises(httpx.HTTPStatusError):
        await ollama.chat("s", "u", client=client)


async def test_chat_uses_trailing_slash_stripped_base_url():
    ollama = OllamaClient(base_url="http://localhost:11434/")
    client = _mock_client("ok")
    await ollama.chat("s", "u", client=client)
    url = client.post.call_args.args[0]
    assert url == "http://localhost:11434/api/chat"


async def test_chat_returns_non_empty_content():
    ollama = OllamaClient()
    client = _mock_client("Some generated text here")
    result = await ollama.chat("s", "u", client=client)
    assert len(result) > 0
