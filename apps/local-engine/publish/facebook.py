"""publish/facebook.py — Facebook Graph API client.

Supports text posts (/{page_id}/feed) and photo posts (/{page_id}/photos).
Auth errors (codes 190, 102) raise FBAuthError — callers should treat these
as circuit-breakers and stop all further posting attempts immediately.
"""

from __future__ import annotations

from pathlib import Path

import httpx


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

_AUTH_ERROR_CODES: frozenset[int] = frozenset({102, 190})


class FBError(Exception):
    """Generic Facebook Graph API error."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.fb_message = message
        super().__init__(f"FB error {code}: {message}")


class FBAuthError(FBError):
    """Auth error — invalid/expired token. Must stop all posting immediately."""


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────


class FacebookClient:
    """Async FB Graph API client.  Injectable httpx.AsyncClient for testing."""

    def __init__(
        self,
        page_id: str,
        page_access_token: str,
        base_url: str = "https://graph.facebook.com/v21.0",
    ) -> None:
        self.page_id = page_id
        self._token = page_access_token
        self._base = base_url.rstrip("/")

    def _raise_for_fb_error(self, data: dict) -> None:
        """Raise FBAuthError or FBError if the response contains an error object."""
        if "error" not in data:
            return
        err = data["error"]
        code = int(err.get("code", 0))
        msg = str(err.get("message", "Unknown FB error"))
        if code in _AUTH_ERROR_CODES:
            raise FBAuthError(code, msg)
        raise FBError(code, msg)

    async def post_text(
        self,
        message: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Post a text-only update to the page feed. Returns the post_id."""
        url = f"{self._base}/{self.page_id}/feed"
        payload = {"message": message, "access_token": self._token}

        async def _post(c: httpx.AsyncClient) -> str:
            resp = await c.post(url, json=payload)
            resp.raise_for_status()
            data: dict = resp.json()
            self._raise_for_fb_error(data)
            return str(data["id"])

        if client is None:
            async with httpx.AsyncClient(timeout=30) as c:
                return await _post(c)
        return await _post(client)

    async def post_photo(
        self,
        message: str,
        image_path: str | Path,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Upload a photo with caption. Returns the post_id."""
        url = f"{self._base}/{self.page_id}/photos"
        image_path = Path(image_path)

        async def _post(c: httpx.AsyncClient) -> str:
            with open(image_path, "rb") as fh:
                resp = await c.post(
                    url,
                    data={"caption": message, "access_token": self._token},
                    files={"source": (image_path.name, fh, "image/jpeg")},
                )
            resp.raise_for_status()
            body: dict = resp.json()
            self._raise_for_fb_error(body)
            # Photos endpoint returns post_id or id
            return str(body.get("post_id") or body.get("id") or "")

        if client is None:
            async with httpx.AsyncClient(timeout=60) as c:
                return await _post(c)
        return await _post(client)
