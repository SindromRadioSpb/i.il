"""summary/ollama.py — backward-compatible shim for legacy imports.

New code should import providers from summary.llm_provider.
"""

from __future__ import annotations

from summary.llm_provider import OllamaProvider


class OllamaClient(OllamaProvider):
    """Compatibility alias: previous code used `OllamaClient`."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b-instruct",
        timeout_sec: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
        )
