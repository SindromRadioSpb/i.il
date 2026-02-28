"""tests/test_embeddings.py — EmbeddingClient and cosine_similarity tests.

All Ollama calls are mocked via a fake httpx.AsyncClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import numpy as np
import pytest

from cluster.embeddings import (
    EmbeddingClient,
    EmbeddingError,
    cosine_similarity,
    load_embedding,
    load_embeddings_for_keys,
    store_embedding,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_client(embedding: list[float], status: int = 200) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json = MagicMock(return_value={"embedding": embedding})
    response.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


def _make_error_client(exc: Exception) -> httpx.AsyncClient:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(side_effect=exc)
    return client


def _make_bad_json_client() -> httpx.AsyncClient:
    """Returns a client whose response has no 'embedding' key."""
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"error": "model not loaded"})
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# cosine_similarity()
# ─────────────────────────────────────────────────────────────────────────────


def test_cosine_identical_vectors():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_opposite_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_zero():
    zero = np.array([0.0, 0.0], dtype=np.float32)
    v = np.array([1.0, 2.0], dtype=np.float32)
    assert cosine_similarity(zero, v) == pytest.approx(0.0)
    assert cosine_similarity(v, zero) == pytest.approx(0.0)


def test_cosine_both_zero():
    zero = np.array([0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(zero, zero) == pytest.approx(0.0)


def test_cosine_high_dimensional():
    rng = np.random.default_rng(42)
    v = rng.random(768).astype(np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingClient.embed()
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_returns_numpy_array():
    vec = [0.1, 0.2, 0.3]
    client = _make_client(vec)
    ec = EmbeddingClient()
    result = await ec.embed("hello", client=client)
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert list(result) == pytest.approx(vec)


async def test_embed_calls_correct_url():
    client = _make_client([0.5])
    ec = EmbeddingClient(base_url="http://localhost:11434", model="nomic-embed-text")
    await ec.embed("test text", client=client)
    call_url = client.post.call_args.args[0]
    assert call_url == "http://localhost:11434/api/embeddings"


async def test_embed_sends_model_and_prompt():
    client = _make_client([0.5])
    ec = EmbeddingClient(model="nomic-embed-text")
    await ec.embed("test prompt", client=client)
    payload = client.post.call_args.kwargs["json"]
    assert payload["model"] == "nomic-embed-text"
    assert payload["prompt"] == "test prompt"


async def test_embed_raises_on_http_error():
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
    client = _make_error_client(exc)
    ec = EmbeddingClient()
    with pytest.raises(EmbeddingError):
        await ec.embed("test", client=client)


async def test_embed_raises_on_connection_error():
    client = _make_error_client(httpx.ConnectError("refused"))
    ec = EmbeddingClient()
    with pytest.raises(EmbeddingError):
        await ec.embed("test", client=client)


async def test_embed_raises_when_no_embedding_key():
    client = _make_bad_json_client()
    ec = EmbeddingClient()
    with pytest.raises(EmbeddingError, match="No 'embedding' key"):
        await ec.embed("test", client=client)


def test_dimensions_known_model():
    ec = EmbeddingClient(model="nomic-embed-text")
    assert ec.dimensions == 768


def test_dimensions_unknown_model():
    ec = EmbeddingClient(model="custom-model")
    assert ec.dimensions is None


# ─────────────────────────────────────────────────────────────────────────────
# store_embedding / load_embedding
# ─────────────────────────────────────────────────────────────────────────────


async def test_store_and_load_roundtrip(db):
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    await store_embedding(db, "key1", vec, "nomic-embed-text")
    loaded = await load_embedding(db, "key1")
    assert loaded is not None
    np.testing.assert_array_almost_equal(loaded, vec)


async def test_load_returns_none_for_missing(db):
    result = await load_embedding(db, "nonexistent")
    assert result is None


async def test_store_upserts_on_second_call(db):
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)
    await store_embedding(db, "key1", v1, "nomic-embed-text")
    await store_embedding(db, "key1", v2, "nomic-embed-text")
    loaded = await load_embedding(db, "key1")
    np.testing.assert_array_almost_equal(loaded, v2)


async def test_load_embeddings_for_keys_batch(db):
    keys = ["k1", "k2", "k3"]
    vecs = [
        np.array([1.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0], dtype=np.float32),
        np.array([0.5, 0.5], dtype=np.float32),
    ]
    for k, v in zip(keys, vecs):
        await store_embedding(db, k, v, "nomic-embed-text")

    result = await load_embeddings_for_keys(db, keys)
    assert set(result.keys()) == set(keys)
    for k, v in zip(keys, vecs):
        np.testing.assert_array_almost_equal(result[k], v)


async def test_load_embeddings_empty_keys(db):
    result = await load_embeddings_for_keys(db, [])
    assert result == {}
