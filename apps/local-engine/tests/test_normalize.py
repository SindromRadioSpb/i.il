"""tests/test_normalize.py — URL normalization tests (port from url_normalization.test.ts)."""

from __future__ import annotations

import pytest

from ingest.normalize import hash_hex, normalize_url, validate_url_for_fetch


# ─────────────────────────────────────────────────────────────────────────────
# normalize_url — port of all 8 TS test cases + additional Python-specific
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_strips_utm_tracking_params(self):
        result = normalize_url("https://example.com/path?utm_source=rss&utm_medium=feed&keep=1")
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "keep=1" in result

    def test_strips_fbclid_and_gclid(self):
        result = normalize_url("https://example.com/p?fbclid=abc&gclid=xyz&id=5")
        assert "fbclid" not in result
        assert "gclid" not in result
        assert "id=5" in result

    def test_sorts_remaining_params_for_stability(self):
        a = normalize_url("https://example.com/?z=1&a=2")
        b = normalize_url("https://example.com/?a=2&z=1")
        assert a == b

    def test_lowercases_scheme_and_hostname(self):
        result = normalize_url("HTTPS://WWW.Example.COM/path")
        assert result.startswith("https://www.example.com/")

    def test_strips_fragment(self):
        result = normalize_url("https://example.com/path#section")
        assert "#" not in result

    def test_strips_trailing_slash_from_non_root(self):
        assert normalize_url("https://example.com/news/") == "https://example.com/news"

    def test_preserves_root_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_returns_lowercased_original_for_invalid_url(self):
        assert normalize_url("not-a-url") == "not-a-url"

    def test_strips_all_utm_variants(self):
        url = (
            "https://example.com/?utm_source=x&utm_medium=y&utm_campaign=z"
            "&utm_term=t&utm_content=c&utm_id=1"
        )
        result = normalize_url(url)
        for param in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id"]:
            assert param not in result

    def test_strips_msclkid_twclid_igshid(self):
        result = normalize_url("https://example.com/?msclkid=a&twclid=b&igshid=c&id=1")
        assert "msclkid" not in result
        assert "twclid" not in result
        assert "igshid" not in result
        assert "id=1" in result

    def test_strips_ref_param(self):
        result = normalize_url("https://example.com/?ref=rss&id=5")
        assert "ref" not in result
        assert "id=5" in result

    def test_real_ynet_url(self):
        raw = "https://www.ynet.co.il/news/article/abcd1234?utm_source=rss&utm_medium=feed"
        result = normalize_url(raw)
        assert "utm_source" not in result
        assert "ynet.co.il" in result

    def test_idempotent(self):
        url = "https://example.com/path?a=1&b=2"
        assert normalize_url(normalize_url(url)) == normalize_url(url)


# ─────────────────────────────────────────────────────────────────────────────
# validate_url_for_fetch — SSRF guard (port of all 13 TS test cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateUrlForFetch:
    def test_allows_https(self):
        validate_url_for_fetch("https://example.com/rss")  # no raise

    def test_allows_http(self):
        validate_url_for_fetch("http://example.com/rss")  # no raise

    def test_throws_for_file_scheme(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            validate_url_for_fetch("file:///etc/passwd")

    def test_throws_for_ftp_scheme(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            validate_url_for_fetch("ftp://example.com/")

    def test_throws_for_localhost(self):
        with pytest.raises(ValueError, match="Disallowed URL host"):
            validate_url_for_fetch("http://localhost/admin")

    def test_throws_for_0_0_0_0(self):
        with pytest.raises(ValueError, match="Disallowed URL host"):
            validate_url_for_fetch("http://0.0.0.0/")

    def test_throws_for_ipv6_loopback(self):
        with pytest.raises(ValueError, match="Disallowed private IP"):
            validate_url_for_fetch("http://[::1]/")

    def test_throws_for_127_loopback(self):
        with pytest.raises(ValueError, match="Disallowed private IP"):
            validate_url_for_fetch("http://127.0.0.1/")

    def test_throws_for_10_x_private(self):
        with pytest.raises(ValueError, match="Disallowed private IP"):
            validate_url_for_fetch("http://10.0.0.1/")

    def test_throws_for_192_168_private(self):
        with pytest.raises(ValueError, match="Disallowed private IP"):
            validate_url_for_fetch("http://192.168.1.1/")

    def test_throws_for_172_16_private(self):
        with pytest.raises(ValueError, match="Disallowed private IP"):
            validate_url_for_fetch("http://172.16.0.1/")

    def test_allows_172_15_public(self):
        validate_url_for_fetch("http://172.15.0.1/")  # no raise

    def test_throws_for_invalid_url_string(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            validate_url_for_fetch("not a url")


# ─────────────────────────────────────────────────────────────────────────────
# hash_hex
# ─────────────────────────────────────────────────────────────────────────────

class TestHashHex:
    def test_returns_64_char_hex(self):
        result = hash_hex("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert hash_hex("test") == hash_hex("test")

    def test_different_inputs_different_hashes(self):
        assert hash_hex("abc") != hash_hex("def")

    def test_known_value(self):
        # sha256("") = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
        assert hash_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
