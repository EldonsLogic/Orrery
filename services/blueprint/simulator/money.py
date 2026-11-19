"""Decimal-only money helpers. No floats anywhere: a float input is refused, never converted.

Amounts are compared in minor currency units (int). Rounding is ROUND_HALF_UP at the currency exponent.
The exponent table is platform data; a currency not in it is refused (fail closed).
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ISO 4217 minor-unit exponents for the currencies the simulator accepts.
EXPONENT = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "EUR": 2, "GBP": 2,
            "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3}
_NUM = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,9})?$")


class MoneyError(ValueError):
    """A value that is not an exact decimal (float, NaN, bad text) or an unknown currency."""


def parse_decimal(value) -> Decimal:
    """Exact Decimal from a decimal string, an int or a finite Decimal. Floats and bools are refused."""
    if isinstance(value, bool) or isinstance(value, float):
        raise MoneyError("float_or_bool")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyError("not_finite")
        return value
    if isinstance(value, str) and _NUM.match(value.strip()):
        try:
            return Decimal(value.strip())
        except InvalidOperation:  # pragma: no cover - the regex already guards this
            raise MoneyError("unparseable")
    raise MoneyError("unparseable")


def exponent(currency) -> int:
    if not isinstance(currency, str) or currency not in EXPONENT:
        raise MoneyError("unknown_currency")
    return EXPONENT[currency]


def quantize(value: Decimal, currency: str) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-exponent(currency)), rounding=ROUND_HALF_UP)


def to_minor(value: Decimal, currency: str) -> int:
    """Round half up to the currency exponent and return integer minor units."""
    return int(quantize(value, currency).scaleb(exponent(currency)))


def exact_minor(value, currency: str):
    """Minor units of a reported amount, or None when it carries more decimals than the currency allows."""
    d = parse_decimal(value)
    scaled = d.scaleb(exponent(currency))
    if scaled != scaled.to_integral_value():
        return None
    return int(scaled)


def minor_to_str(minor: int, currency: str) -> str:
    """Decimal string for an amount in minor units (for rendering only)."""
    return str(Decimal(minor).scaleb(-exponent(currency)))
