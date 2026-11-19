"""Expected totals from source records and their comparison with what the tenant reports. Decimal and integer
minor units only; deterministic code, never model output (principles 3 and 6).

Expected values are computed per document and rounded half up to the currency exponent per document, then
summed. Stock value uses moving average per (item, warehouse) in replay order, rounded once at the end.
Tolerance per metric: allowed = abs_minor + per_document_minor x documents (integers, default 0).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from .codes import Anomaly
from .model import PAYMENT_KINDS
from .money import MoneyError, exact_minor, parse_decimal, to_minor

BUCKETS = ("not_due", "0_30", "31_60", "61_90", "over_90")
# Which steps a metric needs. A metric is not compared while any such step is held for approval.
DEPENDS = {
    "sales_net": (("sales_invoice", "create"),), "vat_output": (("sales_invoice", "create"),),
    "purchases_net": (("purchase_invoice", "create"),), "vat_input": (("purchase_invoice", "create"),),
    "receivables": (("sales_invoice", "post"), ("payment_in", "post")),
    "payables": (("purchase_invoice", "post"), ("payment_out", "post")),
    "stock_value": (("stock_in", "post"), ("stock_out", "post")),
    "payroll_gross": (("payroll_run", "create"),), "payroll_deductions": (("payroll_run", "create"),),
    "payroll_net": (("payroll_run", "create"),),
}
TOLERANCE_KEYS = {"abs_minor", "per_document_minor"}


class ToleranceError(ValueError):
    pass


def metric_family(metric: str) -> str:
    return metric.split("_")[0] if metric.startswith(("receivables_", "payables_")) else metric


def _add(acc, metric, ccy, minor, sid):
    slot = acc.setdefault((metric, ccy), {"minor": 0, "sourceIds": set()})
    slot["minor"] += minor
    slot["sourceIds"].add(sid)


def _bucket(age_days: int) -> str:
    if age_days < 0:
        return "not_due"
    for limit, name in ((30, "0_30"), (60, "31_60"), (90, "61_90")):
        if age_days <= limit:
            return name
    return "over_90"


def expected_totals(records, period_end: dt.date) -> dict:
    """{(metric, currency): {"minor": int, "sourceIds": set}} over records already in replay order."""
    acc = {}
    paid = {}
    for r in records:
        if r.kind in PAYMENT_KINDS and r.against is not None:
            target = "sales_invoice" if r.kind == "payment_in" else "purchase_invoice"
            key = (target, r.against, r.currency)
            paid[key] = paid.get(key, 0) + to_minor(r.amount, r.currency)
    stock = {}
    for r in records:
        c = r.currency
        if r.kind in ("sales_invoice", "purchase_invoice"):
            sales = r.kind == "sales_invoice"
            _add(acc, "sales_net" if sales else "purchases_net", c, to_minor(r.net, c), r.source_id)
            _add(acc, "vat_output" if sales else "vat_input", c, to_minor(r.tax, c), r.source_id)
            open_minor = to_minor(r.amount, c) - paid.get((r.kind, r.number, c), 0)
            if open_minor:
                age = (period_end - (r.due_date or r.posting_date)).days
                _add(acc, f"{'receivables' if sales else 'payables'}_{_bucket(age)}", c, open_minor, r.source_id)
        elif r.kind == "payroll_run":
            gross = sum((ln.gross for ln in r.lines), Decimal(0))
            ded = sum((ln.deductions for ln in r.lines), Decimal(0))
            _add(acc, "payroll_gross", c, to_minor(gross, c), r.source_id)
            _add(acc, "payroll_deductions", c, to_minor(ded, c), r.source_id)
            _add(acc, "payroll_net", c, to_minor(gross - ded, c), r.source_id)
        elif r.kind in ("stock_in", "stock_out"):
            for ln in r.lines:
                key = (ln.item, ln.warehouse, c)
                qty, value, ids = stock.get(key, (Decimal(0), Decimal(0), set()))
                if r.kind == "stock_in":
                    qty, value = qty + ln.qty, value + ln.qty * ln.unit_price
                else:
                    avg = value / qty if qty > 0 else Decimal(0)
                    qty, value = qty - ln.qty, value - ln.qty * avg
                stock[key] = (qty, value, ids | {r.source_id})
    for (_, _, c), (_, value, ids) in sorted(stock.items(), key=lambda kv: tuple(map(str, kv[0]))):
        slot = acc.setdefault(("stock_value", c), {"minor": 0, "sourceIds": set(), "exact": Decimal(0)})
        slot["exact"] += value
        slot["sourceIds"] |= ids
    for (metric, c), slot in acc.items():
        if metric == "stock_value":
            slot["minor"] = to_minor(slot.pop("exact"), c)
    return acc


def check_tolerances(rules) -> dict:
    rules = {} if rules is None else rules
    if not isinstance(rules, dict):
        raise ToleranceError("rules")
    for name, rule in rules.items():
        if not isinstance(name, str) or not isinstance(rule, dict) or set(rule) - TOLERANCE_KEYS:
            raise ToleranceError(str(name))
        for v in rule.values():
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ToleranceError(str(name))
    return rules


def allowed_minor(rules: dict, metric: str, documents: int) -> int:
    rule = rules.get(metric) or rules.get(metric_family(metric)) or rules.get("default") or {}
    return rule.get("abs_minor", 0) + rule.get("per_document_minor", 0) * documents


def blocked_metrics(plan_steps) -> set:
    """Metric families with at least one needed step held for approval (R3 or R4)."""
    held = {(s.kind, s.stage) for s in plan_steps if s.action == "needs_approval"}
    return {m for m, deps in DEPENDS.items() if held & set(deps)}


def _nonzero(raw) -> bool:
    try:
        return parse_decimal(raw) != 0
    except MoneyError:
        return True


def compare(expected: dict, actual, *, blocked: set, rules: dict, aborted: bool):
    """Return (rows, anomalies). `actual` is the port's {metric: {currency: "decimal string"}} or None."""
    actual = actual or {}
    # A reported zero with nothing expected is not a row; any other reported value is compared against zero.
    keys = set(expected) | {(m, c) for m, v in actual.items() for c, a in v.items() if _nonzero(a)}
    rows, found = [], []
    for metric, ccy in sorted(keys):
        exp = expected.get((metric, ccy), {"minor": 0, "sourceIds": set()})
        docs = len(exp["sourceIds"])
        row = {"metric": metric, "currency": ccy, "expectedMinor": exp["minor"], "actualMinor": None,
               "differenceMinor": None, "toleranceMinor": allowed_minor(rules, metric, docs), "documents": docs,
               "status": "not_compared", "reason": None}
        ids = tuple(sorted(exp["sourceIds"]))
        reported = actual.get(metric)
        raw = None if reported is None else reported.get(ccy, "0")  # a reported metric without the currency is zero
        if aborted:
            row["reason"] = "run_aborted"
        elif metric_family(metric) in blocked:
            row["status"], row["reason"] = "blocked_by_approval", "needs_approval"
        elif metric_family(metric) not in DEPENDS:
            row["reason"] = "unknown_metric"
        elif raw is None:
            row["reason"] = "not_reported"
        else:
            try:
                got = exact_minor(raw, ccy)
            except MoneyError:
                got = None
            if got is None:
                row["status"], row["reason"] = "invalid_actual", "precision_or_format"
                found.append(Anomaly("SIM-123", ids, {"metric": metric, "currency": ccy}))
            else:
                diff = got - exp["minor"]
                row.update(actualMinor=got, differenceMinor=diff)
                if diff == 0:
                    row["status"] = "match"
                elif abs(diff) <= row["toleranceMinor"]:
                    row["status"] = "within_tolerance"
                    found.append(Anomaly("SIM-102", ids, {"metric": metric, "currency": ccy, "differenceMinor": diff}))
                else:
                    row["status"] = "mismatch"
                    found.append(Anomaly("SIM-121", ids, {"metric": metric, "currency": ccy, "differenceMinor": diff}))
        if row["status"] in ("not_compared", "blocked_by_approval") and not aborted:
            found.append(Anomaly("SIM-122", ids, {"metric": metric, "currency": ccy, "reason": row["reason"]}))
        rows.append(row)
    return rows, found
