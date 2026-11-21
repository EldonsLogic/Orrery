"""Amount checks and money formatting for the branded documents (ERP-016, ADR-0031, ADR-0033).

Every number a branded document prints for a line comes from the data the caller supplied (the
engine's own line and total amounts). This module only COMPARES them and refuses on a mismatch;
it never replaces a supplied amount to make a document pass. What it checks:

* one currency precision for the whole document (``currency_precision``, default 2): every
  amount, discount and total is already on that grid, so nothing is rounded when printed;
* each line equals quantity x unit_price - line discount - allocated document discount, rounded
  with commercial rounding (half away from zero, ADR-0033); a line with no supplied amount prints
  that same value;
* the line amounts less any document discount not already allocated to lines equal
  ``total_taxable_amount``. The engine supplies the document discount as ``discount_amount``
  (in ``totals`` or at the top level) and may spread it on lines as
  ``distributed_discount_amount``; a line carrying an allocation must carry the engine's net
  amount (``line_total`` or ``line_net_amount``);
* discounts are never negative (a discount is not a surcharge; ZATCA refuses it too).

``checked`` data is what the renderers print, so what was checked is what is printed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
import re
from typing import Any

from .bilingual_tax_invoice import _to_dec

AMOUNT_FIELDS = ("line_total", "line_net_amount")
DEFAULT_PRECISION = 2
MAX_PRECISION = 4
MAX_PRICE_DECIMALS = 6
_PRECISION_RE = re.compile(r"[0-9]")
# 80 digits keeps quantity x price exact for any plausible input; ROUND_HALF_UP is half away from
# zero for Decimal, the commercial rounding ADR-0033 fixes for every tenant.
_CTX = Context(prec=80, rounding=ROUND_HALF_UP)
_ZERO = Decimal(0)


@dataclass(frozen=True)
class CheckedLine:
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    amount: Decimal  # the supplied engine amount, else the commercially rounded computed one


@dataclass(frozen=True)
class CheckedAmounts:
    precision: int
    lines: tuple[CheckedLine, ...]
    document_discount: Decimal


# ------------------------------------------------------------------ shape and precision
def normalise_document(data: Any) -> dict[str, Any]:
    """Return a shallow copy whose ``lines`` is a real list, or refuse (fail closed).

    Called once at each renderer's entry, so that every later check and every printed line see the
    same list. A tuple is accepted (the renderers iterate it); a generator, string, mapping or set
    is refused, never half-checked.
    """
    if not isinstance(data, Mapping):
        raise ValueError("document data must be a mapping")
    doc = dict(data)
    lines = doc.get("lines")
    if isinstance(lines, (list, tuple)):
        doc["lines"] = list(lines)
    elif lines not in (None, ""):
        raise ValueError("lines must be a list of line mappings")
    return doc


def read_precision(data: Mapping[str, Any], errors: list[str]) -> int:
    raw = data.get("currency_precision")
    if raw is None:
        return DEFAULT_PRECISION
    value: int | None = None
    if isinstance(raw, int) and not isinstance(raw, bool):
        value = raw
    elif isinstance(raw, str) and _PRECISION_RE.fullmatch(raw):
        value = int(raw)
    if value is None or not 0 <= value <= MAX_PRECISION:
        errors.append(f"currency_precision must be a whole number from 0 to {MAX_PRECISION}")
        return DEFAULT_PRECISION
    return value


def _grid(places: int) -> Decimal:
    return Decimal(1).scaleb(-places)


def on_grid(value: Decimal, places: int) -> bool:
    try:
        return _CTX.quantize(value, _grid(places)) == value
    except InvalidOperation:
        return False


def round_amount(value: Decimal, places: int) -> Decimal:
    """Commercial rounding (half away from zero); raises ``InvalidOperation`` when absurdly large."""
    return _CTX.quantize(value, _grid(places))


def decimals_of(value: Decimal) -> int:
    return max(0, -int(value.normalize(_CTX).as_tuple().exponent))


def format_amount(value: Decimal, places: int) -> str:
    """Print an amount on the document's grid (it is already there; nothing is rounded away)."""
    return f"{round_amount(value, places):,.{places}f}"


def format_unit_price(value: Decimal, places: int) -> str:
    """Print a unit price at its supplied precision, never below the currency precision."""
    shown = max(places, decimals_of(value))
    return f"{round_amount(value, shown):,.{shown}f}"


# ------------------------------------------------------------------ the check
def _number(value: Any, label: str, errors: list[str]) -> Decimal | None:
    try:
        return _to_dec(value, label)
    except ValueError as exc:
        errors.append(str(exc))
        return None


def _discount(value: Any, label: str, places: int, errors: list[str]) -> Decimal | None:
    number = _number(value, label, errors)
    if number is None:
        return None
    if number < _ZERO:
        errors.append(f"{label} {number} cannot be negative (a discount is not a surcharge)")
        return None
    if not on_grid(number, places):
        errors.append(f"{label} {number} has more than {places} decimals")
        return None
    return number


def _document_discount(data: Mapping[str, Any], totals: Mapping[str, Any], places: int,
                       errors: list[str]) -> Decimal | None:
    found: list[tuple[str, Decimal]] = []
    for where, container in (("totals", totals), ("top level", data)):
        raw = container.get("discount_amount")
        if raw in (None, ""):
            continue
        number = _discount(raw, f"Document discount_amount ({where})", places, errors)
        if number is not None:
            found.append((where, number))
    if len({number for _, number in found}) > 1:
        errors.append("discount_amount in totals and at the top level disagree: "
                      + " vs ".join(f"{number} ({where})" for where, number in found))
    return found[0][1] if found else None


def check_amounts(data: Mapping[str, Any], errors: list[str], *, tax_invoice: bool = False
                  ) -> CheckedAmounts | None:
    """Compare lines, discounts and totals; append to ``errors`` and return None on any problem.

    ``tax_invoice`` selects the ERP-007 print path, which prints every amount with exactly two
    decimals and an unsupplied line amount half-even; it cannot be changed here, so a document it
    would print differently from this check is refused instead of printed.
    """
    before = len(errors)
    places = read_precision(data, errors)
    if tax_invoice and places != DEFAULT_PRECISION:
        errors.append(f"currency_precision {places} is not supported on tax invoices "
                      f"(the print format uses 2 decimals)")
    lines, totals = data.get("lines"), data.get("totals")
    if not isinstance(lines, list) or not lines:
        errors.append("At least one line is required")
    if not isinstance(totals, Mapping) or not totals:
        errors.append("Missing totals")
    if len(errors) > before:
        return None
    assert isinstance(lines, list) and isinstance(totals, Mapping)

    taxable = _number(totals.get("total_taxable_amount"), "total_taxable_amount", errors)
    for key, label in (("total_taxable_amount", "Total taxable amount"),
                       ("total_vat_amount", "Total VAT amount"), ("grand_total", "Grand total")):
        number = taxable if key == "total_taxable_amount" else _number(totals.get(key), key, errors)
        if number is not None and not on_grid(number, places):
            errors.append(f"{label} '{number}' must already be rounded to {places} decimals")
    document_discount = _document_discount(data, totals, places, errors)

    checked: list[CheckedLine] = []
    allocated = _ZERO
    for idx, line in enumerate(lines, start=1):
        row = _check_line(idx, line, places, tax_invoice, errors)
        if row is None:
            continue
        checked.append(row[0])
        allocated = _CTX.add(allocated, row[1])
    if len(errors) > before or taxable is None:
        return None

    discount = allocated if document_discount is None else document_discount
    if allocated > discount:
        errors.append(f"Document discount_amount {discount} is less than the line discounts "
                      f"allocated ({allocated})")
        return None
    running = _ZERO
    for row in checked:
        running = _CTX.add(running, row.amount)
    unallocated = _CTX.subtract(discount, allocated)
    net = _CTX.subtract(running, unallocated)
    if net != taxable:
        shown = (f"Lines total {running} - document discount {unallocated} = {net}"
                 if unallocated else f"Lines total {running}")
        errors.append(f"{shown} != total_taxable_amount {taxable}")
        return None
    return CheckedAmounts(places, tuple(checked), discount)


def _check_line(idx: int, line: Any, places: int, tax_invoice: bool, errors: list[str]
                ) -> tuple[CheckedLine, Decimal] | None:
    pre = f"Line {idx}"
    if not isinstance(line, Mapping):
        errors.append(f"{pre}: must be a mapping")
        return None
    before = len(errors)
    qty = _number(line.get("quantity"), f"{pre} quantity", errors)
    price = _number(line.get("unit_price"), f"{pre} unit_price", errors)
    if price is not None:
        # A unit price is never printed below the precision the check used. Quotes and purchase
        # orders print it at its supplied precision; the ERP-007 invoice print is fixed at the
        # currency precision, so there a longer price is refused instead of printed rounded.
        limit = places if tax_invoice else MAX_PRICE_DECIMALS
        if decimals_of(price) > limit:
            errors.append(f"{pre} unit_price {price} has more than {limit} decimals"
                          + (" (tax invoices print unit prices with 2 decimals)"
                             if tax_invoice else ""))
    discount = _discount(line.get("discount") or "0", f"{pre} discount", places, errors)
    distributed = None
    if line.get("distributed_discount_amount") not in (None, ""):
        distributed = _discount(line["distributed_discount_amount"],
                                f"{pre} distributed_discount_amount", places, errors)

    supplied: list[tuple[str, Decimal]] = []
    for name in AMOUNT_FIELDS:
        if line.get(name) in (None, ""):
            continue
        number = _number(line[name], f"{pre} {name}", errors)
        if number is None:
            continue
        if not on_grid(number, places):
            errors.append(f"{pre} {name} {number} has more than {places} decimals")
            continue
        supplied.append((name, number))
    if len({number for _, number in supplied}) > 1:
        errors.append(f"{pre}: line_total and line_net_amount disagree: "
                      + " vs ".join(f"{name} {number}" for name, number in supplied))
    if len(errors) > before or qty is None or price is None or discount is None:
        return None
    if distributed is not None and not supplied:
        errors.append(f"{pre}: distributed_discount_amount needs the engine's net amount in "
                      f"line_total or line_net_amount")
        return None

    exact = _CTX.subtract(_CTX.subtract(_CTX.multiply(qty, price), discount), distributed or _ZERO)
    try:
        expected = round_amount(exact, places)
    except InvalidOperation:
        errors.append(f"{pre}: amount is out of range")
        return None
    if expected < _ZERO:
        errors.append(f"{pre}: discounts {discount + (distributed or _ZERO)} exceed the line "
                      f"amount {_CTX.multiply(qty, price)}")
        return None
    if supplied:
        name, amount = supplied[0]
        if amount != expected:
            allocation = f" - allocated discount {distributed}" if distributed is not None else ""
            errors.append(f"{pre}: {name} {amount} != quantity {qty} x unit_price {price} "
                          f"- discount {discount}{allocation} = {expected}")
            return None
    else:
        amount = expected
        if tax_invoice and expected != exact:
            errors.append(f"{pre}: amount {exact} needs rounding, which the invoice print would "
                          f"do half-even; supply the engine's line_net_amount")
            return None
    return CheckedLine(qty, price, discount, amount), distributed or _ZERO
