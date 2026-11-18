"""Row validation. `validate_row(row)` returns a new, cleaned dict (the input is never modified) or raises
ExceptionsError. Refuses rather than redacts: a row with personal data or a secret is never stored."""
from __future__ import annotations

import datetime
import re
from typing import Any

from .errors import ExceptionsError
from .sanitize import clean, scan
from .schema import (ALL_COLUMNS, CLASSES, ID_COLUMNS, MAX_ID, MAX_POINTER, OPTIONAL, REQUIRED, TEXT_COLUMNS)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]*")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _str(row: dict, col: str) -> str:
    v = row[col]
    if col == "blueprint_rev" and isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        v = str(v)
    if not isinstance(v, str):
        raise ExceptionsError("EXC-ROW-001", f"{col}: must be a string")
    return v


def validate_row(row: Any) -> dict:
    if not isinstance(row, dict):
        raise ExceptionsError("EXC-ROW-001", "row is not an object")
    extra = sorted(str(k) for k in row if k not in ALL_COLUMNS or k == "id")
    if extra:
        raise ExceptionsError("EXC-ROW-001", f"unknown or reserved columns: {', '.join(extra)[:80]}")
    missing = [c for c in REQUIRED if c not in row]
    if missing:
        raise ExceptionsError("EXC-ROW-001", f"missing columns: {', '.join(missing)}")
    out: dict[str, Any] = {}

    d = _str(row, "date")
    if not _DATE.fullmatch(d):
        raise ExceptionsError("EXC-ROW-002", "date: expected YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(d)
    except ValueError:
        raise ExceptionsError("EXC-ROW-002", "date: not a real calendar date") from None
    out["date"] = d

    for col in ID_COLUMNS:
        v = clean(_str(row, col))
        if not v or len(v) > MAX_ID or not _ID.fullmatch(v):
            raise ExceptionsError("EXC-ROW-002", f"{col}: expected 1-{MAX_ID} characters of letters, digits, . _ : -")
        scan(v, col)
        out[col] = v

    p = _str(row, "element_pointer")
    pc = clean(p)
    if pc != p or not pc.startswith("/") or len(pc) > MAX_POINTER or " " in pc:
        raise ExceptionsError("EXC-ROW-002", f"element_pointer: expected a pointer starting with / (no spaces or "
                                             f"control characters, up to {MAX_POINTER} characters)")
    scan(pc.replace("/", " "), "element_pointer")
    out["element_pointer"] = pc

    cls = _str(row, "class")
    if cls not in CLASSES:
        raise ExceptionsError("EXC-ROW-002", f"class: must be one of {', '.join(CLASSES)}")
    out["class"] = cls

    for col, limit in TEXT_COLUMNS.items():
        if col not in row or (col in OPTIONAL and row[col] is None):
            continue
        v = _str(row, col)
        if len(v) > limit * 4:   # bound the work on hostile input before cleaning
            raise ExceptionsError("EXC-ROW-002", f"{col}: over {limit} characters")
        v = clean(v)
        if not v:
            raise ExceptionsError("EXC-ROW-002", f"{col}: empty")
        if len(v) > limit:
            raise ExceptionsError("EXC-ROW-002", f"{col}: over {limit} characters")
        scan(v, col)
        out[col] = v

    if row.get("corrects") is not None:
        c = row["corrects"]
        if isinstance(c, bool) or not isinstance(c, int) or c < 1:
            raise ExceptionsError("EXC-ROW-001", "corrects: must be a positive integer row id")
        out["corrects"] = c
    return out
