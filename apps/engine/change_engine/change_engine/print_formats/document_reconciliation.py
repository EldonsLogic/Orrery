"""Amount checks and money formatting for the branded documents (ERP-016, ADR-0031, ADR-0033).

Every number a branded document prints for a line comes from the data the caller supplied (the
engine's own line and total amounts). This module only COMPARES them and refuses on a mismatch;
it never replaces a supplied amount to make a document pass. What it checks:

* one currency precision for the whole document: the ISO 4217 minor units of the document
  currency (``CURRENCY_PLACES``; an unknown currency is refused). ``currency_precision`` may still
  be supplied but must equal that value. Every amount and total is already on that grid, so
  nothing is rounded when printed;
* each line equals quantity x unit_price - line discount, rounded with commercial rounding (half
  away from zero, ADR-0033); a line with no supplied amount prints that same value;
* the line amounts equal ``total_taxable_amount``;
* line discounts are never negative (a discount is not a surcharge; ZATCA refuses it too);
* DOCUMENT-LEVEL DISCOUNTS ARE REFUSED (founder decision, ERP-016 round 3). Printing one needs a
  payload builder that emits the discount fields and a reconciled discount row, which is ERP-030.
  Until then a document discount, or any per-line allocation of one, is refused (fail closed)
  rather than printed with amounts that do not add up.

The renderers print only from the snapshot built here. ``snapshot_document`` copies the caller's
input once (every nested mapping and list, each value read once, so a later change to the caller's
objects cannot reach a printed figure) and ``check_amounts`` returns the numbers it checked as
``Decimal`` values together with that snapshot, whose checked numeric fields are those same
``Decimal`` values. All arithmetic runs in explicit local contexts, never the caller's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext,
)
import functools
import re
from typing import Any, Callable, TypeVar

from .bilingual_tax_invoice import _to_dec

AMOUNT_FIELDS = ("line_total", "line_net_amount")
DEFAULT_PRECISION = 2
MAX_PRICE_DECIMALS = 6
# ISO 4217 minor units for the currencies a tenant can document in. An unknown currency is
# refused, never guessed at (a wrong grid would print a wrong amount).
CURRENCY_PLACES = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "KWD": 3, "BHD": 3, "OMR": 3,
                   "USD": 2, "EUR": 2}
# Names the engine and ERPNext use for a document-level discount and for its per-line spread.
DOCUMENT_DISCOUNT_FIELDS = ("discount_amount", "additional_discount_amount",
                            "additional_discount_percentage")
LINE_ALLOCATION_FIELDS = ("distributed_discount_amount", "allocated_discount_amount",
                          "discount_allocation")
_PRECISION_RE = re.compile(r"[0-9]")
_MAX_DIGITS = 30  # of any supplied number; 30 x 30 digits is exact in the 80 digit context
_MAX_ADJUSTED = 30
_MAX_DEPTH = 10
# 80 digits keeps quantity x price exact for every number that passes ``_number``; ROUND_HALF_UP
# is half away from zero for Decimal, the commercial rounding ADR-0033 fixes for every tenant.
_CTX = Context(prec=80, rounding=ROUND_HALF_UP)
# The context the whole render runs in, so ERP-007's own Decimal code (which uses the ambient
# context) is exact and half-even as in its tests, whatever context the caller happens to be in.
_PRINT_CTX = Context(prec=80, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal(0)

_F = TypeVar("_F", bound=Callable[..., Any])


def in_print_context(func: _F) -> _F:
    """Run ``func`` in a fixed local Decimal context, independent of the caller's."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with localcontext(_PRINT_CTX):
            return func(*args, **kwargs)
    return wrapper  # type: ignore[return-value]


@dataclass(frozen=True)
class CheckedLine:
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    vat_rate: Decimal | None
    amount: Decimal  # the supplied engine amount, else the commercially rounded computed one


@dataclass(frozen=True)
class CheckedAmounts:
    precision: int
    lines: tuple[CheckedLine, ...]
    taxable: Decimal
    vat: Decimal
    grand: Decimal
    # The private snapshot the renderers print from: the checked numeric fields are the Decimal
    # values above. Nothing the caller holds can reach it.
    document: dict[str, Any]


# ------------------------------------------------------------------ snapshot and precision
def _freeze(value: Any, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("document data is nested too deeply")
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():  # each entry is read exactly once
            if not isinstance(key, str):
                raise ValueError("document data keys must be text")
            out[str.__str__(key)] = _freeze(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_freeze(item, depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float, Decimal)):
        return value
    if isinstance(value, str):
        return str.__str__(value)  # an exact str, whatever a subclass would answer
    raise ValueError(f"document data contains an unsupported value of type {type(value).__name__}")


def snapshot_document(data: Any) -> dict[str, Any]:
    """A deep, read-once copy of the document whose ``lines`` is a real list, or refuse.

    Called once at each renderer's entry: the check and the print both use this copy, never the
    caller's objects again. A tuple of lines is accepted; a generator, string, mapping or set is
    refused, never half-checked.
    """
    if not isinstance(data, Mapping):
        raise ValueError("document data must be a mapping")
    doc = _freeze(data, 0)
    lines = doc.get("lines")
    if lines not in (None, "") and not isinstance(lines, list):
        raise ValueError("lines must be a list of line mappings")
    return doc


def currency_places(data: Mapping[str, Any], errors: list[str]) -> int | None:
    """The ISO 4217 minor units of the document currency, or None (with an error) if unusable."""
    code = data.get("currency")
    if not isinstance(code, str) or not code.strip():
        errors.append("currency is required (an ISO 4217 code)")
        return None
    code = code.strip()
    if code not in CURRENCY_PLACES:
        errors.append(f"currency '{code}' is not supported (known: "
                      f"{', '.join(sorted(CURRENCY_PLACES))})")
        return None
    return CURRENCY_PLACES[code]


def read_precision(data: Mapping[str, Any], errors: list[str]) -> int:
    """The document precision: the currency's minor units; a supplied value must equal them."""
    places = currency_places(data, errors)
    default = DEFAULT_PRECISION if places is None else places
    raw = data.get("currency_precision")
    if raw is None:
        return default
    value: int | None = None
    if isinstance(raw, int) and not isinstance(raw, bool):
        value = raw
    elif isinstance(raw, str) and _PRECISION_RE.fullmatch(raw):
        value = int(raw)
    if value is None or not 0 <= value <= max(CURRENCY_PLACES.values()):
        errors.append(f"currency_precision must be a whole number from 0 to "
                      f"{max(CURRENCY_PLACES.values())}")
        return default
    if places is not None and value != places:
        errors.append(f"currency_precision {value} does not match {str(data['currency']).strip()}"
                      f" (ISO 4217 minor units: {places})")
        return default
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
    """A finite Decimal from a Decimal, int or numeric string (never a bool or float), in range."""
    try:
        number = _to_dec(value, label)
    except ValueError as exc:
        errors.append(str(exc))
        return None
    if (len(number.as_tuple().digits) > _MAX_DIGITS
            or not -_MAX_ADJUSTED <= number.adjusted() <= _MAX_ADJUSTED):
        errors.append(f"{label} is out of range")
        return None
    return number


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


def _refuse_discounts(container: Mapping[str, Any], names: tuple[str, ...], where: str,
                      errors: list[str]) -> None:
    """Refuse a document-level discount or a per-line allocation of one (see the module note)."""
    for name in names:
        raw = container.get(name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            if _to_dec(raw, name) == _ZERO:
                continue  # an explicit zero discounts nothing; there is nothing to print
        except ValueError:
            pass  # not a number: still a discount field the print cannot honour
        errors.append(f"{where}{name} is refused: document-level discount printing is not "
                      f"supported yet (ERP-030); amounts are never recomputed to make it fit")


def check_amounts(data: Mapping[str, Any], errors: list[str], *, tax_invoice: bool = False
                  ) -> CheckedAmounts | None:
    """Compare lines and totals; append to ``errors`` and return None on any problem.

    ``data`` must be the snapshot from ``snapshot_document``. ``tax_invoice`` selects the ERP-007
    print path, which prints every amount with exactly two decimals and an unsupplied line amount
    half-even; it cannot be changed here, so a document it would print differently from this check
    is refused instead of printed.
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

    _refuse_discounts(data, DOCUMENT_DISCOUNT_FIELDS, "Document ", errors)
    _refuse_discounts(totals, DOCUMENT_DISCOUNT_FIELDS, "Document totals ", errors)

    amounts: dict[str, Decimal] = {}
    for key, label in (("total_taxable_amount", "Total taxable amount"),
                       ("total_vat_amount", "Total VAT amount"), ("grand_total", "Grand total")):
        number = _number(totals.get(key), key, errors)
        if number is None:
            continue
        if not on_grid(number, places):
            errors.append(f"{label} '{number}' must already be rounded to {places} decimals")
        amounts[key] = number

    checked: list[CheckedLine] = []
    for idx, line in enumerate(lines, start=1):
        row = _check_line(idx, line, places, tax_invoice, errors)
        if row is not None:
            checked.append(row)
    if len(errors) > before or len(amounts) != 3:
        return None

    running = _ZERO
    for row in checked:
        running = _CTX.add(running, row.amount)
    if running != amounts["total_taxable_amount"]:
        errors.append(f"Lines total {running} != total_taxable_amount "
                      f"{amounts['total_taxable_amount']}")
        return None
    return CheckedAmounts(places, tuple(checked), amounts["total_taxable_amount"],
                          amounts["total_vat_amount"], amounts["grand_total"],
                          _checked_document(data, lines, checked, amounts))


def _checked_document(data: Mapping[str, Any], lines: list[Any], checked: list[CheckedLine],
                      amounts: dict[str, Decimal]) -> dict[str, Any]:
    """The snapshot with each checked numeric field replaced by the Decimal the check used."""
    document = dict(data)
    document["totals"] = {**data["totals"], **amounts}
    out_lines = []
    for line, row in zip(lines, checked):
        patched = dict(line)
        for key, value in (("quantity", row.quantity), ("unit_price", row.unit_price),
                           ("discount", row.discount), ("vat_rate", row.vat_rate)):
            if key in patched and value is not None:
                patched[key] = value
        for name in AMOUNT_FIELDS:
            if patched.get(name) not in (None, ""):
                patched[name] = row.amount
        out_lines.append(patched)
    document["lines"] = out_lines
    return document


def _check_line(idx: int, line: Any, places: int, tax_invoice: bool, errors: list[str]
                ) -> CheckedLine | None:
    pre = f"Line {idx}"
    if not isinstance(line, Mapping):
        errors.append(f"{pre}: must be a mapping")
        return None
    before = len(errors)
    _refuse_discounts(line, LINE_ALLOCATION_FIELDS, f"{pre} ", errors)
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
    raw_discount = line.get("discount")
    discount = _discount("0" if raw_discount in (None, "") else raw_discount,
                         f"{pre} discount", places, errors)
    vat_rate = None
    if line.get("vat_rate") not in (None, ""):
        vat_rate = _number(line["vat_rate"], f"{pre} vat_rate", errors)

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

    exact = _CTX.subtract(_CTX.multiply(qty, price), discount)
    try:
        expected = round_amount(exact, places)
    except InvalidOperation:
        errors.append(f"{pre}: amount is out of range")
        return None
    if expected < _ZERO:
        errors.append(f"{pre}: discount {discount} exceeds the line amount "
                      f"{_CTX.multiply(qty, price)}")
        return None
    if supplied:
        name, amount = supplied[0]
        if amount != expected:
            errors.append(f"{pre}: {name} {amount} != quantity {qty} x unit_price {price} "
                          f"- discount {discount} = {expected}")
            return None
    else:
        amount = expected
        if tax_invoice and expected != exact:
            errors.append(f"{pre}: amount {exact} needs rounding, which the invoice print would "
                          f"do half-even; supply the engine's line_net_amount")
            return None
    return CheckedLine(qty, price, discount, vat_rate, amount)
