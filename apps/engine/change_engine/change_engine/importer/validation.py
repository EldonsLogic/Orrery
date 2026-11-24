"""Pure bounded validation and reconciliation. No source value is repaired."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

from .errors import ImportFailure

MASTER_FIELDS = {
    "Customer": {"customer_code", "customer_name", "customer_type", "customer_group", "territory", "tax_id"},
    "Supplier": {"supplier_code", "supplier_name", "supplier_type", "supplier_group", "tax_id"},
    "Item": {"item_code", "item_name", "item_group", "stock_uom"},
    "Warehouse": {"warehouse_name", "parent_warehouse"},
    "Account": {"account_number", "account_name", "parent_account", "account_type"},
}
KEYS = {"Customer": ("customer_code", "customer_name"), "Supplier": ("supplier_code", "supplier_name"),
        "Item": ("item_code",), "Warehouse": ("warehouse_name",), "Account": ("account_number", "account_name")}
OPENING_FIELDS = {
    "TrialBalance": {"account", "account_type", "debit", "credit"},
    "AR": {"customer", "amount"}, "AP": {"supplier", "amount"},
    "Stock": {"item_code", "warehouse", "qty", "valuation_rate"},
}
FORMULA = ("=", "+", "-", "@", "\t", "\r")
ACCOUNT_TYPES = {"Receivable", "Payable", "Stock", "Other"}
MAX_BYTES = 2_000_000


def fail(code="IMP-SCHEMA"):
    """Raise only a stable domain code across the untrusted input boundary."""
    raise ImportFailure(code)


def canonical(value) -> str:
    """Stable JSON; Decimal values remain exact strings, never floats."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=lambda v: format(v, "f") if isinstance(v, Decimal) else fail(), allow_nan=False)


def bounded(value, *, depth=0, budget=None):
    """Bound depth, node count, and bytes before copying or hashing input."""
    budget = [0, 0] if budget is None else budget
    budget[0] += 1
    if depth > 12 or budget[0] > 200_000:
        fail("IMP-LIMIT")
    if isinstance(value, str):
        budget[1] += len(value.encode("utf-8"))
    elif isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                fail()
            bounded(k, depth=depth + 1, budget=budget)
            bounded(v, depth=depth + 1, budget=budget)
    elif isinstance(value, (list, tuple)):
        for v in value:
            bounded(v, depth=depth + 1, budget=budget)
    elif isinstance(value, Decimal):
        if not value.is_finite() or len(value.as_tuple().digits) > 38 or abs(value.as_tuple().exponent) > 38:
            fail("IMP-NUMBER")
    elif isinstance(value, int):
        if value.bit_length() > 128:
            fail("IMP-NUMBER")
    elif value is not None and not isinstance(value, (float, bool)):
        fail()
    if budget[1] > MAX_BYTES:
        fail("IMP-LIMIT")


def text(value):
    """Reject formula prefixes even after whitespace; retain exact spelling."""
    if not isinstance(value, str) or not value or not value.strip():
        fail()
    if len(value) > 1024:
        fail("IMP-LIMIT")
    if value.startswith(FORMULA) or value.lstrip().startswith(FORMULA):
        fail("IMP-FORMULA")
    if any(ord(c) < 32 for c in value):
        fail()
    return value


def number(value, *, positive=False):
    """Nonnegative bounded Decimal; reject binary floats and nonfinite values.

    38 significant digits and 18 decimal places bound exact arithmetic work.
    Strings intentionally use plain ASCII decimal notation, without separators.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        fail("IMP-NUMBER")
    if isinstance(value, str) and (len(value) > 60 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)):
        fail("IMP-NUMBER")
    if isinstance(value, int) and value.bit_length() > 128:
        fail("IMP-NUMBER")
    n = Decimal(value)
    if (not n.is_finite() or n < 0 or (positive and n == 0) or len(n.as_tuple().digits) > 38
            or n.as_tuple().exponent < -18 or n.adjusted() > 37):
        fail("IMP-NUMBER")
    return n


def business_key(entity, row):
    """Prefer stable codes; names are fallback keys, without renaming/normalising."""
    for field in KEYS[entity]:
        if row.get(field):
            return canonical([field, row[field]])
    fail()


def check_report(report, source_rows):
    """Consume DSC-019 v1 without adopting suggestions or dropping quarantine.

    There is no confirmed-group field in v1. Any owner review/name group needs
    a new upstream report after human resolution. Matching row multisets detect
    a report reused for different data, including missing quarantined rows.
    """
    try:
        if isinstance(report, str):
            report = json.loads(report, parse_float=Decimal)
        required = {"version", "summary", "counts", "findings", "accepted", "quarantine", "owner_review", "name_groups"}
        if not isinstance(report, dict) or set(report) != required or type(report["version"]) is not int or report["version"] != 1:
            fail("IMP-REPORT")
        bounded(report)
        for key in ("findings", "accepted", "quarantine", "owner_review"):
            if not isinstance(report[key], list):
                fail("IMP-REPORT")
        if (not isinstance(report["name_groups"], dict) or set(report["name_groups"]) != {"party", "item"}
                or any(not isinstance(g, list) for g in report["name_groups"].values())):
            fail("IMP-REPORT")
        if (report["quarantine"] or report["owner_review"] or any(report["name_groups"].values())
                or report["findings"]):
            raise ImportFailure("IMP-REPORT", report_counts={
                "quarantined": len(report["quarantine"]), "owner_review": len(report["owner_review"]),
                "findings": len(report["findings"]),
                "duplicate_groups": sum(len(g) if isinstance(g, list) else 1 for g in report["name_groups"].values()),
            })
        expected = {"rows": len(source_rows), "accepted": len(source_rows), "quarantined": 0,
                    "owner_review": 0, "findings": len(report["findings"])}
        if (report["summary"] != expected or any(type(v) is not int for v in report["summary"].values())
                or report["counts"] != dict(Counter(f["code"] for f in report["findings"]))
                or Counter(canonical(r) for r in report["accepted"]) != Counter(canonical(r) for r in source_rows)):
            fail("IMP-REPORT")
        return report
    except (TypeError, ValueError, KeyError, RecursionError):
        fail("IMP-REPORT")


def prepare(source, max_rows):
    """Validate a complete batch and return canonical plan material plus totals."""
    bounded(source)
    required = {"tenant_id", "company", "batch_id", "posting_date", "currency", "datasets", "prevalidation"}
    if not isinstance(source, dict) or required - source.keys() or source.keys() - required - {"currency_precision"}:
        fail()
    meta = {key: text(source[key]) for key in ("tenant_id", "company", "batch_id", "posting_date", "currency")}
    try:
        if dt.date.fromisoformat(meta["posting_date"]).isoformat() != meta["posting_date"]:
            fail()
    except ValueError:
        fail()
    if not re.fullmatch(r"[A-Z]{3}", meta["currency"]):
        fail()
    precision = source.get("currency_precision", 2)
    if type(precision) is not int or not 0 <= precision <= 6:
        fail()
    meta["currency_precision"] = precision
    datasets = source["datasets"]
    if not isinstance(datasets, dict) or not datasets or set(datasets) - MASTER_FIELDS.keys() - OPENING_FIELDS.keys():
        fail()
    rows, raw_rows, counts, duplicate = {}, [], {}, False
    for entity, dataset in sorted(datasets.items()):
        # DSC-019's optional rows/sheet wrapper is accepted without leaking sheet names.
        if isinstance(dataset, dict):
            if set(dataset) - {"rows", "sheet"} or "rows" not in dataset:
                fail()
            dataset = dataset["rows"]
        if not isinstance(dataset, (list, tuple)):
            fail()
        if len(raw_rows) + len(dataset) > max_rows:
            fail("IMP-LIMIT")
        rows[entity], counts[entity], seen = [], len(dataset), set()
        for raw in dataset:
            fields = MASTER_FIELDS.get(entity, OPENING_FIELDS.get(entity))
            allowed = fields if entity in MASTER_FIELDS else fields | {"currency", "posting_date"}
            if not isinstance(raw, dict) or not raw or raw.keys() - allowed:
                fail()
            numeric = {"debit", "credit", "amount", "qty", "valuation_rate"} if entity in OPENING_FIELDS else set()
            row = {k: number(v, positive=k == "qty") if k in numeric else text(v) for k, v in raw.items()}
            if entity in MASTER_FIELDS:
                key = business_key(entity, row)
                if key in seen:
                    duplicate = True
                seen.add(key)
            else:
                if fields - row.keys():
                    fail()
                for key in ("currency", "posting_date"):
                    if row.get(key, meta[key]) != meta[key]:
                        fail()
                    row[key] = meta[key]
            if "account_type" in row and row["account_type"] not in ACCOUNT_TYPES:
                fail()
            rows[entity].append(row)
            raw_rows.append(raw)
    if not raw_rows:
        fail()
    # 128 digits exceeds the maximum product (76 digits) plus bounded batch sum.
    with localcontext(Context(prec=128)):
        # Do not inherit the caller's exponent limits or rounding traps.
        totals = {k: Decimal(0) for k in ("debit", "credit", "ar", "ap", "stock")}
        controls = {k: Decimal(0) for k in ("ar", "ap", "stock")}
        present, account_types = set(), {}
        for row in rows.get("TrialBalance", []):
            prior = account_types.setdefault(row["account"], row["account_type"])
            if prior != row["account_type"] or (row["debit"] and row["credit"]):
                fail()
            totals["debit"] += row["debit"]
            totals["credit"] += row["credit"]
            control = {"Receivable": "ar", "Payable": "ap", "Stock": "stock"}.get(row["account_type"])
            if control:
                present.add(control)
                controls[control] += (row["credit"] - row["debit"]) if control == "ap" else (row["debit"] - row["credit"])
        if totals["debit"] != totals["credit"]:
            fail("IMP-BALANCE")
        for kind in ("AR", "AP"):
            totals[kind.lower()] = sum((r["amount"] for r in rows.get(kind, [])), Decimal(0))
        for row in rows.get("Stock", []):
            # Comparison/preview value only; never overwrite source qty/rate.
            totals["stock"] += (row["qty"] * row["valuation_rate"]).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
        reconciliations = {}
        for control, entity in (("ar", "AR"), ("ap", "AP"), ("stock", "Stock")):
            checked = control in present and entity in rows
            if checked and totals[control] != controls[control]:
                fail("IMP-RECONCILE")
            reconciliations[control] = True if checked else None
    report = check_report(source["prevalidation"], raw_rows)
    if duplicate:
        fail("IMP-DUPLICATE")
    plan = {**meta, "datasets": rows, "prevalidation": report, "version": 1}
    digest = hashlib.sha256(canonical(plan).encode("utf-8")).hexdigest()
    return plan, {"ok": True, "errors": [], "counts": counts,
                  "totals": {k: format(v, "f") for k, v in totals.items()},
                  "reconciliations": reconciliations, "plan_hash": digest}
