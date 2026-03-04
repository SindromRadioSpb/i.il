"""summary/json_utils.py — JSON parsing helpers for imperfect LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def extract_first_json_region(raw: str) -> str:
    """Extract the first JSON object/array region from arbitrary text.

    Supports:
      - fenced markdown blocks (```json ... ```)
      - leading/trailing prose around JSON payload
      - nested braces inside JSON strings
    """
    block = _JSON_BLOCK_RE.search(raw)
    if block:
        return block.group(1).strip()

    start_obj = raw.find("{")
    start_arr = raw.find("[")

    candidates = [i for i in (start_obj, start_arr) if i >= 0]
    if not candidates:
        raise ValueError("No JSON object or array start found")

    start = min(candidates)
    open_char = raw[start]
    close_char = "}" if open_char == "{" else "]"

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(raw)):
        ch = raw[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == open_char:
            depth += 1
            continue

        if ch == close_char:
            depth -= 1
            if depth == 0:
                return raw[start : idx + 1].strip()

    raise ValueError("JSON region appears truncated")


def parse_json_output(raw: str, *, allow_extractor: bool = True) -> Any:
    """Parse JSON from model output with optional extractor fallback."""
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if not allow_extractor:
            raise

    extracted = extract_first_json_region(raw)
    return json.loads(extracted)


def build_json_retry_instruction() -> str:
    """Instruction appended on retry when model returned invalid JSON."""
    return "Return ONLY valid JSON, no prose, no markdown fences."
