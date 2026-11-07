"""Deterministic text and number normalisation for scoring. Pure functions, stdlib only."""
import re
import unicodedata

_DIGITS = {}
for _i, _c in enumerate("٠١٢٣٤٥٦٧٨٩"):  # Arabic-Indic
    _DIGITS[ord(_c)] = str(_i)
for _i, _c in enumerate("۰۱۲۳۴۵۶۷۸۹"):  # Eastern Arabic (Persian)
    _DIGITS[ord(_c)] = str(_i)

_TATWEEL = "ـ"
_ALEF = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}
_MISC = {"ى": "ي", "ة": "ه"}


def normalize_digits(s: str) -> str:
    """Map Arabic-Indic and Eastern Arabic digits to ASCII; separators become . and ,"""
    return s.translate(_DIGITS).replace("٫", ".").replace("٬", ",").replace("،", ",")


def parse_number(value):
    """Return a float for a number or a numeric string in any digit/separator style, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    s = normalize_digits(value).strip().replace(" ", "").replace(" ", "")
    s = s.replace(",", "")
    if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", s):
        return None
    return float(s)


def numbers_equal(a, b, tol: float = 1e-9) -> bool:
    x, y = parse_number(a), parse_number(b)
    return x is not None and y is not None and abs(x - y) <= tol * max(1.0, abs(y))


def normalize_arabic(text: str) -> str:
    """For matching only: strip tatweel and diacritics, unify alef, ya/maqsura, ta marbuta/ha, digits."""
    text = unicodedata.normalize("NFKC", text or "")
    text = normalize_digits(text).replace(_TATWEEL, "")
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    text = "".join(_ALEF.get(ch, _MISC.get(ch, ch)) for ch in text)
    return text.casefold()
