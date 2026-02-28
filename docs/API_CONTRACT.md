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

- `code`: stable machine-readable code (see error code table below)
- `message`: short human-readable description
- `details`: optional object, safe for clients (no secrets, no internal stack traces)

**Error code table**

| HTTP status | `error.code` | When |
|-------------|-------------|------|
| 400 | `invalid_request` | Invalid query parameter (bad limit, bad cursor format) |
| 400 | `cron_disabled` | Admin cron trigger called but `CRON_ENABLED=false` |
| 403 | `forbidden` | Admin endpoint disabled (`ADMIN_ENABLED=false`) or missing/invalid `x-admin-token` header |
| 404 | `not_found` | Story not found, or unrecognized route |
| 500 | `internal_error` | Unhandled server error (DB failure, unexpected exception) |

**Error examples**

400 Bad Request:
```json
{
  "ok": false,
  "error": {
    "code": "invalid_request",
    "message": "Invalid limit parameter",
    "details": { "param": "limit", "value": "999", "max": 50 }
  }
}
```

403 Forbidden (token):
```json
{
  "ok": false,
  "error": {
    "code": "forbidden",
    "message": "Admin endpoints are disabled",
    "details": {}
  }
}
```

404 Not Found (story):
```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Story not found",
    "details": { "story_id": "01HZ..." }
  }
}
```

404 Not Found (route):
```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Not found",
    "details": { "path": "/api/v1/unknown" }
  }
}
```

500 Internal Error:
```json
{
  "ok": false,
  "error": {
    "code": "internal_error",
    "message": "An unexpected error occurred",
    "details": {}
  }
}
```

### 1.2 Pagination cursor

Cursor is an **opaque** string.
Clients must treat it as a token and must not parse or construct it.

**Encoding (internal — subject to change without notice):**
- Current implementation: base64url-encoded JSON `{"last_update_at":"<ISO8601>","story_id":"<id>"}`
- Clients must NOT rely on this format. Treat the cursor as a black box.
- Max cursor length: 500 characters (validate before storing client-side)

**Usage:**
- Request with cursor: `GET /api/v1/feed?cursor=<opaque>&limit=20`
- Response includes `next_cursor`: string (next page available) or `null` (no more pages)
- An empty page (`stories: []`) always has `next_cursor: null`

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
    "env": "dev|prod",
    "now_utc": "2026-02-27T08:00:00.000Z"
  },
  "last_run": {
    "run_id": "string",
    "started_at": "ISO8601",
    "finished_at": "ISO8601|null",
    "status": "success|partial_failure|failure",
    "sources_ok": 0,
    "sources_failed": 0,
    "items_found": 0,
    "items_new": 0,
    "stories_new": 0,
    "stories_updated": 0,
    "published_web": 0,
    "published_fb": 0,
    "errors_total": 0,
    "duration_ms": 0
  },
  "top_failing_sources": [
    { "source_id": "string", "error_count": 0 }
  ]
}
```

**Notes**
- `last_run` is `null` when no runs have occurred yet.
- `top_failing_sources` lists up to 5 sources with the most error events in the last 24 hours.

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

## 3) Admin endpoints (gated)

Admin endpoints require:
1. `ADMIN_ENABLED=true` (set in `wrangler.toml`)
2. `x-admin-token: <ADMIN_SECRET_TOKEN>` header (when `ADMIN_SECRET_TOKEN` secret is configured)

CORS: Admin endpoints emit `Access-Control-Allow-Origin: <PUBLIC_SITE_BASE_URL>` (not wildcard).
Preflight: `OPTIONS` requests to `/api/v1/admin/*` are handled with `204 No Content`.

**Auth errors:**
- 403 `forbidden`: `ADMIN_ENABLED=false` → `"Admin endpoints are disabled"`
- 403 `forbidden`: token mismatch/missing → `"Invalid or missing admin token"`

---

### 3.1 GET `/api/v1/admin/runs`
Returns last 20 cron run records.

**Response 200**
```json
{
  "ok": true,
  "data": {
    "runs": [
      {
        "run_id": "string",
        "started_at": "ISO8601",
        "finished_at": "ISO8601|null",
        "status": "success|partial_failure|failure",
        "sources_ok": 0,
        "sources_failed": 0,
        "items_found": 0,
        "items_new": 0,
        "stories_new": 0,
        "stories_updated": 0,
        "published_web": 0,
        "published_fb": 0,
        "errors_total": 0,
        "duration_ms": 0
      }
    ]
  }
}
```

---

### 3.2 GET `/api/v1/admin/errors?run_id=<id>`
Returns all error events for a specific run.

**Query params**
- `run_id` (required)

**Response 200**
```json
{
  "ok": true,
  "data": {
    "errors": [
      {
        "event_id": "string",
        "run_id": "string",
        "phase": "string",
        "source_id": "string|null",
        "story_id": "string|null",
        "code": "string|null",
        "message": "string|null",
        "created_at": "ISO8601"
      }
    ]
  }
}
```

**Errors**
- 400 `invalid_request`: `run_id` query param missing

---

### 3.3 GET `/api/v1/admin/drafts`
Returns draft stories pending editorial review plus aggregated counts.

**Response 200**
```json
{
  "ok": true,
  "data": {
    "drafts": [
      {
        "story_id": "string",
        "start_at": "ISO8601",
        "last_update_at": "ISO8601",
        "editorial_hold": 0,
        "item_count": 0,
        "title_sample": "string|null"
      }
    ],
    "counts": {
      "total": 0,
      "held": 0,
      "pending": 0
    }
  }
}
```

---

### 3.4 POST `/api/v1/admin/story/{story_id}/hold`
Sets `editorial_hold=1` on a draft story — prevents auto-publishing.

**Response 200**
```json
{
  "ok": true,
  "data": { "story_id": "string", "editorial_hold": 1 }
}
```

**Errors**
- 404 `not_found`: story not found or not in `draft` state

---

### 3.5 POST `/api/v1/admin/story/{story_id}/release`
Sets `editorial_hold=0` — allows auto-publishing to resume.

**Response 200**
```json
{
  "ok": true,
  "data": { "story_id": "string", "editorial_hold": 0 }
}
```

**Errors**
- 404 `not_found`: story not found

---

### 3.6 POST `/api/v1/admin/cron/trigger`
Triggers a manual ingest run outside the cron schedule.

**Notes:**
- Uses `ctx.waitUntil` — the Worker may terminate before the run completes.
- Reliable only for testing. Prefer the scheduled cron for production.
- Requires `CRON_ENABLED=true`.

**Response 200**
```json
{
  "ok": true,
  "message": "Cron run triggered. Check /api/v1/admin/runs in ~15s."
}
```

**Errors**
- 400 `cron_disabled`: `CRON_ENABLED` is not `"true"`

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
