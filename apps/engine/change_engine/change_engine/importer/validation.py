"""Pure bounded validation and reconciliation. No source value is repaired."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import unicodedata
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

from .errors import ImportFailure
from .upstream import MAX_PREVALIDATION_ROWS, check_report as _check_report, verify_upstream as _verify_upstream

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
OPTIONAL_OPENING_FIELDS = {"AR": {"account"}, "AP": {"account"}, "Stock": {"account"}}
CONTROL_TYPES = {"AR": "Receivable", "AP": "Payable", "Stock": "Stock"}
OPENING_LINKS = {
    "TrialBalance": (("account", "Account"),),
    "AR": (("customer", "Customer"),),
    "AP": (("supplier", "Supplier"),),
    "Stock": (("item_code", "Item"), ("warehouse", "Warehouse")),
}
FORMULA = ("=", "+", "-", "@", "\t", "\r")
SAFE_FORMAT_MARKS = frozenset({"\u200c", "\u200d", "\u200e", "\u200f", "\u061c"})
# Unicode 15.0 Default_Ignorable_Code_Point ranges (DerivedCoreProperties.txt).
DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
NAME_TEXT_FIELDS = frozenset({
    "customer_name", "customer_type",
    "supplier_name", "supplier_type",
    "item_name", "account_name",
})
ACCOUNT_TYPES = {"Receivable", "Payable", "Stock", "Other"}
MAX_BYTES = 2_000_000
# UNVERIFIED minor units from ISO 4217 (SIX Maintenance Agency, List One).
CURRENCY_MINOR_UNITS = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "EUR": 2, "GBP": 2}
CURRENCIES = frozenset(CURRENCY_MINOR_UNITS)


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


def _is_default_ignorable(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in DEFAULT_IGNORABLE_RANGES)


def text(value, *, allow_format_marks: bool = False):
    """Reject formula prefixes and disallowed control/format marks; retain exact spelling."""
    if not isinstance(value, str) or not value or not value.strip():
        fail()
    if not any(not c.isspace() and c not in SAFE_FORMAT_MARKS for c in value):
        fail()
    if len(value) > 1024:
        fail("IMP-LIMIT")
    # Normalize only a detection copy. Preserve accepted source spelling verbatim.
    probe = unicodedata.normalize("NFKC", value)
    probe = probe.lstrip("".join(c for c in probe if c.isspace() or unicodedata.category(c) in {"Cf", "Cc"}))
    if probe.startswith(FORMULA) or value.startswith(FORMULA):
        fail("IMP-FORMULA")
    for ch in value:
        if ch in SAFE_FORMAT_MARKS:
            if not allow_format_marks:
                fail("IMP-SCHEMA")
        elif ch in ("\t", "\n", "\r"):
            fail("IMP-SCHEMA")
        elif unicodedata.category(ch) in {"Cf", "Cc"}:
            fail("IMP-FORMULA")
    if (value != value.strip()
            or any((ch.isspace() and ch != " ")
                   or (ch not in SAFE_FORMAT_MARKS and _is_default_ignorable(ch))
                   for ch in value)):
        fail("IMP-SCHEMA")
    if allow_format_marks:
        stripped = "".join(ch for ch in value if ch not in SAFE_FORMAT_MARKS)
        if stripped != stripped.strip() or "  " in stripped:
            fail("IMP-SCHEMA")
    elif unicodedata.normalize("NFKC", value) != value:
        fail("IMP-SCHEMA")
    return value


def number(value, *, positive=False, currency_precision=None):
    """Nonnegative bounded Decimal; reject binary floats and nonfinite values.

    38 significant digits and 18 decimal places bound exact arithmetic work.
    Money must also fit the configured scale. Retain the input scale exactly.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        fail("IMP-NUMBER")
    if isinstance(value, str) and (len(value) > 60 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)):
        fail("IMP-NUMBER")
    if isinstance(value, int) and value.bit_length() > 128:
        fail("IMP-NUMBER")
    n = Decimal(value)
    if (not n.is_finite() or n < 0 or (positive and n == 0) or len(n.as_tuple().digits) > 38
            or n.adjusted() > 37):
        fail("IMP-NUMBER")
    places = -n.as_tuple().exponent
    if currency_precision is not None and places > currency_precision:
        fail("IMP-PRECISION")
    if places > 18:
        fail("IMP-NUMBER")
    return n


def business_key(entity, row):
    """Prefer stable codes; names are fallback keys, stripping invisible marks from keys."""
    for field in KEYS[entity]:
        if row.get(field):
            val = row[field]
            if field in NAME_TEXT_FIELDS:
                val = "".join(c for c in val if c not in SAFE_FORMAT_MARKS)
            return canonical([field, val])
    fail()


def check_report(report, source_rows, *, allow_name_groups: bool = False):
    """Consume DSC-019 v1 without adopting suggestions or dropping quarantine."""
    return _check_report(
        report, source_rows, allow_name_groups=allow_name_groups,
        bounded_fn=bounded, canonical_fn=canonical, fail_fn=fail,
    )


def verify_upstream(datasets, meta):
    """Re-run DSC-019 on submitted rows with server-owned master name mappings."""
    return _verify_upstream(datasets, meta, bounded_fn=bounded, canonical_fn=canonical, fail_fn=fail)


def _resolve_master(target, value, incoming, lookup, references):
    """Resolve one reference against incoming and stored company masters."""
    candidates = []
    for key_field in KEYS[target]:
        key = canonical([key_field, value])
        master = incoming[target].get(key)
        if master is None:
            master = lookup(target, key)
        if master is not None:
            candidates.append(master)
            references[canonical([target, key])] = master
    if len(candidates) != 1:
        fail("IMP-REFERENCE")
    return candidates[0]


def master_context(rows, row_clears, lookup):
    """Resolve tenant/company masters, merge updates, reject duplicates, and capture audit state.

    Incoming and stored masters use the same stable business key. Account
    classifications come from masters, never detail labels.
    """
    incoming = {entity: {} for entity in MASTER_FIELDS}
    changes = []
    master_update_fields = []
    for entity in MASTER_FIELDS:
        for idx, (row, clears) in enumerate(zip(rows.get(entity, []), row_clears.get(entity, [])), 1):
            key = business_key(entity, row)
            before = lookup(entity, key)
            if before is not None:
                after = dict(before)
                after.update(row)
                for field in clears:
                    after.pop(field, None)
                changed_fields = sorted(k for k in after if k not in before or before[k] != after[k])
                cleared_fields = sorted(k for k in before if k not in after)
                if changed_fields or cleared_fields:
                    master_update_fields.append({
                        "entity": entity, "row": idx,
                        "changed_fields": changed_fields, "cleared_fields": cleared_fields,
                    })
            else:
                after = dict(row)
            incoming[entity][key] = after
            changes.append({"entity": entity, "key": key, "before": before, "after": after})
    for change in changes:
        if (change["entity"] == "Account" and change["before"] is not None
                and change["before"].get("account_type") != change["after"].get("account_type")):
            fail("IMP-REFERENCE")
    references = {}
    tb_controls = {kind: [] for kind in ("Receivable", "Payable", "Stock")}
    tb_seen = set()
    tb_account_keys = []
    for row in rows.get("TrialBalance", []):
        master = _resolve_master("Account", row["account"], incoming, lookup, references)
        if master.get("account_type") != row["account_type"]:
            fail("IMP-REFERENCE")
        acct_key = business_key("Account", master)
        if acct_key in tb_seen:
            fail("IMP-DUPLICATE")
        tb_seen.add(acct_key)
        tb_account_keys.append(acct_key)
        if row["account_type"] in tb_controls:
            tb_controls[row["account_type"]].append((acct_key, master))
    detail_accounts = {}
    for entity in ("AR", "AP", "Stock"):
        fields = OPENING_LINKS[entity]
        control_type = CONTROL_TYPES[entity]
        seen = set()
        detail_accounts[entity] = []
        for row in rows.get(entity, []):
            resolved_keys = []
            for field, target in fields:
                master = _resolve_master(target, row[field], incoming, lookup, references)
                resolved_keys.append(business_key(target, master))
            if "account" in row:
                acct_master = _resolve_master("Account", row["account"], incoming, lookup, references)
                if acct_master.get("account_type") != control_type:
                    fail("IMP-REFERENCE")
                acct_key = business_key("Account", acct_master)
            elif len(tb_controls[control_type]) == 1:
                acct_key, acct_master = tb_controls[control_type][0]
                row["account"] = acct_master.get("account_number") or acct_master.get("account_name")
            else:
                acct_key = None
            resolved_key = tuple(resolved_keys) if entity == "Stock" else (*resolved_keys, acct_key)
            if resolved_key in seen:
                fail("IMP-DUPLICATE")
            seen.add(resolved_key)
            detail_accounts[entity].append(acct_key)
    return changes, references, master_update_fields, tb_account_keys, detail_accounts


def _reconcile_controls(rows, tb_account_keys, detail_accounts, precision):
    """Verify exact TB balance and per-account control reconciliation."""
    with localcontext(Context(prec=128)):
        totals = {k: Decimal(0) for k in ("debit", "credit", "ar", "ap", "stock")}
        tb_controls = {"ar": {}, "ap": {}, "stock": {}}
        for row, acct_key in zip(rows.get("TrialBalance", []), tb_account_keys):
            if row["debit"] and row["credit"]:
                fail()
            totals["debit"] += row["debit"]
            totals["credit"] += row["credit"]
            control = {"Receivable": "ar", "Payable": "ap", "Stock": "stock"}.get(row["account_type"])
            if control:
                expected = (row["credit"] - row["debit"]) if control == "ap" else (row["debit"] - row["credit"])
                tb_controls[control][acct_key] = (expected, bool(row["debit"] or row["credit"]))
        if totals["debit"] != totals["credit"]:
            fail("IMP-BALANCE")
        reconciliations = {}
        for control, entity in (("ar", "AR"), ("ap", "AP"), ("stock", "Stock")):
            controls_for_type = tb_controls[control]
            detail_totals, detail_counts = {}, {}
            for row, acct_key in zip(rows.get(entity, []), detail_accounts[entity]):
                if acct_key is None or acct_key not in controls_for_type:
                    fail("IMP-RECONCILE")
                val = row["amount"] if entity != "Stock" else (
                    row["qty"] * row["valuation_rate"]).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
                totals[control] += val
                detail_totals[acct_key] = detail_totals.get(acct_key, Decimal(0)) + val
                detail_counts[acct_key] = detail_counts.get(acct_key, 0) + 1
            for acct_key, (expected, is_nonzero) in controls_for_type.items():
                has_details = detail_counts.get(acct_key, 0) > 0
                acct_total = detail_totals.get(acct_key, Decimal(0))
                if is_nonzero and (not has_details or acct_total == 0 or acct_total != expected):
                    fail("IMP-RECONCILE")
                if not is_nonzero and has_details and acct_total != expected:
                    fail("IMP-RECONCILE")
            reconciliations[control] = True if controls_for_type else None
        return totals, reconciliations


def prepare(source, max_rows, lookup, currency_lookup, distinct_lookup, *,
            confirm_distinct=None, pending_plan_hash=None):
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
    if meta["currency"] not in CURRENCIES:
        fail()
    functional_currency = currency_lookup(meta["tenant_id"], meta["company"])
    if not isinstance(functional_currency, str) or functional_currency not in CURRENCIES or meta["currency"] != functional_currency:
        fail("IMP-CURRENCY")
    precision = CURRENCY_MINOR_UNITS[meta["currency"]]
    supplied_precision = source.get("currency_precision", precision)
    if type(supplied_precision) is not int or supplied_precision != precision:
        fail()
    meta["currency_precision"] = precision
    datasets = source["datasets"]
    if not isinstance(datasets, dict) or not datasets or set(datasets) - MASTER_FIELDS.keys() - OPENING_FIELDS.keys():
        fail()
    rows, submitted_rows, row_clears, raw_rows, counts, duplicate = {}, {}, {}, [], {}, False
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
        rows[entity], submitted_rows[entity], row_clears[entity], counts[entity], seen = [], [], [], len(dataset), set()
        for raw in dataset:
            fields = MASTER_FIELDS.get(entity, OPENING_FIELDS.get(entity))
            allowed = fields if entity in MASTER_FIELDS else fields | {"currency", "posting_date"} | OPTIONAL_OPENING_FIELDS.get(entity, set())
            if not isinstance(raw, dict) or not raw or raw.keys() - allowed:
                fail()
            if entity in MASTER_FIELDS:
                clears = set()
                row = {}
                for k, v in raw.items():
                    if v in ("", None):
                        if k in KEYS[entity] or k == "account_type":
                            fail()
                        clears.add(k)
                    else:
                        row[k] = text(v, allow_format_marks=k in NAME_TEXT_FIELDS)
                if not row:
                    fail()
                key = business_key(entity, row)
                if key in seen:
                    duplicate = True
                seen.add(key)
                row_clears[entity].append(clears)
            else:
                numeric = {"debit", "credit", "amount", "qty", "valuation_rate"}
                row = {k: number(v, positive=k == "qty", currency_precision=None if k == "qty" else precision)
                       if k in numeric else text(v) for k, v in raw.items()}
                if fields - row.keys():
                    fail()
                for key in ("currency", "posting_date"):
                    if row.get(key, meta[key]) != meta[key]:
                        fail()
                    row[key] = meta[key]
            if "account_type" in row and row["account_type"] not in ACCOUNT_TYPES:
                fail()
            rows[entity].append(row)
            submitted_rows[entity].append(dict(row))
            raw_rows.append(raw)
    if not raw_rows:
        fail()
    changes, references, master_update_fields, tb_account_keys, detail_accounts = master_context(rows, row_clears, lookup)
    totals, reconciliations = _reconcile_controls(rows, tb_account_keys, detail_accounts, precision)
    report = check_report(source["prevalidation"], raw_rows, allow_name_groups=True)
    if duplicate:
        fail("IMP-DUPLICATE")
    detected_groups = verify_upstream(datasets, meta)
    upstream_names = {
        kind: {n for g in detected_groups if g["kind"] == kind for n in g["members"]}
        for kind in ("party", "item")
    }
    for kind in ("party", "item"):
        for grp in report["name_groups"][kind]:
            if {m["name"] for m in grp["members"]} - upstream_names[kind]:
                fail("IMP-REPORT")
    if report["findings"] and not detected_groups:
        fail("IMP-REPORT")
    source_material = {**meta, "datasets": submitted_rows, "prevalidation": report, "version": 2}
    source_digest = hashlib.sha256(canonical(source_material).encode("utf-8")).hexdigest()
    plan = {**meta, "datasets": rows, "prevalidation": report, "version": 2,
            "master_changes": changes, "references": references, "source_digest": source_digest}
    pending_hash = hashlib.sha256(canonical(plan).encode("utf-8")).hexdigest()
    if detected_groups:
        expected_ids = sorted(g["id"] for g in detected_groups)
        if confirm_distinct is not None:
            confirmed_ids = sorted(confirm_distinct)
            if (confirmed_ids != expected_ids or not isinstance(pending_plan_hash, str)
                    or not hmac.compare_digest(pending_plan_hash, pending_hash)):
                fail("IMP-CONFIRM")
        else:
            confirmed_ids = sorted(distinct_lookup(
                meta["tenant_id"], meta["company"], meta["batch_id"], source_digest, pending_hash))
            if confirmed_ids != expected_ids:
                raise ImportFailure(
                    "IMP-REPORT",
                    report_counts={
                        "quarantined": 0,
                        "owner_review": sum(len(g["members"]) for g in detected_groups),
                        "findings": len(detected_groups),
                        "duplicate_groups": len(detected_groups),
                    },
                    name_groups=[{"id": g["id"], "entity": g["entity"], "rule": g["rule"], "members": g["members"]}
                                 for g in detected_groups],
                    plan_hash=pending_hash,
                )
        plan["owner_confirmed_distinct"] = confirmed_ids
    else:
        if confirm_distinct is not None:
            fail("IMP-CONFIRM")
        confirmed_ids = []
    digest = hashlib.sha256(canonical(plan).encode("utf-8")).hexdigest()
    plan["pending_plan_hash"] = pending_hash
    return plan, {"ok": True, "errors": [], "company": meta["company"],
                  "posting_date": meta["posting_date"], "currency": meta["currency"],
                  "counts": counts, "totals": {k: format(v, "f") for k, v in totals.items()},
                  "reconciliations": reconciliations, "plan_hash": digest,
                  "owner_confirmed_distinct": confirmed_ids,
                  "master_updates": len(master_update_fields),
                  "master_update_fields": master_update_fields}
