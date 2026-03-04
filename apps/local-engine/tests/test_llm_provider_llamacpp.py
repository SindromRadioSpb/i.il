"""tests/test_llm_provider_llamacpp.py — OpenAI-compatible llama.cpp provider tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import Settings
from summary.llm_provider import LlamaCppOpenAIProvider, create_llm_provider


async def test_llamacpp_chat_payload_shape_and_url():
    provider = LlamaCppOpenAIProvider(
        base_url="http://localhost:8001/v1",
        model="Qwen-9B",
        timeout_sec=30,
        max_retries=1,
    )

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {"content": "ok"}
                }
            ]
        }
    )

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    out = await provider.chat(
        "sys",
        "user",
        client=client,
        format="json",
        temperature=0.2,
        top_p=0.9,
        max_tokens=128,
    )

    assert out == "ok"
    client.post.assert_awaited_once()
    call = client.post.call_args
    assert call.args[0] == "http://localhost:8001/v1/chat/completions"

    payload = call.kwargs["json"]
    assert payload["model"] == "Qwen-9B"
    assert payload["temperature"] == 0.2
    assert payload["top_p"] == 0.9
    assert payload["max_tokens"] == 128
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


async def test_llamacpp_chat_handles_content_parts_list():
    provider = LlamaCppOpenAIProvider(
        base_url="http://localhost:8001/v1",
        model="Qwen-9B",
        timeout_sec=30,
        max_retries=0,
    )

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "hello "},
                            {"type": "text", "text": "world"},
                        ]
                    }
                }
            ]
        }
    )

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    out = await provider.chat("sys", "user", client=client)
    assert out == "hello world"


async def test_llamacpp_healthcheck_ok_when_model_found():
    provider = LlamaCppOpenAIProvider(
        base_url="http://localhost:8001/v1",
        model="Qwen-9B",
        timeout_sec=30,
        max_retries=0,
    )

    models_resp = MagicMock()
    models_resp.raise_for_status = MagicMock()
    models_resp.json = MagicMock(
        return_value={
            "data": [{"id": "Qwen-9B"}]
        }
    )

    client = AsyncMock()
    client.get = AsyncMock(return_value=models_resp)

    ok, detail = await provider.healthcheck(client=client)
    assert ok is True
    assert "model found" in detail


async def test_llamacpp_healthcheck_fails_when_model_missing():
    provider = LlamaCppOpenAIProvider(
        base_url="http://localhost:8001/v1",
        model="Qwen-9B",
        timeout_sec=30,
        max_retries=0,
    )

    models_resp = MagicMock()
    models_resp.raise_for_status = MagicMock()
    models_resp.json = MagicMock(
        return_value={
            "data": [{"id": "AnotherModel"}]
        }
    )

    client = AsyncMock()
    client.get = AsyncMock(return_value=models_resp)

    ok, detail = await provider.healthcheck(client=client)
    assert ok is False
    assert "NOT FOUND" in detail


async def test_llamacpp_healthcheck_fallback_to_chat_when_models_unavailable():
    provider = LlamaCppOpenAIProvider(
        base_url="http://localhost:8001/v1",
        model="Qwen-9B",
        timeout_sec=30,
        max_retries=0,
    )

    client = AsyncMock()
    client.get = AsyncMock(side_effect=Exception("models endpoint unavailable"))

    chat_resp = MagicMock()
    chat_resp.raise_for_status = MagicMock()
    chat_resp.json = MagicMock(
        return_value={
            "choices": [{"message": {"content": "OK"}}]
        }
    )
    client.post = AsyncMock(return_value=chat_resp)

    ok, detail = await provider.healthcheck(client=client)
    assert ok is True
    assert "chat reachable" in detail


def test_create_llm_provider_llamacpp_from_settings():
    settings = Settings(
        _env_file=None,
        llm_provider="llamacpp",
        llm_base_url="http://localhost:8001/v1",
        llm_model="Qwen-9B",
    )

    provider = create_llm_provider(settings)
    assert provider.provider_name == "llamacpp"
    assert provider.base_url == "http://localhost:8001/v1"
    assert provider.model == "Qwen-9B"
