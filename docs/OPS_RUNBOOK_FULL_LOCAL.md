# Ops Runbook: Full Local Engine

## Prerequisites

- Python 3.11+
- Ollama installed and running (`ollama serve`)
- Model pulled: `ollama pull qwen2.5:7b-instruct`
- (Optional) Facebook Page Access Token

## Install

```bash
cd apps/local-engine
pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
# Edit .env — minimum required:
# DATABASE_PATH=data/news_hub.db
# OLLAMA_BASE_URL=http://localhost:11434
# CF_SYNC_URL=https://iil.sindromradiospb.workers.dev/api/v1/sync/stories
# CF_SYNC_TOKEN=<token from wrangler secret>
```

## Run Once (manual test)

```bash
cd apps/local-engine
python main.py
```

The engine runs one full cycle (ingest → cluster → summary → images → fb → sync), writes results to `data/news_hub.db`, logs to `data/logs/engine.jsonl`, then exits.

## Run as Daemon

```bash
python main.py --loop
```

Loops every `SCHEDULER_INTERVAL_SEC` seconds (default 600) with ±`SCHEDULER_JITTER_SEC` jitter.

## Autostart (Windows Task Scheduler)

1. Open **Task Scheduler** → **Create Task**
2. **General tab:**
   - Name: `NewsHubEngine`
   - Run whether user is logged on or not
   - Run with highest privileges
3. **Triggers tab:** At system startup, repeat every 15 minutes
4. **Actions tab:**
   - Program: `C:\Python314\python.exe`
   - Arguments: `J:\Project_Vibe\i.il\apps\local-engine\main.py --loop`
   - Start in: `J:\Project_Vibe\i.il\apps\local-engine`
5. **Settings tab:**
   - If task is already running: **Do not start a new instance**

Alternatively, create a `.bat` launcher and point the scheduler at it.

## Diagnose: Why Isn't Story X Visible?

```python
# In Python REPL:
import asyncio
from db.connection import get_db
from observe.why_not import why_not_published
from config.settings import Settings

async def check(story_id):
    s = Settings()
    async with get_db(s.database_path) as db:
        reasons = await why_not_published(db, story_id)
        for r in reasons:
            print(r)

asyncio.run(check("your-story-id"))
```

**Common reasons and fixes:**

| Reason | Fix |
|--------|-----|
| `state='draft'` | Wait for next summary run or check Ollama |
| `editorial_hold=1` | `POST /api/v1/admin/story/{id}/release` |
| `summary_ru is NULL` | Check Ollama is running; check `OLLAMA_MODEL` env |
| `no items attached` | Check clustering logs; verify sources are fetching |
| `cf_synced_at is NULL` | Check `CF_SYNC_TOKEN` is set; check Worker logs |
| `no publication record` | Check `FB_POSTING_ENABLED=true` and rate limits |

## View Daily Report

```python
import asyncio
from db.connection import get_db
from observe.report import generate_daily_report
from config.settings import Settings

async def report():
    s = Settings()
    async with get_db(s.database_path) as db:
        md = await generate_daily_report(db, "2026-02-28")
        print(md)

asyncio.run(report())
```

## View Metrics

```python
import asyncio
from db.connection import get_db
from observe.metrics import MetricsRecorder
from config.settings import Settings

async def summary():
    s = Settings()
    async with get_db(s.database_path) as db:
        rec = MetricsRecorder()
        data = await rec.get_summary(db, hours=24)
        for phase, keys in data.items():
            print(f"{phase}: {keys}")

asyncio.run(summary())
```

## Check Logs

```bash
# Real-time tail
tail -f data/logs/engine.jsonl | python -m json.tool

# Filter by phase
grep '"phase":"summary"' data/logs/engine.jsonl | python -m json.tool

# Find errors
grep '"level":"error"' data/logs/engine.jsonl
```

## Force CF Sync

If the CF Worker has `ADMIN_ENABLED=true`:

```bash
curl -X POST https://iil.sindromradiospb.workers.dev/api/v1/admin/cron/trigger \
  -H "x-admin-token: $ADMIN_SECRET_TOKEN"
```

Or run the local push directly (bypasses scheduler):

```python
import asyncio
from db.connection import get_db
from sync.cf_sync import CloudflareSync
from config.settings import Settings

async def push():
    s = Settings()
    syncer = CloudflareSync(s.cf_sync_url, s.cf_sync_token)
    async with get_db(s.database_path) as db:
        counters = await syncer.push_stories(db)
        print(f"pushed={counters.pushed} failed={counters.failed}")

asyncio.run(push())
```

## Reset / Recovery

**Reset a stuck story to draft:**
```sql
UPDATE stories SET state='draft', cf_synced_at=NULL WHERE story_id='...';
```

**Clear all pending FB queue items:**
```sql
DELETE FROM publish_queue WHERE status='pending' AND channel='fb';
```

**Force re-sync of all published stories:**
```sql
UPDATE stories SET cf_synced_at=NULL WHERE state='published';
```

**Release all editorial holds:**
```sql
UPDATE stories SET editorial_hold=0 WHERE editorial_hold=1;
```

## Run Tests

```bash
cd apps/local-engine
pytest tests/ -v
```

Expected: all tests green. Coverage target: 85%+.
