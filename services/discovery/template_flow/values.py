"""Normalise and bound owner values. Owner text is untrusted data: checked, never interpreted."""
from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import VALUE_CHARS, VALUE_RANGE, VALUE_SIZE, VALUE_TYPE, FlowError

MAX_RAW = 1000
_DIGITS = {**{0x0660 + i: 0x30 + i for i in range(10)}, **{0x06F0 + i: 0x30 + i for i in range(10)}}
_TRUE = {"true", "yes", "y", "نعم", "ايوه", "أيوه"}
_FALSE = {"false", "no", "n", "لا", "كلا"}
_NUM = re.compile(r"^[0-9]{1,15}(\.[0-9]{1,4})?\Z", re.ASCII)


def ascii_digits(s: str) -> str:
    return s.translate(_DIGITS)


def _text(raw: Any, spec: dict) -> str:
    if not isinstance(raw, str):
        raise FlowError(VALUE_TYPE, "a text value is required")
    if len(raw) > MAX_RAW:
        raise FlowError(VALUE_SIZE, "value is too long")
    s = unicodedata.normalize("NFC", raw).strip()
    for ch in s:
        if unicodedata.category(ch)[0] == "C":  # Cc, Cf (bidi, zero-width, tag), Cs, Co, Cn
            raise FlowError(VALUE_CHARS, "value has control, invisible or direction-override characters")
    if "{" in s or "}" in s or "<" in s or ">" in s:
        raise FlowError(VALUE_CHARS, "value has template or markup characters")
    if spec.get("kind") == "digits":
        s = ascii_digits(s).replace(" ", "")
        if not re.fullmatch(r"[0-9]{%d}" % spec["length"], s, re.ASCII):
            raise FlowError(VALUE_RANGE, "value must be exactly %d digits" % spec["length"])
        return s
    lo, hi = spec.get("minLength", 1), spec.get("maxLength", 200)
    if not lo <= len(s) <= hi:
        raise FlowError(VALUE_RANGE, "text length must be %d to %d characters" % (lo, hi))
    return s


def _bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and len(raw) <= 20:
        t = unicodedata.normalize("NFC", raw).strip().lower()
        if t in _TRUE:
            return True
        if t in _FALSE:
            return False
        raise FlowError(VALUE_RANGE, "answer must be yes or no")
    raise FlowError(VALUE_TYPE, "a yes or no value is required")


def _number(raw: Any, spec: dict):
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise FlowError(VALUE_TYPE, "a number is required")
    if isinstance(raw, str):
        if len(raw) > 40:
            raise FlowError(VALUE_SIZE, "value is too long")
        s = ascii_digits(raw).strip().replace(",", "").replace("٬", "").replace(" ", "").replace("٫", ".")
        if not _NUM.match(s):
            raise FlowError(VALUE_RANGE, "not a plain number")
        d = Decimal(s)
    else:
        if isinstance(raw, float) and not math.isfinite(raw):
            raise FlowError(VALUE_RANGE, "number must be finite")
        try:
            d = Decimal(repr(raw))
        except InvalidOperation:
            raise FlowError(VALUE_RANGE, "not a plain number") from None
        if abs(d) >= Decimal(10) ** 15 or d.as_tuple().exponent < -4:  # type: ignore[operator]
            raise FlowError(VALUE_RANGE, "number out of range")
    if not Decimal(spec["min"]) <= d <= Decimal(spec["max"]):
        raise FlowError(VALUE_RANGE, "number is outside %s to %s" % (spec["min"], spec["max"]))
    return int(d) if d == d.to_integral_value() else float(d)


def normalise(raw: Any, spec: dict) -> Any:
    """Return the value to store, or raise FlowError. None, lists and objects are never accepted."""
    kind = spec["kind"]
    if kind in ("text", "digits"):
        return _text(raw, spec)
    if kind == "bool":
        return _bool(raw)
    if kind == "number":
        return _number(raw, spec)
    if kind == "enum":
        s = _text(raw, {"kind": "text", "minLength": 1, "maxLength": 40})
        s = s.lower()
        if s not in spec["values"]:
            raise FlowError(VALUE_RANGE, "value is not one of the offered options")
        return s
    raise FlowError(VALUE_TYPE, "unsupported field kind")  # registry error, fail closed
