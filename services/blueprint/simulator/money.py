"""Decimal-only money helpers. No floats anywhere: a float input is refused, never converted.

Amounts are compared in minor currency units (int). Rounding is ROUND_HALF_UP at the currency exponent.
The exponent table is platform data; a currency not in it is refused (fail closed).
"""
from __future__ import annotations

import re
import functools
from decimal import (ROUND_HALF_UP, Context, Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow,
                     localcontext)
from fractions import Fraction

# ISO 4217 minor-unit exponents for the currencies the simulator accepts.
EXPONENT = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "EUR": 2, "GBP": 2,
            "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3}
# Working context: 80 digits is far above the largest product of two allowed amounts (18 + 9 decimals each), so
# arithmetic is exact; any rounding (Inexact), invalid or overflowing operation raises instead of passing silently.
CTX = Context(prec=80, rounding=ROUND_HALF_UP, traps=[InvalidOperation, Inexact, Overflow, DivisionByZero])
_Q = Context(prec=80, rounding=ROUND_HALF_UP, traps=[])  # explicit rounding to the currency exponent only
_NUM = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,9})?$")


class MoneyError(ValueError):
    """A value that is not an exact decimal (float, NaN, bad text) or an unknown currency."""


def in_context(fn):
    """Run `fn` in the exact Decimal context (CTX)."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with localcontext(CTX):
            return fn(*a, **kw)
    return wrapper


def fmt(value: Decimal) -> str:
    """Plain positional decimal string, never scientific notation (the gateway money pattern)."""
    return format(value, "f")


def parse_decimal(value) -> Decimal:
    """Exact Decimal from a decimal string, an int or a finite Decimal. Floats and bools are refused."""
    if isinstance(value, bool) or isinstance(value, float):
        raise MoneyError("float_or_bool")
    if isinstance(value, int):
        if abs(value) >= 10 ** 18:
            raise MoneyError("too_large")
        return Decimal(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyError("not_finite")
        if value.adjusted() >= 18 or value.as_tuple().exponent < -9:
            raise MoneyError("too_large_or_precise")
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
    return value.quantize(Decimal(1).scaleb(-exponent(currency)), rounding=ROUND_HALF_UP, context=_Q)


def round_half_up(value: Decimal, places: int = 0) -> int:
    return int(value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP, context=_Q))


def to_minor(value, currency: str) -> int:
    """Round half up (away from zero at .5) to the currency exponent; Decimal or exact Fraction in."""
    e = exponent(currency)
    if isinstance(value, Fraction):
        s = value * 10 ** e
        n = (abs(s.numerator) * 2 + s.denominator) // (2 * s.denominator)
        return n if s >= 0 else -n
    return int(quantize(value, currency).scaleb(e))


def exact_minor(value, currency: str):
    """Minor units of a reported amount, or None when it carries more decimals than the currency allows."""
    d = parse_decimal(value)
    scaled = d.scaleb(exponent(currency))
    if scaled != scaled.to_integral_value():
        return None
    return int(scaled)


def minor_to_str(minor: int, currency: str) -> str:
    """Decimal string for an amount in minor units (for rendering only)."""
    return fmt(Decimal(minor).scaleb(-exponent(currency)))
