"""Explicit mapping of DSC-011 extracted sheet cells to importer row dicts."""
from __future__ import annotations

import re

from .errors import ImportFailure
from .validation import bounded, fail, text


def from_tabular(sheet: dict, mapping: dict[str, str], *, max_rows=10_000) -> list[dict]:
    """Accept a real TabularConnector.extract sheet, preserving cell text exactly.

    Only explicit one-to-one header mappings are accepted. Refuse formulas even
    when their cached value looks numeric, all hidden content and metadata that
    requires owner decisions. Never use normalise's flattened model-facing text
    to reconstruct numeric source data.
    """
    try:
        bounded(sheet)
        if (not isinstance(sheet, dict) or sheet.get("type") != "sheet" or sheet.get("state") != "visible"
                or not isinstance(sheet.get("header_row"), int) or sheet["header_row"] < 1
                or sheet.get("hidden_rows") or sheet.get("hidden_cols") or sheet.get("comments")
                or sheet.get("external_links") or not isinstance(mapping, dict) or not mapping
                or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())
                or len(set(mapping.values())) != len(mapping)):
            fail()
        cells, header, rows, occupied = sheet["cells"], {}, {}, set()
        if not isinstance(cells, list) or len(cells) > 100_000:
            fail("IMP-LIMIT")
        for cell in cells:
            if cell.get("formula"):
                fail("IMP-FORMULA")
            if cell.get("hidden"):
                fail()
            match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", cell["ref"])
            if not match or cell["ref"] in occupied:
                fail()
            occupied.add(cell["ref"])
            column, row = match[1], int(match[2])
            value = cell["text"]
            if not isinstance(value, str):
                fail()
            if row == sheet["header_row"]:
                header[column] = text(value)
            elif row < sheet["header_row"]:
                fail()  # Do not silently discard preamble data.
            else:
                rows.setdefault(row, {})[column] = value
        if set(header.values()) != set(mapping) or len(set(header.values())) != len(header):
            fail()
        if len(rows) > max_rows:
            fail("IMP-LIMIT")
        result = []
        for row in sorted(rows):
            if set(rows[row]) - header.keys():
                fail()
            result.append({mapping[header[col]]: value for col, value in rows[row].items()})
        return result
    except ImportFailure:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        raise ImportFailure("IMP-SCHEMA") from None
