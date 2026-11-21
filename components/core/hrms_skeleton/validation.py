"""Exact, fail-closed value validation (ADR-0031: no float maths, no implicit coercion).

Pure functions: no engine, no I/O. Decimals come from strings, ints or `Decimal` only; floats,
booleans, NaN, infinities, exponent notation and non-ASCII digits are refused. Dates are ISO
`YYYY-MM-DD` strings or `datetime.date` (a `datetime` is refused). The component only checks and
normalises configuration; it never computes pay, tax or leave balances.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .errors import HrmsError
from .specs import (
    CALLER_IDENTITY_FIELDS, FORBIDDEN_PAYROLL_LOGIC_FIELDS, ChildSpec, DocSpec, Rule,
)

_DECIMAL_RE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?", re.ASCII)
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_MIN_YEAR, _MAX_YEAR = 1900, 2100


def decimal_places(number: Decimal) -> int:
    """Decimal places actually needed, read from the digits and exponent (no context rounding)."""
    _, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int) or exponent >= 0 or not any(digits):
        return 0
    trailing = 0
    for digit in reversed(digits):
        if digit != 0 or trailing >= -exponent:
            break
        trailing += 1
    return -exponent - trailing


def canonical_decimal(number: Decimal) -> str:
    """Exact plain-notation string without trailing fraction zeros, ignoring the ambient context.

    `Decimal.normalize()` and `format()` round to the current context precision, which would
    silently change a stored figure, so the string is built from the sign, digits and exponent.
    """
    sign, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("not a finite decimal")
    if not any(digits):
        return "0"
    text = "".join(map(str, digits))
    if exponent >= 0:
        text += "0" * exponent
    else:
        text = text.rjust(-exponent + 1, "0")
        whole, fraction = text[:exponent], text[exponent:]
        fraction = fraction.rstrip("0")
        text = f"{whole}.{fraction}" if fraction else whole
    return f"-{text}" if sign else text


def parse_decimal(value: Any, rule: Rule, field: str) -> Decimal:
    """Return a finite, in-range `Decimal` with at most `rule.scale` decimal places."""
    if isinstance(value, bool) or isinstance(value, float):
        raise HrmsError("invalid_decimal", field=field)
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        number = Decimal(value)
    else:
        raise HrmsError("invalid_decimal", field=field)
    try:
        finite = number.is_finite()
    except InvalidOperation:  # pragma: no cover - defensive
        finite = False
    if not finite:
        raise HrmsError("invalid_decimal", field=field)
    if (rule.minimum is not None and number < rule.minimum) or (
        rule.maximum is not None and number > rule.maximum
    ):
        raise HrmsError("decimal_out_of_range", field=field)
    if decimal_places(number) > rule.scale:
        raise HrmsError("decimal_precision_exceeded", field=field)
    return number


def parse_date(value: Any, field: str) -> str:
    """Return an ISO date string for a valid calendar date in a sane year range."""
    if isinstance(value, datetime):
        raise HrmsError("invalid_date", field=field)
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str) and _DATE_RE.fullmatch(value):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise HrmsError("invalid_date", field=field) from None
    else:
        raise HrmsError("invalid_date", field=field)
    if not _MIN_YEAR <= parsed.year <= _MAX_YEAR:
        raise HrmsError("invalid_date", field=field)
    return parsed.isoformat()


def _parse_text(value: Any, rule: Rule, field: str) -> str:
    if not isinstance(value, str):
        raise HrmsError("invalid_text", field=field)
    text = value.strip()
    allowed_controls = {"\n"} if rule.kind == "text" else set()
    if not text or len(text) > int(rule.maximum or 0):
        raise HrmsError("invalid_text", field=field)
    if any(unicodedata.category(c) in ("Cc", "Cf") and c not in allowed_controls for c in text):
        raise HrmsError("invalid_text", field=field)
    return text


def normalise_value(value: Any, rule: Rule, field: str) -> Any:
    """Validate one value and return its canonical form (strings for decimals and dates)."""
    if rule.kind in ("str", "text"):
        return _parse_text(value, rule, field)
    if rule.kind == "date":
        return parse_date(value, field)
    if rule.kind == "bool":
        if not isinstance(value, bool):
            raise HrmsError("invalid_boolean", field=field)
        return value
    if rule.kind == "decimal":
        return canonical_decimal(parse_decimal(value, rule, field))
    if rule.kind == "enum":
        if not isinstance(value, str) or value not in rule.choices:
            raise HrmsError("invalid_choice", field=field)
        return value
    raise HrmsError("payload_invalid", field=field)  # pragma: no cover - unknown rule kind


def _check_field_names(payload: Mapping[str, Any], allowed: Mapping[str, Rule], doctype: str) -> None:
    for name in payload:
        if not isinstance(name, str):
            raise HrmsError("payload_invalid", doctype=doctype)
        if name in CALLER_IDENTITY_FIELDS:
            raise HrmsError("caller_identity_not_accepted", field=name, doctype=doctype)
        if name in FORBIDDEN_PAYROLL_LOGIC_FIELDS:
            raise HrmsError("payroll_logic_not_allowed", field=name, doctype=doctype)
        if name not in allowed:
            raise HrmsError("field_not_allowed", field=name, doctype=doctype)


def _normalise_children(spec: ChildSpec, rows: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)):
        raise HrmsError("invalid_list", field=field)
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise HrmsError("invalid_list", field=field)
        _check_field_names(row, spec.fields, spec.doctype)
        for name in spec.required:
            if name not in row:
                raise HrmsError("field_required", field=name, doctype=spec.doctype)
        clean = {name: normalise_value(value, spec.fields[name], name) for name, value in row.items()}
        marker = clean[spec.unique_by]
        if marker in seen:
            raise HrmsError("duplicate_row", field=spec.unique_by, doctype=spec.doctype)
        seen.add(marker)
        out.append(clean)
    return out


def normalise_record(spec: DocSpec, payload: Any, company: str) -> dict[str, Any]:
    """Validate a payload against `spec` and return the canonical values to store.

    Unknown fields, caller-supplied identity, payroll logic and a mismatched company are refused.
    For a company-scoped doctype the scoped company is filled in when the caller omits it.
    """
    if not isinstance(payload, Mapping):
        raise HrmsError("payload_invalid", doctype=spec.doctype)
    allowed: dict[str, Rule] = {**spec.fields, **{name: Rule("list") for name in spec.children}}
    _check_field_names(payload, allowed, spec.doctype)
    if "company" in payload and payload["company"] != company:
        raise HrmsError("company_mismatch", field="company", doctype=spec.doctype)
    if spec.company_scoped:
        payload = {**payload, "company": company}
    for name in spec.required:
        if name not in payload:
            raise HrmsError("field_required", field=name, doctype=spec.doctype)
    values: dict[str, Any] = {}
    for name, value in payload.items():
        if name in spec.children:
            values[name] = _normalise_children(spec.children[name], value, name)
        else:
            values[name] = normalise_value(value, spec.fields[name], name)
    if spec.date_range:
        start, end = spec.date_range
        if values[start] > values[end]:  # ISO strings sort like dates
            raise HrmsError("date_range_invalid", field=end, doctype=spec.doctype)
    return values
