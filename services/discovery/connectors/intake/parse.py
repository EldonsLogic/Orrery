"""Deterministic value parsing for OCR text: digits, amounts, Gregorian and Hijri dates, currency.
Everything here is pure and offline. Parsed values are comparison copies; the original OCR string is
always kept next to them. No model is involved."""
from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from hijridate import Hijri

_MAP = {**{0x0660 + i: ord("0") + i for i in range(10)}, **{0x06F0 + i: ord("0") + i for i in range(10)},
        0x0623: 0x0627, 0x0625: 0x0627, 0x0622: 0x0627, 0x0649: 0x064A, 0x0629: 0x0647}
AMT = r"\d[\d,٬.٫]*"
AMT_RX = re.compile(AMT)


def fold(s: str) -> str:
    """Length-preserving fold for matching: digits to ASCII, alef forms unified, alef maqsura to ya,
    ta marbuta to ha, lower case. Spans found on the fold index the original text."""
    return s.translate(_MAP).lower()


def parse_amount(tok: str) -> tuple:
    """Return (Decimal or None, ambiguous). A lone separator followed by exactly three digits is
    ambiguous (thousands or decimal); it is read as thousands for a comma and as decimal for a dot,
    and flagged so a human checks it."""
    t = tok.rstrip(",.٫٬")
    if not t:
        return None, False
    amb = False
    if "٫" in t:
        ip, _, fp = t.rpartition("٫")
        ip = re.sub(r"[,.٬]", "", ip)
        s = f"{ip}.{fp}" if re.fullmatch(r"\d+", fp) and re.fullmatch(r"\d*", ip) else ""
    else:
        t = t.replace("٬", ",")
        if "," in t and "." in t:
            dec = "," if t.rfind(",") > t.rfind(".") else "."
            ip, _, fp = t.rpartition(dec)
            ip = ip.replace(",", "").replace(".", "")
            s = f"{ip}.{fp}"
        else:
            seps = [c for c in t if c in ",."]
            if not seps:
                s = t
            elif len(seps) > 1:
                groups = t.split(seps[0])
                s = "".join(groups) if len(set(seps)) == 1 and all(len(g) == 3 for g in groups[1:]) else ""
            else:
                sep = seps[0]
                ip, _, fp = t.partition(sep)
                if len(fp) == 3:
                    amb = True
                s = (ip + fp) if (sep == "," and len(fp) == 3) else f"{ip}.{fp}"
    try:
        return Decimal(s), amb
    except InvalidOperation:
        return None, False


def money(d: Decimal) -> str:
    return format(d, "f")


# --- dates ---------------------------------------------------------------------------------------
_YMD = re.compile(r"(?<!\d)(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)")
_DMY = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?!\d)")


def hijri_to_gregorian(y: int, m: int, d: int) -> datetime.date:
    """Umm al-Qura (the Saudi official calendar) via the pinned `hijridate` library (MIT, tables 1343-1500 AH).
    Raises ValueError for an invalid date or a year outside the tables."""
    try:
        return Hijri(y, m, d).to_gregorian()
    except OverflowError as e:
        raise ValueError(str(e)) from e


def find_dates(f: str) -> list:
    """Return [{"span","calendar","iso","approx","flags"}] for date-like strings in a folded line."""
    out = []
    for rx, order in ((_YMD, "ymd"), (_DMY, "dmy")):
        for m in rx.finditer(f):
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
            flags = []
            if order == "dmy" and a <= 12 and b <= 12 and a != b:
                flags.append("ambiguous_day_month")  # read as day/month
            try:
                if 1900 <= y <= 2100:
                    out.append({"span": m.span(), "calendar": "gregorian",
                                "iso": datetime.date(y, mo, d).isoformat(), "approx": False, "flags": flags})
                elif 1300 <= y <= 1500 and 1 <= mo <= 12 and 1 <= d <= 30:
                    out.append({"span": m.span(), "calendar": "hijri",
                                "iso": hijri_to_gregorian(y, mo, d).isoformat(), "approx": False, "flags": flags})
            except ValueError:
                continue
    return sorted(out, key=lambda x: x["span"])


# --- currency ------------------------------------------------------------------------------------
_CUR = (
    ("SAR", re.compile(r"\bsar\b|\bsr\b|ر\.\s?س|ريال\s+سعودي")),
    ("AED", re.compile(r"\baed\b|د\.\s?ا\b|درهم")),
    ("EGP", re.compile(r"\begp\b|ج\.\s?م|جنيه")),
    ("QAR", re.compile(r"\bqar\b|\bqr\b|ر\.\s?ق|ريال\s+قطري")),
)
_RIAL_SIGN = "﷼"


def find_currency(f: str) -> Optional[tuple]:
    """Return (code, ambiguous, span). The bare rial sign is read as SAR and flagged ambiguous."""
    for code, rx in _CUR:
        m = rx.search(f)
        if m:
            return code, False, m.span()
    i = f.find(_RIAL_SIGN)
    if i >= 0:
        return "SAR", True, (i, i + 1)
    return None
