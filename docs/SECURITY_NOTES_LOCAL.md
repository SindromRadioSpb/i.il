# Security Notes: Local Engine

## Secrets Management

### What Is Secret

| Secret | Where stored | How used |
|--------|-------------|----------|
| `CF_SYNC_TOKEN` | `.env` (gitignored) | Bearer auth to CF Worker sync endpoint |
| `FB_PAGE_ACCESS_TOKEN` | `.env` (gitignored) | FB Graph API authentication |
| `FB_PAGE_ID` | `.env` (gitignored) | FB Graph API page identifier |
| `ADMIN_SECRET_TOKEN` | Cloudflare secret | Admin API gating |

### Rules

1. **Never commit `.env`** — it is in `.gitignore`
2. **Never log secrets** — see Log Redaction section below
3. **Rotate on leak** — if a token appears in logs or git history, rotate immediately
4. **CF_SYNC_TOKEN** — set via `wrangler secret put CF_SYNC_TOKEN`; never hardcoded in wrangler.toml
5. **FB token** — long-lived page access tokens expire every 60 days; monitor for 190/102 errors

### Checking for Leaked Secrets

```bash
# Check git history for token patterns
git log --all -p | grep -E "(Bearer|access_token|CF_SYNC|FB_PAGE)" | head -20

# Check .env is not tracked
git ls-files .env
# should return nothing
```

---

## Log Redaction

The structlog-based logger (`observe/logger.py`) does **not** automatically redact fields.
Code that logs HTTP requests must manually exclude headers:

```python
# GOOD — log only status, not headers
log.info("http_post", url=url, status=resp.status_code)

# BAD — leaks Authorization header
log.info("http_post", headers=headers, ...)
```

The `FacebookClient` and `CloudflareSync` classes do not log Authorization headers.
If you add new HTTP callers, follow this pattern.

**JSON log file** (`data/logs/engine.jsonl`) contains no secrets.
Rotating file handler: 10 MB × 5 files = max 50 MB.

---

## Network Security

### Outbound Only

The local engine makes outbound HTTP requests only:
- RSS feeds (8 sources over HTTPS)
- Ollama API (`localhost:11434` — loopback only)
- FB Graph API (`graph.facebook.com` over HTTPS)
- CF Worker sync endpoint (`workers.dev` over HTTPS)

### SSRF Protection

`validate_url_for_fetch()` in `ingest/normalize.py` blocks:
- Private IP ranges (10.x, 172.16–31.x, 192.168.x)
- Loopback (127.x, ::1)
- Link-local (169.254.x)
- Non-HTTP(S) schemes

All RSS feed URLs and article URLs pass through this validator before fetching.

### Ollama Endpoint

Ollama runs on `localhost:11434`. It is not exposed externally.
Do not change `OLLAMA_BASE_URL` to a non-localhost address without
appropriate network security controls.

---

## Data Handling

### Hebrew Content

Raw Hebrew article text (titles, snippets) is stored in SQLite and
is not privacy-sensitive — it originates from public RSS feeds.

### Russian Summaries

AI-generated Russian summaries are stored locally and pushed to Cloudflare D1.
They contain no personally identifiable information (PII).

### Images

Images are downloaded from public URLs and validated (format + size).
They are stored in `data/images/` which is gitignored.
No authentication credentials are stored alongside images.

---

## File Permissions (Windows)

Recommended permissions for sensitive files:

| Path | Recommended |
|------|-------------|
| `.env` | Owner read/write only |
| `data/news_hub.db` | Owner read/write only |
| `data/logs/` | Owner read/write only |
| `data/images/` | Owner read/write only |

---

## Dependency Security

Run `pip audit` periodically to check for known vulnerabilities:

```bash
pip install pip-audit
pip-audit
```

Key dependencies and their security posture:
- `httpx` — actively maintained, used for outbound HTTP
- `aiosqlite` — thin async wrapper over stdlib sqlite3
- `Pillow` — image validation; keep updated (frequent CVEs in image parsing)
- `beautifulsoup4` — HTML parsing of public pages only; no user input
- `feedparser` — RSS parsing of external feeds; sandboxed (no exec)
