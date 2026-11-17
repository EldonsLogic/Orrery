"""Shared helpers: cell classification, header rule, A1 references."""
from __future__ import annotations

import re

# Plain numbers (ASCII, Arabic-Indic or Persian digits, separators, exponent) are data, not formulas.
_NUM = re.compile(r"^[+-]?\d[\d.,٫٬]*([eE][+-]?\d+)?$")
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
HEADER_SCAN_ROWS = 10


def looks_numeric(s: str) -> bool:
    return bool(_NUM.match(s.strip()))


def formula_like(s: str) -> bool:
    """Text a spreadsheet application could evaluate if re-exported. Flag only, never evaluate."""
    return bool(s) and s[0] in FORMULA_STARTS and not looks_numeric(s)


def col_to_idx(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def idx_to_col(i: int) -> str:
    out = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


_REF = re.compile(r"^([A-Z]{1,3})([0-9]{1,7})$")


def split_ref(ref: str):
    m = _REF.match(ref)
    return (col_to_idx(m.group(1)), int(m.group(2))) if m else None


def detect_header_row(rows: dict) -> int:
    """rows: {row_number: [(text, kind)]} in order. Rule: among the first 10 non-empty rows, the
    first whose cells are all non-numeric text and at least half as many as the widest of them.
    Returns the row number, or 0 for none. Deterministic, no model."""
    cand = [(r, cells) for r, cells in list(rows.items())[:HEADER_SCAN_ROWS] if cells]
    if not cand:
        return 0
    widest = max(len(c) for _, c in cand)
    for r, cells in cand:
        if len(cells) * 2 >= widest and all(k == "text" and not looks_numeric(t) for t, k in cells):
            return r
    return 0
