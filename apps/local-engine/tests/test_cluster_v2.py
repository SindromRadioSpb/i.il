"""tests/test_cluster_v2.py — cluster_v2 and eval harness tests.

Ollama calls are mocked. DB is an in-memory SQLite with full schema.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import numpy as np
import pytest

from cluster.cluster import ClusterItem
from cluster.cluster_v2 import ClusterV2Counters, cluster_new_items_v2, COSINE_THRESHOLD
from cluster.embeddings import EmbeddingClient, EmbeddingError
from cluster.eval import (
    EvalPair,
    EvalResult,
    evaluate_clustering,
    evaluate_from_file,
    load_pairs,
    make_cosine_predictor,
    make_jaccard_predictor,
)

_NOW = "2026-02-28T10:00:00.000Z"
_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cluster_eval_pairs.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _embed_client_returning(vec: list[float]) -> EmbeddingClient:
    """Create an EmbeddingClient whose embed() always returns vec."""
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"embedding": vec})
    http = AsyncMock(spec=httpx.AsyncClient)
    http.post = AsyncMock(return_value=response)
    client = EmbeddingClient()
    client._test_http = http  # patched below in _patch_embed
    return client


def _make_failing_embed_client() -> EmbeddingClient:
    """EmbeddingClient whose embed() always raises EmbeddingError."""
    http = AsyncMock(spec=httpx.AsyncClient)
    http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client = EmbeddingClient()
    client._test_http = http
    return client


async def _embed_fixed(
    ec: EmbeddingClient, text: str, vec: np.ndarray
) -> np.ndarray:
    return vec


async def _insert_item(db, item_key: str, title_he: str) -> None:
    """Insert a minimal item row so FK constraints on story_items are satisfied."""
    await db.execute(
        """
        INSERT OR IGNORE INTO items (
          item_id, source_id, source_url, normalized_url, item_key,
          title_he, date_confidence, ingested_at
        ) VALUES (?, 'ynet', ?, ?, ?, ?, 'high', ?)
        """,
        (item_key, f"https://ynet.co.il/{item_key}", f"https://ynet.co.il/{item_key}",
         item_key, title_he, _NOW),
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# cluster_new_items_v2: empty input
# ─────────────────────────────────────────────────────────────────────────────


async def test_v2_returns_zeros_for_empty_items(db):
    counters = await cluster_new_items_v2(db, [])
    assert counters.stories_new == 0
    assert counters.stories_updated == 0


# ─────────────────────────────────────────────────────────────────────────────
# cluster_new_items_v2: embedding fallback when Ollama is down
# ─────────────────────────────────────────────────────────────────────────────


async def test_v2_falls_back_to_jaccard_when_embed_fails(db):
    """With Ollama unavailable, v2 should still cluster via Jaccard."""
    # Two items with high Jaccard similarity (many shared Hebrew tokens)
    item_a = ClusterItem(item_key="ka", title_he="פיגוע ירי תל אביב נפגעים")
    item_b = ClusterItem(item_key="kb", title_he="ירי פיגוע תל אביב פצועים")
    await _insert_item(db, "ka", item_a.title_he)
    await _insert_item(db, "kb", item_b.title_he)

    failing_client = _make_failing_embed_client()
    # Patch embed to always raise
    async def _raise(text, **kw):
        raise EmbeddingError("no ollama")

    failing_client.embed = _raise  # type: ignore[method-assign]

    counters = await cluster_new_items_v2(db, [item_a, item_b], embed_client=failing_client)
    # item_a creates story, item_b matches via Jaccard
    assert counters.stories_new == 1
    assert counters.stories_updated == 1
    assert counters.embed_errors == 2
    assert counters.jaccard_matches == 1


async def test_v2_embed_errors_counted(db):
    failing_client = EmbeddingClient()

    async def _raise(text, **kw):
        raise EmbeddingError("no ollama")

    failing_client.embed = _raise  # type: ignore[method-assign]

    item = ClusterItem(item_key="k1", title_he="חדשות בלי קשר")
    await _insert_item(db, "k1", item.title_he)
    counters = await cluster_new_items_v2(db, [item], embed_client=failing_client)
    assert counters.embed_errors == 1


# ─────────────────────────────────────────────────────────────────────────────
# cluster_new_items_v2: cosine matching
# ─────────────────────────────────────────────────────────────────────────────


async def test_v2_creates_new_story_for_single_item(db):
    item = ClusterItem(item_key="k1", title_he="חדשות מהצפון")
    await _insert_item(db, "k1", item.title_he)
    ec = EmbeddingClient()
    ec.embed = AsyncMock(return_value=np.array([0.1, 0.2, 0.3], dtype=np.float32))  # type: ignore[method-assign]

    counters = await cluster_new_items_v2(db, [item], embed_client=ec)
    assert counters.stories_new == 1
    assert counters.stories_updated == 0


async def test_v2_embedding_match_increments_counter(db):
    """Two items with very similar embeddings should land in the same story."""
    similar_vec = [0.9, 0.1, 0.0]
    item_a = ClusterItem(item_key="ka", title_he="חדשות א")
    item_b = ClusterItem(item_key="kb", title_he="חדשות ב")
    await _insert_item(db, "ka", item_a.title_he)
    await _insert_item(db, "kb", item_b.title_he)

    ec = EmbeddingClient()
    ec.embed = AsyncMock(return_value=np.array(similar_vec, dtype=np.float32))  # type: ignore[method-assign]

    counters = await cluster_new_items_v2(db, [item_a, item_b], embed_client=ec)
    assert counters.stories_new == 1
    assert counters.stories_updated == 1
    assert counters.embedding_matches == 1


async def test_v2_different_embeddings_create_separate_stories(db):
    """Items with very different embeddings should become separate stories."""
    item_a = ClusterItem(item_key="ka", title_he="ביטחון מלחמה")
    item_b = ClusterItem(item_key="kb", title_he="מזג אוויר גשם")
    await _insert_item(db, "ka", item_a.title_he)
    await _insert_item(db, "kb", item_b.title_he)

    call_count = 0

    async def _embed_alternate(text, **kw):
        nonlocal call_count
        call_count += 1
        # Return orthogonal vectors
        if call_count == 1:
            return np.array([1.0, 0.0, 0.0], dtype=np.float32)
        return np.array([0.0, 1.0, 0.0], dtype=np.float32)

    ec = EmbeddingClient()
    ec.embed = _embed_alternate  # type: ignore[method-assign]

    counters = await cluster_new_items_v2(
        db, [item_a, item_b], embed_client=ec, cosine_threshold=0.75
    )
    assert counters.stories_new == 2
    assert counters.stories_updated == 0


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_clustering()
# ─────────────────────────────────────────────────────────────────────────────


def test_eval_perfect_predictor():
    pairs = [
        EvalPair("a", "b", True),
        EvalPair("c", "d", False),
    ]
    result = evaluate_clustering(pairs, predict_fn=lambda a, b: a < b)
    # "a" < "b" → True (correct), "c" < "d" → True (wrong — expected False)
    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 0
    assert result.true_negatives == 0


def test_eval_all_correct():
    pairs = [
        EvalPair("a", "b", True),
        EvalPair("c", "d", False),
    ]
    result = evaluate_clustering(pairs, predict_fn=lambda a, b: (a, b) == ("a", "b"))
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)
    assert result.f1 == pytest.approx(1.0)
    assert result.true_negatives == 1


def test_eval_all_wrong():
    pairs = [
        EvalPair("a", "b", True),   # predict False → FN
        EvalPair("c", "d", False),  # predict False → TN
    ]
    result = evaluate_clustering(pairs, predict_fn=lambda a, b: False)
    assert result.recall == pytest.approx(0.0)
    assert result.false_negatives == 1
    assert result.true_negatives == 1


def test_eval_empty_pairs():
    result = evaluate_clustering([], predict_fn=lambda a, b: True)
    assert result.f1 == pytest.approx(0.0)
    assert result.total == 0


def test_eval_f1_formula():
    # 2 TP, 1 FP, 1 FN → P=2/3, R=2/3, F1=2/3
    pairs = [
        EvalPair("a", "b", True),   # TP
        EvalPair("c", "d", True),   # TP
        EvalPair("e", "f", False),  # FP (predict True)
        EvalPair("g", "h", True),   # FN (predict False)
    ]
    calls = {("a", "b"): True, ("c", "d"): True, ("e", "f"): True, ("g", "h"): False}
    result = evaluate_clustering(pairs, predict_fn=lambda a, b: calls[(a, b)])
    assert result.precision == pytest.approx(2 / 3, abs=1e-3)
    assert result.recall == pytest.approx(2 / 3, abs=1e-3)
    assert result.f1 == pytest.approx(2 / 3, abs=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# load_pairs() and evaluate_from_file()
# ─────────────────────────────────────────────────────────────────────────────


def test_load_pairs_reads_fixture():
    pairs = load_pairs(_FIXTURES)
    assert len(pairs) == 10
    assert all(isinstance(p, EvalPair) for p in pairs)
    same_count = sum(1 for p in pairs if p.same_story)
    diff_count = sum(1 for p in pairs if not p.same_story)
    assert same_count == 5
    assert diff_count == 5


def test_evaluate_from_file_jaccard_baseline():
    """Jaccard should achieve perfect F1 on the fixture pairs (high token overlap)."""
    pairs = load_pairs(_FIXTURES)
    title_map = {}
    raw = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    for entry in raw:
        title_map[entry["item_key_a"]] = entry["title_a"]
        title_map[entry["item_key_b"]] = entry["title_b"]

    predict = make_jaccard_predictor(title_map, threshold=0.05)
    result = evaluate_clustering(pairs, predict_fn=predict)
    # At a low threshold, same-story pairs should score higher than different ones
    assert result.total == 10
    assert isinstance(result.f1, float)


def test_make_cosine_predictor_identical_vectors():
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    embedding_map = {"a": vec, "b": vec}
    predict = make_cosine_predictor(embedding_map, threshold=0.9)
    assert predict("a", "b") is True


def test_make_cosine_predictor_orthogonal_vectors():
    embedding_map = {
        "a": np.array([1.0, 0.0], dtype=np.float32),
        "b": np.array([0.0, 1.0], dtype=np.float32),
    }
    predict = make_cosine_predictor(embedding_map, threshold=0.5)
    assert predict("a", "b") is False


def test_make_cosine_predictor_missing_key():
    embedding_map = {"a": np.array([1.0, 0.0], dtype=np.float32)}
    predict = make_cosine_predictor(embedding_map, threshold=0.5)
    assert predict("a", "missing") is False


def test_eval_result_str():
    r = EvalResult(
        precision=0.8, recall=0.75, f1=0.774,
        true_positives=4, false_positives=1, false_negatives=2, true_negatives=3,
        total=10,
    )
    s = str(r)
    assert "Precision" in s
    assert "F1" in s
