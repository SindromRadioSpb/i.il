"""sources/models.py — Pydantic Source model matching TS SourceSchema."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class Throttle(BaseModel):
    min_interval_sec: int = 10
    max_items_per_run: int = 30


class Source(BaseModel):
    id: str
    name: str
    type: str  # rss | sitemap | html
    url: str
    lang: str = "he"
    enabled: bool
    throttle: Throttle = Throttle()
    category_hints: list[str] = []
    parser: dict[str, object] | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("rss", "sitemap", "html"):
            raise ValueError(f"Unknown source type: {v}")
        return v
