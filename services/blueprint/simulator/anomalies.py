"""Source-data anomaly detection (before any call). Deterministic; flags, never corrects.

Records outside the month are excluded from the replay and from the expected totals (SIM-107). Everything else
here is a flag on a record that is still replayed: the comparison then shows what the tenant made of it.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from .codes import Anomaly
from .model import INVOICE_KINDS, KIND_ORDER, PAYMENT_KINDS, STOCK_KINDS
from .money import to_minor


def replay_order(records) -> list:
    return sorted(records, key=lambda r: (r.posting_date, KIND_ORDER[r.kind], r.number, r.source_id))


def check_records(records, *, period_start: dt.date, period_end: dt.date, tax_codes=None, accounts=None):
    """Return (kept records in replay order, anomalies).

    `tax_codes`: the tenant's tax codes (set) or None (only presence is checked). `accounts`: the tenant's
    account codes (set) or None (account mapping not checked)."""
    found, kept = [], []
    for r in records:
        if not period_start <= r.posting_date <= period_end:
            found.append(Anomaly("SIM-107", (r.source_id,), {"date": r.posting_date.isoformat()}))
            continue
        kept.append(r)
        if r.quality_flags:
            found.append(Anomaly("SIM-112", (r.source_id,), {"codes": list(r.quality_flags)}))
    kept = replay_order(kept)
    found += _tax_and_accounts(kept, tax_codes, accounts)
    found += _rounding(kept)
    found += _possible_duplicates(kept)
    found += _negative_stock(kept)
    found += _unallocated(kept)
    return kept, found


def _tax_and_accounts(records, tax_codes, accounts):
    out = []
    for r in records:
        if r.kind in INVOICE_KINDS:
            missing = [i for i, ln in enumerate(r.lines, 1)
                       if ln.tax_code is None or (tax_codes is not None and ln.tax_code not in tax_codes)]
            if missing:
                out.append(Anomaly("SIM-103", (r.source_id,), {"lines": missing}))
        if accounts is not None:
            bad = sorted({ln.account for ln in r.lines if ln.account is not None and ln.account not in accounts})
            if bad:
                out.append(Anomaly("SIM-101", (r.source_id,), {"accounts": bad}))
    return out


def _rounding(records):
    out = []
    for r in records:
        if r.doc_total is None or r.kind in PAYMENT_KINDS or r.kind == "payroll_run":
            continue
        diff = to_minor(r.doc_total, r.currency) - to_minor(r.amount, r.currency)
        if diff:
            out.append(Anomaly("SIM-102", (r.source_id,), {"differenceMinor": diff, "where": "document_total"}))
    return out


def _possible_duplicates(records):
    """Same kind, party, date and amount under different numbers: possibly entered twice."""
    groups = {}
    for r in records:
        if r.kind == "payroll_run":
            continue
        key = (r.kind, r.party, r.posting_date, r.currency, to_minor(r.amount, r.currency))
        groups.setdefault(key, []).append(r.source_id)
    return [Anomaly("SIM-106", tuple(ids), {}) for ids in groups.values() if len(ids) > 1]


def _negative_stock(records):
    """Running quantity per (item, warehouse) in replay order; flag the first record that drives it below 0."""
    bal, flagged, out = {}, set(), []
    for r in records:
        if r.kind not in STOCK_KINDS:
            continue
        for ln in r.lines:
            key = (ln.item, ln.warehouse)
            bal[key] = bal.get(key, Decimal(0)) + (ln.qty if r.kind == "stock_in" else -ln.qty)
            if bal[key] < 0 and key not in flagged:
                flagged.add(key)
                out.append(Anomaly("SIM-104", (r.source_id,), {"item": ln.item, "warehouse": ln.warehouse,
                                                               "balance": str(bal[key])}))
    return out


def _unallocated(records):
    """A payment must name an invoice of the month with the matching direction; otherwise it cannot age."""
    numbers = {("sales_invoice", r.number) for r in records if r.kind == "sales_invoice"}
    numbers |= {("purchase_invoice", r.number) for r in records if r.kind == "purchase_invoice"}
    out = []
    for r in records:
        if r.kind in PAYMENT_KINDS:
            target = "sales_invoice" if r.kind == "payment_in" else "purchase_invoice"
            if r.against is None or (target, r.against) not in numbers:
                out.append(Anomaly("SIM-113", (r.source_id,), {"against": r.against}))
    return out
