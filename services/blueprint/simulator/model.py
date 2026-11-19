"""Input model: a month of source records normalised from intake rows (DSC-011, DSC-014 via DSC-019).

Input rows are the `accepted` rows of a pre-validation report (quarantined rows never reach the simulator),
keyed by the logical field names of `services/discovery/prevalidate` plus a few simulator fields. One row is
one line; rows are grouped into documents by (type, number). Provenance (connector, sheet, row, row hash) and
the intake's needs-owner finding codes stay on every record. Values are Decimal or exact strings: a float, an
unparseable amount or date, or an unknown currency drops the document with SIM-114 (never guessed).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from .codes import Anomaly
from .safe import clean_text
from .money import MoneyError, exponent, parse_decimal

KINDS = ("stock_in", "purchase_invoice", "payment_out", "stock_out", "sales_invoice", "payment_in", "payroll_run")
KIND_ORDER = {k: i for i, k in enumerate(KINDS)}  # same-day order: receipts before issues, bills before payments
INVOICE_KINDS = ("sales_invoice", "purchase_invoice")
PAYMENT_KINDS = ("payment_in", "payment_out")
STOCK_KINDS = ("stock_in", "stock_out")
LINE_REQUIRED = {
    "sales_invoice": ("item", "qty", "unit_price"), "purchase_invoice": ("item", "qty", "unit_price"),
    "payment_in": ("total",), "payment_out": ("total",),
    "stock_in": ("item", "warehouse", "qty", "unit_price"), "stock_out": ("item", "warehouse", "qty"),
    "payroll_run": ("employee", "gross", "deductions"),
}
HEADER = ("date", "party", "currency", "due_date", "against")
AMOUNTS = ("qty", "unit_price", "vat", "total", "doc_total", "gross", "deductions")
TEXTS = ("item", "warehouse", "tax_code", "account", "employee")


@dataclass(frozen=True)
class Line:
    item: str = None
    warehouse: str = None
    qty: Decimal = None
    unit_price: Decimal = None
    vat: Decimal = Decimal(0)
    total: Decimal = None
    tax_code: str = None
    account: str = None
    employee: str = None
    gross: Decimal = None
    deductions: Decimal = None

    @property
    def net(self) -> Decimal:
        if self.qty is not None and self.unit_price is not None:
            return self.qty * self.unit_price
        return Decimal(0)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    kind: str
    number: str
    posting_date: dt.date
    currency: str
    lines: tuple
    party: str = None
    due_date: dt.date = None
    against: str = None
    doc_total: Decimal = None
    provenance: tuple = ()
    quality_flags: tuple = ()

    @property
    def net(self) -> Decimal:
        return sum((ln.net for ln in self.lines), Decimal(0))

    @property
    def tax(self) -> Decimal:
        return sum((ln.vat for ln in self.lines), Decimal(0))

    @property
    def amount(self) -> Decimal:
        """Payment amount (payments) or net plus tax (everything else)."""
        if self.kind in PAYMENT_KINDS:
            return sum((ln.total for ln in self.lines), Decimal(0))
        return self.net + self.tax


@dataclass
class Normalised:
    records: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _date(v):
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v.strip()):
        try:
            return dt.date.fromisoformat(v.strip())
        except ValueError:
            pass
    raise MoneyError("date")


def _text(v):
    t = clean_text(v.strip(), 128) if isinstance(v, str) else None
    if t:
        return t
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    raise MoneyError("text")


def row_sha256(row: dict) -> str:
    blob = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _line(kind: str, row: dict) -> Line:
    vals = {}
    for k in LINE_REQUIRED[kind]:
        if _blank(row.get(k)):
            raise MoneyError(f"missing:{k}")
    for k in AMOUNTS:
        if k != "doc_total" and not _blank(row.get(k)):
            vals[k] = parse_decimal(row[k])
    for k in TEXTS:
        if not _blank(row.get(k)):
            vals[k] = _text(row[k])
    return Line(**vals)


def _header(row: dict) -> dict:
    h = {"date": _date(row.get("date")), "currency": _text(row.get("currency"))}
    exponent(h["currency"])
    h["party"] = None if _blank(row.get("party")) else _text(row["party"])
    h["due_date"] = None if _blank(row.get("due_date")) else _date(row["due_date"])
    h["against"] = None if _blank(row.get("against")) else _text(row["against"])
    h["doc_total"] = None if _blank(row.get("doc_total")) else parse_decimal(row["doc_total"])
    return h


def normalise(rows, *, connector_id: str, kind_aliases=None, findings=None) -> Normalised:
    """Group intake rows into SourceRecords. `findings` are pre-validation findings (rows are pointers
    {sheet, row}); their codes become each record's `quality_flags` (SIM-112). Pure and deterministic."""
    aliases = {k: k for k in KINDS}
    aliases.update({str(a).strip().casefold(): k for a, k in (kind_aliases or {}).items() if k in KINDS})
    flags = {}
    for f in findings or []:
        for p in f.get("rows", []):
            flags.setdefault((clean_text(str(p.get("sheet")), 64), clean_text(str(p.get("row")), 32)), set()).add(f.get("code"))
    out = Normalised()
    groups, order = {}, []
    for idx, row in enumerate(rows):
        ptr = (clean_text(str(row.get("sheet")), 64), clean_text(str(row.get("row", idx + 1)), 32))
        rtype = row.get("type")
        kind = aliases.get(rtype.strip().casefold()) if isinstance(rtype, str) else None
        if kind is None:
            out.anomalies.append(Anomaly("SIM-116", (f"{connector_id}:{ptr[0]}:{ptr[1]}",), {"type": str(rtype)[:64]}))
            continue
        number = row.get("number")
        number = f"row-{ptr[0]}-{ptr[1]}" if _blank(number) else clean_text(str(number).strip(), 128)
        key = (kind, number)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((ptr, row))
    for kind, number in order:
        # Lines in source-pointer order, so the input row order never changes the arguments.
        members = sorted(groups[(kind, number)], key=lambda m: (m[0][0], len(m[0][1]), m[0][1]))
        sid = f"{connector_id}:{kind}:{number}"
        sheets = sorted({p[0] for p, _ in members})
        if len(sheets) > 1:  # the same document number arrives from two sources: keep neither silently
            out.anomalies.append(Anomaly("SIM-105", (sid,), {"sheets": sheets}))
            continue
        try:
            heads = [_header(r) for _, r in members]
            lines = tuple(_line(kind, r) for _, r in members)
        except MoneyError as e:
            out.anomalies.append(Anomaly("SIM-114", (sid,), {"reason": str(e)}))
            continue
        core = [(x["date"], x["currency"], x["party"], x["against"]) for x in heads]
        conflict = any(c != core[0] for c in core[1:])
        h = dict(heads[0])
        for k in ("due_date", "doc_total"):  # a sheet often fills these on one line only: take the single value
            vals = {x[k] for x in heads if x[k] is not None}
            conflict = conflict or len(vals) > 1
            h[k] = next(iter(vals)) if len(vals) == 1 else None
        if conflict:
            out.anomalies.append(Anomaly("SIM-115", (sid,), {}))
            continue
        prov = tuple({"connector": connector_id, "sheet": p[0], "row": p[1], "rowSha256": row_sha256(r)}
                     for p, r in members)
        qf = sorted(set().union(*(flags.get(p, set()) for p, _ in members)) - {None})
        out.records.append(SourceRecord(sid, kind, number, h["date"], h["currency"], lines, h["party"],
                                        h["due_date"], h["against"], h["doc_total"], prov, tuple(qf)))
    return out
