"""The tier 2 (file upload) tabular connector: CSV and .xlsx. Read-only; nothing is evaluated."""
from __future__ import annotations

from ..model import Budget, Registry
from .common import formula_like
from .csvreader import read_csv
from .errors import Tab001UnsupportedFormat
from .xlsx import read_xlsx

ISSUE_CAP = 200  # per code per sheet; the rest is counted in stats
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class TabularConnector:
    id = "discovery.tabular"
    version = "0.1.0"
    tier = 2
    writes = False
    capabilities = frozenset({"read", "parse"})

    def __init__(self, max_rows: int = 50_000, max_cols: int = 256, max_cells: int = 200_000,
                 max_sheets: int = 100):
        self.max_rows, self.max_cols, self.max_cells, self.max_sheets = max_rows, max_cols, max_cells, max_sheets

    def extract(self, source: bytes, budget: Budget) -> list:
        budget.tick()
        if source.startswith(OLE_MAGIC):
            raise Tab001UnsupportedFormat("legacy .xls or encrypted Office file; save as .xlsx or CSV")
        if source.startswith(b"PK"):
            return read_xlsx(source, budget, self.max_rows, self.max_cols, self.max_cells, self.max_sheets)
        if source.lstrip()[:5] in (b"%PDF-", b"{\\rtf") or source[:4] in (b"\x89PNG", b"GIF8", b"\xff\xd8\xff\xe0"):
            raise Tab001UnsupportedFormat("not a tabular file")
        return [read_csv(source, budget, self.max_rows, self.max_cols, self.max_cells)]

    def normalise(self, raw: list, budget: Budget) -> dict:
        entities, issues = [], []
        st = {k: 0 for k in ("sheets", "cells", "formulas", "formula_like", "hidden_sheets", "hidden_rows",
                             "hidden_cells", "comments", "defined_names", "header_rows", "external_links",
                             "issues_omitted")}

        def issue(sev, code, detail):
            issues.append({"severity": sev, "code": code, "detail": detail})

        for item in raw:
            budget.tick()
            if item["type"] == "workbook":
                if item["external_links"]:
                    st["external_links"] += 1
                    issue("warn", "external_link", "workbook references external content; never fetched")
                fields = []
                for nm in item["names"]:
                    st["defined_names"] += 1
                    f = {"path": f"name:{nm['name']}", "text": f"{nm['name']} = {nm['text']}", "kind": "metadata"}
                    if nm["hidden"]:
                        f.update(visible=False, hidden_reason="hidden_name")
                    fields.append(f)
                if fields:
                    entities.append({"name": "workbook", "kind": "workbook", "fields": fields})
                continue
            sname, state = item["name"], item["state"]
            hidden = state != "visible"
            st["sheets"] += 1
            if item["encoding"]:
                issue("info", "encoding_used", item["encoding"])
                issue("info", "delimiter_used", item["delimiter"])
            if hidden:
                st["hidden_sheets"] += 1
                issue("warn", "hidden_sheet", f"{sname} ({state}); excluded from the model-facing copy")
            if item.get("external_links"):
                st["external_links"] += 1
                issue("warn", "external_link", f"{sname}: external hyperlink or link target; never fetched")
            if item["hidden_rows"]:
                issue("warn", "hidden_rows", f"{sname}!rows {','.join(item['hidden_rows'])}")
            if item["hidden_cols"]:
                issue("warn", "hidden_columns", f"{sname}!columns {','.join(item['hidden_cols'])}")
            if item["header_row"]:
                st["header_rows"] += 1
            fields, counts = [], {"formula": 0, "formula_like": 0}

            def capped(code, detail):
                if counts[code] < ISSUE_CAP:
                    issue("warn", code, detail)
                else:
                    st["issues_omitted"] += 1
                counts[code] += 1

            for c in item["cells"]:
                budget.tick()
                st["cells"] += 1
                path = f"{sname}!{c['ref']}"
                row = int("".join(ch for ch in c["ref"] if ch.isdigit()))
                kind = "column_header" if row == item["header_row"] and not c["hidden"] else "cell"
                f = {"path": path, "text": c["text"], "kind": kind}
                reason = "hidden_sheet" if hidden else c["hidden"]
                if reason:
                    f.update(visible=False, hidden_reason=reason)
                    if c["hidden"]:
                        st["hidden_cells"] += 1
                fields.append(f)
                if c["formula"]:
                    st["formulas"] += 1
                    capped("formula", f"{path}: cached value kept, formula never evaluated")
                if c["kind"] == "text" and formula_like(c["text"]):
                    st["formula_like"] += 1
                    capped("formula_like", f"{path}: text starts with a formula character; kept as data")
            for cm in item["comments"]:
                budget.tick()
                st["comments"] += 1
                f = {"path": f"{sname}!{cm['ref']}#comment", "text": cm["text"], "kind": "comment"}
                if hidden:
                    f.update(visible=False, hidden_reason="hidden_sheet")
                fields.append(f)
            st["hidden_rows"] += len(item["hidden_rows"])
            entities.append({"name": sname, "kind": "table", "fields": fields})
        return {"entities": entities, "issues": issues, "stats": st}


def register(registry: Registry) -> TabularConnector:
    c = TabularConnector()
    registry.register(c)
    return c
