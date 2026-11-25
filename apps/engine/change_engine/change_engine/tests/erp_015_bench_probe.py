"""ERP-015 in-bench probe: post synthetic stock operations and dump what the engine recorded.

Runs inside the bench (``env/bin/python apps/change_engine/change_engine/tests/erp_015_bench_probe.py``) on a
fresh throwaway synthetic site. It never asserts: it writes one JSON document to stdout and the host test
(``test_erp_015_inventory_valuation.py``) checks it. Amounts are read as decimal strings (``CAST(... AS CHAR)``),
so no float sits between the ledger and the checks. Input on stdin: ``{"site": ..., "ops": [...]}`` built by the
host from a seed. Each operation posts on ``POSTING_DATE`` at a later time than the one before, unless it names
its own ``date`` and ``time`` (a back-dated move). The dev bench runs no worker, so after every move the probe runs
the engine's own repost job (``repost_entries``, normally the hourly scheduler job) in-process; the host test checks
the ledger it leaves. The probe changes Stock, System and Accounts settings, so it refuses any site that already
has another company or any GL entry. All names and data are synthetic.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "apps", "change_engine"))

from change_engine.proofs.phase0_bench_proof import (  # noqa: E402
    _FrappeSiteContext,
    _ensure_warehouse,
    _find_account,
)

CO = {"company": "ERP15 Trading KSA", "abbr": "E15K", "country": "Saudi Arabia", "currency": "SAR"}
ITEMS = {"E15-GOLD": "Nos", "E15-HALF": "Nos", "E15-XFER": "Nos", "E15-RECO": "Nos", "E15-DRIFT": "Kg",
         "E15-QTY": "Kg", "E15-BACK": "Nos", "E15-BKIS": "Nos", "E15-BKTX": "Nos"}
WAREHOUSES = ("W1", "W2", "W3")
POSTING_DATE = "2026-03-02"
ENTRY_TYPES = {"receipt": "Material Receipt", "issue": "Material Issue", "transfer": "Material Transfer"}


def _rows(fr, query, values=()):
    return fr.db.sql(query, values, as_dict=True)


def _leaf(fr, doctype):
    return fr.get_all(doctype, filters={"is_group": 0}, pluck="name", order_by="name asc", limit=1)[0]


def _setup(fr):
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete

    name = CO["company"]
    if not fr.db.exists("Company", name):
        setup_complete(fr._dict({
            "country": CO["country"], "currency": CO["currency"], "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31", "company_name": name, "company_abbr": CO["abbr"],
            "chart_of_accounts": "Standard", "domain": "Distribution", "full_name": "ERP15 Owner",
            "email": "owner.erp015@example.invalid", "language": "English",
        }))
    # ADR-0033 and trading scope 4.3 settings, set explicitly before the first stock move (never the defaults).
    fr.db.set_single_value("Stock Settings", "valuation_method", "Moving Average")
    fr.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
    fr.db.set_single_value("System Settings", "rounding_method", "Commercial Rounding")
    fr.db.set_single_value("Accounts Settings", "enable_immutable_ledger", 1)
    fr.clear_cache()
    if not fr.db.exists("UOM", "Kg"):
        fr.get_doc({"doctype": "UOM", "uom_name": "Kg", "must_be_whole_number": 0}).insert(ignore_permissions=True)
    fr.db.set_value("UOM", "Kg", "must_be_whole_number", 0)
    for code, uom in ITEMS.items():
        if not fr.db.exists("Item", code):
            fr.get_doc({"doctype": "Item", "item_code": code, "item_name": f"ERP15 {code}", "stock_uom": uom,
                        "item_group": "All Item Groups", "is_stock_item": 1,
                        "valuation_method": ""}).insert(ignore_permissions=True)
    acc = {
        "stock_in_hand": _find_account(fr, name, "Asset", "Stock In Hand"),
        "srbnb": _find_account(fr, name, "Liability", "Stock Received But Not Billed"),
        "cogs": _find_account(fr, name, "Expense", "Cost of Goods Sold"),
        "stock_adjustment": _find_account(fr, name, "Expense", "Stock Adjustment"),
    }
    cost_center = fr.db.get_value("Company", name, "cost_center")
    fr.db.set_value("Company", name, {
        "enable_perpetual_inventory": 1, "default_inventory_account": acc["stock_in_hand"],
        "stock_received_but_not_billed": acc["srbnb"], "default_expense_account": acc["cogs"],
        "stock_adjustment_account": acc["stock_adjustment"],
        "round_off_account": _find_account(fr, name, "Expense", "Round Off"), "round_off_cost_center": cost_center})
    wh = {label: _ensure_warehouse(fr, name, CO["abbr"], label) for label in WAREHOUSES}
    for w in wh.values():
        fr.db.set_value("Warehouse", w, "account", None)  # every warehouse posts to the company Stock In Hand
    parties = {}
    for doctype, group, label in (("Supplier", "Supplier Group", "supplier"), ("Customer", "Customer Group", "customer")):
        party = f"ERP15 {doctype}"
        if not fr.db.exists(doctype, party):
            extra = {"territory": _leaf(fr, "Territory")} if doctype == "Customer" else {}
            fr.get_doc({"doctype": doctype, f"{label}_name": party, f"{label}_type": "Company",
                        f"{label}_group": _leaf(fr, group), **extra}).insert(ignore_permissions=True)
        parties[label] = party
    for kind in ("Buying", "Selling"):
        plist = f"ERP15 {kind} SAR"
        if not fr.db.exists("Price List", plist):
            fr.get_doc({"doctype": "Price List", "price_list_name": plist, "currency": CO["currency"],
                        kind.lower(): 1}).insert(ignore_permissions=True)
    fr.db.commit()
    return {"accounts": acc, "cost_center": cost_center, "wh": wh, **parties}


def _post(fr, ctx, op, when, vouchers):
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    kind, wh = op["op"], ctx["wh"]
    base = {"company": CO["company"], "posting_date": op.get("date", POSTING_DATE), "posting_time": op.get("time", when),
            "set_posting_time": 1}
    if kind == "cancel":
        doc = fr.get_doc(*vouchers[op["ref"]])
        doc.cancel()
        return doc.doctype, doc.name
    if kind in ENTRY_TYPES:
        row = {"item_code": op["item"], "qty": float(op["qty"]), "cost_center": ctx["cost_center"],
               "expense_account": ctx["accounts"]["stock_adjustment"]}
        if kind != "receipt":
            row["s_warehouse"] = wh[op["wh"]]
        if kind != "issue":
            row["t_warehouse"] = wh[op.get("to_wh", op["wh"])]
        if kind == "receipt":
            row["basic_rate"] = float(op["rate"])
        doc = fr.get_doc({"doctype": "Stock Entry", "stock_entry_type": ENTRY_TYPES[kind], **base, "items": [row]})
    elif kind in ("purchase_receipt", "delivery"):
        buying = kind == "purchase_receipt"
        doc = fr.get_doc({
            "doctype": "Purchase Receipt" if buying else "Delivery Note", **base, "currency": CO["currency"],
            **({"supplier": ctx["supplier"], "buying_price_list": "ERP15 Buying SAR"} if buying else
               {"customer": ctx["customer"], "selling_price_list": "ERP15 Selling SAR"}),
            "items": [{"item_code": op["item"], "qty": float(op["qty"]), "warehouse": wh[op["wh"]],
                       "rate": float(op["rate"]) if buying else 200.0}]})
    elif kind == "purchase_return":
        doc = make_return_doc("Purchase Receipt", vouchers[op["ref"]][1])
        for item in doc.items:
            item.qty = item.received_qty = item.stock_qty = -float(op["qty"])
            item.rejected_qty = 0
        doc.update(base)
    elif kind == "sales_return":
        doc = make_return_doc("Delivery Note", vouchers[op["ref"]][1])
        doc.update(base)
    elif kind == "reconcile":
        doc = fr.get_doc({"doctype": "Stock Reconciliation", "purpose": "Stock Reconciliation", **base,
                          "expense_account": ctx["accounts"]["stock_adjustment"], "cost_center": ctx["cost_center"],
                          "items": [{"item_code": op["item"], "warehouse": wh[op["wh"]], "qty": float(op["qty"]),
                                     "valuation_rate": float(op["rate"])}]})
    else:
        raise ValueError(f"unknown op {kind}")
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.doctype, doc.name


def _run_reposts(fr):
    """Run the queued valuation reposts now, with the engine's own scheduler job (no worker on the dev bench)."""
    from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost_entries

    if fr.db.exists("Repost Item Valuation", {"docstatus": 1, "status": ["in", ["Queued", "In Progress"]]}):
        repost_entries()
        fr.db.commit()


def _refuse_a_used_site(fr):
    """Before any setting changes: a site with ERP-015 postings, another company or any GL entry is not ours."""
    if fr.db.exists("Stock Ledger Entry", {"item_code": ["like", "E15-%"]}):
        raise SystemExit("site already holds ERP-015 postings: use a fresh disposable site")
    others = [c for c in fr.get_all("Company", pluck="name") if c != CO["company"]]
    if others or fr.db.count("GL Entry"):
        raise SystemExit("site has another company or GL entries: the probe changes Stock, System and Accounts "
                         "settings, so it runs only on a fresh disposable site")


def _settings(fr, ctx):
    from frappe.model.meta import get_field_precision

    name = CO["company"]
    currency = fr.db.get_value("Company", name, "default_currency")
    columns = _rows(fr, "select column_name c, column_type t from information_schema.columns where table_schema = "
                        "database() and table_name = 'tabStock Ledger Entry' and column_name in ('valuation_rate', "
                        "'stock_value', 'stock_value_difference', 'qty_after_transaction')")
    return {
        "valuation_method": fr.db.get_single_value("Stock Settings", "valuation_method"),
        "allow_negative_stock": fr.db.get_single_value("Stock Settings", "allow_negative_stock"),
        "rounding_method": fr.db.get_single_value("System Settings", "rounding_method"),
        "enable_immutable_ledger": fr.db.get_single_value("Accounts Settings", "enable_immutable_ledger"),
        "enable_perpetual_inventory": fr.db.get_value("Company", name, "enable_perpetual_inventory"),
        "company_currency": currency,
        "currency_precision": get_field_precision(fr.get_meta("Stock Ledger Entry").get_field("stock_value"),
                                                  currency=currency),
        "float_precision": fr.db.get_default("float_precision"),
        "item_valuation_methods": [fr.db.get_value("Item", code, "valuation_method") or "" for code in ITEMS],
        "warehouse_accounts": {label: fr.db.get_value("Warehouse", w, "account") for label, w in ctx["wh"].items()},
        "sle_columns": {r["c"]: r["t"] for r in columns},
    }


def main():
    params = json.load(sys.stdin)
    with _FrappeSiteContext(params["site"]) as fr:
        _refuse_a_used_site(fr)
        ctx = _setup(fr)
        results, vouchers = {}, {}
        for i, op in enumerate(params["ops"]):
            when = f"{8 + i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}"
            at = [op.get("date", POSTING_DATE), op.get("time", when)]
            try:
                vtype, vno = _post(fr, ctx, op, when, vouchers)
                fr.db.commit()
                vouchers[op["id"]] = (vtype, vno)
                results[op["id"]] = {"voucher_type": vtype, "voucher_no": vno, "at": at, "error": None}
            except Exception as exc:  # recorded for the host test; a rejected move must leave nothing behind
                fr.db.rollback()
                results[op["id"]] = {"voucher_no": None, "at": at, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
                continue
            _run_reposts(fr)
        labels = {w: label for label, w in ctx["wh"].items()}
        sle = _rows(fr, "select voucher_type, voucher_no, item_code, warehouse, is_cancelled, "
                        "cast(posting_date as char) posting_date, cast(posting_time as char) posting_time, "
                        "cast(actual_qty as char) actual_qty, cast(qty_after_transaction as char) qty_after, "
                        "cast(valuation_rate as char) rate, cast(stock_value as char) value, "
                        "cast(stock_value_difference as char) diff from `tabStock Ledger Entry` "
                        "where item_code like 'E15-%%' order by posting_datetime, creation, name")
        for seq, r in enumerate(sle):
            r["seq"], r["wh"] = seq, labels.get(r["warehouse"], r["warehouse"])
        bins = _rows(fr, "select item_code, warehouse, cast(actual_qty as char) qty, cast(stock_value as char) value "
                         "from `tabBin` where item_code like 'E15-%%'")
        for b in bins:
            b["wh"] = labels.get(b["warehouse"], b["warehouse"])
        gl = _rows(fr, "select voucher_type, voucher_no, company, account, cast(debit as char) debit, "
                       "cast(credit as char) credit, is_cancelled from `tabGL Entry` where company = %s",
                   (CO["company"],))
        reposts = _rows(fr, "select voucher_type, voucher_no, item_code, warehouse, based_on, status, docstatus, "
                            "cast(posting_date as char) posting_date, "
                            "left(coalesce(error_log, ''), 500) error from `tabRepost Item Valuation` order by creation")
        json.dump({"settings": _settings(fr, ctx), "accounts": ctx["accounts"], "results": results, "sle": sle,
                   "bins": bins, "gl": gl, "reposts": reposts}, sys.stdout, default=str)


if __name__ == "__main__":
    main()
