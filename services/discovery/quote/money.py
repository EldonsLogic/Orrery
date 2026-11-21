"""Money as integer minor units. No floats; rounding is Decimal ROUND_HALF_UP (documented, tested)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from .errors import QuoteError

# ISO 4217 minor-unit digits. SAR, AED, EGP, QAR are the platform's four markets (2 digits). The 3- and 0-digit
# entries exist so the arithmetic is proven for them before a market needs them (KW, BH, OM are reserved).
EXPONENT = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3, "JPY": 0}
MAX_MINOR = 10 ** 15  # any single price, subtotal or total at or above this is refused


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def mul_bp(minor: int, bp: int) -> int:
    """minor * bp / 10000 rounded half up to a whole minor unit (non-negative inputs)."""
    if not is_int(minor) or not is_int(bp) or minor < 0 or not 0 <= bp <= 10000:
        raise QuoteError("QTE-MONEY-001", "mul_bp")
    with localcontext() as ctx:
        ctx.prec = 60
        return int((Decimal(minor) * bp / Decimal(10000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def checked(minor: int) -> int:
    if not is_int(minor) or not -MAX_MINOR < minor < MAX_MINOR:
        raise QuoteError("QTE-RANGE-001", "amount out of range")
    return minor


def money(minor: int, currency: str) -> dict:
    """Display object: integer minor units are the truth; `text` is a plain positional decimal (Western digits)."""
    if not is_int(minor) or currency not in EXPONENT:
        raise QuoteError("QTE-MONEY-002", "money")
    exp = EXPONENT[currency]
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 10 ** exp)
    text = f"{sign}{whole}.{frac:0{exp}d}" if exp else f"{sign}{whole}"
    return {"minor": minor, "currency": currency, "exponent": exp, "text": text}


def percent_text(bp: int) -> str:
    """Basis points as a percent string: 1500 -> '15', 1450 -> '14.5', 125 -> '1.25'."""
    whole, frac = divmod(bp, 100)
    return f"{whole}.{frac:02d}".rstrip("0").rstrip(".")
