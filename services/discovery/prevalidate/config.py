"""Config validation. All config is data; unknown keys are refused (fail closed)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .errors import PrevalidationError

LOGICAL = ("type", "number", "date", "party", "item", "warehouse", "qty", "unit_price",
           "discount", "vat", "total", "doc_total", "currency", "row", "sheet")
DEFAULT_REQUIRED = {
    "*": ["type", "date"],
    "purchase_receipt": ["type", "number", "date", "party", "item", "qty", "unit_price", "warehouse"],
    "sales_invoice": ["type", "number", "date", "party", "item", "qty", "unit_price", "warehouse"],
    "stock_move": ["type", "date", "item", "qty", "warehouse"],
    "payment": ["type", "date", "party", "total"],
}
_KEYS = {"fields", "period", "today", "decimals", "tolerance", "stock_in_types", "stock_out_types",
         "required", "name_threshold", "max_rows"}


def _bad(detail):
    return PrevalidationError("PRE-E03", detail)


def _iso(v, name):
    try:
        if isinstance(v, str) and len(v) == 10:
            return dt.date.fromisoformat(v)
    except ValueError:
        pass
    raise _bad(name)


@dataclass(frozen=True)
class Config:
    fields: dict
    start: object
    end: object
    today: object
    decimals: int
    tolerance: Decimal
    stock_in: frozenset
    stock_out: frozenset
    required: dict
    name_threshold: int
    max_rows: int


def _types(v, name, default):
    if v is None:
        return frozenset(default)
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise _bad(name)
    return frozenset(x.strip().casefold() for x in v)


def load_config(raw) -> Config:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - _KEYS:
        raise _bad("keys")
    fields = {k: k for k in LOGICAL}
    f = raw.get("fields", {})
    if not isinstance(f, dict) or set(f) - set(LOGICAL) or not all(isinstance(v, str) and v for v in f.values()):
        raise _bad("fields")
    fields.update(f)
    if len(set(fields.values())) != len(fields):
        raise _bad("fields")
    period = raw.get("period") or {}
    if not isinstance(period, dict) or set(period) - {"start", "end"}:
        raise _bad("period")
    start = _iso(period["start"], "period") if "start" in period else None
    end = _iso(period["end"], "period") if "end" in period else None
    if start and end and start > end:
        raise _bad("period")
    today = _iso(raw["today"], "today") if raw.get("today") is not None else None
    dec = raw.get("decimals", 2)
    if isinstance(dec, bool) or not isinstance(dec, int) or not 0 <= dec <= 6:
        raise _bad("decimals")
    try:
        tol = Decimal(str(raw.get("tolerance", "0")))
        if not tol.is_finite() or tol < 0:
            raise InvalidOperation
    except InvalidOperation:
        raise _bad("tolerance")
    sin = _types(raw.get("stock_in_types"), "stock_in_types", ["purchase_receipt", "stock_in", "opening_stock"])
    sout = _types(raw.get("stock_out_types"), "stock_out_types", ["sales_invoice", "delivery_note", "stock_out"])
    if sin & sout:
        raise _bad("stock_types")
    req = {k: list(v) for k, v in DEFAULT_REQUIRED.items()}
    rr = raw.get("required", {})
    if not isinstance(rr, dict):
        raise _bad("required")
    for k, v in rr.items():
        if not isinstance(k, str) or not isinstance(v, list) or any(x not in LOGICAL for x in v):
            raise _bad("required")
        req[k if k == "*" else k.strip().casefold()] = list(v)
    nt = raw.get("name_threshold", 1)
    if isinstance(nt, bool) or not isinstance(nt, int) or not 0 <= nt <= 3:
        raise _bad("name_threshold")
    mr = raw.get("max_rows", 200000)
    if isinstance(mr, bool) or not isinstance(mr, int) or mr < 1:
        raise _bad("max_rows")
    return Config(fields, start, end, today, dec, tol, sin, sout, req, nt, mr)
