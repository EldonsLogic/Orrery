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
* DOCUMENT DISCOUNTS (round 4). The engine's document discount is ``discount_amount`` (top level
  or in totals; both must agree) and its per-line spread is ``distributed_discount_amount``,
  which must come with the engine's net line amount. A line must equal quantity x unit_price -
  line discount - its allocation; the allocations never exceed the document discount; and the
  line amounts less the part of the document discount the lines do NOT carry (the unallocated
  remainder, which the Discount row prints) must equal ``total_taxable_amount``. Any other
  discount field name, a mismatch or a wrong allocation is refused, never corrected.
* THE PINNED ENGINE'S DISCOUNT SEMANTICS (round 5; ERPNext ``erpnext/controllers/
  taxes_and_totals.py`` at e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce). A document discount needs
  the engine's ``apply_discount_on`` ("Grand Total" or "Net Total"; the engine refuses a discount
  without it, L903-906). The engine spreads it onto the lines in proportion to their net amounts
  over the total it names (L903-959, L961-1002) and then recomputes the taxes, so grand total =
  net total + taxes (L771-785), checked for every document. For "Net Total" the allocations are
  the discount itself (the round-4 check above, with its unallocated remainder). For "Grand
  Total" the discount includes VAT: the lines carry the net part (their amounts must equal
  ``total_taxable_amount``, nothing is left over) and the rest is the VAT the recomputed taxes no
  longer charge, so the allocations must equal discount x lines before it / (grand total +
  discount), the engine's own quotient, within one minor unit (the engine rounds the
  recomputed tax per row). ``additional_discount_percentage``, when given, must produce the
  discount from that same total (L858-865), within one minor unit. A cash or non-trade discount
  (taken off the grand total only, L86-90, L913-915) is refused.

The renderers print only from the snapshot built here. ``snapshot_document`` copies the caller's
input once (every nested mapping and list, each value read once, so a later change to the caller's
objects cannot reach a printed figure; every number becomes an exact built-in ``Decimal``, ``int``
or ``float`` through the base class's own methods, so a subclass is never asked anything) and ``check_amounts`` returns the numbers it checked as
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
# The engine's names for a document-level discount and for its per-line spread.
DOCUMENT_DISCOUNT_FIELD = "discount_amount"
LINE_ALLOCATION_FIELD = "distributed_discount_amount"
# The engine's choice of the total a document discount comes off, its percentage of that total
# and its flag for a discount that only reduces the grand total (round 5).
APPLY_DISCOUNT_ON_FIELD = "apply_discount_on"
GRAND_TOTAL, NET_TOTAL = "Grand Total", "Net Total"
PERCENTAGE_FIELD = "additional_discount_percentage"
CASH_DISCOUNT_FIELD = "is_cash_or_non_trade_discount"
# Other names a discount can arrive under. Not read, so refused when they carry a value.
OTHER_DOCUMENT_DISCOUNT_FIELDS = ("additional_discount_amount",)
OTHER_LINE_ALLOCATION_FIELDS = ("allocated_discount_amount", "discount_allocation")
_PRECISION_RE = re.compile(r"[0-9]")
_MAX_DIGITS = 30  # coefficient digits of any supplied number; 30 x 30 is exact in the 80 digits
_MAX_INTEGER_DIGITS = 30  # digits before the decimal point (adjusted exponent + 1)
_MAX_LEADING_ZEROS = 30  # the smallest magnitude, as an adjusted exponent: 1E-30
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
    allocated: Decimal = _ZERO  # the part of the document discount the engine spread onto it

    @property
    def shown_discount(self) -> Decimal:
        """What the line's Discount column prints: its own discount plus its allocation."""
        return self.discount + self.allocated


@dataclass(frozen=True)
class CheckedAmounts:
    precision: int
    lines: tuple[CheckedLine, ...]
    taxable: Decimal
    vat: Decimal
    grand: Decimal
    # The Discount row: the part of the document discount the printed line amounts do not carry.
    discount: Decimal
    # The private snapshot the renderers print from: the checked numeric fields are the Decimal
    # values above. Nothing the caller holds can reach it.
    document: dict[str, Any]
    # The part of the document discount the engine spread into the line amounts (already in them).
    allocated: Decimal = _ZERO


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
    if value is None or type(value) is bool:
        return value
    # Exact built-in copies made with the base class's own methods: a subclass (whose methods
    # could answer differently later) is never called, and nothing the caller holds is kept.
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        return float.__float__(value)
    if isinstance(value, Decimal):
        return Decimal(Decimal.as_tuple(value))
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
    # Integer digits are the adjusted exponent + 1 (9E+30 has 31), not the coefficient's digits.
    if (len(number.as_tuple().digits) > _MAX_DIGITS
            or not -_MAX_LEADING_ZEROS <= number.adjusted() < _MAX_INTEGER_DIGITS):
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


def _blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _refuse_other_names(container: Mapping[str, Any], names: tuple[str, ...], where: str,
                        engine_name: str, errors: list[str]) -> None:
    """Refuse a discount that arrives under a name this print does not read (never guessed)."""
    for name in names:
        raw = container.get(name)
        if _blank(raw):
            continue
        try:
            if _to_dec(raw, name) == _ZERO:
                continue  # an explicit zero discounts nothing; there is nothing to print
        except ValueError:
            pass  # not a number: still a discount field the print cannot honour
        errors.append(f"{where}{name} is not supported (the engine's name is {engine_name}); "
                      f"amounts are never recomputed to make a discount fit")


def _document_discount(data: Mapping[str, Any], totals: Mapping[str, Any], places: int,
                       errors: list[str]) -> Decimal:
    """The engine's document discount, read at the top level and/or in totals (they must agree)."""
    for container, where in ((data, "Document "), (totals, "Document totals ")):
        _refuse_other_names(container, OTHER_DOCUMENT_DISCOUNT_FIELDS, where,
                            DOCUMENT_DISCOUNT_FIELD, errors)
    found: list[Decimal] = []
    for container, label in ((data, DOCUMENT_DISCOUNT_FIELD),
                             (totals, f"totals {DOCUMENT_DISCOUNT_FIELD}")):
        raw = container.get(DOCUMENT_DISCOUNT_FIELD)
        if _blank(raw):
            continue
        number = _discount(raw, label, places, errors)
        if number is not None:
            found.append(number)
    if len(set(found)) > 1:
        errors.append(f"{DOCUMENT_DISCOUNT_FIELD} differs between the document ({found[0]}) and "
                      f"its totals ({found[1]})")
    return found[0] if found else _ZERO


def _document_values(data: Mapping[str, Any], totals: Mapping[str, Any], name: str) -> list[Any]:
    """The non-blank values of ``name`` at the top level and in totals, in that order."""
    return [c.get(name) for c in (data, totals) if not _blank(c.get(name))]


def _discount_basis(data: Mapping[str, Any], totals: Mapping[str, Any], discount: Decimal,
                    errors: list[str]) -> str | None:
    """The engine's ``apply_discount_on``; required with a document discount (L903-906)."""
    found: list[str] = []
    for raw in _document_values(data, totals, APPLY_DISCOUNT_ON_FIELD):
        if not isinstance(raw, str) or raw.strip() not in (GRAND_TOTAL, NET_TOTAL):
            errors.append(f"{APPLY_DISCOUNT_ON_FIELD} must be '{GRAND_TOTAL}' or '{NET_TOTAL}' "
                          f"(the engine's values), not {raw!r}")
            return None
        found.append(raw.strip())
    if len(set(found)) > 1:
        errors.append(f"{APPLY_DISCOUNT_ON_FIELD} differs between the document ({found[0]}) and "
                      f"its totals ({found[1]})")
        return None
    if discount > _ZERO and not found:
        errors.append(f"{APPLY_DISCOUNT_ON_FIELD} is required with a document discount ('"
                      f"{GRAND_TOTAL}' or '{NET_TOTAL}'; the engine refuses a discount without it)")
        return None
    return found[0] if found else None


def _discount_percentage(data: Mapping[str, Any], totals: Mapping[str, Any], discount: Decimal,
                         errors: list[str]) -> Decimal | None:
    """The engine's ``additional_discount_percentage`` (0 to 100), or None when not given."""
    found: list[Decimal] = []
    for raw in _document_values(data, totals, PERCENTAGE_FIELD):
        number = _number(raw, PERCENTAGE_FIELD, errors)
        if number is None:
            return None
        if not _ZERO <= number <= 100:
            errors.append(f"{PERCENTAGE_FIELD} {number} must be from 0 to 100")
            return None
        found.append(number)
    if len(set(found)) > 1:
        errors.append(f"{PERCENTAGE_FIELD} differs between the document ({found[0]}) and its "
                      f"totals ({found[1]})")
        return None
    if not found or found[0] == _ZERO:
        return None
    if discount == _ZERO:
        errors.append(f"{PERCENTAGE_FIELD} {found[0]} needs the engine's {DOCUMENT_DISCOUNT_FIELD}"
                      f" (the amount it produced); it is never computed here")
        return None
    return found[0]


def _refuse_cash_discount(data: Mapping[str, Any], totals: Mapping[str, Any],
                          errors: list[str]) -> None:
    """The engine takes a cash or non-trade discount off the grand total only.

    L86-90 and L913-915: it is never spread onto the lines or the VAT.
    """
    for raw in _document_values(data, totals, CASH_DISCOUNT_FIELD):
        if raw in (0, False, "0"):
            continue
        errors.append(f"{CASH_DISCOUNT_FIELD} is not supported: the engine takes that discount "
                      f"off the grand total without spreading it onto the lines or the VAT")
        return


def _within_one_unit(posted: Decimal, exact: Decimal, places: int) -> bool:
    return abs(_CTX.subtract(posted, exact)) <= _grid(places)


def _shown(value: Decimal, places: int) -> str:
    return format(round_amount(value, places), "f")


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

    document_discount = _document_discount(data, totals, places, errors)
    basis = _discount_basis(data, totals, document_discount, errors)
    percentage = _discount_percentage(data, totals, document_discount, errors)
    _refuse_cash_discount(data, totals, errors)

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

    running = allocated = _ZERO
    for row in checked:
        running = _CTX.add(running, row.amount)
        allocated = _CTX.add(allocated, row.allocated)
    # The lines before the document discount: the engine's net total before it is applied.
    before_discount = _CTX.add(running, allocated)
    taxable, vat, grand = (amounts[k] for k in ("total_taxable_amount", "total_vat_amount",
                                                "grand_total"))
    if _CTX.add(taxable, vat) != grand:
        if tax_invoice:
            # The ERP-007 validation every tax invoice print runs next (ZATCA Phase 1, or the
            # neutral check) refuses exactly this with its own error type, which callers rely
            # on; the discount relations below need these totals, so they are not checked first.
            return CheckedAmounts(places, tuple(checked), taxable, vat, grand, _ZERO,
                                  _checked_document(data, lines, checked, amounts), allocated)
        # The engine posts grand total = net total + taxes (L771-785). Worded as the quote and
        # purchase order totals check words it, so the joined message shows it once.
        errors.append(f"Engine totals disagree: taxable {taxable} + VAT {vat} != grand total "
                      f"{grand}")
        return None
    if allocated > document_discount:
        errors.append(f"The lines carry {allocated} of the document discount but "
                      f"{DOCUMENT_DISCOUNT_FIELD} is {document_discount}")
        return None
    if basis == GRAND_TOTAL:
        # The engine spreads all of it: the lines carry the net part, nothing is left over.
        remainder = _ZERO
        if running != taxable:
            errors.append(f"Lines total {running} != total_taxable_amount {taxable} (the engine "
                          f"spreads a {GRAND_TOTAL} discount onto the lines)")
            return None
        base = _CTX.add(grand, document_discount)  # the grand total before the discount
        share = (_CTX.divide(_CTX.multiply(document_discount, before_discount), base)
                 if document_discount > _ZERO else _ZERO)
        if not _within_one_unit(allocated, share, places):
            errors.append(
                f"The lines carry {allocated} of the {GRAND_TOTAL} discount {document_discount}; "
                f"the engine spreads {document_discount} x {before_discount} / {base} = "
                f"{_shown(share, places)} onto them")
            return None
    else:
        base = before_discount
        # The part of the document discount the printed line amounts do not already carry.
        remainder = _CTX.subtract(document_discount, allocated)
        expected = _CTX.subtract(running, remainder)
        if expected != taxable:
            errors.append(
                f"Lines total {running} != total_taxable_amount {taxable}"
                if remainder == _ZERO else
                f"Lines total {running} less the document discount not in the lines {remainder} "
                f"= {expected} != total_taxable_amount {taxable}")
            return None
    if percentage is not None:
        produced = _CTX.divide(_CTX.multiply(base, percentage), Decimal(100))
        if not _within_one_unit(document_discount, produced, places):
            errors.append(f"{PERCENTAGE_FIELD} {percentage} of {basis} {base} is "
                          f"{_shown(produced, places)}, not {DOCUMENT_DISCOUNT_FIELD} "
                          f"{document_discount}")
            return None
    return CheckedAmounts(places, tuple(checked), taxable, vat, grand, remainder,
                          _checked_document(data, lines, checked, amounts), allocated)


def _checked_document(data: Mapping[str, Any], lines: list[Any], checked: list[CheckedLine],
                      amounts: dict[str, Decimal]) -> dict[str, Any]:
    """The snapshot with each checked numeric field replaced by the Decimal the check used.

    A line's ``discount`` becomes what its Discount column prints (its discount plus its
    allocation), whether or not the caller supplied the key, so every printed line reads
    quantity x unit price - discount = amount.
    """
    document = dict(data)
    document["totals"] = {**data["totals"], **amounts}
    out_lines = []
    for line, row in zip(lines, checked):
        patched = dict(line)
        for key, value in (("quantity", row.quantity), ("unit_price", row.unit_price),
                           ("vat_rate", row.vat_rate)):
            if key in patched and value is not None:
                patched[key] = value
        patched["discount"] = row.shown_discount
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
    _refuse_other_names(line, OTHER_LINE_ALLOCATION_FIELDS, f"{pre} ", LINE_ALLOCATION_FIELD,
                        errors)
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
    raw_allocation = line.get(LINE_ALLOCATION_FIELD)
    allocated = (_ZERO if _blank(raw_allocation) else
                 _discount(raw_allocation, f"{pre} {LINE_ALLOCATION_FIELD}", places, errors))
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
    if (allocated or _ZERO) > _ZERO and not supplied:
        errors.append(f"{pre}: {LINE_ALLOCATION_FIELD} {allocated} needs the engine's "
                      f"line_net_amount (the net of the allocation); it is never computed here")
    if (len(errors) > before or qty is None or price is None or discount is None
            or allocated is None):
        return None

    exact = _CTX.subtract(_CTX.subtract(_CTX.multiply(qty, price), discount), allocated)
    try:
        expected = round_amount(exact, places)
    except InvalidOperation:
        errors.append(f"{pre}: amount is out of range")
        return None
    if expected < _ZERO:
        errors.append(f"{pre}: discount {_CTX.add(discount, allocated)} exceeds the line amount "
                      f"{_CTX.multiply(qty, price)}")
        return None
    if supplied:
        name, amount = supplied[0]
        if amount != expected:
            errors.append(f"{pre}: {name} {amount} != quantity {qty} x unit_price {price} "
                          f"- discount {discount}"
                          + (f" - {LINE_ALLOCATION_FIELD} {allocated}" if allocated else "")
                          + f" = {expected}")
            return None
    else:
        amount = expected
        if tax_invoice and expected != exact:
            errors.append(f"{pre}: amount {exact} needs rounding, which the invoice print would "
                          f"do half-even; supply the engine's line_net_amount")
            return None
    return CheckedLine(qty, price, discount, vat_rate, amount, allocated)
