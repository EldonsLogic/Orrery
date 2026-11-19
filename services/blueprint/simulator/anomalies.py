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
    found += _amounts(kept)
    found += _payment_links(kept)
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
        if diff:  # rounding only within one minor unit per line; a bigger gap is a mismatch to look at
            code = "SIM-102" if abs(diff) <= len(r.lines) else "SIM-131"
            out.append(Anomaly(code, (r.source_id,), {"differenceMinor": diff, "where": "document_total"}))
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
                                                               "balance": format(bal[key], "f")}))
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


_NONNEG = ("qty", "unit_price", "vat", "total", "gross", "deductions")


def _amounts(records):
    """Negative amounts (credit notes are not modelled) and zero payments."""
    out = []
    for r in records:
        bad = sorted({f for ln in r.lines for f in _NONNEG if getattr(ln, f) is not None and getattr(ln, f) < 0})
        if r.kind in PAYMENT_KINDS and r.amount == 0:
            bad.append("total")
        if bad:
            out.append(Anomaly("SIM-124", (r.source_id,), {"fields": sorted(set(bad))}))
    return out


def _payment_links(records):
    """Payments that name an invoice of the month: currency, date and amount against that invoice."""
    inv = {(r.kind, r.number): r for r in records if r.kind in INVOICE_KINDS}
    paid, out = {}, []
    for r in records:
        if r.kind not in PAYMENT_KINDS or r.against is None:
            continue
        target = inv.get(("sales_invoice" if r.kind == "payment_in" else "purchase_invoice", r.against))
        if target is None:
            continue
        if r.currency != target.currency:
            out.append(Anomaly("SIM-125", (r.source_id, target.source_id), {}))
            continue
        if r.posting_date < target.posting_date:
            out.append(Anomaly("SIM-127", (r.source_id, target.source_id), {}))
        slot = paid.setdefault(target.source_id, [0, [target.source_id]])
        slot[0] += to_minor(r.amount, r.currency)
        slot[1].append(r.source_id)
    for sid, (total, ids) in sorted(paid.items()):
        target = next(r for r in inv.values() if r.source_id == sid)
        if total > to_minor(target.amount, target.currency):
            out.append(Anomaly("SIM-126", tuple(ids), {}))
    return out
