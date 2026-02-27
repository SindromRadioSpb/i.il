# docs/API_CONTRACT.md — Worker Public API (v1)

This document defines the authoritative API contract for the Cloudflare Worker.
The web frontend and any external clients must rely on this contract.

Principles:
- Read-only endpoints are public and must not expose secrets.
- Responses are stable and versioned (v1).
- Pagination uses an opaque cursor.
- All timestamps are ISO 8601 strings in UTC (`YYYY-MM-DDTHH:mm:ss.sssZ`).

Base path:
- Production: `https://<worker-domain>/api/v1`
- Local dev: `http://127.0.0.1:8787/api/v1`

---

## 1) Common types

### 1.1 Error response
```json
{
  "ok": false,
  "error": {
    "code": "string",
    "message": "string",
    "details": { "any": "json" }
  }
}
```

- `code`: stable machine-readable code
- `message`: short human-readable
- `details`: optional, safe for clients (no secrets)

### 1.2 Pagination cursor
Cursor is an opaque string.
Clients must treat it as a token and not parse it.

- Request: `cursor=<opaque>`
- Response: `next_cursor=<opaque|null>`

---

## 2) Public endpoints (read-only)

### 2.1 GET `/api/v1/health`
Returns safe operational summary.

**Response 200**
```json
{
  "ok": true,
  "service": {
    "name": "news-hub",
    "version": "string",
    "env": "dev|staging|prod",
    "now_utc": "2026-02-27T08:00:00.000Z"
  },
  "last_run": {
    "run_id": "string|null",
    "started_at": "ISO8601|null",
    "finished_at": "ISO8601|null",
    "status": "success|partial_failure|failure|null",
    "counters": {
      "sources_ok": 0,
      "sources_failed": 0,
      "items_found": 0,
      "items_new": 0,
      "stories_new": 0,
      "stories_updated": 0,
      "published_web": 0,
      "published_fb": 0,
      "errors_total": 0
    },
    "duration_ms": 0
  }
}
```

**Errors**
- 500: returns standard error response with code `internal_error`

---

### 2.2 GET `/api/v1/feed`
Returns a paginated list of published stories, ordered by `last_update_at desc`.

**Query**
- `limit` (optional, default 20, max 50)
- `cursor` (optional)

**Response 200**
```json
{
  "ok": true,
  "data": {
    "stories": [
      {
        "story_id": "string",
        "canonical_url": "string",
        "title_ru": "string",
        "summary_excerpt_ru": "string",
        "category": "politics|security|economy|society|tech|health|culture|sport|weather|other",
        "risk_level": "low|medium|high",
        "source_count": 0,
        "start_at": "ISO8601",
        "last_update_at": "ISO8601",
        "updated_label_ru": "string|null"
      }
    ],
    "next_cursor": "string|null"
  }
}
```

**Notes**
- `summary_excerpt_ru` is truncated to ~200–300 chars for feed readability.
- `updated_label_ru` optional (e.g., “Обновлено: 12:40”).

**Errors**
- 400: invalid limit/cursor → `invalid_request`
- 500: `internal_error`

---

### 2.3 GET `/api/v1/story/{story_id}`
Returns full story details.

**Path params**
- `story_id`: string (opaque id)

**Response 200**
```json
{
  "ok": true,
  "data": {
    "story": {
      "story_id": "string",
      "canonical_url": "string",
      "title_ru": "string",
      "summary_ru": "string",
      "category": "politics|security|economy|society|tech|health|culture|sport|weather|other",
      "risk_level": "low|medium|high",
      "start_at": "ISO8601",
      "last_update_at": "ISO8601",
      "sources": [
        {
          "source_id": "string",
          "name": "string",
          "url": "string"
        }
      ],
      "timeline": [
        {
          "item_id": "string",
          "source_id": "string",
          "title_he": "string",
          "url": "string",
          "published_at": "ISO8601|null",
          "updated_at": "ISO8601|null"
        }
      ]
    }
  }
}
```

**Errors**
- 404: story not found → `not_found`
- 500: `internal_error`

---

## 3) Admin endpoints (dev-only, gated)

These endpoints MUST be disabled by default in production and require auth when enabled.

Auth mechanism (default):
- `ADMIN_ENABLED=true`
- `X-Admin-Secret: <ADMIN_SHARED_SECRET>`

### 3.1 POST `/api/v1/admin/cron/run`
Triggers a manual ingest run (dev only).

**Response 200**
```json
{
  "ok": true,
  "data": { "run_id": "string" }
}
```

**Errors**
- 401: missing/invalid admin secret → `unauthorized`
- 403: admin disabled → `forbidden`
- 500: `internal_error`

---

### 3.2 POST `/api/v1/admin/story/{story_id}/rebuild`
Rebuilds summary for a story (dev only).

**Response 200**
```json
{
  "ok": true,
  "data": { "story_id": "string", "summary_version": 1 }
}
```

**Errors**
- 401/403 as above
- 404: story not found
- 500: internal

---

## 4) Versioning policy

- Breaking changes require bump to `/api/v2`.
- v1 must remain backward compatible:
  - fields can be added
  - new enum values require fallback behavior in clients
  - existing fields must not change meaning

---

## 5) Security constraints for API

- No secrets or tokens in any response.
- No raw full article bodies returned.
- All user inputs (limit/cursor/story_id) validated.
- Queries must be parameterized.
