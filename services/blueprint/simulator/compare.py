"""Expected totals from source records and their comparison with what the tenant reports. Decimal and integer
minor units only; deterministic code, never model output (principles 3 and 6).

Expected values are computed per document and rounded half up to the currency exponent per document, then
summed. Stock value uses moving average per (item, warehouse) in replay order, rounded once at the end.
Tolerance per metric (or family, or `default`; the first rule present wins): allowed = abs_minor +
per_document_minor x documents + per_line_minor x lines (integers, capped, default 0 when no rule is given).
Tax and net are rounded per document here and, in the engine, probably per line (Q-242): use per_line_minor.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from fractions import Fraction

from .codes import Anomaly
from .aging import BUCKETS, aging_bucket
from .model import PAYMENT_KINDS
from .money import EXPONENT, MoneyError, exact_minor, in_context, parse_decimal, to_minor
from .valuation import StockBook
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
KNOWN_METRICS = frozenset(set(DEPENDS) - {"receivables", "payables"}
                          | {f"{f}_{b}" for f in ("receivables", "payables") for b in BUCKETS})
TOLERANCE_KEYS = {"abs_minor", "per_document_minor", "per_line_minor"}
TOLERANCE_CAP = 1_000_000


class ToleranceError(ValueError):
    pass


def metric_family(metric: str) -> str:
    return metric.split("_")[0] if metric.startswith(("receivables_", "payables_")) else metric


def _add(acc, metric, ccy, minor, sid, lines=1):
    slot = acc.setdefault((metric, ccy), {"minor": 0, "sourceIds": set(), "lines": 0})
    slot["minor"] += minor
    slot["sourceIds"].add(sid)
    slot["lines"] += lines


@in_context
def expected_totals(records, period_end: dt.date) -> dict:
    """{(metric, currency): {"minor", "sourceIds", "lines", optional "invalid"}} over records in replay order."""
    acc = {}
    paid = {}
    for r in records:
        if r.kind in PAYMENT_KINDS and r.against is not None:
            target = "sales_invoice" if r.kind == "payment_in" else "purchase_invoice"
            key = (target, r.against, r.currency)
            paid[key] = paid.get(key, 0) + to_minor(r.amount, r.currency)
    book, stock_ids = StockBook(), {}
    for r in records:
        c, n = r.currency, len(r.lines)
        if r.kind in ("sales_invoice", "purchase_invoice"):
            sales = r.kind == "sales_invoice"
            _add(acc, "sales_net" if sales else "purchases_net", c, to_minor(r.net, c), r.source_id, n)
            _add(acc, "vat_output" if sales else "vat_input", c, to_minor(r.tax, c), r.source_id, n)
            open_minor = to_minor(r.amount, c) - paid.get((r.kind, r.number, c), 0)
            if open_minor:
                age = (period_end - (r.due_date or r.posting_date)).days
                _add(acc, f"{'receivables' if sales else 'payables'}_{aging_bucket(age)}", c, open_minor,
                     r.source_id, n)
        elif r.kind == "payroll_run":
            gross = sum((ln.gross for ln in r.lines), Decimal(0))
            ded = sum((ln.deductions for ln in r.lines), Decimal(0))
            _add(acc, "payroll_gross", c, to_minor(gross, c), r.source_id, n)
            _add(acc, "payroll_deductions", c, to_minor(ded, c), r.source_id, n)
            _add(acc, "payroll_net", c, to_minor(gross - ded, c), r.source_id, n)
        elif r.kind in ("stock_in", "stock_out"):
            for ln in r.lines:
                key = (ln.item, ln.warehouse, c)
                if r.kind == "stock_in":
                    book.receive(key, ln.qty, ln.unit_price)
                else:
                    book.issue(key, ln.qty)
            ids, cnt = stock_ids.setdefault(c, (set(), [0]))
            ids.add(r.source_id)
            cnt[0] += n
    totals, bad = book.totals(), book.invalid_currencies()
    for c, (ids, cnt) in sorted(stock_ids.items()):
        slot = {"minor": to_minor(totals.get(c, 0) if c in totals else Fraction(0), c), "sourceIds": ids,
                "lines": cnt[0]}
        if c in bad:
            slot["invalid"] = True
        acc[("stock_value", c)] = slot
    return acc


def check_tolerances(rules) -> dict:
    rules = {} if rules is None else rules
    if not isinstance(rules, dict):
        raise ToleranceError("rules")
    for name, rule in rules.items():  # an explicit empty rule is an error, not "zero" and not "use the default"
        if not isinstance(name, str) or not isinstance(rule, dict) or not rule or set(rule) - TOLERANCE_KEYS:
            raise ToleranceError(str(name))
        for v in rule.values():
            if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > TOLERANCE_CAP:
                raise ToleranceError(str(name))
    return rules


def allowed_minor(rules: dict, metric: str, documents: int, lines: int = 0) -> int:
    rule = {}
    for k in (metric, metric_family(metric), "default"):
        if k in rules:
            rule = rules[k]
            break
    return (rule.get("abs_minor", 0) + rule.get("per_document_minor", 0) * documents
            + rule.get("per_line_minor", 0) * lines)


def blocked_metrics(plan_steps) -> set:
    """Metric families with at least one needed step held for approval (R3 or R4)."""
    held = {(s.kind, s.stage) for s in plan_steps if s.action == "needs_approval"}
    return {m for m, deps in DEPENDS.items() if held & set(deps)}


def _nonzero(raw) -> bool:
    try:
        return parse_decimal(raw) != 0
    except MoneyError:
        return True


def _known_only(actual):
    """Keep only metrics in KNOWN_METRICS and currencies in EXPONENT. Returns (clean, [], dropped_any)."""
    clean, dropped = {}, False
    for m, v in (actual or {}).items():
        if m not in KNOWN_METRICS:
            dropped = True
            continue
        clean.setdefault(m, {})
        for c, a in v.items():
            if c in EXPONENT:
                clean[m][c] = a
            else:
                dropped = True
    return clean, [], dropped


def compare(expected: dict, actual, *, blocked: set, rules: dict, aborted: bool):
    """Return (rows, anomalies). `actual` is the port's {metric: {currency: "decimal string"}} or None."""
    actual, found, dropped = _known_only(actual)
    # A reported zero with nothing expected is not a row; any other reported value is compared against zero.
    keys = set(expected) | {(m, c) for m, v in actual.items() for c, a in v.items() if _nonzero(a)}
    rows = []
    if dropped:  # untrusted metric or currency keys never reach the report: one fixed-token anomaly instead
        found.append(Anomaly("SIM-122", (), {"reason": "unknown_metric_or_currency"}))
    for metric, ccy in sorted(keys):
        exp = expected.get((metric, ccy), {"minor": 0, "sourceIds": set(), "lines": 0})
        docs, nlines = len(exp["sourceIds"]), exp.get("lines", 0)
        row = {"metric": metric, "currency": ccy, "expectedMinor": exp["minor"], "actualMinor": None,
               "differenceMinor": None, "toleranceMinor": allowed_minor(rules, metric, docs, nlines),
               "documents": docs, "lines": nlines, "status": "not_compared", "reason": None}
        ids = tuple(sorted(exp["sourceIds"]))
        reported = actual.get(metric)
        raw = None if reported is None else reported.get(ccy, "0")  # a reported metric without the currency is zero
        if aborted:
            row["reason"] = "run_aborted"
        elif metric_family(metric) in blocked:
            row["status"], row["reason"] = "blocked_by_approval", "needs_approval"
        elif exp.get("invalid"):  # oversold or negative stock: the expected value is not defined
            row["reason"] = "negative_stock"
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
