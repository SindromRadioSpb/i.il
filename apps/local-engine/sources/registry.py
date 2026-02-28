"""sources/registry.py — Load sources from registry.yaml."""

from __future__ import annotations

import yaml

from sources.models import Source


def load_sources(path: str) -> list[Source]:
    """Load and validate all sources from the YAML registry."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    sources = data.get("sources", [])
    result: list[Source] = []
    for raw in sources:
        try:
            result.append(Source.model_validate(raw))
        except Exception as exc:
            raise ValueError(f"Invalid source definition {raw.get('id', '?')}: {exc}") from exc
    return result


def get_enabled_sources(sources: list[Source]) -> list[Source]:
    """Return only sources with enabled=True and type='rss'."""
    return [s for s in sources if s.enabled and s.type == "rss"]


def get_source_by_id(sources: list[Source], source_id: str) -> Source | None:
    for s in sources:
        if s.id == source_id:
            return s
    return None
