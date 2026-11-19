"""Sanitising of untrusted text before it reaches the report (principle 7). Source text (item names, party,
sheet names, document numbers) and port text (error codes, record ids, metric and currency keys) are data:
control and bidirectional-format characters are stripped, length is capped, and codes and keys must match an
allow-list pattern. BPL-019 still renders every param as escaped data."""
from __future__ import annotations

import re
import unicodedata

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.:/\-]{1,140}$")
_BAD = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}  # controls, bidi and format marks, separators, unassigned


def clean_text(value, limit: int = 64) -> str:
    s = value if isinstance(value, str) else str(value)
    return "".join(ch for ch in s if unicodedata.category(ch) not in _BAD)[:limit]


def clean_obj(value, limit: int = 128):
    """Recursively clean strings (and dict keys) in report params."""
    if isinstance(value, str):
        return clean_text(value, limit)
    if isinstance(value, dict):
        return {clean_text(k, 64): clean_obj(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_obj(v, limit) for v in value]
    return value


def safe_code(value):
    """An error code from a port: a short snake_case token, else `unknown_error`; None stays None."""
    if not isinstance(value, str):
        return None
    return value if CODE_RE.fullmatch(value) else "unknown_error"
