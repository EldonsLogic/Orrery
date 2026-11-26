"""Strict JSON reading for pack files (CMP-036): refuse duplicate keys and runaway nesting.

`json.loads` lets the last duplicate key win and raises RecursionError on deep nesting. A pack,
manifest or evidence file with either must be refused, never half-read. Every error is a ValueError.
"""

import json
from typing import Any


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    """Parse JSON text; raise ValueError on malformed JSON, duplicate keys or too-deep nesting."""
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except RecursionError as exc:
        raise ValueError("nesting too deep") from exc
