"""Metric definitions (platform registry, Q-669) and their deterministic formulas.

Money is Decimal end to end: amounts are summed exactly and rounded once, half-up, to the currency's minor
units at the end. A formula reads only the event types its definition lists in `sources`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from .errors import MetricError

MINOR_UNITS = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2}  # exponent per currency; an unknown currency refuses
_AMOUNT = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,6})?$")
_PERIOD = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_MIN = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class MetricDef:
    id: str
    label_key: str  # i18n key carrying the ar and en text
    unit: str  # "money" or "count"
    grain: str  # "month" (param period=YYYY-MM) or "as_of" (param as_of=YYYY-MM-DD)
    sources: tuple  # event types read
    dimensions: tuple  # declared dimensions; none are sliceable in v0
    roles: frozenset  # any-of roles allowed to read it
    formula: Callable  # (events, (start, end), currency) -> Decimal | int; end is exclusive


def amount(v) -> Decimal:
    if not isinstance(v, str) or not _AMOUNT.match(v):
        raise MetricError("MET-006")
    return Decimal(v)


def _when(e) -> datetime:
    try:
        return datetime.strptime(e["occurred_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        raise MetricError("MET-006") from None


def parse_window(grain: str, params: dict):
    """Half-open UTC window (start, end). UTC days; tenant time zones are a follow-up."""
    try:
        if grain == "month":
            p = params["period"]
            if not isinstance(p, str) or not _PERIOD.match(p):
                raise ValueError
            y, m = int(p[:4]), int(p[5:])
            return (datetime(y, m, 1, tzinfo=timezone.utc),
                    datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc))
        s = params["as_of"]
        if not isinstance(s, str) or not _DAY.match(s):
            raise ValueError
        d = date.fromisoformat(s)
        return _MIN, datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)
    except (KeyError, ValueError, TypeError):
        raise MetricError("MET-003") from None


def _documents(events, window):
    for e in events:
        if e["type"] == "document.issued" and window[0] <= _when(e) < window[1]:
            d = e.get("data") or {}
            if d.get("document_type") in ("invoice", "credit_note"):
                yield d


def _signed_total(events, window, currency):
    total = Decimal(0)
    for d in _documents(events, window):
        if d.get("currency") != currency:
            raise MetricError("MET-005")
        total += amount(d.get("total")) * (1 if d["document_type"] == "invoice" else -1)
    return total


def revenue(events, window, currency):
    return _signed_total(events, window, currency)


def invoice_count(events, window, currency):
    return sum(1 for d in _documents(events, window) if d["document_type"] == "invoice")


def receivables(events, window, currency):
    total = _signed_total(events, window, currency)
    for e in events:
        if e["type"] == "payment.created" and _when(e) < window[1]:
            d = e.get("data") or {}
            if d.get("currency") != currency:
                raise MetricError("MET-005")
            total -= amount(d.get("amount"))
    return total


def quantize(value: Decimal, currency: str) -> str:
    return str(value.quantize(Decimal(1).scaleb(-MINOR_UNITS[currency]), rounding=ROUND_HALF_UP))


def default_registry() -> dict:
    # ids from the example Blueprint's roles; sales_rep gets no company-wide metrics (Eldon, 2026-11-26)
    sales = frozenset({"owner", "accountant"})
    defs = (
        MetricDef("sales.revenue", "metrics.sales.revenue", "money", "month",
                  ("document.issued",), (), sales, revenue),
        MetricDef("sales.order_count", "metrics.sales.order_count", "count", "month",
                  ("document.issued",), (), sales, invoice_count),
        MetricDef("finance.receivables_outstanding", "metrics.finance.receivables_outstanding", "money",
                  "as_of", ("document.issued", "payment.created"), (), frozenset({"owner", "accountant"}),
                  receivables),
    )
    return {d.id: d for d in defs}
