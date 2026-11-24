"""Rule-based field extraction from OCR lines. No model. Every value keeps its original OCR string,
source page/line/box and confidence, and is marked unverified. Stated totals are only extracted;
the one cross-check is computed in code and yields a flag, never a correction (A22)."""
from __future__ import annotations

import re
from decimal import Decimal

from ..sanitise import strip_controls
from .parse import AMT, AMT_RX, find_currency, find_dates, fold, money, parse_amount

R = re.compile
SUBTOTAL = R(r"sub\s*total|المجموع\s+الفرعي|الاجمالي\s+(?:قبل|بدون)\s+الضريبه|total\s+(?:excl|before|ex)")
VAT = R(r"\bvat\b|\btax\b|ضريبه")
TOTAL = R(r"\btotal\b|grand\s+total|amount\s+due|الاجمالي|المجموع|المبلغ\s+المستحق|اجمالي")
INCL = R(r"incl|شامل")
INVOICE = R(r"(?:invoice\s*(?:number|no|num|#)|inv\.?\s*(?:no|#)|رقم\s+الفاتوره|فاتوره\s+رقم)\.?\s*[:#\-]?\s*"
            r"([a-z0-9؀-ۿ][a-z0-9؀-ۿ/_.\-]{1,30})")
TAXNO = R(r"(?:vat\s*(?:reg(?:istration)?\.?\s*)?(?:no|number|#)|tax\s*(?:id|no|number|registration\s*(?:no|number))|trn|"
          r"الرقم\s+الضريبي|رقم\s+التسجيل\s+الضريبي)\.?\s*[:#\-]?\s*(\d{10,17})(?!\d)")
SELLER = R(r"(?:seller|supplier|vendor|from|البائع|البايع|المورد)\s*[:\-]\s*(\S.*)")
BUYER = R(r"(?:buyer|customer|bill\s+to|client|العميل|المشتري)\s*[:\-]\s*(\S.*)")
ITEM = R(rf"^(.*?[^\d\s.,٫٬%].*?)\s+({AMT})\s+({AMT})\s+({AMT})\s*$")
DATE_LABEL = R(r"\bdate\b|التاريخ")
MAX_ITEMS = 200


def build_lines(page: dict) -> list:
    """Group visible tokens into lines. Text is the control-stripped join of token texts."""
    by: dict = {}
    for t in page["tokens"]:
        if t["v"]:
            by.setdefault(t["l"], []).append(t)
    lines = []
    for ln in sorted(by):
        text, spans, pos = "", [], 0
        for t in by[ln]:
            clean, _ = strip_controls(t["t"])
            if text:
                text += " "
                pos += 1
            spans.append((pos, pos + len(clean), t))
            text += clean
            pos += len(clean)
        lines.append({"page": page["page"], "line": ln, "text": text, "spans": spans,
                      "raw": " ".join(t["t"] for t in by[ln]), "tokens": by[ln]})
    return lines


def _loc(line: dict, s: int, e: int) -> dict:
    tk = [t for a, b, t in line["spans"] if a < e and b > s] or [t for _, _, t in line["spans"]]
    conf = min(t["c"] for t in tk) if tk else 0.0
    xs = [t["b"] for t in tk]
    if xs:
        x1, y1 = min(b[0] for b in xs), min(b[1] for b in xs)
        x2, y2 = max(b[0] + b[2] for b in xs), max(b[1] + b[3] for b in xs)
        box = [x1, y1, x2 - x1, y2 - y1]
    else:
        box = [0, 0, 0, 0]
    return {"page": line["page"], "line": line["line"], "conf": conf, "box": box}


def extract_fields(lines: list, threshold: float, tolerance: Decimal) -> dict:
    """Return {"values": [...], "checks": [...], "issues": [...]}. A value is
    {"name","text","norm","norm_kind","page","line","conf","box","flags"}."""
    values, seen = [], {}

    def add(name, line, s, e, norm=None, norm_kind="", flags=()):
        loc = _loc(line, s, e)
        fl = list(flags)
        if loc["conf"] < threshold:
            fl.append("low_confidence")
        values.append({"name": name, "text": line["text"][s:e], "norm": norm, "norm_kind": norm_kind,
                       "flags": sorted(set(fl)), **loc})
        seen[name] = values[-1]

    amounts: dict = {}  # name -> (Decimal, value dict)
    dates_seen = {"gregorian": 0, "hijri": 0}
    ntax = 0
    cur = None
    items = []
    for line in lines:
        t = line["text"]
        f = fold(t)
        if cur is None:
            c = find_currency(f)
            if c:
                cur = (c, line)
        labelled = False
        m = INVOICE.search(f)
        if m and "invoice_number" not in seen:
            add("invoice_number", line, m.start(1), m.end(1))
            labelled = True
        m = TAXNO.search(f)
        taxline = bool(m)
        if m:
            labelled = True
            if ntax < 4:
                ntax += 1
                add(f"tax_number_{ntax}", line, m.start(1), m.end(1), norm=None)  # raw string only
        for name, rx in (("seller_name", SELLER), ("buyer_name", BUYER)):
            m = rx.search(f)
            if m and name not in seen:
                add(name, line, m.start(1), len(t.rstrip()))
                labelled = True
        for d in find_dates(f):
            labelled = True
            cal = d["calendar"]
            if dates_seen[cal] == 0:
                dates_seen[cal] += 1
                name = "date" if cal == "gregorian" else "date_hijri"
                add(name, line, d["span"][0], d["span"][1], norm=d["iso"],
                    norm_kind="iso_date_hijri_civil_approx" if d["approx"] else "iso_date",
                    flags=d["flags"] + (["hijri_conversion_approximate"] if d["approx"] else []))
        if not taxline:
            kind = None
            if SUBTOTAL.search(f):
                kind = "subtotal"
            elif TOTAL.search(f) and VAT.search(f) and INCL.search(f):
                kind = "total"
            elif VAT.search(f):
                kind = "vat"
            elif TOTAL.search(f):
                kind = "total"
            if kind:
                labelled = True
                cands = [m for m in AMT_RX.finditer(f) if f[m.end():m.end() + 1] not in ("%", "\u066a")]
                if cands:
                    m = cands[-1]
                    val, amb = parse_amount(m.group(0))
                    if val is not None:
                        # subtotal and vat: first line wins; total: the last (bottom of the page) wins
                        if kind == "total" or kind not in amounts:
                            if kind == "total" and "total" in seen:
                                values.remove(seen["total"])
                            add(kind, line, m.start(), m.end(), norm=money(val), norm_kind="decimal",
                                flags=["ambiguous_separator"] if amb else [])
                            amounts[kind] = val
        if not labelled:
            m = ITEM.match(f)
            if m and len(items) < MAX_ITEMS:
                q, up, am = (parse_amount(m.group(i)) for i in (2, 3, 4))
                if None not in (q[0], up[0], am[0]):
                    n = len(items) + 1
                    flg = ["ambiguous_separator"] if any(x[1] for x in (q, up, am)) else []
                    add(f"line_item_{n}.description", line, m.start(1), m.end(1))
                    add(f"line_item_{n}.quantity", line, m.start(2), m.end(2), money(q[0]), "decimal", flg)
                    add(f"line_item_{n}.unit_price", line, m.start(3), m.end(3), money(up[0]), "decimal", flg)
                    add(f"line_item_{n}.amount", line, m.start(4), m.end(4), money(am[0]), "decimal", flg)
                    items.append(am[0])
    if cur:
        (code, amb, span), line = cur
        add("currency", line, span[0], span[1], norm=code, norm_kind="iso_4217",
            flags=["ambiguous_symbol"] if amb else [])
    checks = []
    if items:
        s = sum(items, Decimal(0))
        stated = amounts.get("subtotal", amounts.get("total"))
        label = "subtotal" if "subtotal" in amounts else "total"
        ok_vs = [stated] if stated is not None else []
        if "subtotal" not in amounts and "total" in amounts and "vat" in amounts:
            ok_vs.append(amounts["total"] - amounts["vat"])
        if not ok_vs:
            checks.append({"name": "lines_vs_stated", "status": "not_checked", "detail": "no stated total or subtotal"})
        else:
            hit = any(abs(s - v) <= tolerance for v in ok_vs)
            checks.append({"name": "lines_vs_stated", "status": "match" if hit else "mismatch",
                           "detail": f"sum_of_lines={money(s)}; stated_{label}={money(stated)}; "
                                     f"difference={money(s - stated)}"})
    if {"subtotal", "vat", "total"} <= set(amounts):
        d = amounts["subtotal"] + amounts["vat"] - amounts["total"]
        checks.append({"name": "subtotal_plus_vat_vs_total", "status": "match" if abs(d) <= tolerance else "mismatch",
                       "detail": f"subtotal+vat-total={money(d)}"})
    return {"values": values, "checks": checks, "stats": {"line_items": len(items)}}
