"""Synthetic fixtures for the simulator tests: an anonymised, invented month (no customer data).

The tool set is hand-made in the generated shape (contract 3, section 1.1) with permissive input schemas, so the
tests exercise the simulator rather than one Blueprint's field names. A separate test uses the tool set the real
generator produces for the trading fixture Blueprint.
"""
from __future__ import annotations

import copy

PERIOD = ("2026-03-01", "2026-03-31")
TENANT = "t_sim_demo"
CALLER = {"user_id": "u_replay", "role_ids": ["accountant", "warehouse_keeper"]}
TAX_RATES = {"VAT15": "0.15", "ZERO": "0"}


def _tool(name, risk, roles, transitions=None):
    t = {"name": name, "kind": "write", "risk_class": risk, "requires": {"roles": roles},
         "input_schema": {"type": "object"}, "idempotency": "required"}
    if transitions is not None:
        t["transitions"] = transitions
    return t


def tool_set(ledger_post="R3", stock_post="R2"):
    acc, wh = ["accountant"], ["warehouse_keeper"]
    tools = []
    for ent, roles, post in (("sales_invoice", acc, ledger_post), ("purchase_invoice", acc, ledger_post),
                             ("payment", acc, ledger_post), ("payroll_entry", acc, ledger_post),
                             ("purchase_receipt", wh, stock_post), ("delivery_note", wh, stock_post)):
        tools.append(_tool(f"{ent}.create", "R1", roles))
        tools.append(_tool(f"{ent}.submit", post, roles))
        tools.append(_tool(f"{ent}.list", "R0", roles))
    return {"toolApiVersion": "0.2.0", "blueprintRevision": 3, "contentHash": "sha256:synthetic-tool-set",
            "tools": tools}


MAPPING = {
    "sales_invoice": {"entity": "sales_invoice", "lines": "lines", "post": {"verb": "submit"},
                      "header": {"party": "customer", "date": "posting_date", "due_date": "due_date",
                                 "number": "reference"},
                      "line": {"item": "item", "qty": "quantity", "unit_price": "rate", "tax_code": "tax_code"}},
    "purchase_invoice": {"entity": "purchase_invoice", "lines": "lines", "post": {"verb": "submit"},
                         "header": {"party": "supplier", "date": "posting_date", "due_date": "due_date",
                                    "number": "reference"},
                         "line": {"item": "item", "qty": "quantity", "unit_price": "rate", "tax_code": "tax_code"}},
    "payment_in": {"entity": "payment", "constants": {"direction": "receive"}, "post": {"verb": "submit"},
                   "header": {"party": "party", "date": "posting_date", "against": "against"},
                   "line": {"total": "amount"}},
    "payment_out": {"entity": "payment", "constants": {"direction": "pay"}, "post": {"verb": "submit"},
                    "header": {"party": "party", "date": "posting_date", "against": "against"},
                    "line": {"total": "amount"}},
    "stock_in": {"entity": "purchase_receipt", "lines": "lines", "post": {"verb": "submit"},
                 "header": {"date": "posting_date"},
                 "line": {"item": "item", "warehouse": "warehouse", "qty": "quantity", "unit_price": "unit_cost"}},
    "stock_out": {"entity": "delivery_note", "lines": "lines", "post": {"verb": "submit"},
                  "header": {"date": "posting_date"},
                  "line": {"item": "item", "warehouse": "warehouse", "qty": "quantity"}},
    "payroll_run": {"entity": "payroll_entry", "lines": "employees", "post": {"verb": "submit"},
                    "header": {"date": "posting_date"},
                    "line": {"employee": "employee", "gross": "gross", "deductions": "deductions"}},
}


def row(**kw):
    base = {"sheet": "month", "currency": "SAR"}
    base.update(kw)
    return base


def month_rows():
    """A small invented month. Row numbers are the intake pointers."""
    return [
        row(row=1, type="stock_in", number="GRN-1", date="2026-03-02", item="ITM-A", warehouse="WH-1",
            qty="10", unit_price="20.00"),
        row(row=2, type="purchase_invoice", number="PI-1", date="2026-03-02", party="SUP-1", item="ITM-A",
            qty="10", unit_price="20.00", vat="30.00", tax_code="VAT15", due_date="2026-04-01"),
        row(row=3, type="sales_invoice", number="SI-1", date="2026-03-05", party="CUS-1", item="ITM-A",
            qty="3", unit_price="33.33", vat="14.9985", tax_code="VAT15", due_date="2026-03-20"),
        row(row=4, type="sales_invoice", number="SI-1", date="2026-03-05", party="CUS-1", item="ITM-B",
            qty="1", unit_price="10.01", vat="1.5015", tax_code="VAT15", due_date="2026-03-20"),
        row(row=5, type="stock_out", number="DN-1", date="2026-03-05", item="ITM-A", warehouse="WH-1", qty="3"),
        row(row=6, type="sales_invoice", number="SI-2", date="2026-03-12", party="CUS-2", item="ITM-C",
            qty="1", unit_price="0.10", vat="0.015", tax_code="VAT15"),
        row(row=7, type="sales_invoice", number="SI-2", date="2026-03-12", party="CUS-2", item="ITM-C",
            qty="1", unit_price="0.10", vat="0.015", tax_code="VAT15"),
        row(row=8, type="sales_invoice", number="SI-2", date="2026-03-12", party="CUS-2", item="ITM-C",
            qty="1", unit_price="0.10", vat="0.015", tax_code="VAT15"),
        row(row=9, type="payment_in", number="RC-1", date="2026-03-20", party="CUS-1", total="50.00",
            against="SI-1"),
        row(row=10, type="payroll_run", number="PAY-2026-03", date="2026-03-31", employee="EMP-1",
            gross="8000.00", deductions="800.00"),
        row(row=11, type="payroll_run", number="PAY-2026-03", date="2026-03-31", employee="EMP-2",
            gross="6000.00", deductions="600.00"),
    ]


def port(ts=None, **kw):
    from simulator import SimulatedPort

    return SimulatedPort(ts or tool_set(), copy.deepcopy(MAPPING), tax_rates=TAX_RATES, **kw)


def run(rows=None, ts=None, p=None, **kw):
    from simulator import simulate

    ts = ts or tool_set()
    p = p or port(ts)
    kw.setdefault("tolerances", {"default": {"per_document_minor": 1}})
    report = simulate(rows if rows is not None else month_rows(), tenant_id=TENANT, period=PERIOD, tool_set=ts,
                      mapping=copy.deepcopy(MAPPING), caller=dict(CALLER), port=p, **kw)
    return report, p


def codes(report):
    return [a["code"] for a in report["anomalies"]]


def metric(report, name, ccy="SAR"):
    return next(r for r in report["comparison"] if r["metric"] == name and r["currency"] == ccy)
