"""Refusals of the exceptions package. Every refusal carries a stable `EXC-` code; nothing partial is written."""
from __future__ import annotations

CODES = {
    "EXC-ROW-001": "Row is not an object, has unknown or missing columns, or a column has the wrong type",
    "EXC-ROW-002": "A column value is malformed (date, id, pointer, class) or free text is empty or too long",
    "EXC-ROW-003": "`corrects` does not point to an earlier row of the same tenant",
    "EXC-DATA-001": "Free text looks like personal data (email, phone number, long digit run)",
    "EXC-DATA-002": "Free text looks like a secret (credential in a URL, key-like string, secret assignment)",
    "EXC-FILE-001": "The register file path is not allowed (inside the repo, a symlink, or not a file)",
    "EXC-FILE-002": "The register file is corrupt or unreadable (bad JSON line, ids not sequential)",
    "EXC-IN-001": "Reconcile input is malformed (removals, tenant or revision)",
}


class ExceptionsError(Exception):
    """Raised for every refusal. `code` is one of CODES."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
