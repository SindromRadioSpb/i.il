"""ingest/normalize.py — URL normalization and SSRF guard.

IMPORTANT: normalize_url() must produce output IDENTICAL to the TypeScript
implementation in apps/worker/src/normalize/url.ts. The item_key is computed
as sha256(normalized_url) and must match across Python and Worker for the
Cloudflare sync to work correctly (INSERT OR REPLACE by story_id + item_key).

Reference: apps/worker/src/normalize/url.ts
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import (
    SplitResult,
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

# Tracking parameters stripped during normalization — identical to TS list.
TRACKING_PARAMS: frozenset[str] = frozenset(
    [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_source_platform",
        "utm_creative_format",
        "utm_marketing_tactic",
        "fbclid",
        "gclid",
        "msclkid",
        "twclid",
        "igshid",
        "ref",
        "_ga",
        "mc_cid",
        "mc_eid",
    ]
)

# IPv4 private / loopback ranges — identical logic to TS PRIVATE_IP_RE.
_PRIVATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^127\."),
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^0\."),
]


def validate_url_for_fetch(url: str) -> None:
    """SSRF guard: raise ValueError if the URL is unsafe to fetch.

    Blocks non-http(s) schemes, localhost, 0.0.0.0, IPv6 loopback,
    and private IPv4 ranges. Identical to TS validateUrlForFetch().

    Raises:
        ValueError: with a message matching the TS error messages for
                    compatibility with existing test assertions.
    """
    try:
        parsed: SplitResult = urlsplit(url)
    except Exception:
        raise ValueError(f"Invalid URL: {url}")

    if not parsed.scheme:
        raise ValueError(f"Invalid URL: {url}")

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {scheme}:")

    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    host = parsed.hostname or ""
    host_lower = host.lower()

    if host_lower in ("localhost", "0.0.0.0"):
        raise ValueError(f"Disallowed URL host: {host_lower}")

    # IPv6 loopback
    if host_lower in ("::1", "[::1]"):
        raise ValueError(f"Disallowed private IP: {host_lower}")

    for pattern in _PRIVATE_PATTERNS:
        if pattern.match(host_lower):
            raise ValueError(f"Disallowed private IP: {host_lower}")


def normalize_url(raw_url: str) -> str:
    """Normalize a URL for stable deduplication.

    Operations (identical to TS normalizeUrl()):
    - Strip leading/trailing whitespace
    - Lowercase scheme + host
    - Strip fragment (#...)
    - Strip tracking query params (TRACKING_PARAMS set)
    - Sort remaining query params for stability
    - Strip trailing slash from non-root paths

    For invalid URLs: return lowercased, trimmed original (fallback).
    """
    raw = raw_url.strip()
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            raise ValueError("not a url")
    except Exception:
        return raw.lower()

    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    port_str = f":{parts.port}" if parts.port else ""
    netloc = host + port_str

    # Strip tracking params, sort remaining
    params = parse_qsl(parts.query, keep_blank_values=True)
    filtered = sorted(
        [(k, v) for k, v in params if k.lower() not in TRACKING_PARAMS]
    )
    new_query = urlencode(filtered)

    # Strip trailing slash from non-root paths
    path = parts.path
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    normalized = urlunsplit((scheme, netloc, path, new_query, ""))
    return normalized


def hash_hex(data: str) -> str:
    """SHA-256 hex digest of a UTF-8 string. Synchronous (no async needed in Python)."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
