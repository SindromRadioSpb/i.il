"""tests/test_summary.py — Summary pipeline integration tests.

Uses real in-memory SQLite + mocked OllamaClient to verify the full
generate → persist lifecycle without requiring a running Ollama instance.

WOW-story note: the pipeline makes 5+ Ollama calls per story
(summary, category, hashtags, fact_extract, draft_wow[, critic]).
Tests that only provide 3 mock responses let WOW generation fail silently
(best-effort) — stories are still published and counters.failed stays 0.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from cluster.cluster import ClusterItem, cluster_new_items
from db.repos.runs_repo import start_run
from summary.generate import SummaryCounters, _memoization_hash, run_summary_pipeline
from summary.ollama import OllamaClient


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# A well-formed summary whose body (Что произошло + Почему важно + Что дальше) is
# deliberately long enough to pass guard_length(400, 700).
_VALID_SUMMARY = (
    "Заголовок: В Тель-Авиве произошло землетрясение\n"
    "Что произошло: Землетрясение магнитудой 4.5 произошло ранним утром в районе "
    "Тель-Авива. По данным Геологической службы Израиля, эпицентр находился "
    "в 10 км к западу от центра города, на глубине 15 км. Несколько зданий "
    "получили незначительные повреждения, жертв и пострадавших нет.\n"
    "Почему важно: Это первое значительное землетрясение в центральном Израиле "
    "за последние десять лет, что указывает на активизацию сейсмической "
    "активности в регионе Мёртвого моря и требует внимания властей.\n"
    "Что дальше: Сейсмологи продолжают мониторинг ситуации и оценивают "
    "возможность повторных толчков в ближайшие 48 часов. Власти призывают "
    "граждан сохранять спокойствие и следовать инструкциям гражданской обороны.\n"
    "Источники: Ynet, Mako"
)

_VALID_CATEGORY = "society"
_VALID_HASHTAGS = "#Израиль #землетрясение #ТельАвив"


@pytest.fixture
async def run_id(db):
    """Insert a run row so record_error FK constraint is satisfied."""
    rid = "test-run-1"
    await start_run(db, rid)
    return rid


async def _insert_item(db, item_id: str, title_he: str, source_id: str = "ynet") -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO items (
          item_id, source_id, source_url, normalized_url, item_key,
          title_he, date_confidence, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'high', '2026-02-28T10:00:00.000Z')
        """,
        (item_id, source_id, f"https://ynet.co.il/{item_id}",
         f"https://ynet.co.il/{item_id}", item_id, title_he),
    )
    await db.commit()


def _make_ollama(responses: list[str]) -> OllamaClient:
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=responses)
    return ollama


async def _setup_story(db) -> str:
    """Insert one item and cluster it → return story_id."""
    await _insert_item(db, "item1", "רעידת אדמה בתל אביב")
    await cluster_new_items(db, [ClusterItem("item1", "רעידת אדמה בתל אביב")])
    async with db.execute("SELECT story_id FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    return row["story_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Memoization hash
# ─────────────────────────────────────────────────────────────────────────────


def test_memoization_hash_is_deterministic():
    h1 = _memoization_hash(["id1", "id2"], "low")
    h2 = _memoization_hash(["id2", "id1"], "low")  # different order
    assert h1 == h2  # sorted before hashing


def test_memoization_hash_differs_on_risk_level():
    h1 = _memoization_hash(["id1"], "low")
    h2 = _memoization_hash(["id1"], "high")
    assert h1 != h2


def test_memoization_hash_is_64_hex_chars():
    h = _memoization_hash(["id1"], "low")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline — happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_pipeline_publishes_valid_summary(db, run_id):
    await _setup_story(db)
    ollama = _make_ollama([_VALID_SUMMARY, _VALID_CATEGORY, _VALID_HASHTAGS])

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.published == 1
    assert counters.failed == 0
    assert counters.skipped == 0

    async with db.execute("SELECT state, title_ru FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row["state"] == "published"
    assert row["title_ru"] == "В Тель-Авиве произошло землетрясение"


async def test_pipeline_creates_publication_row(db, run_id):
    await _setup_story(db)
    ollama = _make_ollama([_VALID_SUMMARY, _VALID_CATEGORY, _VALID_HASHTAGS])

    await run_summary_pipeline(db, ollama, run_id)

    async with db.execute("SELECT web_status FROM publications LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["web_status"] == "published"


async def test_pipeline_stores_category_and_hashtags(db, run_id):
    await _setup_story(db)
    ollama = _make_ollama([_VALID_SUMMARY, _VALID_CATEGORY, _VALID_HASHTAGS])

    await run_summary_pipeline(db, ollama, run_id)

    async with db.execute("SELECT category, hashtags FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row["category"] == "society"
    assert row["hashtags"] is not None
    assert "#Израиль" in row["hashtags"]


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline — skip conditions
# ─────────────────────────────────────────────────────────────────────────────


async def test_pipeline_skips_story_with_no_items(db, run_id):
    await db.execute(
        "INSERT INTO stories (story_id, start_at, last_update_at, category, risk_level, state) "
        "VALUES ('orphan', '2026-02-28T10:00:00.000Z', '2026-02-28T10:00:00.000Z', 'other', 'low', 'draft')"
    )
    await db.commit()

    ollama = _make_ollama([])
    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.skipped == 1
    assert counters.published == 0


async def test_pipeline_skips_already_published_story(db, run_id):
    await _setup_story(db)
    ollama1 = _make_ollama([_VALID_SUMMARY, _VALID_CATEGORY, _VALID_HASHTAGS])
    await run_summary_pipeline(db, ollama1, run_id)

    # Story is now published; won't appear in draft query
    ollama2 = _make_ollama([])
    counters = await run_summary_pipeline(db, ollama2, run_id)
    assert counters.attempted == 0


async def test_pipeline_skips_editorial_hold_story(db, run_id):
    await _setup_story(db)
    await db.execute("UPDATE stories SET editorial_hold = 1")
    await db.commit()

    ollama = _make_ollama([])
    counters = await run_summary_pipeline(db, ollama, run_id)
    assert counters.attempted == 0


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline — failure modes
# ─────────────────────────────────────────────────────────────────────────────


async def test_pipeline_fails_on_unparseable_output(db, run_id):
    await _setup_story(db)
    ollama = _make_ollama(["This is not a valid structured summary at all."])

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.failed == 1
    assert counters.published == 0

    async with db.execute("SELECT state FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row["state"] == "draft"


async def test_pipeline_fails_on_forbidden_word(db, run_id):
    await _setup_story(db)
    bad = _VALID_SUMMARY.replace("произошло ранним утром", "это настоящий ужас для жителей")
    ollama = _make_ollama([bad])

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.failed == 1
    assert counters.published == 0


async def test_pipeline_records_error_on_ollama_exception(db, run_id):
    await _setup_story(db)
    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=Exception("Connection refused"))

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.failed == 1
    async with db.execute("SELECT COUNT(*) as cnt FROM error_events") as cur:
        row = await cur.fetchone()
    assert row["cnt"] >= 1


async def test_pipeline_respects_max_summaries_limit(db, run_id):
    # Insert 3 distinct stories
    for i in range(3):
        await _insert_item(db, f"item{i}", f"כותרת {i}")
        await cluster_new_items(db, [ClusterItem(f"item{i}", f"כותרת {i}")])

    call_count = 0

    async def _chat(system, user, client=None):
        nonlocal call_count
        call_count += 1
        if call_count % 3 == 1:
            return _VALID_SUMMARY
        if call_count % 3 == 2:
            return _VALID_CATEGORY
        return _VALID_HASHTAGS

    ollama = MagicMock(spec=OllamaClient)
    ollama.chat = AsyncMock(side_effect=_chat)

    counters = await run_summary_pipeline(db, ollama, run_id, max_summaries=1)
    assert counters.attempted <= 1


# ─────────────────────────────────────────────────────────────────────────────
# WOW-story FB caption
# ─────────────────────────────────────────────────────────────────────────────

# A valid WOW-story FB caption that passes all guards.
# Note: numbers list is empty for this story (no numbers in Hebrew title).
_VALID_FACTS_JSON = json.dumps({
    "event_type": "society",
    "location": "Тель-Авив",
    "time_ref": "утром",
    "actors": [],
    "numbers": [],
    "claims": ["Землетрясение произошло в Тель-Авиве", "Жертв нет"],
    "uncertainty_notes": [],
    "sources": ["ynet"],
    "risk_level": "low",
    "story_url": "https://ynet.co.il/item1",
})

_VALID_WOW = (
    "Землетрясение в Тель-Авиве: всё под контролем\n\n"
    "Ранним утром в районе Тель-Авива произошло сейсмическое событие магнитудой по шкале Рихтера. "
    "По данным Геологической службы Израиля, эпицентр находился к западу от центра города на значительной глубине. "
    "Официально подтверждено: жертв и серьёзных структурных разрушений в результате толчков нет. "
    "Сейсмологи продолжают круглосуточный мониторинг ситуации и призывают жителей сохранять спокойствие.\n\n"
    "Ощущали ли вы это землетрясение сегодня утром?\n\n"
    "Подробнее → https://ynet.co.il/item1"
)


async def test_pipeline_generates_fb_caption(db, run_id):
    """Pipeline stores fb_caption in DB when WOW generation succeeds."""
    await _setup_story(db)
    # 5 calls: summary + category + hashtags + fact_extract + draft_wow
    ollama = _make_ollama([
        _VALID_SUMMARY,
        _VALID_CATEGORY,
        _VALID_HASHTAGS,
        _VALID_FACTS_JSON,
        _VALID_WOW,
    ])

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.published == 1
    assert counters.failed == 0
    assert counters.wow_caption_ok == 1
    assert counters.wow_caption_fail == 0

    async with db.execute("SELECT fb_caption FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row["fb_caption"] is not None
    assert "Подробнее →" in row["fb_caption"]
    assert "#" not in row["fb_caption"]
    # No section headers
    assert "Что произошло:" not in row["fb_caption"]
    assert "Почему важно:" not in row["fb_caption"]


async def test_pipeline_publishes_without_fb_caption_on_wow_failure(db, run_id):
    """Story is published even when WOW story generation fails (best-effort)."""
    await _setup_story(db)
    # Only 3 responses — WOW generation will run out of mocked responses and fail silently
    ollama = _make_ollama([_VALID_SUMMARY, _VALID_CATEGORY, _VALID_HASHTAGS])

    counters = await run_summary_pipeline(db, ollama, run_id)

    assert counters.published == 1
    assert counters.failed == 0
    assert counters.wow_caption_fail == 1

    async with db.execute("SELECT state, fb_caption FROM stories LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row["state"] == "published"
    # fb_caption may be None — WOW failed silently, story still published
