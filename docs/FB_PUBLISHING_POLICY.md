# Facebook Publishing Policy

## Rate Limits

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Posts per hour | 8 | sliding window (`hour_window_start`) |
| Posts per day | 40 | sliding window (`day_window_start`) |
| Minimum gap between posts | 3 minutes | `last_post_at` |

These limits are enforced in `publish/queue.py` via the pure `check_rate()` function
against the `fb_rate_state` singleton row in SQLite. No posts are made until the
applicable window has cleared.

## Retry Policy

| Attempt | Backoff |
|---------|---------|
| 1 | 60 s |
| 2 | 120 s |
| 3 | 240 s |
| 4 | 480 s |
| 5 | 960 s (cap: 3600 s) |

Formula: `min(2^attempt × 60, 3600)` seconds.

After `max_attempts` (default 5) the item is marked `status='failed'`
(permanent failure) and no further retries are attempted.

## Idempotency

Each story generates a dedupe key: `{story_id}:v{summary_version}`

If the summary is regenerated (new items added to the story), `summary_version`
increments and a **new queue entry** is created — the old post is not deleted,
but a fresh post with the updated summary is enqueued.

The UNIQUE index on `fb_dedupe_key WHERE fb_dedupe_key IS NOT NULL` ensures
that even if `enqueue()` is called twice for the same story/version, only one
queue row exists.

## Image Posts

When a cached image is available for the story:
- Uses `POST /{page_id}/photos` with `multipart/form-data` (source field)
- `message` field carries the full Russian summary text
- Falls back to text-only `POST /{page_id}/feed` if no image

## Circuit Breaker

If the Facebook Graph API returns error code **190** (invalid access token)
or **102** (session expired), `FBAuthError` is raised and the entire
publish queue processing loop is halted immediately for that cycle.

No further posts are attempted until the next scheduler run. This prevents
spamming invalid requests against a revoked token.

**Recovery:** Rotate `FB_PAGE_ACCESS_TOKEN` in `.env`, then restart the engine.

## Anti-Spam

- `editorial_hold=1` prevents any story from entering the publish queue
- Minimum 3-minute gap between any two posts regardless of queue depth
- Stories are ordered by `priority` then `scheduled_at ASC` — no "burst" processing
- All posts are Russian-language summaries; no raw Hebrew content is published

## Disabling FB Posting

Set `FB_POSTING_ENABLED=false` in `.env`. The queue manager skips
Phase 5 entirely. Already-queued items remain in the DB and are
processed when the flag is re-enabled.
