"""cluster/embeddings.py — Ollama embedding client + cosine similarity.

Generates dense vector embeddings for Hebrew/Russian text via Ollama's
/api/embeddings endpoint. Used by cluster_v2.py as the primary similarity
signal, with Jaccard as fallback.

Usage:
    client = EmbeddingClient("http://localhost:11434", "nomic-embed-text")
    vec = await client.embed("חדשות מהצפון")
    sim = cosine_similarity(vec_a, vec_b)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
import numpy as np


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D float arrays.

    Returns a value in [0, 1] (embeddings are non-negative after L2 norm,
    but we clamp to be safe). Returns 0.0 if either vector is all zeros.
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    dot = float(np.dot(a, b))
    raw = dot / (norm_a * norm_b)
    return float(np.clip(raw, -1.0, 1.0))


class EmbeddingError(Exception):
    """Raised when the Ollama embedding call fails."""


class EmbeddingClient:
    """Calls Ollama /api/embeddings to produce dense text embeddings."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(
        self,
        text: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> np.ndarray:
        """Return a 1-D float32 embedding array for the given text.

        Args:
            text:   The string to embed (Hebrew or Russian, typically a title).
            client: Optional injected httpx client (for testing).

        Raises:
            EmbeddingError: If the HTTP call fails or returns unexpected data.
        """
        payload = {"model": self.model, "prompt": text}

        async def _call(c: httpx.AsyncClient) -> list[float]:
            resp = await c.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if "embedding" not in data:
                raise EmbeddingError(f"No 'embedding' key in response: {data}")
            return data["embedding"]  # type: ignore[no-any-return]

        try:
            if client is None:
                async with httpx.AsyncClient() as c:
                    raw = await _call(c)
            else:
                raw = await _call(client)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Embedding call failed: {exc}") from exc

        return np.array(raw, dtype=np.float32)

    @property
    def dimensions(self) -> int | None:
        """Known output dimensions for common models (None = unknown until called)."""
        _dims = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "all-minilm": 384,
        }
        return _dims.get(self.model)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers for item_embeddings table
# ─────────────────────────────────────────────────────────────────────────────


async def store_embedding(
    db,
    item_key: str,
    vec: np.ndarray,
    model: str,
) -> None:
    """Upsert an embedding into item_embeddings."""
    blob = vec.astype(np.float32).tobytes()
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO item_embeddings (item_key, embedding, model, dimensions, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(item_key) DO UPDATE SET
            embedding  = excluded.embedding,
            model      = excluded.model,
            dimensions = excluded.dimensions,
            created_at = excluded.created_at
        """,
        (item_key, blob, model, len(vec), now),
    )
    await db.commit()


async def load_embedding(db, item_key: str) -> np.ndarray | None:
    """Load a stored embedding for item_key, or None if not found."""
    async with db.execute(
        "SELECT embedding, dimensions FROM item_embeddings WHERE item_key = ?",
        (item_key,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return np.frombuffer(row["embedding"], dtype=np.float32).copy()


async def load_embeddings_for_keys(
    db,
    item_keys: list[str],
) -> dict[str, np.ndarray]:
    """Load all stored embeddings for the given item keys."""
    if not item_keys:
        return {}
    placeholders = ",".join("?" * len(item_keys))
    async with db.execute(
        f"SELECT item_key, embedding FROM item_embeddings WHERE item_key IN ({placeholders})",
        item_keys,
    ) as cur:
        rows = await cur.fetchall()
    return {
        row["item_key"]: np.frombuffer(row["embedding"], dtype=np.float32).copy()
        for row in rows
    }
