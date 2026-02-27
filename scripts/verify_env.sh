#!/usr/bin/env bash
# scripts/verify_env.sh — Check local dev environment readiness.
# Verifies that key env vars are set for a coding session.
# This does NOT check Cloudflare secrets (those are wrangler-managed).
# Exit code 0 = ready; non-zero = missing required vars (print list).
set -euo pipefail

ERRORS=0
WARNINGS=0

require() {
  local var="$1"
  local desc="$2"
  if [ -z "${!var:-}" ]; then
    echo "MISSING (required): $var — $desc"
    ERRORS=$((ERRORS + 1))
  fi
}

warn_missing() {
  local var="$1"
  local desc="$2"
  if [ -z "${!var:-}" ]; then
    echo "WARNING (optional): $var — $desc"
    WARNINGS=$((WARNINGS + 1))
  fi
}

echo "== verify_env.sh: checking local dev environment =="
echo "   (source .env first if needed: export \$(grep -v '^#' .env | xargs))"
echo ""

# Load .env if present and not already loaded
if [ -f ".env" ] && [ -z "${_ENV_LOADED:-}" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  _ENV_LOADED=1
fi

# --- Required for basic local dev ---
require "PUBLIC_API_BASE_URL" "Worker API base URL for web (e.g. http://127.0.0.1:8787)"

# --- Required for Worker feature flags ---
require "CRON_ENABLED"         "Cron execution flag (true|false)"
require "FB_POSTING_ENABLED"   "Facebook posting flag (true|false)"
require "ADMIN_ENABLED"        "Admin endpoints flag (true|false; false in prod)"

# --- Optional: translation ---
warn_missing "TRANSLATION_PROVIDER" "Translation backend: google|deepl|none (default: google)"
warn_missing "GOOGLE_CLOUD_PROJECT_ID" "GCP project (required if TRANSLATION_PROVIDER=google)"
warn_missing "GOOGLE_CLOUD_LOCATION"   "GCP translate location (default: global)"

# --- Optional: Facebook ---
warn_missing "FACEBOOK_PAGE_ID"  "Facebook Page ID (required if FB_POSTING_ENABLED=true)"
warn_missing "FACEBOOK_APP_ID"   "Facebook App ID (optional metadata)"

# --- Secrets (not in .env — just check if they would be needed) ---
if [ "${FB_POSTING_ENABLED:-false}" = "true" ]; then
  if [ -z "${FACEBOOK_PAGE_ACCESS_TOKEN:-}" ]; then
    echo "WARNING: FACEBOOK_PAGE_ACCESS_TOKEN not set in env — required when FB_POSTING_ENABLED=true"
    echo "         For Cloudflare, set via: pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

if [ "${ADMIN_ENABLED:-false}" = "true" ]; then
  if [ -z "${ADMIN_SHARED_SECRET:-}" ]; then
    echo "WARNING: ADMIN_SHARED_SECRET not set — required when ADMIN_ENABLED=true"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# --- Tuning (all have defaults, just informational) ---
echo ""
echo "Tuning vars (defaults used if not set):"
echo "  CRON_INTERVAL_MIN      = ${CRON_INTERVAL_MIN:-10 (default)}"
echo "  MAX_NEW_ITEMS_PER_RUN  = ${MAX_NEW_ITEMS_PER_RUN:-25 (default)}"
echo "  SUMMARY_TARGET_MIN     = ${SUMMARY_TARGET_MIN:-400 (default)}"
echo "  SUMMARY_TARGET_MAX     = ${SUMMARY_TARGET_MAX:-700 (default)}"

echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "== verify_env.sh: $ERRORS REQUIRED VAR(S) MISSING — copy .env.example to .env and fill in values =="
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "== verify_env.sh: READY (with $WARNINGS warning(s) — optional vars not set) =="
  exit 0
else
  echo "== verify_env.sh: READY (all vars set) =="
  exit 0
fi
