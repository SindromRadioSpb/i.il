"""summary/llm_provider.py — LLM provider abstraction and implementations.

Supports:
  - Ollama (/api/chat, /api/embeddings)
  - llama.cpp server in OpenAI-compatible mode (/v1/chat/completions, /v1/embeddings)
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import httpx

_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@runtime_checkable
class LLMProvider(Protocol):
    """Common interface for local LLM backends."""

    provider_name: str
    base_url: str
    model: str
    timeout_sec: float
    max_retries: int

    async def chat(
        self,
        system: str,
        user: str,
        client: httpx.AsyncClient | None = None,
        *,
        format: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate assistant text for a system+user message pair."""

    async def embed(
        self,
        text: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[float]:
        """Generate an embedding for text."""

    async def healthcheck(
        self,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[bool, str]:
        """Return `(ok, detail)` for dependency health reporting."""


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else None
        return code in _RETRYABLE_STATUS_CODES
    return False


class _BaseHTTPProvider:
    provider_name = "llm"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_sec: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max(0, int(max_retries))

    async def _request_with_retries(
        self,
        request_coro,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await request_coro()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= self.max_retries or not _should_retry(exc):
                    raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("request_with_retries failed without an exception")

    async def _post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        client: httpx.AsyncClient | None = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"

        async def _call_with(c: httpx.AsyncClient) -> Any:
            resp = await c.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

        if client is not None:
            return await self._request_with_retries(lambda: _call_with(client))

        async with httpx.AsyncClient(timeout=self.timeout_sec) as c:
            return await self._request_with_retries(lambda: _call_with(c))

    async def _get_json(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"

        async def _call_with(c: httpx.AsyncClient) -> Any:
            resp = await c.get(url)
            resp.raise_for_status()
            return resp.json()

        if client is not None:
            return await self._request_with_retries(lambda: _call_with(client))

        async with httpx.AsyncClient(timeout=self.timeout_sec) as c:
            return await self._request_with_retries(lambda: _call_with(c))


class OllamaProvider(_BaseHTTPProvider):
    """Ollama implementation: /api/chat + /api/embeddings."""

    provider_name = "ollama"

    async def chat(
        self,
        system: str,
        user: str,
        client: httpx.AsyncClient | None = None,
        *,
        format: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if format:
            payload["format"] = format
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if max_tokens is not None:
            options["num_predict"] = int(max_tokens)
        if options:
            payload["options"] = options

        data = await self._post_json("/api/chat", payload, client=client)
        return str(data["message"]["content"])

    async def embed(
        self,
        text: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[float]:
        payload = {"model": self.model, "prompt": text}
        data = await self._post_json("/api/embeddings", payload, client=client)
        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            raise KeyError("Ollama /api/embeddings response missing embedding array")
        return [float(v) for v in embedding]

    async def healthcheck(
        self,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[bool, str]:
        try:
            data = await self._get_json("/api/tags", client=client)
            models = data.get("models", []) if isinstance(data, dict) else []
            model_names = [
                str(m.get("name", ""))
                for m in models
                if isinstance(m, dict)
            ]
            model_found = any(self.model in name for name in model_names)
            detail = (
                "reachable, model found"
                if model_found
                else f"reachable, model NOT FOUND: {self.model}"
            )
            return model_found, detail
        except Exception as exc:  # noqa: BLE001
            return False, f"unreachable: {exc}"


class LlamaCppOpenAIProvider(_BaseHTTPProvider):
    """llama.cpp server implementation via OpenAI-compatible /v1 endpoints."""

    provider_name = "llamacpp"

    async def chat(
        self,
        system: str,
        user: str,
        client: httpx.AsyncClient | None = None,
        *,
        format: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if format == "json":
            # Best-effort JSON hint for OpenAI-compatible servers.
            payload["response_format"] = {"type": "json_object"}

        data = await self._post_json("/chat/completions", payload, client=client)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise KeyError("chat/completions response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise KeyError("chat/completions response has invalid first choice")
        message = first.get("message")
        if not isinstance(message, dict):
            raise KeyError("chat/completions response missing message")
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text" and isinstance(part.get("text"), str):
                        parts.append(part["text"])
                    elif isinstance(part.get("content"), str):
                        parts.append(part["content"])
            if parts:
                return "".join(parts)
        return json.dumps(content, ensure_ascii=False)

    async def embed(
        self,
        text: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[float]:
        payload = {"model": self.model, "input": text}
        data = await self._post_json("/embeddings", payload, client=client)
        rows = data.get("data")
        if not isinstance(rows, list) or not rows:
            raise KeyError("/embeddings response missing data array")
        first = rows[0]
        if not isinstance(first, dict) or not isinstance(first.get("embedding"), list):
            raise KeyError("/embeddings response missing embedding vector")
        return [float(v) for v in first["embedding"]]

    async def healthcheck(
        self,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[bool, str]:
        models_exc: Exception | None = None
        try:
            data = await self._get_json("/models", client=client)
            rows = data.get("data", []) if isinstance(data, dict) else []
            model_names = [
                str(m.get("id", ""))
                for m in rows
                if isinstance(m, dict)
            ]
            model_found = any(self.model == name or self.model in name for name in model_names)
            detail = (
                "reachable, model found"
                if model_found
                else f"reachable, model NOT FOUND: {self.model}"
            )
            return model_found, detail
        except Exception as exc:  # noqa: BLE001
            models_exc = exc

        # Fallback when /models is absent/disabled on a specific build.
        try:
            _ = await self.chat(
                "You are a healthcheck endpoint.",
                "Reply with OK.",
                client=client,
                max_tokens=8,
            )
            suffix = type(models_exc).__name__ if models_exc is not None else "n/a"
            return True, f"chat reachable (/models unavailable: {suffix})"
        except Exception as exc:  # noqa: BLE001
            return False, f"unreachable: {exc}"


def create_llm_provider(settings) -> LLMProvider:
    """Factory that returns the configured provider instance."""
    provider_name = str(settings.llm_provider).strip().lower()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_sec=float(settings.llm_timeout_sec),
            max_retries=int(settings.llm_max_retries),
        )
    if provider_name == "llamacpp":
        return LlamaCppOpenAIProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_sec=float(settings.llm_timeout_sec),
            max_retries=int(settings.llm_max_retries),
        )
    raise ValueError(f"Unsupported LLM_PROVIDER={settings.llm_provider!r}")
