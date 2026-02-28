"""summary/ollama.py — HTTP client for the local Ollama instance.

Calls /api/chat (non-streaming) and returns the assistant message content.
Accepts an optional httpx.AsyncClient for dependency injection (testing).
"""

from __future__ import annotations

import httpx


class OllamaClient:
    """Thin wrapper around the Ollama /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b-instruct",
        timeout_sec: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec

    async def chat(
        self,
        system: str,
        user: str,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Call Ollama /api/chat and return the assistant message content.

        Args:
            system: System prompt.
            user: User message.
            client: Optional pre-constructed httpx.AsyncClient (for tests).
                    If None, a new client is created for this request.

        Returns:
            The assistant's response text.

        Raises:
            httpx.HTTPStatusError: on non-2xx responses.
            KeyError: if the response JSON is malformed.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        url = f"{self.base_url}/api/chat"

        if client is not None:
            response = await client.post(url, json=payload)
        else:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as c:
                response = await c.post(url, json=payload)

        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
