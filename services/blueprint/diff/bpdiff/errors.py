"""Error type and the stable error codes of the Blueprint diff."""
from __future__ import annotations

CODES = {
    "BPD-INPUT-001": "Blueprint nesting deeper than 64 levels",
    "BPD-INPUT-002": "Blueprint holds a value that is not plain JSON data",
    "BPD-INPUT-003": "Blueprint root is not an object",
    "BPD-BASE-001": "The diff was made against a different base revision (hash mismatch)",
    "BPD-APPLY-001": "An operation does not fit the document (missing path, key clash, stale value)",
    "BPD-APPLY-002": "The result does not match the target hash recorded in the diff",
    "BPD-DIFF-001": "The diff object is malformed",
}


class BpdError(Exception):
    """Raised for every refusal. `code` is one of CODES; nothing partial is ever returned."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
