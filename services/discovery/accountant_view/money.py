"""Money from integer minor units, by code (principle 6). No floats anywhere: a float or bool is refused."""
from __future__ import annotations

import re
from decimal import Decimal

from .errors import AccountantViewError

# ISO 4217 minor-unit exponents for the currencies the platform accepts (same table as the simulator).
EXPONENT = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "EUR": 2, "GBP": 2,
            "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3}
MAX_MINOR = 10 ** 18
_NUM = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,9})?$")


def to_minor(value, currency: str) -> int:
    """A Blueprint amount (int or decimal string, major units) as integer minor units; exact or refused."""
    if currency not in EXPONENT:
        raise AccountantViewError("ACV-MONEY-001", "currency")
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (int, str)):
        raise AccountantViewError("ACV-MONEY-002", "amount must be an int or decimal string")
    if isinstance(value, str) and not _NUM.fullmatch(value):
        raise AccountantViewError("ACV-MONEY-002", "amount")
    d = Decimal(value)
    scaled = d.scaleb(EXPONENT[currency])
    if scaled != scaled.to_integral_value() or abs(scaled) >= MAX_MINOR:
        raise AccountantViewError("ACV-MONEY-003", "too many decimals or too large")
    return int(scaled)


def money(minor: int, currency: str) -> dict:
    """Display object: integer minor units are the truth; `text` is a plain positional decimal (Western digits)."""
    if isinstance(minor, bool) or not isinstance(minor, int) or currency not in EXPONENT:
        raise AccountantViewError("ACV-MONEY-001", "money")
    exp = EXPONENT[currency]
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 10 ** exp)
    return {"minor": minor, "currency": currency, "exponent": exp, "text": f"{sign}{whole}.{frac:0{exp}d}"}


def percent_basis_points(value) -> int:
    """A percent (15 or 15.5 from JSON) as integer basis points; more than two decimals is refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AccountantViewError("ACV-MONEY-004", "percent")
    scaled = Decimal(repr(value) if isinstance(value, float) else value).scaleb(2)
    if scaled != scaled.to_integral_value() or not 0 <= scaled <= 10000:
        raise AccountantViewError("ACV-MONEY-004", "percent")
    return int(scaled)
