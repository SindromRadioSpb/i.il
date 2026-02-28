"""tests/test_fb_publish.py — FacebookClient unit tests with mocked httpx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from publish.facebook import FBAuthError, FBError, FacebookClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _mock_client(body: dict, status: int = 200) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json = MagicMock(return_value=body)
    response.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


def _fb_client(page_id: str = "12345", token: str = "tok") -> FacebookClient:
    return FacebookClient(page_id=page_id, page_access_token=token)


# ─────────────────────────────────────────────────────────────────────────────
# post_text
# ─────────────────────────────────────────────────────────────────────────────


async def test_post_text_returns_post_id():
    client = _mock_client({"id": "12345_67890"})
    post_id = await _fb_client().post_text("Hello world", client=client)
    assert post_id == "12345_67890"


async def test_post_text_sends_to_feed_endpoint():
    client = _mock_client({"id": "1_2"})
    await _fb_client(page_id="99999").post_text("msg", client=client)
    url = client.post.call_args.args[0]
    assert "99999/feed" in url


async def test_post_text_includes_message_and_token():
    client = _mock_client({"id": "1_2"})
    await _fb_client(token="my_tok").post_text("Test message", client=client)
    payload = client.post.call_args.kwargs["json"]
    assert payload["message"] == "Test message"
    assert payload["access_token"] == "my_tok"


async def test_post_text_uses_base_url():
    fb = FacebookClient("p", "t", base_url="https://graph.facebook.com/v21.0")
    client = _mock_client({"id": "1"})
    await fb.post_text("msg", client=client)
    url = client.post.call_args.args[0]
    assert url.startswith("https://graph.facebook.com/v21.0/")


async def test_post_text_raises_fb_auth_error_on_190():
    body = {"error": {"code": 190, "message": "Invalid OAuth access token"}}
    client = _mock_client(body)
    with pytest.raises(FBAuthError) as exc_info:
        await _fb_client().post_text("msg", client=client)
    assert exc_info.value.code == 190


async def test_post_text_raises_fb_auth_error_on_102():
    body = {"error": {"code": 102, "message": "Session expired"}}
    client = _mock_client(body)
    with pytest.raises(FBAuthError):
        await _fb_client().post_text("msg", client=client)


async def test_post_text_raises_fb_error_on_other_code():
    body = {"error": {"code": 200, "message": "Permissions error"}}
    client = _mock_client(body)
    with pytest.raises(FBError) as exc_info:
        await _fb_client().post_text("msg", client=client)
    assert exc_info.value.code == 200
    assert not isinstance(exc_info.value, FBAuthError)


async def test_post_text_raises_on_http_error():
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=response)
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    with pytest.raises(httpx.HTTPStatusError):
        await _fb_client().post_text("msg", client=client)


# ─────────────────────────────────────────────────────────────────────────────
# post_photo
# ─────────────────────────────────────────────────────────────────────────────


async def test_post_photo_returns_post_id(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal fake JPEG header
    client = _mock_client({"post_id": "12345_99999"})
    post_id = await _fb_client().post_photo("Caption", img, client=client)
    assert post_id == "12345_99999"


async def test_post_photo_falls_back_to_id_field(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)
    client = _mock_client({"id": "12345_77777"})
    post_id = await _fb_client().post_photo("cap", img, client=client)
    assert post_id == "12345_77777"


async def test_post_photo_sends_to_photos_endpoint(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)
    client = _mock_client({"post_id": "1_2"})
    await _fb_client(page_id="54321").post_photo("cap", img, client=client)
    url = client.post.call_args.args[0]
    assert "54321/photos" in url


async def test_post_photo_sends_multipart_source_field(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)
    client = _mock_client({"post_id": "1_2"})
    await _fb_client().post_photo("caption text", img, client=client)
    call_kwargs = client.post.call_args.kwargs
    assert "files" in call_kwargs
    files = call_kwargs["files"]
    assert "source" in files


async def test_post_photo_raises_fb_auth_error(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)
    body = {"error": {"code": 190, "message": "Invalid token"}}
    client = _mock_client(body)
    with pytest.raises(FBAuthError):
        await _fb_client().post_photo("cap", img, client=client)
