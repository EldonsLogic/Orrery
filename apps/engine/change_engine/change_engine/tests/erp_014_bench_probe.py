"""ERP-014 in-bench probe: post synthetic vouchers and dump what the engine recorded.

Runs inside the bench (``env/bin/python apps/change_engine/change_engine/tests/erp_014_bench_probe.py``)
on a throwaway synthetic site. It never asserts: it writes one JSON document to stdout and the host
test (``test_erp_014_accounting_properties.py``) checks the invariants. Amounts are read from the
database as decimal strings (``CAST(... AS CHAR)``) so no float conversion sits between the ledger and
the checks. Input on stdin: ``{"site": ..., "cases": [...], "stock_moves": [...], "rounding_samples": [...]}``
built by the host from a seed. All names and data are synthetic.
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

KSA = {"company": "ERP14 Trading KSA", "abbr": "E14K", "country": "Saudi Arabia", "currency": "SAR", "vat": 15}
UAE = {"company": "ERP14 Trading UAE", "abbr": "E14U", "country": "United Arab Emirates", "currency": "AED", "vat": 5}
SERVICE_ITEMS = {"S": "E14-SVC-STD", "Z": "E14-SVC-ZERO", "E": "E14-SVC-EXEMPT"}
STOCK_ITEM = "ITEM-001"


def _sql_rows(fr, query, values=()):
    return fr.db.sql(query, values, as_dict=True)


def _leaf(fr, doctype):
    return fr.get_all(doctype, filters={"is_group": 0}, pluck="name", order_by="name asc", limit=1)[0]


def _setup(fr):
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete

    if not fr.db.exists("Company", KSA["company"]):
        setup_complete(fr._dict({
            "country": KSA["country"], "currency": KSA["currency"], "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31", "company_name": KSA["company"], "company_abbr": KSA["abbr"],
            "chart_of_accounts": "Standard", "domain": "Distribution", "full_name": "ERP14 Owner",
            "email": "owner.erp014@example.invalid", "language": "English",
        }))
    # ADR-0033 and Q-23 provisioning settings, set explicitly (never the engine defaults).
    fr.db.set_single_value("Stock Settings", "valuation_method", "Moving Average")
    fr.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
    fr.db.set_single_value("System Settings", "rounding_method", "Commercial Rounding")
    fr.db.set_single_value("Accounts Settings", "enable_immutable_ledger", 1)
    fr.clear_cache()
    if not fr.db.exists("Company", UAE["company"]):
        fr.get_doc({"doctype": "Company", "company_name": UAE["company"], "abbr": UAE["abbr"],
                    "country": UAE["country"], "default_currency": UAE["currency"],
                    "chart_of_accounts": "Standard"}).insert(ignore_permissions=True)
    for code in SERVICE_ITEMS.values():
        if not fr.db.exists("Item", code):
            fr.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "All Item Groups",
                        "stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)
    if not fr.db.exists("Item", STOCK_ITEM):
        fr.get_doc({"doctype": "Item", "item_code": STOCK_ITEM, "item_name": "ERP14 widget",
                    "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 1,
                    "valuation_method": ""}).insert(ignore_permissions=True)
    ctx = {}
    for co in (KSA, UAE):
        name = co["company"]
        vat_parent = fr.db.get_value("Account", {"company": name, "account_type": "Tax", "is_group": 1}, "name") \
            or fr.db.get_value("Account", {"company": name, "account_name": "Duties and Taxes"}, "name")
        vat_acc = fr.db.get_value("Account", {"company": name, "account_name": f"VAT {co['vat']}%"}, "name")
        if not vat_acc:
            vat_acc = fr.get_doc({"doctype": "Account", "account_name": f"VAT {co['vat']}%", "company": name,
                                  "parent_account": vat_parent, "account_type": "Tax",
                                  "tax_rate": co["vat"]}).insert(ignore_permissions=True).name
        inv = _find_account(fr, name, "Asset", "Stock In Hand")
        opening = _find_account(fr, name, "Equity", "Temporary Opening")
        income = _find_account(fr, name, "Income", "Sales")
        receivable = _find_account(fr, name, "Asset", "Debtors")
        fr.db.set_value("Company", name, {"enable_perpetual_inventory": 1, "default_inventory_account": inv,
                                          "stock_adjustment_account": opening, "default_income_account": income,
                                          "default_receivable_account": receivable,
                                          "round_off_account": _find_account(fr, name, "Expense", "Round Off"),
                                          "round_off_cost_center": fr.db.get_value("Company", name, "cost_center")})
        cust = f"ERP14 Customer {co['currency']}"
        if not fr.db.exists("Customer", cust):
            fr.get_doc({"doctype": "Customer", "customer_name": cust, "customer_type": "Company",
                        "customer_group": _leaf(fr, "Customer Group"), "territory": _leaf(fr, "Territory"),
                        "default_currency": co["currency"]}).insert(ignore_permissions=True)
        plist = f"ERP14 Selling {co['currency']}"
        if not fr.db.exists("Price List", plist):
            fr.get_doc({"doctype": "Price List", "price_list_name": plist, "currency": co["currency"],
                        "selling": 1}).insert(ignore_permissions=True)
        templates = {}
        for cat in SERVICE_ITEMS:  # S at the full rate; Z (zero-rated) and E (exempt) both 0% on the VAT account
            title = f"ERP14 {cat} {co['abbr']}"
            templates[cat] = fr.db.get_value("Item Tax Template", {"title": title, "company": name}, "name") or \
                fr.get_doc({"doctype": "Item Tax Template", "title": title, "company": name, "taxes": [
                    {"tax_type": vat_acc, "tax_rate": co["vat"] if cat == "S" else 0}]}).insert(
                    ignore_permissions=True).name
        ctx[name] = {"templates": templates, "vat_account": vat_acc, "income_account": income, "inventory_account": inv, "opening_account": opening,
                     "customer": cust, "price_list": plist, "warehouse": _ensure_warehouse(fr, name, co["abbr"], "W1"),
                     "currency": co["currency"], "vat": co["vat"]}
    fr.db.commit()
    return ctx


def _invoice(fr, c, case, lines):
    pct = case.get("discount_percent") or 0
    rows = []
    for ln in lines:
        rows.append({"item_code": SERVICE_ITEMS[ln["category"]], "qty": float(ln["qty"]), "rate": float(ln["rate"]),
                     "item_tax_template": c["templates"][ln["category"]],
                     "income_account": c["income_account"]})
    return fr.get_doc({
        "doctype": "Sales Invoice", "company": case["company"], "customer": c["customer"], "currency": c["currency"],
        "selling_price_list": c["price_list"], "posting_date": "2026-02-10", "set_posting_time": 1,
        "posting_time": "10:00:00", "ignore_pricing_rule": 1, "update_stock": 0, "items": rows,
        **({"apply_discount_on": "Net Total", "additional_discount_percentage": pct} if pct else {}),
        "taxes": [{"charge_type": "On Net Total", "account_head": c["vat_account"], "rate": c["vat"],
                   "description": f"VAT {c['vat']}%"}],
    })


def _run_cases(fr, ctx, cases):
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    out = []
    for case in cases:
        c = ctx[case["company"]]
        si = _invoice(fr, c, case, case["lines"])
        si.insert(ignore_permissions=True)
        si.submit()
        perm = _invoice(fr, c, case, [case["lines"][i] for i in case["permutation"]])
        perm.insert(ignore_permissions=True)  # draft only: totals are computed on insert
        rec = {
            "case_id": case["case_id"], "voucher_no": si.name, "company": case["company"], "vat": c["vat"],
            "lines": [{"net_amount": r["n"], "category": case["lines"][i]["category"]}
                      for i, r in enumerate(_sql_rows(fr, "select cast(net_amount as char) n from `tabSales Invoice Item` "
                                                          "where parent=%s order by idx", (si.name,)))],
            "tax_amount": _sql_rows(fr, "select cast(tax_amount as char) t from `tabSales Taxes and Charges` "
                                        "where parent=%s", (si.name,))[0]["t"],
            "totals": _sql_rows(fr, "select cast(net_total as char) net_total, cast(total_taxes_and_charges as char) "
                                    "taxes, cast(grand_total as char) grand_total from `tabSales Invoice` where name=%s",
                                (si.name,))[0],
            "permuted": _sql_rows(fr, "select cast(net_total as char) net_total, cast(total_taxes_and_charges as char) "
                                      "taxes, cast(grand_total as char) grand_total from `tabSales Invoice` "
                                      "where name=%s", (perm.name,))[0],
        }
        if case["action"] == "return":
            ret = make_return_doc("Sales Invoice", si.name)
            ret.posting_date = "2026-02-11"
            ret.posting_time = "10:00:00"
            ret.set_posting_time = 1
            ret.insert(ignore_permissions=True)
            ret.submit()
            rec["return_voucher_no"] = ret.name
            rec["return_totals"] = _sql_rows(fr, "select cast(total_taxes_and_charges as char) taxes, "
                                                 "cast(grand_total as char) grand_total from `tabSales Invoice` "
                                                 "where name=%s", (ret.name,))[0]
        elif case["action"] == "cancel":
            si.reload()
            si.cancel()
        rec["action"] = case["action"]
        fr.db.commit()
        out.append(rec)
    return out


def _run_stock(fr, ctx, moves):
    """Golden path opening (100 at 10.00) then seeded receipts/issues on ITEM-001 in the KSA company."""
    c = ctx[KSA["company"]]
    docs = []
    for idx, mv in enumerate([{"type": "Material Receipt", "qty": "100", "rate": "10.00"}] + moves):
        row = {"item_code": STOCK_ITEM, "qty": float(mv["qty"]), "expense_account": c["opening_account"]}
        if mv["type"] == "Material Receipt":
            row.update({"t_warehouse": c["warehouse"], "basic_rate": float(mv["rate"])})
        else:
            row.update({"s_warehouse": c["warehouse"]})
        se = fr.get_doc({"doctype": "Stock Entry", "stock_entry_type": mv["type"], "company": KSA["company"],
                         "posting_date": "2026-01-05", "set_posting_time": 1,
                         "posting_time": f"09:{idx // 60:02d}:{idx % 60:02d}", "items": [row]})
        se.insert(ignore_permissions=True)
        se.submit()
        docs.append(se.name)
    fr.db.commit()
    bin_row = _sql_rows(fr, "select cast(actual_qty as char) qty, cast(stock_value as char) value from `tabBin` "
                            "where item_code=%s and warehouse=%s", (STOCK_ITEM, c["warehouse"]))[0]
    sle = _sql_rows(fr, "select cast(coalesce(sum(stock_value_difference),0) as char) v from `tabStock Ledger Entry` "
                        "where item_code=%s and warehouse=%s and is_cancelled=0", (STOCK_ITEM, c["warehouse"]))[0]["v"]
    gl = _sql_rows(fr, "select cast(coalesce(sum(debit)-sum(credit),0) as char) v from `tabGL Entry` "
                       "where account=%s and is_cancelled=0", (c["inventory_account"],))[0]["v"]
    steps = _sql_rows(fr, "select voucher_no, cast(qty_after_transaction as char) qty, cast(stock_value as char) value "
                          "from `tabStock Ledger Entry` where item_code=%s and warehouse=%s and is_cancelled=0 "
                          "order by posting_datetime, creation", (STOCK_ITEM, c["warehouse"]))
    return {"vouchers": docs, "steps": steps, "bin_qty": bin_row["qty"], "bin_value": bin_row["value"], "sle_value": sle,
            "gl_stock_in_hand": gl, "stock_in_hand_account": c["inventory_account"]}


def main():
    params = json.load(sys.stdin)
    with _FrappeSiteContext(params["site"]) as fr:
        from frappe.utils import flt

        if fr.db.exists("Stock Ledger Entry", {"item_code": STOCK_ITEM}):
            raise SystemExit("site already holds ERP-014 postings: use a fresh disposable site")
        ctx = _setup(fr)
        stock = _run_stock(fr, ctx, params["stock_moves"])
        invoices = _run_cases(fr, ctx, params["cases"])
        companies = [KSA["company"], UAE["company"]]
        gl = _sql_rows(fr, "select voucher_type, voucher_no, company, account, cast(debit as char) debit, "
                           "cast(credit as char) credit, is_cancelled from `tabGL Entry` where company in %s",
                       (companies,))
        settings = {
            "rounding_method": fr.db.get_single_value("System Settings", "rounding_method"),
            "valuation_method": fr.db.get_single_value("Stock Settings", "valuation_method"),
            "enable_immutable_ledger": fr.db.get_single_value("Accounts Settings", "enable_immutable_ledger"),
            "round_row_wise_tax": fr.db.get_single_value("Accounts Settings", "round_row_wise_tax"),
            "currency_precision": fr.db.get_default("currency_precision"),
            "company_currency": {n: fr.db.get_value("Company", n, "default_currency") for n in companies},
        }
        # The engine receives Python floats from its own forms and APIs; feed the decimal string as float.
        rounding = [{"value": s, "engine": repr(flt(float(s), 2))} for s in params["rounding_samples"]]
        json.dump({"settings": settings, "stock": stock, "invoices": invoices, "gl": gl,
                   "rounding": rounding}, sys.stdout, default=str)


if __name__ == "__main__":
    main()
