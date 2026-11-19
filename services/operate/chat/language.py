"""Language handling: detect per message, bidi-safe text, deterministic number parsing.

No model is involved. Digits are normalised only here, by pure parsers, for tool arguments; the model never writes
a number that reaches a tool (principle 6). Message text itself is kept as typed (mixed Arabic and English intact)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_BIDI_UNSAFE = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))  # embeddings, overrides, isolates
_INVISIBLE = {0x200B, 0x2060, 0xFEFF, 0x00AD} | set(range(0xE0000, 0xE0080))
_KEEP_CC = {0x09, 0x0A, 0x0D}
# LRM, RLM, ALM (0x200E, 0x200F, 0x061C), ZWJ and ZWNJ are kept: Arabic and Persian text needs them.
_DIGITS = {**{0x0660 + i: ord("0") + i for i in range(10)}, **{0x06F0 + i: ord("0") + i for i in range(10)},
           0x066B: ord("."), 0x066C: ord(",")}


@dataclass(frozen=True)
class LangInfo:
    locale: str        # ar | en: the language to reply in
    mixed: bool        # both scripts are present in a meaningful share
    direction: str     # rtl | ltr (base direction hint; clients should still render the text with dir=auto)
    arabic_letters: int = 0
    latin_letters: int = 0


def clean_text(text: str) -> str:
    """Remove bidi overrides, embeddings and isolates (Trojan Source style spoofing), invisible and control
    characters. Balanced by construction, because none of the unbalanced controls survive. Safe on any chunk."""
    out = []
    for ch in text:
        o = ord(ch)
        if o in _BIDI_UNSAFE or o in _INVISIBLE or (o < 0x20 and o not in _KEEP_CC) or 0x7F <= o <= 0x9F:
            continue
        out.append(ch)
    return "".join(out)


def _is_arabic(o: int) -> bool:
    return (0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF
            or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF)


def detect(text: str, default: str = "en") -> LangInfo:
    """Reply language of one message: the majority script among its letters. No letters (digits only): `default`."""
    ar = lat = 0
    for ch in text:
        if not ch.isalpha():
            continue
        if _is_arabic(ord(ch)):
            ar += 1
        elif ch.isascii() or 0xC0 <= ord(ch) <= 0x24F:
            lat += 1
    if ar + lat == 0:
        loc = default if default in ("ar", "en") else "en"
        return LangInfo(loc, False, "rtl" if loc == "ar" else "ltr")
    loc = "ar" if ar > lat else "en"
    minority = min(ar, lat) / (ar + lat)
    return LangInfo(loc, minority >= 0.2, "rtl" if loc == "ar" else "ltr", ar, lat)


def normalise_digits(text: str) -> str:
    """Arabic-Indic and Persian digits to ASCII, Arabic decimal and thousands marks to . and ,."""
    return text.translate(_DIGITS)


_NUM = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?")


def parse_decimal(text: str):
    """One number to a canonical decimal string ('1234.5'), or None when it is not exactly one clear number.
    Fails closed on ambiguity: '1,5' (could be a decimal comma) is None; the caller asks the user."""
    s = normalise_digits(text).strip()
    m = _NUM.fullmatch(s)
    if not m or len(s) > 40:
        return None
    s = s.replace(",", "")
    sign = "-" if s.startswith("-") else ""
    s = s.lstrip("+-")
    whole, _, frac = s.partition(".")
    return sign + (whole.lstrip("0") or "0") + ("." + frac if frac else "")


def extract_numbers(text: str, limit: int = 20) -> list:
    """Clear numbers found in a message, canonical strings, in order. Ambiguous ones are skipped."""
    out = []
    for m in re.finditer(r"\d+(?:[,.]\d+)*", normalise_digits(text)):
        n = parse_decimal(m.group(0))
        if n is not None:
            out.append(n)
        if len(out) >= limit:
            break
    return out
