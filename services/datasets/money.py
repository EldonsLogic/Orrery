"""Decimal helpers for the dataset's *test expectations*. Not tax logic: the rate comes from the dataset's config table."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ROUNDING = "ROUND_HALF_UP"  # decimal's half-up is half away from zero for negatives too (matches the golden path rounding rule)


def d(value) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal) -> Decimal:
    """Quantise to 2 decimals, half away from zero."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def s(value: Decimal) -> str:
    return format(q(value), "f")


def compute_totals(lines, doc_discount_percent, vat_rate_percent) -> dict:
    """lines: iterable of (quantity, unit_price, line_discount_percent) as strings or Decimals.

    Order: line gross, line discount (rounded), line net; subtotal; document discount (rounded) on the subtotal;
    net total; VAT (rounded once on the net total) at the single configured rate; total. All amounts 2 decimals.
    """
    line_nets, subtotal = [], Decimal("0")
    for qty, price, disc in lines:
        gross = d(qty) * d(price)
        net = gross - q(gross * d(disc) / 100)
        line_nets.append(net)
        subtotal += net
    doc_discount = q(subtotal * d(doc_discount_percent) / 100)
    net_total = subtotal - doc_discount
    vat_raw = net_total * d(vat_rate_percent) / 100
    vat = q(vat_raw)
    return {
        "line_nets": [s(n) for n in line_nets],
        "subtotal": s(subtotal),
        "document_discount": s(doc_discount),
        "net_total": s(net_total),
        "vat_lines": [{"rate_percent": format(d(vat_rate_percent), "f"), "taxable_amount": s(net_total), "tax_amount": s(vat)}],
        "vat_amount": s(vat),
        "total": s(net_total + vat),
        "vat_unrounded": format(vat_raw.normalize(), "f") if vat_raw else "0",
    }
