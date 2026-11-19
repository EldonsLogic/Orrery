"""Moving-average stock valuation in exact fractions (no Decimal rounding, no dust).

Per (item, warehouse, currency). An issue larger than the quantity on hand (oversell), a negative quantity or a
negative price makes the key `invalid`: its value is excluded and the metric is not compared (SIM-104 already
flags it). A zero-quantity issue is a no-op. When the quantity reaches zero the value is reset to zero.
"""
from __future__ import annotations

from fractions import Fraction

ZERO = Fraction(0)


class StockBook:
    def __init__(self):
        self.pos = {}
        self.bad = set()

    def receive(self, key, qty, price) -> None:
        if key in self.bad:
            return
        if qty < 0 or price < 0:
            self.bad.add(key)
            return
        q, v = self.pos.get(key, (ZERO, ZERO))
        self.pos[key] = (q + Fraction(qty), v + Fraction(qty) * Fraction(price))

    def issue(self, key, qty) -> None:
        if key in self.bad or qty == 0:
            return
        q, v = self.pos.get(key, (ZERO, ZERO))
        qty = Fraction(qty)
        if qty < 0 or qty > q:
            self.bad.add(key)
            return
        v = v - qty * (v / q)
        q = q - qty
        self.pos[key] = (q, ZERO if q == 0 else v)

    def totals(self) -> dict:
        """{currency: exact value} over valid keys (key = (item, warehouse, currency))."""
        out = {}
        for key, (_, v) in self.pos.items():
            if key not in self.bad:
                out[key[2]] = out.get(key[2], ZERO) + v
        return out

    def invalid_currencies(self) -> set:
        return {k[2] for k in self.bad}
