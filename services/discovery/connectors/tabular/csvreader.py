"""CSV bytes to cells. Encoding, delimiter and header row are decided by fixed rules."""
from __future__ import annotations

import csv
import io

from ..model import Budget, BudgetExceeded
from .common import detect_header_row, idx_to_col
from .errors import Tab001UnsupportedFormat, Tab006Malformed, Tab007Undecodable

DELIMS = (",", ";", "\t")
DELIM_NAMES = {",": "comma", ";": "semicolon", "\t": "tab"}


def decode(data: bytes):
    """BOM first (UTF-8, UTF-16), then strict UTF-8, then windows-1256 (Arabic exports)."""
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise Tab007Undecodable("UTF-32 is not supported")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8-sig"  # strict: a bad byte after a BOM is an error below
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            raise Tab007Undecodable("invalid UTF-16") from None
    if b"\x00" in data:
        raise Tab001UnsupportedFormat("binary content (NUL bytes) is not CSV")
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1256"), "windows-1256"
    except UnicodeDecodeError:
        raise Tab007Undecodable("not UTF-8, UTF-16 or windows-1256") from None


def sniff(text: str) -> str:
    """Score each candidate on the first 20 records: records matching the modal width (width > 1),
    then that width. Ties: comma, semicolon, tab."""
    best, best_score = ",", (0, 0)
    for d in DELIMS:
        widths = []
        try:
            for i, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=d)):
                if i >= 20:
                    break
                if row:
                    widths.append(len(row))
        except csv.Error:
            continue
        if not widths:
            continue
        modal = max(sorted(set(widths)), key=lambda w: (widths.count(w), w))
        score = (widths.count(modal), modal) if modal > 1 else (0, 0)
        if score > best_score:
            best, best_score = d, score
    return best


def read_csv(data: bytes, budget: Budget, max_rows: int, max_cols: int, max_cells: int) -> dict:
    text, enc = decode(data)
    budget.tick()
    delim = sniff(text)
    cells, rows_seen, ncells = [], {}, 0
    try:
        for rno, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delim), start=1):
            budget.tick()
            if rno > max_rows:
                raise BudgetExceeded("rows", max_rows)
            if len(row) > max_cols:
                raise BudgetExceeded("columns", max_cols)
            line = []
            for cno, v in enumerate(row, start=1):
                if v == "":
                    continue
                ncells += 1
                if ncells > max_cells:
                    raise BudgetExceeded("cells", max_cells)
                cells.append({"ref": f"{idx_to_col(cno)}{rno}", "text": v, "kind": "text", "formula": False,
                              "hidden": ""})
                line.append((v, "text"))
            if line:
                rows_seen[rno] = line
    except csv.Error as e:
        raise Tab006Malformed(f"csv: {e}") from None
    return {"type": "sheet", "name": "csv", "state": "visible", "encoding": enc,
            "delimiter": DELIM_NAMES[delim], "header_row": detect_header_row(rows_seen),
            "cells": cells, "comments": [], "hidden_rows": [], "hidden_cols": []}
