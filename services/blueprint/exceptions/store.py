"""Append-only JSON Lines store. One line per row, ids 1, 2, 3... in file order. `append` only ever adds a line at
the end (mode "a"); no function here rewrites, truncates or deletes. The register lives outside the repo."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import ExceptionsError
from .schema import MAX_LINE_BYTES
from .validate import validate_row

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_FILE_BYTES = 16 * 1024 * 1024


def _check_path(path: Any, must_exist: bool) -> Path:
    p = Path(path)
    if p.is_symlink():
        raise ExceptionsError("EXC-FILE-001", "register path is a symlink")
    r = p.resolve()
    if r == REPO_ROOT or REPO_ROOT in r.parents:
        raise ExceptionsError("EXC-FILE-001", "register must live outside the repo (private tenant record)")
    if r.exists() and not r.is_file():
        raise ExceptionsError("EXC-FILE-001", "register path is not a regular file")
    if must_exist and not r.exists():
        raise ExceptionsError("EXC-FILE-001", "register file does not exist")
    if not r.parent.is_dir():
        raise ExceptionsError("EXC-FILE-001", "register folder does not exist")
    return r


def read_rows(path: Any) -> list[dict]:
    """All rows in file order. A missing file is an empty register. Raises EXC-FILE-002 on a corrupt file."""
    p = _check_path(path, False)
    if not p.exists():
        return []
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ExceptionsError("EXC-FILE-002", "register file too large")
    rows: list[dict] = []
    try:
        data = p.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ExceptionsError("EXC-FILE-002", "register file unreadable") from None
    if data and not data.endswith("\n"):
        raise ExceptionsError("EXC-FILE-002", "register file does not end with a newline")
    for n, line in enumerate(data.split("\n")[:-1] if data else [], 1):
        try:
            row = json.loads(line)
        except ValueError:
            raise ExceptionsError("EXC-FILE-002", f"line {n}: not valid JSON") from None
        if not isinstance(row, dict) or row.get("id") != n:
            raise ExceptionsError("EXC-FILE-002", f"line {n}: not an object with id {n}")
        rows.append(row)
    return rows


def append(path: Any, row: Any) -> dict:
    """Validate `row`, then append it as one line. Returns the stored row (with its id). Nothing is written on a
    refusal. A correction is a new row with `corrects` set to a prior row id of the same tenant."""
    clean_row = validate_row(row)
    p = _check_path(path, False)
    existing = read_rows(p)
    if "corrects" in clean_row:
        target = next((r for r in existing if r["id"] == clean_row["corrects"]), None)
        if target is None or target["tenant"] != clean_row["tenant"]:
            raise ExceptionsError("EXC-ROW-003", "corrects: no earlier row of the same tenant with that id")
    stored = {"id": len(existing) + 1, **clean_row}
    line = json.dumps(stored, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if len(line.encode("utf-8")) > MAX_LINE_BYTES:
        raise ExceptionsError("EXC-ROW-002", f"row over {MAX_LINE_BYTES} bytes")
    fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as fh:
        fh.write(line.encode("utf-8"))
    return stored
