"""Read-only reports over a register: `summary` for the monthly autonomy report, `reconcile` for go-live."""
from __future__ import annotations

from typing import Any

from .errors import ExceptionsError
from .schema import CLASSES
from .store import read_rows


def effective_rows(rows: list[dict]) -> list[dict]:
    """Rows not corrected by a later row (a correction replaces the row it points to)."""
    corrected = {r["corrects"] for r in rows if "corrects" in r}
    return [r for r in rows if r["id"] not in corrected]


def summary(path: Any) -> dict:
    """Counts of effective rows by class and by tenant (and tenant x class). Deterministic: sorted keys, no times."""
    rows = read_rows(path)
    eff = effective_rows(rows)
    by_class = {c: 0 for c in CLASSES}
    by_tenant: dict[str, int] = {}
    by_tenant_class: dict[str, dict[str, int]] = {}
    for r in eff:
        by_class[r["class"]] += 1
        by_tenant[r["tenant"]] = by_tenant.get(r["tenant"], 0) + 1
        tc = by_tenant_class.setdefault(r["tenant"], {c: 0 for c in CLASSES})
        tc[r["class"]] += 1
    return {
        "total_rows": len(rows), "effective_rows": len(eff), "corrections": sum(1 for r in rows if "corrects" in r),
        "by_class": by_class,
        "by_tenant": dict(sorted(by_tenant.items())),
        "by_tenant_class": {t: by_tenant_class[t] for t in sorted(by_tenant_class)},
    }


def _covers(edit: str, pointer: str) -> bool:
    return pointer == edit or pointer.startswith(edit + "/")


def reconcile(path: Any, removals: Any, tenant: str, revision: Any) -> dict:
    """Compare the effective rows of tenant+revision with the human edits of the Blueprint history.

    `removals`: list of element pointers the BPL-022 metrics module reported (its `removed` and `manual` lists;
    the CLI passes both). A row covers an edit when its element_pointer equals the edit or is under it. Result:
    `ok`, `rows`, `edits`, `edits_without_row` (pointers), `rows_without_edit` (row ids). Any mismatch is a finding.
    """
    if not isinstance(removals, (list, tuple)) or not all(isinstance(x, str) for x in removals):
        raise ExceptionsError("EXC-IN-001", "removals: expected a list of pointer strings")
    if not isinstance(tenant, str) or not tenant:
        raise ExceptionsError("EXC-IN-001", "tenant: expected a non-empty string")
    if isinstance(revision, bool) or not isinstance(revision, (int, str)) or revision == "":
        raise ExceptionsError("EXC-IN-001", "revision: expected an integer or string")
    edits = sorted(set(removals))
    rows = [r for r in effective_rows(read_rows(path)) if r["tenant"] == tenant and r["blueprint_rev"] == str(revision)]
    no_row = [e for e in edits if not any(_covers(e, r["element_pointer"]) for r in rows)]
    no_edit = [r["id"] for r in rows if not any(_covers(e, r["element_pointer"]) for e in edits)]
    return {
        "ok": not no_row and not no_edit and len(rows) == len(edits),
        "tenant": tenant, "revision": str(revision), "rows": len(rows), "edits": len(edits),
        "edits_without_row": no_row, "rows_without_edit": no_edit,
    }
