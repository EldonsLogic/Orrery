"""Row checks. Pure functions over parsed records; nothing is corrected or adopted.

Parsing helpers live here too: amounts (Decimal, ASCII or Arabic digits, comma thousands)
and dates (ISO year-month-day only; Hijri detected, never converted).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .arabic import normalise_arabic

SEV = {"blocking": 0, "needs_owner": 1, "info": 2}
CODES = {
    "PRE-101": ("negative_stock", "blocking"),
    "PRE-201": ("date_unparseable", "blocking"),
    "PRE-202": ("date_future", "needs_owner"),
    "PRE-203": ("date_outside_period", "needs_owner"),
    "PRE-204": ("date_hijri", "needs_owner"),
    "PRE-301": ("line_total_mismatch", "blocking"),
    "PRE-302": ("document_total_mismatch", "blocking"),
    "PRE-303": ("amount_unparseable", "blocking"),
    "PRE-401": ("duplicate_row", "blocking"),
    "PRE-402": ("number_conflict", "blocking"),
    "PRE-403": ("possible_duplicate_document", "needs_owner"),
    "PRE-501": ("missing_required", "blocking"),
    "PRE-601": ("quantity_not_positive", "blocking"),
    "PRE-602": ("price_negative", "blocking"),
    "PRE-603": ("price_zero", "needs_owner"),
    "PRE-701": ("currency_mismatch", "blocking"),
    "PRE-801": ("duplicate_party_names", "needs_owner"),
    "PRE-802": ("duplicate_item_names", "needs_owner"),
}

_DIG = {**{0x0660 + i: 0x30 + i for i in range(10)}, **{0x06F0 + i: 0x30 + i for i in range(10)}}
_NUM1 = re.compile(r"[+-]?\d+(\.\d+)?")
_NUM2 = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")
_ISO = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
HIJRI_MONTHS = ("محرم", "صفر", "ربيع", "جمادى", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة")
_HIJRI_MARK = re.compile(r"(هـ|\bah\b|\bh\b)", re.I)
HIJRI_YEARS = range(1300, 1500)


def blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def parse_amount(v):
    """Decimal or None. Rejects bool, NaN, Infinity, ambiguous separators."""
    if isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v if v.is_finite() else None
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        return Decimal(repr(v)) if v == v and v not in (float("inf"), float("-inf")) else None
    if not isinstance(v, str):
        return None
    s = v.translate(_DIG).replace("٫", ".").replace("٬", ",").replace(" ", "").replace(" ", "")
    if _NUM1.fullmatch(s):
        return Decimal(s)
    if _NUM2.fullmatch(s):
        return Decimal(s.replace(",", ""))
    return None


def parse_date(v):
    """(status, date|None): status ok | hijri | bad."""
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        return ("hijri", None) if v.year in HIJRI_YEARS else ("ok", v)
    if not isinstance(v, str):
        return ("bad", None)
    s = v.translate(_DIG).strip()
    if _HIJRI_MARK.search(s) or any(m in s for m in HIJRI_MONTHS):
        return ("hijri", None)
    m = _ISO.fullmatch(s)
    if not m:
        return ("bad", None)
    y, mo, d = (int(x) for x in m.groups())
    if y in HIJRI_YEARS:
        return ("hijri", None)
    try:
        return ("ok", dt.date(y, mo, d))
    except ValueError:
        return ("bad", None)


def q(x: Decimal, places: int) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


@dataclass
class Rec:
    idx: int
    ptr: dict
    raw: dict
    type: str = ""
    number: str = ""
    date_status: str = "missing"
    date: object = None
    party: str = ""
    item: str = ""
    warehouse: str = ""
    currency: str = ""
    qty: object = None
    unit_price: object = None
    discount: object = None
    vat: object = None
    total: object = None
    doc_total: object = None
    present: set = field(default_factory=set)
    bad_amounts: list = field(default_factory=list)


@dataclass
class Finding:
    code: str
    rows: list  # primary row indexes (quarantined when blocking)
    related: list = field(default_factory=list)  # evidence row indexes
    params: dict = field(default_factory=dict)

    @property
    def severity(self):
        return CODES[self.code][1]


def build_rec(idx, row, cfg, sheet_default):
    f = cfg.fields
    g = lambda k: row.get(f[k])
    rid = g("row")
    sheet = g("sheet")
    ptr = {"sheet": sheet if not blank(sheet) else sheet_default, "row": rid if not blank(rid) else idx + 1}
    r = Rec(idx, ptr, row)
    for k in ("type", "number", "party", "item", "warehouse", "currency", "date", "qty", "unit_price",
              "discount", "vat", "total", "doc_total"):
        if not blank(g(k)):
            r.present.add(k)
    r.type = str(g("type")).strip().casefold() if "type" in r.present else ""
    r.number = normalise_arabic(str(g("number"))) if "number" in r.present else ""
    r.party = normalise_arabic(str(g("party"))) if "party" in r.present else ""
    r.item = normalise_arabic(str(g("item"))) if "item" in r.present else ""
    r.warehouse = normalise_arabic(str(g("warehouse"))) if "warehouse" in r.present else ""
    r.currency = str(g("currency")).strip().upper() if "currency" in r.present else ""
    if "date" in r.present:
        r.date_status, r.date = parse_date(g("date"))
    for k in ("qty", "unit_price", "discount", "vat", "total", "doc_total"):
        if k in r.present:
            a = parse_amount(g(k))
            if a is None:
                r.bad_amounts.append(k)
            setattr(r, k, a)
    return r


def check_required(recs, cfg):
    out = []
    for r in recs:
        need = cfg.required.get(r.type, cfg.required["*"])
        miss = [k for k in need if k not in r.present]
        if miss:
            out.append(Finding("PRE-501", [r.idx], params={"fields": sorted(miss)}))
    return out


def check_amounts_and_signs(recs):
    out = []
    for r in recs:
        if r.bad_amounts:
            out.append(Finding("PRE-303", [r.idx], params={"fields": sorted(r.bad_amounts)}))
        if r.qty is not None and r.qty <= 0:
            out.append(Finding("PRE-601", [r.idx], params={"qty": str(r.qty)}))
        if r.unit_price is not None:
            if r.unit_price < 0:
                out.append(Finding("PRE-602", [r.idx], params={"unit_price": str(r.unit_price)}))
            elif r.unit_price == 0:
                out.append(Finding("PRE-603", [r.idx]))
    return out


def check_dates(recs, cfg):
    out = []
    for r in recs:
        if r.date_status == "bad":
            out.append(Finding("PRE-201", [r.idx]))
        elif r.date_status == "hijri":
            out.append(Finding("PRE-204", [r.idx]))
        elif r.date_status == "ok":
            if cfg.today and r.date > cfg.today:
                out.append(Finding("PRE-202", [r.idx], params={"date": r.date.isoformat()}))
            elif (cfg.start and r.date < cfg.start) or (cfg.end and r.date > cfg.end):
                out.append(Finding("PRE-203", [r.idx], params={"date": r.date.isoformat()}))
    return out


def expected_line(r, cfg):
    """qty*price - discount + vat, rounded; None when qty or price is unavailable."""
    if r.qty is None or r.unit_price is None or r.bad_amounts:
        return None
    gross = q(r.qty * r.unit_price, cfg.decimals)
    return q(gross - (r.discount or Decimal(0)) + (r.vat or Decimal(0)), cfg.decimals)


def _docs(recs):
    docs = {}
    for r in recs:
        if r.number:
            docs.setdefault((r.type, r.number), []).append(r)
    return docs


def check_totals(recs, cfg):
    out = []
    for r in recs:
        exp = expected_line(r, cfg)
        if exp is not None and r.total is not None and abs(exp - r.total) > cfg.tolerance:
            out.append(Finding("PRE-301", [r.idx], params={
                "expected": str(exp), "stated": str(r.total), "difference": str(r.total - exp)}))
    for (_, num), rows in sorted(_docs(recs).items()):
        stated = {r.doc_total for r in rows if r.doc_total is not None}
        if not stated:
            continue
        lines = [expected_line(r, cfg) for r in rows]
        if any(x is None for x in lines):
            continue
        s = sum(lines, Decimal(0))
        if len(stated) > 1 or any(abs(s - d) > cfg.tolerance for d in stated):
            out.append(Finding("PRE-302", [r.idx for r in rows], params={
                "computed": str(s), "stated": sorted(str(d) for d in stated)}))
    return out


def check_duplicates(recs, cfg):
    out = []
    seen = {}
    dup_rows = set()
    skip = {cfg.fields["row"], cfg.fields["sheet"]}
    for r in recs:
        sig = tuple(sorted((k, repr(v)) for k, v in r.raw.items() if k not in skip))
        if sig in seen:
            out.append(Finding("PRE-401", [r.idx], [seen[sig]]))
            dup_rows.add(r.idx)
        else:
            seen[sig] = r.idx
    for (_, num), rows in sorted(_docs(recs).items()):
        heads = {(r.party, r.date) for r in rows if r.party or r.date}
        if len({h for h in heads}) > 1:
            first = rows[0]
            bad = [r.idx for r in rows if (r.party, r.date) != (first.party, first.date)]
            out.append(Finding("PRE-402", bad, [first.idx]))
    groups = {}
    for r in recs:
        if r.party and r.date and r.total is not None and r.idx not in dup_rows:
            groups.setdefault((r.type, r.party, r.date, r.total), []).append(r)
    for key, rows in sorted(groups.items(), key=lambda kv: kv[1][0].idx):
        nums = {r.number for r in rows}
        if len(nums) > 1:
            out.append(Finding("PRE-403", [r.idx for r in rows[1:] if r.number != rows[0].number], [rows[0].idx]))
    return out


def check_currency(recs):
    out = []
    for (_, num), rows in sorted(_docs(recs).items()):
        cur = {r.currency for r in rows if r.currency}
        if len(cur) > 1:
            out.append(Finding("PRE-701", [r.idx for r in rows], params={"currencies": sorted(cur)}))
    return out


def check_stock(recs, cfg):
    """Chronological simulation per (item, warehouse), Decimal quantities.

    Order: date, then receipts before issues on the same date, then input order.
    Rows with unusable date, item, quantity or an unlisted type are skipped.
    Flags the first row where the balance would go below zero, per (item, warehouse);
    related = the receipts that came before it. The row is not removed from the simulation.
    """
    items = {}
    for r in recs:
        if r.date_status != "ok" or not r.item or r.qty is None or r.qty <= 0:
            continue
        if r.type in cfg.stock_in:
            sign = 1
        elif r.type in cfg.stock_out:
            sign = -1
        else:
            continue
        items.setdefault((r.item, r.warehouse), []).append((r.date, 0 if sign > 0 else 1, r.idx, sign, r))
    out = []
    for (item, wh), ev in sorted(items.items()):
        bal = Decimal(0)
        ins = []
        for date, _, idx, sign, r in sorted(ev, key=lambda e: e[:3]):
            if sign > 0:
                ins.append(idx)
            bal += sign * r.qty
            if bal < 0:
                out.append(Finding("PRE-101", [idx], ins, {
                    "item": item, "warehouse": wh, "balance": str(bal), "date": date.isoformat()}))
                break
    return out
