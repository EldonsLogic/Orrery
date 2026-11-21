"""ERP-015: inventory valuation correctness tests (Moving Average, ADR-0033), modelled on ERP-014.

Two layers, stdlib only (seeded ``random``, no property-testing dependency):

* Pure tests (always run, CI): a Decimal oracle of Moving Average valuation and the checker that
  compares engine rows with it. They are checked on the ADR-0033 bench figures, on hand-computed forced cases
  and on seeded sequences, and the checker is shown to catch one-cent, FIFO, banker's-rounding, drift,
  cancellation and transfer defects.
* Live tests (skip unless a bench is named): ``erp_015_bench_probe.py`` posts the same seeded synthetic
  operations on a throwaway site and returns the stock ledger, bins and GL as decimal strings. The engine
  computes every figure; this file only checks.

Every expected value comes from first principles in Decimal, never from the engine's valuation code. The
oracle keeps the book value of each item and warehouse in whole currency units, as the ledger does (a sub-cent
value is not a ledger figure), and rounds half away from zero to the currency precision (ADR-0033 decision 2):
* Moving Average (ADR-0033 decision 1): the rate is book value / qty. A receipt books value + qty x rate. An
  issue, delivery or transfer leaves (qty on hand - qty) x rate in stock; the difference is its cost. Issuing
  everything leaves exactly zero, and the next receipt restarts the rate at its own rate.
* A transfer's destination receives exactly the cost the source books out, so the company total never moves.
  A purchase return leaves at its receipt rate. A Stock Reconciliation books qty x the new valuation rate (the
  v1 way to change a valuation rate; v1 has no landed costs).
* A sales return: the expected v1 rule is that it adds back exactly the cost its delivery booked (a credit note
  reverses COGS). The pinned engine values it at the current moving average instead; the main checks follow the
  engine's rule and ``test_6`` keeps the v1 expectation as an expected failure until Q-514 (a) is answered.
* Negative stock is blocked (``Stock Settings.allow_negative_stock = 0``, trading scope section 4.3).
* Quantities: provisioning leaves ``System Settings.float_precision`` unset; the engine's stock ledger then
  rounds the running quantity to 2 decimals while quantity fields accept 3. The seeded moves use 2 decimals;
  ``test_7`` keeps a 3-decimal case as an expected failure until Q-514 (b) is answered; ``test_8`` pins the
  observed engine baseline for it, so the expected failure cannot hide an unrelated one.
* Back-dated entries (trading scope 2.3 keeps the engine's repost on): the oracle values the moves that are
  posted and not cancelled in POSTING order (date, then time), whatever order they were submitted in, which is
  what the engine's repost must leave behind. A cancellation removes its move from that order. An issue is
  rejected if, in posting order, it would leave any move of its item and warehouse without stock. The dev bench
  runs no worker, so the probe runs the engine's own repost job (``repost_entries``, the hourly scheduler job)
  in-process after each move; ``test_9`` checks the result.

Out of scope for v1, so not tested: FIFO and LIFO (ADR-0033 rejects FIFO; the engine default is FIFO and the
live test asserts it is overridden), Landed Cost Voucher (hidden, deferred ERP-011 candidate in the trading
scope), batches and serial numbers (hidden), multi-currency purchases.

Run the live layer against your own bench (never someone else's Compose project, never 127.0.0.1:3306)::

    ERP015_COMPOSE_PROJECT=<your project> ERP015_BENCH_SITE=<fresh synthetic site> \
    PYTHONPATH=apps/engine/change_engine python3 -m unittest \
    apps/engine/change_engine/change_engine/tests/test_erp_015_inventory_valuation.py -v

The site needs a synthetic tenant in its config (``bench --site <site> set-config tenant_id t_<name>``), which
the event stream requires. ``ERP015_EXAMPLES`` (default 40) sets the seeded drift moves, ``ERP015_SEED`` the seed.
The probe refuses a site that already holds its items, another company or any GL entry.
"""
from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
import unittest
from collections import defaultdict
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from pathlib import Path

from change_engine.tests.test_erp_014_accounting_properties import half_away, mirror_mismatch, unbalanced_vouchers

REPO_ROOT = Path(__file__).resolve().parents[5]
COMPOSE_FILE = REPO_ROOT / "infra" / "dev" / "docker" / "docker-compose.dev.yml"
PROBE_FILE = Path(__file__).with_name("erp_015_bench_probe.py")
PROBE = "apps/change_engine/change_engine/tests/erp_015_bench_probe.py"
SEED = int(os.environ.get("ERP015_SEED", "15015"))
EXAMPLES = int(os.environ.get("ERP015_EXAMPLES", "40"))
D0, CENT = Decimal(0), Decimal("0.01")
NEAR_TIE = Decimal("0.0001")  # engine rates carry 9 decimals; only this close to x.xx5 may the stored cent differ
RATE_TOL = Decimal("0.000001")
MOVES = ("receipt", "purchase_receipt", "issue", "delivery", "transfer", "purchase_return", "sales_return",
         "reconcile", "cancel")
ISSUES = ("issue", "delivery", "transfer")  # the moves that negative stock can reject
POSTING_DATE, BACK_DATE = "2026-03-02", "2026-03-01"  # every move posts on POSTING_DATE unless it names a date

# ---- inputs ----

FORCED = [
    # ADR-0033 bench evidence, then returns, a rejected issue, zero stock, a restart, a cancellation, zero again.
    {"id": "g1", "op": "purchase_receipt", "item": "E15-GOLD", "wh": "W1", "qty": "10", "rate": "100.00"},
    {"id": "g2", "op": "purchase_receipt", "item": "E15-GOLD", "wh": "W1", "qty": "10", "rate": "130.00"},
    {"id": "g3", "op": "delivery", "item": "E15-GOLD", "wh": "W1", "qty": "5"},
    {"id": "g4", "op": "purchase_receipt", "item": "E15-GOLD", "wh": "W1", "qty": "5", "rate": "160.00"},
    {"id": "g5", "op": "purchase_return", "ref": "g2", "qty": "3"},
    {"id": "g6", "op": "sales_return", "ref": "g3"},
    {"id": "g7", "op": "issue", "item": "E15-GOLD", "wh": "W1", "qty": "23"},  # 22 on hand: must be rejected
    {"id": "g8", "op": "issue", "item": "E15-GOLD", "wh": "W1", "qty": "22"},
    {"id": "g9", "op": "receipt", "item": "E15-GOLD", "wh": "W1", "qty": "4", "rate": "99.99"},
    {"id": "g10", "op": "receipt", "item": "E15-GOLD", "wh": "W1", "qty": "2", "rate": "50.00"},
    {"id": "g11", "op": "cancel", "ref": "g10"},
    {"id": "g12", "op": "issue", "item": "E15-GOLD", "wh": "W1", "qty": "5"},  # 4 on hand after the cancel
    {"id": "g13", "op": "issue", "item": "E15-GOLD", "wh": "W1", "qty": "4"},
    {"id": "g14", "op": "issue", "item": "E15-GOLD", "wh": "W1", "qty": "1"},  # zero on hand: must be rejected
    # Half-cent stock values: Commercial Rounding gives 1.01 and 4.01, banker's rounding 1.00 and 4.00.
    {"id": "h1", "op": "receipt", "item": "E15-HALF", "wh": "W1", "qty": "1", "rate": "1.00"},
    {"id": "h2", "op": "receipt", "item": "E15-HALF", "wh": "W1", "qty": "1", "rate": "1.01"},
    {"id": "h3", "op": "issue", "item": "E15-HALF", "wh": "W1", "qty": "1"},
    {"id": "h4", "op": "issue", "item": "E15-HALF", "wh": "W1", "qty": "1"},
    {"id": "h5", "op": "receipt", "item": "E15-HALF", "wh": "W1", "qty": "3", "rate": "2.00"},
    {"id": "h6", "op": "receipt", "item": "E15-HALF", "wh": "W1", "qty": "1", "rate": "2.01"},
    {"id": "h7", "op": "issue", "item": "E15-HALF", "wh": "W1", "qty": "2"},
    {"id": "h8", "op": "issue", "item": "E15-HALF", "wh": "W1", "qty": "2"},
    # Three warehouses: transfers at the source's moving average, an emptied warehouse, a cancelled transfer.
    {"id": "x1", "op": "receipt", "item": "E15-XFER", "wh": "W1", "qty": "10", "rate": "12.00"},
    {"id": "x2", "op": "receipt", "item": "E15-XFER", "wh": "W2", "qty": "3", "rate": "7.33"},
    {"id": "x3", "op": "receipt", "item": "E15-XFER", "wh": "W1", "qty": "7", "rate": "12.50"},
    {"id": "x4", "op": "transfer", "item": "E15-XFER", "wh": "W1", "to_wh": "W2", "qty": "5"},
    {"id": "x5", "op": "transfer", "item": "E15-XFER", "wh": "W2", "to_wh": "W3", "qty": "4"},
    {"id": "x6", "op": "transfer", "item": "E15-XFER", "wh": "W1", "to_wh": "W3", "qty": "12"},
    {"id": "x7", "op": "transfer", "item": "E15-XFER", "wh": "W3", "to_wh": "W1", "qty": "1"},
    {"id": "x8", "op": "cancel", "ref": "x7"},
    # Valuation-rate change through Stock Reconciliation (rate only, then qty and rate).
    {"id": "r1", "op": "receipt", "item": "E15-RECO", "wh": "W1", "qty": "8", "rate": "20.00"},
    {"id": "r2", "op": "issue", "item": "E15-RECO", "wh": "W1", "qty": "3"},
    {"id": "r3", "op": "reconcile", "item": "E15-RECO", "wh": "W1", "qty": "5", "rate": "22.37"},
    {"id": "r4", "op": "issue", "item": "E15-RECO", "wh": "W1", "qty": "2"},
    {"id": "r5", "op": "reconcile", "item": "E15-RECO", "wh": "W1", "qty": "7", "rate": "21.10"},
    {"id": "r6", "op": "issue", "item": "E15-RECO", "wh": "W1", "qty": "7"},
    # Three-decimal quantities: receive and issue the same 12.345 Kg; exactly nothing may remain.
    {"id": "q1", "op": "receipt", "item": "E15-QTY", "wh": "W1", "qty": "12.345", "rate": "10.00"},
    {"id": "q2", "op": "issue", "item": "E15-QTY", "wh": "W1", "qty": "12.345"},
    # Back-dated entries: two receipts dated the day before every other move, then a cancellation of one of
    # them. Each forces the engine to repost b1 and b2 (and the cancellation, b6's starting rate).
    {"id": "b1", "op": "receipt", "item": "E15-BACK", "wh": "W1", "qty": "10", "rate": "50.00"},
    {"id": "b2", "op": "issue", "item": "E15-BACK", "wh": "W1", "qty": "4"},
    {"id": "b3", "op": "receipt", "item": "E15-BACK", "wh": "W1", "qty": "5", "rate": "80.00",
     "date": BACK_DATE, "time": "09:00:00"},
    {"id": "b4", "op": "receipt", "item": "E15-BACK", "wh": "W1", "qty": "6", "rate": "70.00",
     "date": BACK_DATE, "time": "10:00:00"},
    {"id": "b5", "op": "cancel", "ref": "b4"},
    {"id": "b6", "op": "issue", "item": "E15-BACK", "wh": "W1", "qty": "3"},
]
SALES_RETURN_RULE = "current average"  # the engine's rule; "delivery cost" is the v1 expectation (Q-514 a)
QTY_PRECISION_ITEMS = {"E15-QTY"}  # checked only by test_7 and test_8 (Q-514 b)
BACKDATED_ITEMS = {"E15-BACK"}  # checked by test_9, so a repost failure is reported on its own
REJECTED = {"g7", "g12", "g14"}
# Hand-computed from first principles (not by the oracle): rate = value / qty; value rounded half away from zero.
FORCED_EXACT = {
    "g1": {"value": "1000.00", "rate": "100"}, "g2": {"value": "2300.00", "rate": "115"},
    "g3": {"value": "1725.00", "diff": "-575.00", "rate": "115"},  # FIFO would issue 500.00
    "g4": {"value": "2525.00", "rate": "126.25"}, "g5": {"value": "2135.00", "diff": "-390.00"},
    # g6 is a REGRESSION PIN of observed engine behaviour, not an independent expectation: its rule (a sales
    # return at the current average, 5 x 2135.00 / 17) comes from the engine, which ADR-0031 does not let us
    # change, until Q-514 (a) is answered. If (a) is answered "delivery cost", test_1 and test_2 fail by design
    # and V1_SALES_RETURN (test_6) becomes the expectation.
    "g6": {"value": "2762.94", "diff": "627.94"},
    "g8": {"value": "0.00", "diff": "-2762.94"},
    "g9": {"value": "399.96", "rate": "99.99"}, "g13": {"value": "0.00", "diff": "-399.96"},
    "h2": {"value": "2.01", "rate": "1.005"}, "h3": {"value": "1.01", "diff": "-1.00"},
    "h4": {"value": "0.00", "diff": "-1.01"}, "h6": {"value": "8.01", "rate": "2.0025"},
    "h7": {"value": "4.01", "diff": "-4.00"}, "h8": {"value": "0.00", "diff": "-4.01"},
    "r3": {"value": "111.85", "diff": "11.85", "rate": "22.37"}, "r4": {"value": "67.11", "diff": "-44.74"},
    "r5": {"value": "147.70", "diff": "80.59", "rate": "21.10"}, "r6": {"value": "0.00", "diff": "-147.70"},
}
V1_SALES_RETURN = {"g6": {"value": "2710.00", "diff": "575.00"}}  # adds back the 575.00 that g3 booked
# Hand-computed in posting order b3 (5 x 80.00), b1, b2, b6, with b4 cancelled: rate 900.00 / 15 = 60.
# Submitted order without a repost would leave b1 at 500.00 and b2 at 300.00 (-200.00).
BACKDATED_EXACT = {
    "b3": {"value": "400.00", "diff": "400.00", "rate": "80"},
    "b1": {"value": "900.00", "diff": "500.00", "rate": "60"},
    "b2": {"value": "660.00", "diff": "-240.00", "rate": "60"},
    "b6": {"value": "480.00", "diff": "-180.00", "rate": "60"},
}
# While b4 stood (before b5), in posting order b3, b4, b1, b2: b2 left 17 x 1320.00 / 21 = 1068.571... -> 1068.57.
BACKDATED_BEFORE_CANCEL = {"b4": ("820.00", "420.00"), "b2": ("1068.57", "-251.43")}


def make_ops(seed: int, n: int) -> list:
    """The forced cases, then ``n`` seeded moves of E15-DRIFT (Kg to 2 decimals, rates in cents) in W1 and W2,
    ending with every warehouse issued to zero. Issues never exceed stock; only REJECTED ops do."""
    rnd = random.Random(seed)
    ops, on_hand = [dict(o) for o in FORCED], {"W1": D0, "W2": D0}

    def add(op, **kw):
        ops.append({"id": f"d{len(ops) - len(FORCED) + 1}", "op": op, "item": "E15-DRIFT", **kw})

    def qty_upto(limit):
        return Decimal(rnd.randint(1, int(limit * 100))) / 100

    add("receipt", wh="W1", qty="12.34", rate="17.29")
    on_hand["W1"] += Decimal("12.34")
    for _ in range(n):
        stocked = [w for w in on_hand if on_hand[w] > 0]
        roll = rnd.random()
        if roll < 0.4 or not stocked:
            wh, q = rnd.choice(sorted(on_hand)), qty_upto(50)
            add("receipt", wh=wh, qty=str(q), rate=f"{rnd.randint(1, 99999) / 100:.2f}")
            on_hand[wh] += q
        elif roll < 0.7:
            wh = rnd.choice(stocked)
            q = qty_upto(on_hand[wh])
            add("issue", wh=wh, qty=str(q))
            on_hand[wh] -= q
        elif roll < 0.8:
            wh = rnd.choice(stocked)
            add("issue", wh=wh, qty=str(on_hand[wh]))
            on_hand[wh] = D0
        else:
            wh = rnd.choice(stocked)
            to, q = ("W2" if wh == "W1" else "W1"), qty_upto(on_hand[wh])
            add("transfer", wh=wh, to_wh=to, qty=str(q))
            on_hand[wh] -= q
            on_hand[to] += q
    for wh in sorted(on_hand):
        if on_hand[wh] > 0:
            add("issue", wh=wh, qty=str(on_hand[wh]))
    return ops


# ---- exact oracle (test code: it checks, it never posts) ----

def slot(i: int) -> str:
    """The posting time the probe gives the i-th submitted operation (unless the operation names one)."""
    return f"{8 + i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}"


def posting_keys(ops) -> dict:
    """{op id: (posting date, posting time)}, the order the engine's ledger and repost follow."""
    return {o["id"]: (o.get("date", POSTING_DATE), o.get("time", slot(i))) for i, o in enumerate(ops)}


class _Short(Exception):
    """A move would leave its item and warehouse with negative stock."""


def _replay(live, by_id, sales_return):
    """Value ``live`` (posted, not cancelled, already in posting order) from an empty book. Returns
    ({op id: effects}, book). Raises _Short on negative stock."""
    book, out = {}, {}
    for op in live:
        oid, kind = op["id"], op["op"]
        src = by_id[op["ref"]] if "ref" in op else op
        item, wh = src["item"], src["wh"]
        qty, val = book.get((item, wh), (D0, D0))
        q = Decimal(op["qty"]) if "qty" in op else None
        if kind in ("receipt", "purchase_receipt"):
            moves = [(wh, q, val + q * Decimal(op["rate"]))]
        elif kind in ISSUES:
            if q > qty:
                raise _Short(oid)
            left = D0 if q == qty else (qty - q) * val / qty
            moves = [(wh, -q, left)]
            if kind == "transfer":
                dq, dv = book.get((item, op["to_wh"]), (D0, D0))
                moves.append((op["to_wh"], q, dv + val - half_away(left)))
        elif kind == "purchase_return":
            if q >= qty:
                raise ValueError(f"{oid}: v1 tests never return the whole stock to a supplier")
            moves = [(wh, -q, val - q * Decimal(src["rate"]))]
        elif kind == "sales_return":
            e = out[op["ref"]][0]
            if sales_return == "delivery cost":
                moves = [(wh, -e["dqty"], val - e["dvalue"])]
            else:
                moves = [(wh, -e["dqty"], (qty - e["dqty"]) * val / qty)]
        elif kind == "reconcile":
            moves = [(wh, q, q * Decimal(op["rate"]))]
        else:
            raise ValueError(f"unknown op {kind}")
        effects = []
        for w, nq_or_dq, raw in moves:
            qty, val = book.get((item, w), (D0, D0))
            nq = nq_or_dq if kind == "reconcile" else qty + nq_or_dq
            nv = half_away(raw)
            if nq < 0:
                raise _Short(oid)
            if nq == 0 and nv != 0:
                raise ValueError(f"{oid}: stock would keep value at zero qty")
            book[(item, w)] = (nq, nv)
            effects.append({"item": item, "wh": w, "dqty": nq - qty, "dvalue": nv - val, "qty": nq, "value": nv,
                            "raw": raw, "reconcile": kind == "reconcile"})
        out[oid] = effects
    return out, book


def simulate(ops, sales_return=SALES_RETURN_RULE):
    """Moving Average on whole-cent book values, in posting order. Operations are submitted in list order;
    after each one the posted, uncancelled moves are revalued in posting order (what the engine's repost
    does), so a back-dated move or a cancellation changes the moves posted after it. Returns
    ({op id: {"effects": [...], "at", "reject", "cancels"}}, final book), where ``at`` is the op's posting
    (date, time) in the whole run (so it stays right on a subset of the ops). An effect is one (item, wh) row: dqty,
    dvalue, qty and value after, and ``raw``, the value before rounding to the cent (used only to spot half-cent
    ties). A cancelled move keeps the effects it had when it was last posted."""
    by_id, keys = {o["id"]: o for o in ops}, posting_keys(ops)
    live, effects, book, out = [], {}, {}, {}
    for op in ops:
        oid = op["id"]
        if op["op"] == "cancel":
            trial = [o for o in live if o["id"] != op["ref"]]
            out[oid] = {"effects": [], "cancels": op["ref"]}
        else:
            trial = sorted(live + [op], key=lambda o: keys[o["id"]])
        try:
            now, book_now = _replay(trial, by_id, sales_return)
        except _Short as short:
            if op["op"] not in ISSUES:
                raise ValueError(f"{oid}: would leave {short} with negative stock") from None
            out[oid] = {"effects": [], "reject": True}
            continue
        live, book = trial, book_now
        effects.update(now)
    for op in ops:
        if op["id"] not in out:
            out[op["id"]] = {"effects": effects[op["id"]]}
        out[op["id"]]["at"] = keys[op["id"]]
    return out, book


def item_of(op, ops):
    return op.get("item") or item_of(next(o for o in ops if o["id"] == op["ref"]), ops)


def subset(ops, final, data, keep):
    """The operations, final book and engine rows of the items for which ``keep(item)`` is true."""
    return ([o for o in ops if keep(item_of(o, ops))], {k: v for k, v in final.items() if keep(k[0])},
            data["results"], [r for r in data["sle"] if keep(r["item_code"])],
            [b for b in data["bins"] if keep(b["item_code"])])


def posted_at(row) -> tuple:
    """A ledger row's (posting date, posting time) as the probe dumps them (CAST AS CHAR), normalised."""
    return str(row["posting_date"])[:10], str(row["posting_time"]).split(".")[0].zfill(8)


def cents_ok(engine: Decimal, exact: Decimal) -> bool:
    """The stored value is ``exact`` rounded half away from zero; one cent either way only within NEAR_TIE of
    a half cent, where the engine's 9-decimal stored rate may fall on the other side."""
    want = half_away(exact)
    if engine == want:
        return True
    tie = ((exact * 100).to_integral_value(ROUND_FLOOR) + Decimal("0.5")) / 100
    return abs(exact - tie) <= NEAR_TIE and abs(engine - want) <= CENT


def check_run(ops, sim, final, results, sle, bins):
    """Compare the engine's stock ledger and bins with the oracle. Returns a list of problems (empty = pass)."""
    problems, active, every = [], defaultdict(list), defaultdict(list)
    for r in sle:
        every[r["voucher_no"]].append(r)
        if not int(r["is_cancelled"]):
            active[r["voucher_no"]].append(r)
    cancelled = {o["ref"] for o in ops if o["op"] == "cancel"}
    for op in ops:
        oid, res, exp = op["id"], results[op["id"]], sim[op["id"]]
        if op["op"] != "cancel" and tuple(res.get("at") or ()) != exp["at"]:
            problems.append(f"{oid}: posted at {res.get('at')}, the oracle orders it at {exp['at']}")
        if exp.get("reject"):
            if "NegativeStock" not in (res.get("error") or ""):
                problems.append(f"{oid}: not rejected for negative stock: {res.get('error') or 'it posted'}")
            # Nothing may be left behind: no row of its voucher, and no row of its item and warehouses at its
            # posting time (on the live path a rejected move has no voucher, so the time is what identifies it).
            whs, at = {op["wh"], op.get("to_wh")}, tuple(res.get("at") or ())
            left = [r for r in sle if (res.get("voucher_no") and r["voucher_no"] == res["voucher_no"])
                    or (r["item_code"] == op["item"] and r["wh"] in whs and posted_at(r) == at)]
            if left or not at:
                problems.append(f"{oid}: a rejected move left {len(left)} ledger rows (posting time {at or 'unknown'})")
            continue
        if res.get("error"):
            problems.append(f"{oid}: engine error {res['error']}")
            continue
        if op["op"] == "cancel":
            target = results[op["ref"]]["voucher_no"]
            if active.get(target) or not every.get(target):
                problems.append(f"{oid}: {target} is not fully cancelled in the stock ledger")
            continue
        rows = active.get(res["voucher_no"], [])
        if oid in cancelled:
            continue
        if len(rows) != len(exp["effects"]):
            problems.append(f"{oid}: {len(rows)} ledger rows, expected {len(exp['effects'])}")
            continue
        for e in exp["effects"]:
            row = next((r for r in rows if r["item_code"] == e["item"] and r["wh"] == e["wh"]), None)
            if row is None:
                problems.append(f"{oid}: no ledger row for {e['item']} in {e['wh']}")
                continue
            moved = D0 if e["reconcile"] else e["dqty"]  # the engine stores 0 moved qty on a reconciliation
            if Decimal(row["actual_qty"]) != moved or Decimal(row["qty_after"]) != e["qty"]:
                problems.append(f"{oid} {e['wh']}: qty {row['actual_qty']}/{row['qty_after']}, want {moved}/{e['qty']}")
            if not cents_ok(Decimal(row["value"]), e["raw"]):
                problems.append(f"{oid} {e['wh']}: value {row['value']}, want {e['value']}")
            if e["qty"] and abs(Decimal(row["rate"]) - e["value"] / e["qty"]) > RATE_TOL:
                problems.append(f"{oid} {e['wh']}: rate {row['rate']}, want {e['value'] / e['qty']}")
    chains = defaultdict(list)
    for v_rows in active.values():
        for r in v_rows:
            chains[(r["item_code"], r["wh"])].append(r)
    for key, rows in chains.items():
        prev = D0
        for r in sorted(rows, key=lambda x: x["seq"]):  # the ledger difference is the change in stored value
            if Decimal(r["diff"]) != Decimal(r["value"]) - prev:
                problems.append(f"{r['voucher_no']} {key}: difference {r['diff']} != {r['value']} - {prev}")
            prev = Decimal(r["value"])
    for op in ops:
        if op["op"] == "transfer" and op["id"] not in cancelled and not results[op["id"]].get("error"):
            total = sum((Decimal(r["diff"]) for r in active.get(results[op["id"]]["voucher_no"], [])), D0)
            if total:
                problems.append(f"{op['id']}: transfer changed total stock value by {total}")
    seen = {(b["item_code"], b["wh"]) for b in bins}
    for key, (qty, val) in final.items():
        b = next((x for x in bins if (x["item_code"], x["wh"]) == key), None)
        if b is None or Decimal(b["qty"]) != qty or not cents_ok(Decimal(b["value"]), val):
            problems.append(f"bin {key}: {b and (b['qty'], b['value'])}, exact ({qty}, {val})")
        elif chains.get(key) and Decimal(b["value"]) != Decimal(max(chains[key], key=lambda x: x["seq"])["value"]):
            problems.append(f"bin {key}: value differs from the last ledger row")
    problems += [f"bin {k}: not expected" for k in seen - set(final)]
    problems += [f"{r['voucher_no']}: off-cent {f} {r[f]}" for r in sle for f in ("value", "diff")
                 if Decimal(r[f]) != half_away(Decimal(r[f]))]
    return problems


def forced_exact_problems(results, sle, cases=None):
    problems = []
    for oid, want in (cases or FORCED_EXACT).items():
        rows = [r for r in sle if r["voucher_no"] == results[oid]["voucher_no"] and not int(r["is_cancelled"])]
        if len(rows) != 1:
            problems.append(f"{oid}: {len(rows)} active rows")
            continue
        for field, value in want.items():
            if Decimal(rows[0][field]) != Decimal(value):
                problems.append(f"{oid}: {field} {rows[0][field]}, want {value}")
    return problems


def perfect_engine(ops, sim):
    """Synthetic engine output that follows the documented rules (values stored half away from zero, rates
    to 9 decimals, ledger rows in posting order after the repost, a rejected move posts nothing and has no
    voucher). Only the pure layer uses it, to show the checker passes it and catches mutations."""
    keys, results, sle, stored = posting_keys(ops), {}, [], {}
    cancelled = {o["ref"] for o in ops if o["op"] == "cancel"}
    for op in ops:
        reject = sim[op["id"]].get("reject")
        results[op["id"]] = {"voucher_no": None if reject else f"V-{op['id']}", "at": list(keys[op["id"]]),
                             "error": "NegativeStockError: insufficient stock" if reject else None}
    posted = [o for o in ops if o["op"] != "cancel" and not sim[o["id"]].get("reject")]
    for op in sorted(posted, key=lambda o: keys[o["id"]]):
        for e in sim[op["id"]]["effects"]:
            key, value, active = (e["item"], e["wh"]), e["value"], op["id"] not in cancelled
            rate = (value / e["qty"]).quantize(Decimal("1e-9")) if e["qty"] else D0
            sle.append({"voucher_no": f"V-{op['id']}", "item_code": e["item"], "wh": e["wh"], "seq": len(sle),
                        "is_cancelled": int(not active), "posting_date": keys[op["id"]][0],
                        "posting_time": keys[op["id"]][1], "actual_qty": str(D0 if e["reconcile"] else e["dqty"]),
                        "qty_after": str(e["qty"]), "rate": str(rate), "value": str(value),
                        "diff": str(value - stored.get(key, D0) if active else e["dvalue"])})
            if active:
                stored[key] = value
    _, final = simulate(ops)
    bins = [{"item_code": i, "wh": w, "qty": str(q), "value": str(v)} for (i, w), (q, v) in final.items()]
    return results, sle, bins


# ---- pure layer ----

class TestOracleAndChecker(unittest.TestCase):
    def test_oracle_matches_the_hand_computed_cases(self):
        sim, _ = simulate(make_ops(SEED, 1))
        for oid, want in FORCED_EXACT.items():
            e = sim[oid]["effects"][0]
            got = {"value": e["value"], "diff": e["dvalue"], "rate": e["value"] / e["qty"] if e["qty"] else None}
            for field, value in want.items():
                self.assertEqual(got[field], Decimal(value), f"{oid} {field}")
        self.assertEqual(sim["h3"]["effects"][0]["raw"], Decimal("1.005"))
        self.assertEqual(Decimal("1.005").quantize(CENT, ROUND_HALF_EVEN), Decimal("1.00"), "banker's would differ")
        self.assertEqual(5 * Decimal(100), Decimal("500"), "FIFO issues the oldest 100.00 layer, not 115")
        self.assertEqual({o for o, s in sim.items() if s.get("reject")}, REJECTED)
        v1, _ = simulate(make_ops(SEED, 1), sales_return="delivery cost")
        for oid, want in V1_SALES_RETURN.items():
            self.assertEqual((v1[oid]["effects"][0]["value"], v1[oid]["effects"][0]["dvalue"]),
                             (Decimal(want["value"]), Decimal(want["diff"])))
        self.assertEqual((sim["q2"]["effects"][0]["qty"], sim["q2"]["effects"][0]["value"]), (D0, D0))
        for oid, want in BACKDATED_EXACT.items():
            e = sim[oid]["effects"][0]
            got = {"value": e["value"], "diff": e["dvalue"], "rate": e["value"] / e["qty"]}
            for field, value in want.items():
                self.assertEqual(got[field], Decimal(value), f"{oid} {field}")

    def test_oracle_replays_back_dated_moves_in_posting_order(self):
        ops = make_ops(SEED, 1)
        cut = [o["id"] for o in ops].index("b5")
        before, _ = simulate(ops[:cut])  # b4 still stands
        for oid, (value, diff) in BACKDATED_BEFORE_CANCEL.items():
            e = before[oid]["effects"][0]
            self.assertEqual((e["value"], e["dvalue"]), (Decimal(value), Decimal(diff)), oid)
        sim, final = simulate(ops)
        self.assertEqual(final[("E15-BACK", "W1")], (Decimal(8), Decimal("480.00")))
        self.assertEqual(sim["b4"]["effects"][0]["value"], Decimal("820.00"), "a cancelled move keeps its last value")
        # Submission order is not posting order: without the dates the same moves value b2 at 50 a unit.
        undated = [{k: v for k, v in o.items() if k not in ("date", "time")} for o in ops]
        flat, _ = simulate(undated)
        self.assertEqual((flat["b2"]["effects"][0]["value"], flat["b2"]["effects"][0]["dvalue"]),
                         (Decimal("300.00"), Decimal("-200.00")))
        base = [{"id": "k1", "op": "receipt", "item": "I", "wh": "W1", "qty": "5", "rate": "10.00"},
                {"id": "k2", "op": "issue", "item": "I", "wh": "W1", "qty": "5"},
                {"id": "k3", "op": "receipt", "item": "I", "wh": "W1", "qty": "2", "rate": "12.00",
                 "date": BACK_DATE, "time": "09:00:00"}]
        sim, final = simulate(base)  # posting order k3, k1, k2: k2 leaves 2 x 74.00 / 7 = 21.142... -> 21.14
        self.assertEqual((sim["k2"]["effects"][0]["value"], final[("I", "W1")]),
                         (Decimal("21.14"), (2, Decimal("21.14"))))
        # A back-dated issue that has stock on its own date but would leave k2 short is rejected.
        late_short = base + [{"id": "k4", "op": "issue", "item": "I", "wh": "W1", "qty": "1", "date": BACK_DATE,
                              "time": "10:00:00"}, {"id": "k5", "op": "issue", "item": "I", "wh": "W1", "qty": "2"}]
        sim, final = simulate(late_short)
        self.assertEqual((sim["k4"].get("reject"), sim["k5"].get("reject")), (None, True))
        self.assertEqual(final[("I", "W1")], (1, Decimal("10.33")))  # k3, k4, k1, k2: 1 x 62.00 / 6
        with self.assertRaises(ValueError):  # cancelling k3 would leave k4 short in posting order
            simulate(late_short + [{"id": "k6", "op": "cancel", "ref": "k3"}])

    def test_oracle_invariants_on_seeded_sequences(self):
        for k in range(25):
            ops = make_ops(SEED + k, EXAMPLES)
            sim, final = simulate(ops)
            for op in ops:
                for e in sim[op["id"]]["effects"]:
                    self.assertGreaterEqual(e["qty"], 0)
                    self.assertEqual(e["value"], half_away(e["value"]), "book values are whole cents")
                    self.assertLessEqual(abs(e["value"] - e["raw"]), CENT / 2)
                if op["op"] == "transfer":  # the destination receives exactly what the source books out
                    src, dst = sim[op["id"]]["effects"]
                    self.assertEqual(dst["dvalue"], -src["dvalue"])
            self.assertEqual(final[("E15-GOLD", "W1")], (D0, D0))
            self.assertEqual(sim["g11"]["cancels"], "g10")
            self.assertEqual({k_: v for k_, v in final.items() if k_[0] == "E15-DRIFT"},
                             {("E15-DRIFT", "W1"): (D0, D0), ("E15-DRIFT", "W2"): (D0, D0)})

    def test_checker_passes_a_correct_engine(self):
        ops = make_ops(SEED, EXAMPLES)
        sim, final = simulate(ops)
        results, sle, bins = perfect_engine(ops, sim)
        self.assertEqual(check_run(ops, sim, final, results, sle, bins), [])
        self.assertEqual(forced_exact_problems(results, sle), [])
        self.assertEqual(forced_exact_problems(results, sle, BACKDATED_EXACT), [])
        data = {"results": results, "sle": sle, "bins": bins}  # the live tests check item subsets of one run
        for keep in (lambda i: i in BACKDATED_ITEMS, lambda i: i in QTY_PRECISION_ITEMS,
                     lambda i: i not in QTY_PRECISION_ITEMS | BACKDATED_ITEMS):
            ops_k, final_k, results_k, sle_k, bins_k = subset(ops, final, data, keep)
            self.assertEqual(check_run(ops_k, sim, final_k, results_k, sle_k, bins_k), [])

    def test_checker_catches_defects(self):
        ops = make_ops(SEED, EXAMPLES)
        sim, final = simulate(ops)

        def run(mutate):
            results, sle, bins = perfect_engine(ops, sim)
            mutate(results, sle, bins)
            return check_run(ops, sim, final, results, sle, bins) + forced_exact_problems(results, sle)

        def row(sle, oid, wh=None):
            return next(r for r in sle if r["voucher_no"] == f"V-{oid}" and (wh is None or r["wh"] == wh))

        def bump(r, amount):
            r["value"] = str(Decimal(r["value"]) + amount)
            r["diff"] = str(Decimal(r["diff"]) + amount)

        cases = {
            "one cent": lambda res, s, b: bump(row(s, "d3"), CENT),
            "FIFO issue": lambda res, s, b: (row(s, "g3").update(value="1800.00", diff="-500.00")),
            "banker's rounding": lambda res, s, b: (row(s, "h3").update(value="1.00", diff="-1.01")),
            "drift": lambda res, s, b: [bump(r, Decimal("0.003") * i) for i, r in
                                        enumerate(x for x in s if x["item_code"] == "E15-DRIFT")],
            "cancel left active": lambda res, s, b: row(s, "x7", "W1").update(is_cancelled=0),
            "transfer leak": lambda res, s, b: bump(row(s, "x4", "W2"), CENT),
            "negative stock allowed": lambda res, s, b: res["g7"].update(error=None),
            "rate off": lambda res, s, b: row(s, "g4").update(rate="126.26"),
            "unrounded value": lambda res, s, b: row(s, "h3").update(value="1.005", diff="-1.005"),
            "bin differs": lambda res, s, b: b[0].update(value=str(Decimal(b[0]["value"]) + 1)),
            "rejected for another reason": lambda res, s, b: res["g7"].update(error="ValidationError: closed period"),
            "rejected move left a row": lambda res, s, b: s.append(
                {**row(s, "g6"), "voucher_no": "V-orphan", "seq": len(s), "posting_time": res["g7"]["at"][1]}),
            "posted at another time": lambda res, s, b: res["b3"].update(at=[POSTING_DATE, "23:00:00"]),
            "back-dated receipt not reposted": lambda res, s, b: [
                row(s, "b1").update(value="500.00", diff="500.00", rate="50"),
                row(s, "b2").update(value="300.00", diff="-200.00", rate="50"),
                row(s, "b6").update(value="225.00", diff="-75.00", rate="50")],
            "cancelled back-dated receipt not reposted": lambda res, s, b: row(s, "b2").update(
                value="1068.57", diff="-251.43", rate=str((Decimal("1068.57") / 11).quantize(Decimal("1e-9")))),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.assertTrue(run(mutate), f"checker missed: {name}")

    def test_inputs_are_deterministic_and_bounded(self):
        for n in (1, EXAMPLES):
            a = make_ops(SEED, n)
            self.assertEqual(a, make_ops(SEED, n))
            self.assertEqual(a[:len(FORCED)], FORCED)
            self.assertEqual(len({o["id"] for o in a}), len(a))
            self.assertTrue(all(o["op"] in MOVES for o in a))
            self.assertTrue(all(Decimal(o["qty"]) > 0 for o in a if "qty" in o))
            ids, by_id = [o["id"] for o in a], {o["id"]: o for o in a}
            for o in a:
                if o["op"] == "cancel":  # the probe cancels the move it just submitted (b4 is back-dated)
                    self.assertEqual(ids.index(o["id"]), ids.index(o["ref"]) + 1)
                if "date" in o:  # back-dated moves post the day before every other move, at a time of their own
                    self.assertEqual((o["date"], o["op"]), (BACK_DATE, "receipt"))
                    self.assertLess(BACK_DATE, POSTING_DATE)
            self.assertEqual(by_id["b4"].get("date"), BACK_DATE, "b5 cancels a back-dated move")
            keys = list(posting_keys(a).values())
            self.assertEqual(len(set(keys)), len(keys), "every move has its own posting time")
            simulate(a)  # raises on negative stock, whole-stock purchase returns and cancels that leave a gap

    def test_live_bench_env_is_all_or_nothing(self):
        """Fail closed: one variable alone (or REQUIRE_ERP015_LIVE=1 without a bench) must not skip silently."""
        project, site = os.environ.get("ERP015_COMPOSE_PROJECT"), os.environ.get("ERP015_BENCH_SITE")
        self.assertEqual(bool(project), bool(site), "set both ERP015_COMPOSE_PROJECT and ERP015_BENCH_SITE, or neither")
        if os.environ.get("REQUIRE_ERP015_LIVE") == "1":
            self.assertTrue(project and site, "REQUIRE_ERP015_LIVE=1 but no bench is configured")

    def test_probe_is_valid_python_with_the_expected_shape(self):
        tree = ast.parse(PROBE_FILE.read_text(encoding="utf-8"), filename=str(PROBE_FILE))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "json", "os", "sys", "change_engine", "erpnext", "frappe"})
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Assert)], "the probe never asserts")
        self.assertIn("main", {n.name for n in tree.body if isinstance(n, ast.FunctionDef)})
        source = PROBE_FILE.read_text(encoding="utf-8")
        self.assertNotIn("127.0.0.1", source)
        self.assertTrue(f'POSTING_DATE = "{POSTING_DATE}"' in source, "the probe and the oracle share the posting date")
        self.assertTrue("repost_entries" in source, "the probe runs the engine's repost job")
        self.assertNotIn("3306", source)


# ---- live layer ----

@unittest.skipUnless(os.environ.get("ERP015_COMPOSE_PROJECT") and os.environ.get("ERP015_BENCH_SITE"),
                     "No bench configured: set ERP015_COMPOSE_PROJECT and ERP015_BENCH_SITE to a fresh synthetic "
                     "site on your own Compose project (see module docstring)")
class TestLiveInventoryValuation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ops = make_ops(SEED, EXAMPLES)
        cls.sim, cls.final = simulate(cls.ops)
        payload = json.dumps({"site": os.environ["ERP015_BENCH_SITE"], "ops": cls.ops})
        res = subprocess.run(
            ["docker", "compose", "--project-name", os.environ["ERP015_COMPOSE_PROJECT"], "--env-file", os.devnull,
             "-f", str(COMPOSE_FILE), "exec", "-T", "engine", "env/bin/python", PROBE],
            input=payload, capture_output=True, text=True, timeout=1800, check=False,
            env={**os.environ, "DB_ROOT_PASSWORD": "unused", "ADMIN_PASSWORD": "unused"})
        if res.returncode != 0:
            raise RuntimeError(f"probe failed rc={res.returncode}:\n{res.stderr[-4000:]}")
        cls.data = json.loads(res.stdout[res.stdout.index('{"settings"'):])

    def test_0_configuration_is_the_adr_0033_one(self):
        s = self.data["settings"]
        self.assertEqual(s["valuation_method"], "Moving Average")
        self.assertEqual(s["item_valuation_methods"], [""] * len(s["item_valuation_methods"]), "items inherit")
        self.assertEqual(int(s["allow_negative_stock"]), 0)
        self.assertEqual(s["rounding_method"], "Commercial Rounding")
        self.assertEqual(int(s["enable_perpetual_inventory"]), 1)
        self.assertEqual((s["company_currency"], int(s["currency_precision"])), ("SAR", 2))
        self.assertTrue(s["sle_columns"]["valuation_rate"].endswith(",9)"), s["sle_columns"])

    def test_1_stock_ledger_follows_moving_average(self):
        ops, final, results, sle, bins = subset(self.ops, self.final, self.data,
                                                lambda item: item not in QTY_PRECISION_ITEMS | BACKDATED_ITEMS)
        self.assertEqual(check_run(ops, self.sim, final, results, sle, bins), [])

    def test_2_forced_cases_are_exact(self):
        self.assertEqual(forced_exact_problems(self.data["results"], self.data["sle"]), [])

    def test_3_rejected_issues_name_negative_stock(self):
        for oid in REJECTED:
            self.assertIn("NegativeStock", self.data["results"][oid]["error"] or "", oid)

    def test_4_stock_ledger_ties_to_the_gl(self):
        d, acc = self.data, self.data["accounts"]
        gl = [r for r in d["gl"] if not int(r["is_cancelled"])]
        self.assertEqual(unbalanced_vouchers(d["gl"]), {})
        sle_sum, gl_stock = defaultdict(Decimal), defaultdict(Decimal)
        for r in d["sle"]:
            if not int(r["is_cancelled"]):
                sle_sum[r["voucher_no"]] += Decimal(r["diff"])
        for r in gl:
            if r["account"] == acc["stock_in_hand"]:
                gl_stock[r["voucher_no"]] += Decimal(r["debit"]) - Decimal(r["credit"])
        bins = sum((Decimal(b["value"]) for b in d["bins"]), D0)
        self.assertEqual(sum(gl_stock.values(), D0), sum(sle_sum.values(), D0))
        self.assertEqual(sum(sle_sum.values(), D0), bins)
        offset = {"Purchase Receipt": acc["srbnb"], "Delivery Note": acc["cogs"],
                  "Stock Entry": acc["stock_adjustment"], "Stock Reconciliation": acc["stock_adjustment"]}
        vtype = {r["voucher_no"]: r["voucher_type"] for r in d["sle"]}
        for voucher, total in sle_sum.items():
            with self.subTest(voucher):
                self.assertEqual(gl_stock[voucher], total)
                other = sum((Decimal(r["debit"]) - Decimal(r["credit"]) for r in gl
                             if r["voucher_no"] == voucher and r["account"] == offset[vtype[voucher]]), D0)
                self.assertEqual(other, -total)
        for oid in ("g1", "g2", "g4"):  # receipt value = qty x rate, credited to Stock Received But Not Billed
            op = next(o for o in self.ops if o["id"] == oid)
            self.assertEqual(sle_sum[d["results"][oid]["voucher_no"]], Decimal(op["qty"]) * Decimal(op["rate"]))
        amounts = [r[k] for r in d["gl"] for k in ("debit", "credit")]
        self.assertEqual([a for a in amounts if Decimal(a) != half_away(Decimal(a))], [])

    def _gl_by_voucher(self):
        by_voucher = defaultdict(list)
        for r in self.data["gl"]:
            by_voucher[r["voucher_no"]].append(r)
        return by_voucher

    def test_5_cancellations_reverse_exactly(self):
        d, by_voucher = self.data, self._gl_by_voucher()
        rows = by_voucher[d["results"]["g10"]["voucher_no"]]  # receipt g10, cancelled by g11
        self.assertTrue(any(Decimal(r["debit"]) or Decimal(r["credit"]) for r in rows), "g10 posts to the GL")
        self.assertFalse(mirror_mismatch(rows), "a cancellation reverses every GL row exactly")
        # x7 (cancelled by x8) moves stock between warehouses on the same account at zero difference: no GL rows.
        self.assertEqual(by_voucher[d["results"]["x7"]["voucher_no"]], [])

    @staticmethod
    def _not_the_known_mismatch(reason):
        """For the expected failures below: when the engine no longer shows the pinned figures, or the data
        cannot be read, the test returns WITHOUT failing. unittest reports a passing ``expectedFailure`` as an
        unexpected success, which fails the run, so the decorator only ever absorbs the known mismatch."""
        print(f"\nERP-015 expected failure is not the known mismatch: {reason}", file=sys.stderr)

    @unittest.expectedFailure  # Q-514 (a): the engine values a Moving Average sales return at the current average
    def test_6_sales_return_adds_back_the_delivery_cost(self):
        d, res = self.data, self.data["results"]
        try:
            pinned = forced_exact_problems(res, d["sle"], {"g6": FORCED_EXACT["g6"]})  # 2762.94 and 627.94
            problems = forced_exact_problems(res, d["sle"], V1_SALES_RETURN)
            by_voucher = self._gl_by_voucher()
            mismatch = mirror_mismatch(by_voucher[res["g3"]["voucher_no"]] + by_voucher[res["g6"]["voucher_no"]])
        except Exception as exc:  # noqa: BLE001 - any read error is reported, never absorbed
            return self._not_the_known_mismatch(f"g3/g6 could not be read: {exc!r}")
        if pinned:
            return self._not_the_known_mismatch(f"g6 is no longer at the observed engine figures: {pinned}")
        # The known mismatch, the only line expected to fail: a full sales return mirrors its delivery.
        self.assertEqual((problems, mismatch), ([], {}))

    @unittest.expectedFailure  # Q-514 (b): with float_precision unset the ledger rounds running qty to 2 decimals
    def test_7_three_decimal_quantities_leave_exact_stock(self):
        d = self.data
        try:
            q1 = [r for r in d["sle"] if r["voucher_no"] == d["results"]["q1"]["voucher_no"]]
            observed = [(Decimal(r["qty_after"]), Decimal(r["rate"])) for r in q1]
            ops, final, results, sle, bins = subset(self.ops, self.final, d, lambda item: item in QTY_PRECISION_ITEMS)
            problems = check_run(ops, self.sim, final, results, sle, bins)
        except Exception as exc:  # noqa: BLE001 - any read error is reported, never absorbed
            return self._not_the_known_mismatch(f"q1/q2 could not be read: {exc!r}")
        if observed != [(Decimal("12.35"), Decimal("9.995951417"))]:
            return self._not_the_known_mismatch(f"q1 is no longer at the observed engine figures: {observed}")
        self.assertEqual(problems, [])  # the known mismatch, the only line expected to fail

    def test_8_three_decimal_quantities_post_at_the_engine_baseline(self):
        """Not an expected failure, so test_7 cannot hide an unrelated one: q1 and q2 post, and the only
        difference from the oracle is the 2-decimal running quantity of Q-514 (b), observed with float_precision
        unset. Revisit together with test_7 when Q-514 (b) is answered."""
        d = self.data
        self.assertIn(d["settings"]["float_precision"], (None, ""), "baseline observed with float_precision unset")
        observed = {"q1": ("12.345", "12.35", "9.995951417", "123.45", "123.45"),
                    "q2": ("-12.345", "0", "9.995951417", "0", "-123.45")}
        for oid, (moved, after, rate, value, diff) in observed.items():
            with self.subTest(oid):
                self.assertIsNone(d["results"][oid]["error"])
                rows = [r for r in d["sle"] if r["voucher_no"] == d["results"][oid]["voucher_no"]]
                self.assertEqual(len(rows), 1)
                got = tuple(Decimal(rows[0][f]) for f in ("actual_qty", "qty_after", "rate", "value", "diff"))
                self.assertEqual(got, tuple(map(Decimal, (moved, after, rate, value, diff))))
        ops, final, results, sle, bins = subset(self.ops, self.final, d, lambda item: item in QTY_PRECISION_ITEMS)
        problems = check_run(ops, self.sim, final, results, sle, bins)
        self.assertEqual([" ".join(p.split()[:3]) for p in problems], ["q1 W1: qty", "q1 W1: rate"], problems)

    def test_9_back_dated_entries_are_reposted_in_posting_order(self):
        """b3 and b4 post the day before every other move and b5 cancels b4. After the engine's repost job the
        ledger, bins and GL must be those of posting order (b3, b1, b2, b6), not of submission order."""
        d, res = self.data, self.data["results"]
        # Item-based reposting (the engine default): each entry names the item and warehouse, not the voucher.
        ours = [r for r in d["reposts"] if r["item_code"] in BACKDATED_ITEMS]
        self.assertGreaterEqual(len(ours), 2, "b3, b4 and the cancellation b5 queue reposts")
        self.assertEqual({r["posting_date"] for r in ours}, {BACK_DATE}, "reposted from the back date")
        self.assertEqual([r for r in d["reposts"] if r["status"] not in ("Completed", "Skipped")], [],
                         "every queued repost ran to completion")
        ops, final, results, sle, bins = subset(self.ops, self.final, d, lambda item: item in BACKDATED_ITEMS)
        self.assertEqual(check_run(ops, self.sim, final, results, sle, bins), [])
        self.assertEqual(forced_exact_problems(res, d["sle"], BACKDATED_EXACT), [])
        by_voucher, acc = self._gl_by_voucher(), d["accounts"]
        for oid, want in BACKDATED_EXACT.items():  # the GL was reposted too: stock account = ledger difference
            with self.subTest(oid):
                rows = [r for r in by_voucher[res[oid]["voucher_no"]] if not int(r["is_cancelled"])]
                net = {a: sum((Decimal(r["debit"]) - Decimal(r["credit"]) for r in rows if r["account"] == a), D0)
                       for a in (acc["stock_in_hand"], acc["stock_adjustment"])}
                self.assertEqual((net[acc["stock_in_hand"]], net[acc["stock_adjustment"]]),
                                 (Decimal(want["diff"]), -Decimal(want["diff"])))
        b4 = by_voucher[res["b4"]["voucher_no"]]
        self.assertTrue(b4, "b4 posted to the GL before it was cancelled")
        self.assertFalse(mirror_mismatch(b4), "the cancelled back-dated receipt is reversed exactly")


if __name__ == "__main__":
    unittest.main()
