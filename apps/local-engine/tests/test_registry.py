"""tests/test_registry.py — Source registry loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sources.models import Source, Throttle
from sources.registry import get_enabled_sources, get_source_by_id, load_sources

REGISTRY_PATH = str(Path(__file__).parent.parent.parent.parent / "sources" / "registry.yaml")


def test_load_sources_real_registry():
    sources = load_sources(REGISTRY_PATH)
    assert len(sources) >= 7
    ids = {s.id for s in sources}
    assert "ynet_main" in ids
    assert "maariv_breaking" in ids


def test_all_sources_have_required_fields():
    sources = load_sources(REGISTRY_PATH)
    for s in sources:
        assert s.id
        assert s.name
        assert s.url.startswith("http")
        assert s.type in ("rss", "sitemap", "html")
        assert isinstance(s.enabled, bool)


def test_get_enabled_sources_filters_rss_only():
    sources = load_sources(REGISTRY_PATH)
    enabled = get_enabled_sources(sources)
    assert len(enabled) >= 6
    for s in enabled:
        assert s.enabled is True
        assert s.type == "rss"


def test_get_source_by_id_found():
    sources = load_sources(REGISTRY_PATH)
    s = get_source_by_id(sources, "ynet_main")
    assert s is not None
    assert s.id == "ynet_main"


def test_get_source_by_id_not_found():
    sources = load_sources(REGISTRY_PATH)
    assert get_source_by_id(sources, "nonexistent") is None


def test_throttle_defaults():
    s = Source(id="x", name="X", type="rss", url="https://x.com/", enabled=True)
    assert s.throttle.min_interval_sec == 10
    assert s.throttle.max_items_per_run == 30


def test_invalid_source_type_raises():
    with pytest.raises(Exception):
        Source(id="x", name="X", type="invalid_type", url="https://x.com/", enabled=True)
