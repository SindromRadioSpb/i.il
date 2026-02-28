"""cluster/cluster_v2.py — Hybrid embedding + Jaccard clustering.

Strategy:
  1. For each new item, try to find an existing story using cosine similarity
     of Ollama embeddings (threshold 0.75).
  2. If cosine match found → attach to that story.
  3. If embedding unavailable (Ollama down, timeout) → fall back to Jaccard.
  4. If no match above either threshold → create a new story.

This produces tighter clusters than Jaccard alone for stories that use
different phrasings for the same event, while preserving Jaccard as a
reliable offline fallback.

DB: embeddings are cached in item_embeddings to avoid re-calling Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite

from cluster.cluster import ClusterCounters, ClusterItem, CLUSTER_WINDOW_SEC, SIMILARITY_THRESHOLD
from cluster.embeddings import EmbeddingClient, EmbeddingError, cosine_similarity, store_embedding
from cluster.tokens import jaccard_similarity, tokenize
from db.repos.stories_repo import (
    create_story,
    find_recent_stories,
    update_story_last_update,
)
from db.repos.story_items_repo import attach_item

# Cosine similarity threshold for embedding-based match.
# Higher = stricter clustering (fewer merges).
COSINE_THRESHOLD: float = 0.75


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class ClusterV2Counters:
    stories_new: int = 0
    stories_updated: int = 0
    embedding_matches: int = 0   # matched via cosine
    jaccard_matches: int = 0     # fell back to Jaccard
    embed_errors: int = 0        # Ollama unavailable


async def cluster_new_items_v2(
    db: aiosqlite.Connection,
    items: list[ClusterItem],
    embed_client: EmbeddingClient | None = None,
    *,
    cosine_threshold: float = COSINE_THRESHOLD,
    jaccard_threshold: float = SIMILARITY_THRESHOLD,
) -> ClusterV2Counters:
    """Cluster items using embeddings (cosine) with Jaccard fallback.

    Args:
        db:                aiosqlite connection.
        items:             New items to cluster.
        embed_client:      EmbeddingClient instance. If None, a default
                           localhost client is created.
        cosine_threshold:  Minimum cosine similarity to merge via embeddings.
        jaccard_threshold: Minimum Jaccard similarity to merge as fallback.

    Returns:
        ClusterV2Counters with per-method match breakdown.
    """
    if not items:
        return ClusterV2Counters()

    if embed_client is None:
        embed_client = EmbeddingClient()

    candidates = await find_recent_stories(db, CLUSTER_WINDOW_SEC)

    # In-memory token sets (same as v1) for Jaccard fallback.
    candidate_tokens: dict[str, frozenset[str]] = {
        c.story_id: tokenize(c.title_he) for c in candidates
    }

    # In-memory centroid embeddings for cosine matching.
    # Keyed by story_id; value is the running mean embedding.
    candidate_embeddings: dict[str, tuple[np.ndarray, int]] = {}

    # Pre-load stored embeddings for recent story items.
    if candidates:
        from cluster.embeddings import load_embeddings_for_keys
        import numpy as np

        # Collect all item_keys linked to recent stories.
        story_ids = [c.story_id for c in candidates]
        placeholders = ",".join("?" * len(story_ids))
        async with db.execute(
            f"SELECT story_id, item_key FROM story_items WHERE story_id IN ({placeholders})",
            story_ids,
        ) as cur:
            si_rows = await cur.fetchall()

        all_keys = [r["item_key"] for r in si_rows]
        stored = await load_embeddings_for_keys(db, all_keys)

        # Build per-story centroid from stored embeddings.
        story_vecs: dict[str, list[np.ndarray]] = {}
        for row in si_rows:
            vec = stored.get(row["item_key"])
            if vec is not None:
                story_vecs.setdefault(row["story_id"], []).append(vec)

        for sid, vecs in story_vecs.items():
            centroid = np.mean(np.stack(vecs), axis=0).astype(np.float32)
            candidate_embeddings[sid] = (centroid, len(vecs))
    else:
        import numpy as np

    counters = ClusterV2Counters()
    now = _now_iso()

    for item in items:
        item_tokens = tokenize(item.title_he)
        best_story_id: str | None = None
        used_embedding = False

        # ── Step 1: Try embedding cosine match ──────────────────────────────
        item_vec: np.ndarray | None = None
        try:
            item_vec = await embed_client.embed(item.title_he)
            await store_embedding(db, item.item_key, item_vec, embed_client.model)
        except EmbeddingError:
            counters.embed_errors += 1

        if item_vec is not None and candidate_embeddings:
            best_cosine = cosine_threshold  # must strictly exceed
            for story_id, (centroid, _count) in candidate_embeddings.items():
                sim = cosine_similarity(item_vec, centroid)
                if sim > best_cosine:
                    best_cosine = sim
                    best_story_id = story_id
                    used_embedding = True

        # ── Step 2: Jaccard fallback ─────────────────────────────────────────
        if best_story_id is None:
            best_jaccard = jaccard_threshold  # must strictly exceed
            for story_id, story_tokens in candidate_tokens.items():
                score = jaccard_similarity(item_tokens, story_tokens)
                if score > best_jaccard:
                    best_jaccard = score
                    best_story_id = story_id

        # ── Step 3: Attach or create ─────────────────────────────────────────
        if best_story_id is not None:
            attached = await attach_item(db, best_story_id, item.item_key, now)
            if attached:
                await update_story_last_update(db, best_story_id, now)

                # Update in-memory structures.
                existing_tokens = candidate_tokens[best_story_id]
                candidate_tokens[best_story_id] = existing_tokens | item_tokens

                if item_vec is not None:
                    if best_story_id in candidate_embeddings:
                        old_centroid, old_count = candidate_embeddings[best_story_id]
                        new_count = old_count + 1
                        new_centroid = (
                            (old_centroid * old_count + item_vec) / new_count
                        ).astype(np.float32)
                        candidate_embeddings[best_story_id] = (new_centroid, new_count)
                    else:
                        candidate_embeddings[best_story_id] = (item_vec, 1)

                counters.stories_updated += 1
                if used_embedding:
                    counters.embedding_matches += 1
                else:
                    counters.jaccard_matches += 1
        else:
            new_story_id = str(uuid4())
            start_at = item.published_at or now
            await create_story(db, new_story_id, start_at)
            await attach_item(db, new_story_id, item.item_key, now)

            candidate_tokens[new_story_id] = item_tokens
            if item_vec is not None:
                candidate_embeddings[new_story_id] = (item_vec, 1)

            counters.stories_new += 1

    await db.commit()
    return counters


# numpy import needed at module level after conditional block
import numpy as np  # noqa: E402
