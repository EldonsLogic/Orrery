"""Refusals of the metrics package. Every refusal carries a stable `MET-` code; nothing partial is returned."""
from __future__ import annotations

CODES = {
    "MET-INPUT-001": "Blueprint root is not an object, or tenant/revision is not a string/integer",
    "MET-INPUT-002": "An element collection or an element is malformed (not a list of objects with a string id)",
    "MET-INPUT-003": "Duplicate element id inside one collection",
    "MET-INPUT-004": "The Blueprint cannot be diffed (not plain JSON data, or nested too deep)",
    "MET-AUTO-001": "The applied Blueprint has no countable elements (rate undefined)",
    "MET-REUSE-001": "Reuse input is malformed (tenant -> list of (component id, version) expected)",
    "MET-REUSE-002": "No component is in use (ratio undefined)",
    "MET-NEW-001": "Registry id collections are malformed (expected collections of non-empty string ids)",
}


class MetricsError(Exception):
    """Raised for every refusal. `code` is one of CODES."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
