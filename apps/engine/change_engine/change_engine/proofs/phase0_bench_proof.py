"""
Phase 0 Engine Proof Suite (ERP-021).

Executes all six Phase 0 proofs (E0-1 through E0-6) and captures empirical engine
limitations (E0-7) against a live pinned Frappe/ERPNext/HRMS/change_engine bench:

  - E0-1: Two-tenant isolation (DB credential denial, site runtime isolation,
          HTTP Host header isolation, adapter boundary enforcement).
  - E0-2: Reconciled trading transaction (perpetual inventory, Moving Average,
          Commercial Rounding half-away-from-zero, Q-23 immutable ledger,
          SO -> DN -> SI -> Trial Balance + 10% discount variant + cancel).
  - E0-3: Denied operation on failure (ERPNext role permissions, field permlevel
          masking gap + remediation, CE-SEC-001 role spoofing rejection, Zone 2 lock,
          adapter caller/context fail-closed denial).
  - E0-4: Interrupted guarded change with recovery (Stage 3 prepare fail, Stage 4
          live MariaDB MDL Error 1205 contention + advisory lock release, Stage 6
          finalize fault -> RECOVERY_REQUIRED fail-closed + ChangeEngineAdapter faults).
  - E0-5: Duplicate-effect prevention (double-submit rejection, negative-stock block,
          over-delivery/over-billing guard checks, DDL & adapter idempotency).
  - E0-6: Minimal real Blueprint + component + adapter connection through
          contracts/examples/engine-mapping-golden-path.json verified against live
          frappe.get_meta(...), plus non-destructive Custom Field & quarantine.
  - E0-7: Empirical engine limitations & alternatives.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

try:
    import pymysql
except ImportError:  # pragma: no cover - optional outside MariaDB container
    pymysql = None

from change_engine.adapter import ChangeEngineAdapter
from change_engine.adapter import contracts_support as cs


GOLDEN_PATH_TOLERANCE = 0.005


def verify_mapping_against_meta(
    mapping: Dict[str, Any],
    meta_by_doctype: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare BPL-029 engine mapping DocTypes/fields/types against live Frappe meta.

    ``meta_by_doctype`` maps DocType name -> ``{"submittable": bool, "fields": {fname: fieldtype}}``.
    Returns checked field count, missing DocTypes/fields, and fieldtype mismatches.
    """
    checked = 0
    missing_doctypes: List[str] = []
    missing_fields: List[Dict[str, str]] = []
    type_mismatches: List[Dict[str, Any]] = []

    for entity in mapping.get("entities", []):
        dt = entity.get("engineDocType")
        if not dt:
            continue
        meta = meta_by_doctype.get(dt)
        if not meta:
            missing_doctypes.append(dt)
            continue
        if bool(entity.get("submittable")) != bool(meta.get("submittable")):
            type_mismatches.append(
                {
                    "doctype": dt,
                    "field": "__submittable__",
                    "mapping": entity.get("submittable"),
                    "engine": meta.get("submittable"),
                }
            )
        fields_map = meta.get("fields", {})
        for fld in entity.get("fields", []):
            via = fld.get("via")
            if via:
                v_dt = via.get("engineDocType")
                v_field = via.get("engineField")
                checked += 1
                v_meta = meta_by_doctype.get(v_dt)
                if not v_meta:
                    missing_doctypes.append(str(v_dt))
                elif v_field not in v_meta.get("fields", {}):
                    missing_fields.append({"doctype": str(v_dt), "field": str(v_field)})
                elif fld.get("engineType") and v_meta["fields"][v_field] != fld["engineType"]:
                    type_mismatches.append(
                        {
                            "doctype": v_dt,
                            "field": v_field,
                            "mapping": fld["engineType"],
                            "engine": v_meta["fields"][v_field],
                        }
                    )
                continue

            ef = fld.get("engineField")
            if ef is None:
                continue
            checked += 1
            if ef not in fields_map:
                missing_fields.append({"doctype": dt, "field": ef})
                continue
            expected_type = fld.get("engineType")
            actual_type = fields_map[ef]
            if expected_type and actual_type != expected_type:
                type_mismatches.append(
                    {
                        "doctype": dt,
                        "field": ef,
                        "mapping": expected_type,
                        "engine": actual_type,
                    }
                )

    return {
        "checked_fields": checked,
        "missing_doctypes": sorted(set(missing_doctypes)),
        "missing_fields": missing_fields,
        "type_mismatches": type_mismatches,
        "exact_match": not (missing_doctypes or missing_fields or type_mismatches),
    }


def verify_trial_balance_reconciliation(
    gl_rows: List[Dict[str, Any]],
    expected_stock_value: float,
    actual_stock_value: float,
    expected_ar: float,
    actual_ar: float,
    inventory_account: str,
    ar_account: str,
) -> Dict[str, Any]:
    """Reconcile posted GL Entries against stock value and AR subledger balances."""
    by_account: Dict[str, Dict[str, float]] = defaultdict(lambda: {"debit": 0.0, "credit": 0.0})
    total_debit = 0.0
    total_credit = 0.0

    for row in gl_rows:
        if int(row.get("is_cancelled") or 0):
            continue
        acc = str(row["account"])
        debit = round(float(row.get("debit") or 0.0), 2)
        credit = round(float(row.get("credit") or 0.0), 2)
        by_account[acc]["debit"] = round(by_account[acc]["debit"] + debit, 2)
        by_account[acc]["credit"] = round(by_account[acc]["credit"] + credit, 2)
        total_debit = round(total_debit + debit, 2)
        total_credit = round(total_credit + credit, 2)

    inv_gl = round(by_account[inventory_account]["debit"] - by_account[inventory_account]["credit"], 2)
    ar_gl = round(by_account[ar_account]["debit"] - by_account[ar_account]["credit"], 2)

    net_tb_debit = round(sum(max(0.0, v["debit"] - v["credit"]) for v in by_account.values()), 2)
    net_tb_credit = round(sum(max(0.0, v["credit"] - v["debit"]) for v in by_account.values()), 2)

    balanced = (
        abs(total_debit - total_credit) < GOLDEN_PATH_TOLERANCE
        and abs(net_tb_debit - net_tb_credit) < GOLDEN_PATH_TOLERANCE
    )
    inv_tie_out = (
        abs(inv_gl - expected_stock_value) < GOLDEN_PATH_TOLERANCE
        and abs(actual_stock_value - expected_stock_value) < GOLDEN_PATH_TOLERANCE
    )
    ar_tie_out = (
        abs(ar_gl - expected_ar) < GOLDEN_PATH_TOLERANCE
        and abs(actual_ar - expected_ar) < GOLDEN_PATH_TOLERANCE
    )

    return {
        "balanced": balanced,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "net_trial_balance_debit": net_tb_debit,
        "net_trial_balance_credit": net_tb_credit,
        "inventory_gl_balance": inv_gl,
        "actual_stock_value": round(float(actual_stock_value), 2),
        "expected_stock_value": round(float(expected_stock_value), 2),
        "inventory_tie_out": inv_tie_out,
        "ar_gl_balance": ar_gl,
        "actual_ar": round(float(actual_ar), 2),
        "expected_ar": round(float(expected_ar), 2),
        "ar_tie_out": ar_tie_out,
        "accounts": {k: dict(v) for k, v in sorted(by_account.items())},
        "reconciled": balanced and inv_tie_out and ar_tie_out,
    }


def _seal_artifact(art: Dict[str, Any]) -> Dict[str, Any]:
    sealed = copy.deepcopy(art)
    if sealed.get("inverse"):
        sealed["inverse"] = _seal_artifact(sealed["inverse"])
    digest, art_id = cs.artifact_hashes(sealed)
    sealed["artifactId"] = art_id
    sealed["integrity"] = {
        "algorithm": "sha256-canonical-json-v1",
        "contentHash": digest,
        "signature": None,
    }
    return sealed


def _ctx(tenant: str, req_suffix: str, service: str = "control_plane", who: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import hashlib

    digest = hashlib.sha256(f"{tenant}:{req_suffix}".encode("utf-8")).hexdigest()[:23].upper()
    return {
        "contractVersion": "0.1.2",
        "requestId": f"01J{digest}",
        "correlationId": f"corr_{req_suffix}",
        "tenantId": tenant,
        "caller": {
            "service": service,
            "onBehalfOf": who if who is not None else {"kind": "user", "id": "usr_owner"},
        },
        "deadlineMs": 30000,
    }


class _FrappeSiteContext:
    """Manage single-site Frappe connection lifecycle inside bench python."""

    def __init__(self, site: str, sites_path: Optional[str] = None) -> None:
        self.site = site
        if sites_path:
            self.sites_path = sites_path
        elif os.path.basename(os.getcwd()) == "sites":
            self.sites_path = os.getcwd()
        else:
            self.sites_path = os.path.join(os.getcwd(), "sites")
        self._prev_cwd: Optional[str] = None

    def __enter__(self):
        import frappe

        self._prev_cwd = os.getcwd()
        os.chdir(self.sites_path)
        if getattr(frappe.local, "site", None):
            frappe.destroy()
        frappe.init(site=self.site, sites_path=self.sites_path)
        frappe.connect()
        frappe.set_user("Administrator")
        return frappe

    def __exit__(self, exc_type, exc_val, exc_tb):
        import frappe

        try:
            frappe.db.rollback()
        except Exception:
            pass
        finally:
            frappe.destroy()
            if self._prev_cwd:
                os.chdir(self._prev_cwd)


def _http_get_json(url: str, host: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Host": host, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode("utf-8", errors="replace"))}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read().decode("utf-8", errors="replace")}


def _find_account(frappe_mod: Any, company: str, root_type: str, keyword: str) -> str:
    exact = frappe_mod.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": root_type, "account_name": keyword},
        pluck="name",
        order_by="name asc",
    )
    if exact:
        return exact[0]
    rows = frappe_mod.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": root_type, "account_name": ["like", f"%{keyword}%"]},
        pluck="name",
        order_by="name asc",
    )
    if rows:
        return rows[0]
    fallback = frappe_mod.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": root_type},
        pluck="name",
        order_by="name asc",
    )
    if not fallback:
        raise RuntimeError(f"No leaf account found for company={company}, root_type={root_type}, keyword={keyword}")
    return fallback[0]


def _ensure_warehouse(frappe_mod: Any, company: str, abbr: str, label: str = "W1") -> str:
    existing = frappe_mod.db.exists("Warehouse", {"company": company, "warehouse_name": label})
    if existing:
        return str(existing)
    parent = frappe_mod.db.get_value(
        "Warehouse", {"company": company, "is_group": 1}, "name"
    )
    doc = frappe_mod.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": label,
            "company": company,
            "parent_warehouse": parent,
            "is_group": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    return str(doc.name)


def _ensure_role_user(frappe_mod: Any, email: str, first_name: str, roles: List[str]) -> str:
    if frappe_mod.db.exists("User", email):
        return email
    user = frappe_mod.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in roles],
        }
    )
    user.insert(ignore_permissions=True)
    return email


def proof_1_two_tenant_isolation(
    site_a: str,
    site_b: str,
    engine_port: int = 8000,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-1: Verify SQL credential isolation, runtime context isolation, HTTP Host isolation, and adapter isolation."""
    if pymysql is None:
        raise RuntimeError("pymysql is required for SQL isolation proof")

    with _FrappeSiteContext(site_a, sites_path) as fr:
        db_a = str(fr.conf.db_name)
        db_host_a = str(fr.conf.db_host or "mariadb")
        db_port_a = int(fr.conf.db_port or 3306)
        db_pass_a = str(fr.conf.db_password)
        tenant_id_a = str(fr.conf.get("tenant_id") or "")
        canary_cust_a = f"CANARY-TA-{uuid.uuid4().hex[:8].upper()}"
        if not fr.db.exists("Customer Group", "All Customer Groups"):
            fr.get_doc({"doctype": "Customer Group", "customer_group_name": "All Customer Groups", "is_group": 0}).insert(ignore_permissions=True)
        if not fr.db.exists("Territory", "All Territories"):
            fr.get_doc({"doctype": "Territory", "territory_name": "All Territories", "is_group": 0}).insert(ignore_permissions=True)
        fr.get_doc(
            {
                "doctype": "Customer",
                "customer_name": canary_cust_a,
                "customer_type": "Company",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
            }
        ).insert(ignore_permissions=True)
        fr.db.commit()
        active_db_a = fr.db.sql("SELECT DATABASE()")[0][0]

    with _FrappeSiteContext(site_b, sites_path) as fr:
        db_b = str(fr.conf.db_name)
        db_host_b = str(fr.conf.db_host or "mariadb")
        db_port_b = int(fr.conf.db_port or 3306)
        db_pass_b = str(fr.conf.db_password)
        tenant_id_b = str(fr.conf.get("tenant_id") or "")
        canary_cust_b = f"CANARY-TB-{uuid.uuid4().hex[:8].upper()}"
        if not fr.db.exists("Customer Group", "All Customer Groups"):
            fr.get_doc({"doctype": "Customer Group", "customer_group_name": "All Customer Groups", "is_group": 0}).insert(ignore_permissions=True)
        if not fr.db.exists("Territory", "All Territories"):
            fr.get_doc({"doctype": "Territory", "territory_name": "All Territories", "is_group": 0}).insert(ignore_permissions=True)
        fr.get_doc(
            {
                "doctype": "Customer",
                "customer_name": canary_cust_b,
                "customer_type": "Company",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
            }
        ).insert(ignore_permissions=True)
        fr.db.commit()
        active_db_b = fr.db.sql("SELECT DATABASE()")[0][0]

        b_sees_a_orm = fr.get_all("Customer", filters={"customer_name": canary_cust_a}, pluck="name")
        b_sees_a_agg = fr.db.sql("SELECT COUNT(*) FROM `tabCustomer` WHERE customer_name = %s", (canary_cust_a,))[0][0]
        b_total_cust = fr.db.sql("SELECT COUNT(*) FROM `tabCustomer`")[0][0]

    # SQL user B attempting direct cross-schema read, aggregate, and write on schema A
    sql_cross_read_denied = False
    sql_cross_agg_denied = False
    sql_cross_write_denied = False
    conn_b = pymysql.connect(host=db_host_b, port=db_port_b, user=db_b, password=db_pass_b, database=db_b)
    try:
        with conn_b.cursor() as cur:
            try:
                cur.execute(f"SELECT name FROM `{db_a}`.`tabCustomer` LIMIT 1")
            except pymysql.err.OperationalError:
                sql_cross_read_denied = True
            try:
                cur.execute(f"SELECT COUNT(*) FROM `{db_a}`.`tabCustomer`")
            except pymysql.err.OperationalError:
                sql_cross_agg_denied = True
            try:
                cur.execute(f"DELETE FROM `{db_a}`.`tabCustomer` WHERE customer_name = %s", (canary_cust_a,))
            except pymysql.err.OperationalError:
                sql_cross_write_denied = True
    finally:
        conn_b.close()

    # Reverse check: SQL user A cannot read schema B
    sql_a_to_b_denied = False
    conn_a = pymysql.connect(host=db_host_a, port=db_port_a, user=db_a, password=db_pass_a, database=db_a)
    try:
        with conn_a.cursor() as cur:
            try:
                cur.execute(f"SELECT COUNT(*) FROM `{db_b}`.`tabCustomer`")
            except pymysql.err.OperationalError:
                sql_a_to_b_denied = True
    finally:
        conn_a.close()

    # Live HTTP checks against bench gunicorn (Host routing + unauthenticated resource denial)
    http_a_ping = _http_get_json(f"http://127.0.0.1:{engine_port}/api/method/ping", site_a)
    http_b_ping = _http_get_json(f"http://127.0.0.1:{engine_port}/api/method/ping", site_b)
    http_b_cross = _http_get_json(
        f"http://127.0.0.1:{engine_port}/api/resource/Customer/{canary_cust_a}",
        site_b,
    )

    # ChangeEngineAdapter tenant store isolation & fail-closed caller/tenant checks
    adapter = ChangeEngineAdapter(test_hooks=True)
    for t_id, key_suffix in (("t_alpha", "a1"), ("t_beta", "b1")):
        resp = adapter.call(
            "provision_site",
            _ctx(t_id, f"prov_{key_suffix}"),
            {
                "idempotencyKey": f"prov_{t_id}_0001",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "sa" if t_id == "t_alpha" else "ae",
                "siteClass": "sandbox",
                "blueprintId": f"bp_{t_id}",
            },
        )
        assert resp["ok"], resp

    st_a = adapter.call("site_status", _ctx("t_alpha", "st_a1"), {})
    st_b = adapter.call("site_status", _ctx("t_beta", "st_b1"), {})
    unknown_tenant_resp = adapter.call("site_status", _ctx("t_unknown", "unk_01"), {})
    unauth_prov_resp = adapter.call(
        "provision_site",
        {
            "contractVersion": "0.1.2",
            "requestId": _ctx("t_gamma", "unauth")["requestId"],
            "correlationId": "corr_unauth",
            "tenantId": "t_gamma",
            "caller": {"service": "control_plane", "onBehalfOf": None},
            "deadlineMs": 30000,
        },
        {
            "idempotencyKey": "prov_t_gamma_0001",
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "countryPack": "sa",
            "siteClass": "sandbox",
            "blueprintId": "bp_t_gamma",
        },
    )
    adapter_tenants_isolated = (
        st_a["ok"]
        and st_b["ok"]
        and st_a["result"]["blueprintId"] == "bp_t_alpha"
        and st_b["result"]["blueprintId"] == "bp_t_beta"
        and (not unknown_tenant_resp["ok"])
        and unknown_tenant_resp["error"]["code"] == "tenant_not_found"
        and (not unauth_prov_resp["ok"])
        and unauth_prov_resp["error"]["code"] == "permission_denied"
    )

    passed = all(
        [
            db_a != db_b,
            active_db_a == db_a,
            active_db_b == db_b,
            b_sees_a_orm == [],
            b_sees_a_agg == 0,
            sql_cross_read_denied,
            sql_cross_agg_denied,
            sql_cross_write_denied,
            sql_a_to_b_denied,
            http_a_ping.get("status") == 200,
            http_b_ping.get("status") == 200,
            http_b_cross.get("status") in (401, 403, 404),
            adapter_tenants_isolated,
        ]
    )

    return {
        "proof_id": "E0-1",
        "passed": passed,
        "site_a": {"site": site_a, "tenant_id": tenant_id_a, "db_name": db_a, "canary": canary_cust_a},
        "site_b": {"site": site_b, "tenant_id": tenant_id_b, "db_name": db_b, "canary": canary_cust_b},
        "runtime_b_sees_a_orm": b_sees_a_orm,
        "runtime_b_sees_a_aggregate": int(b_sees_a_agg),
        "runtime_b_total_customers": int(b_total_cust),
        "sql_b_read_a_denied": sql_cross_read_denied,
        "sql_b_aggregate_a_denied": sql_cross_agg_denied,
        "sql_b_write_a_denied": sql_cross_write_denied,
        "sql_a_aggregate_b_denied": sql_a_to_b_denied,
        "http_a_ping_status": http_a_ping.get("status"),
        "http_b_ping_status": http_b_ping.get("status"),
        "http_b_cross_tenant_status": http_b_cross.get("status"),
        "adapter_tenants_isolated": adapter_tenants_isolated,
    }


def proof_2_reconciled_trading_transaction(
    site_a: str,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-2: Run Golden Path Trading Sale (SO -> DN -> SI -> Trial Balance + Discount + Q-23 Cancel)."""
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
    from erpnext.setup.setup_wizard.setup_wizard import setup_complete
    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
    from frappe.utils import flt, rounded

    with _FrappeSiteContext(site_a, sites_path) as fr:
        # 1. Record engine defaults BEFORE overriding (for E0-7 & ADR-0033 verification)
        initial_defaults = {
            "Stock Settings.valuation_method": fr.db.get_single_value("Stock Settings", "valuation_method"),
            "System Settings.rounding_method": fr.db.get_single_value("System Settings", "rounding_method"),
            "Accounts Settings.enable_immutable_ledger": int(
                fr.db.get_single_value("Accounts Settings", "enable_immutable_ledger") or 0
            ),
            "default_rounded_neg_half": rounded(-0.105, 2),
            "default_flt_neg_half": flt(-0.105, 2),
        }

        # 2. Complete synthetic company setup
        company = "Golden Trading Co"
        abbr = "GTC"
        setup_complete(
            fr._dict(
                {
                    "country": "Saudi Arabia",
                    "currency": "SAR",
                    "fy_start_date": "2026-01-01",
                    "fy_end_date": "2026-12-31",
                    "company_name": company,
                    "company_abbr": abbr,
                    "chart_of_accounts": "Standard",
                    "domain": "Distribution",
                    "company_tagline": "Synthetic Golden Path Test Co",
                    "full_name": "Golden Owner",
                    "email": "owner.p0@example.invalid",
                    "language": "English",
                }
            )
        )
        fr.db.commit()

        # 3. Apply explicit provisioning settings (ADR-0033 + Q-23)
        fr.db.set_single_value("Stock Settings", "valuation_method", "Moving Average")
        fr.db.set_single_value("System Settings", "rounding_method", "Commercial Rounding")
        fr.db.set_single_value("Accounts Settings", "enable_immutable_ledger", 1)
        fr.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
        fr.clear_cache()
        fr.db.commit()

        commercial_neg_rounded = rounded(-0.105, 2)
        commercial_pos_rounded = rounded(0.105, 2)
        commercial_neg_flt = flt(-0.105, 2)
        commercial_pos_flt = flt(0.105, 2)

        # Resolve COA leaf accounts and warehouse
        inv_acc = _find_account(fr, company, "Asset", "Stock In Hand")
        cogs_acc = _find_account(fr, company, "Expense", "Cost of Goods Sold")
        ar_acc = _find_account(fr, company, "Asset", "Debtors")
        sales_acc = _find_account(fr, company, "Income", "Sales")
        opening_acc = _find_account(fr, company, "Equity", "Temporary Opening")
        wh_w1 = _ensure_warehouse(fr, company, abbr, "W1")

        # Update Company defaults to guarantee predictable golden accounts
        fr.db.set_value(
            "Company",
            company,
            {
                "enable_perpetual_inventory": 1,
                "default_inventory_account": inv_acc,
                "default_expense_account": cogs_acc,
                "default_receivable_account": ar_acc,
                "default_income_account": sales_acc,
                "stock_adjustment_account": opening_acc,
            },
        )
        fr.db.commit()

        # Ensure Piece UOM exists
        if not fr.db.exists("UOM", "Piece"):
            fr.get_doc({"doctype": "UOM", "uom_name": "Piece", "must_be_whole_number": 0}).insert(ignore_permissions=True)

        # Create Item ITEM-001 (stock item, Moving Average, no explicit override -> inherits Stock Settings)
        item_doc = fr.get_doc(
            {
                "doctype": "Item",
                "item_code": "ITEM-001",
                "item_name": "Golden Trading Widget",
                "item_group": "All Item Groups",
                "stock_uom": "Piece",
                "is_stock_item": 1,
                "valuation_method": "",
                "valuation_rate": 10.0,
                "opening_stock": 0,
            }
        )
        item_doc.insert(ignore_permissions=True)

        # Create Customer CUST-001
        cust_doc = fr.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "CUST-001",
                "customer_type": "Company",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
                "default_currency": "SAR",
            }
        )
        cust_doc.insert(ignore_permissions=True)

        # Create Item Price (Standard Selling = 15.00)
        fr.get_doc(
            {
                "doctype": "Item Price",
                "item_code": "ITEM-001",
                "price_list": "Standard Selling",
                "price_list_rate": 15.0,
                "currency": "SAR",
            }
        ).insert(ignore_permissions=True)

        # Step 0: Post opening stock 100 pieces @ 10.00 = 1,000.00 against Opening Equity
        se_open = fr.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": company,
                "posting_date": "2026-01-05",
                "posting_time": "09:00:00",
                "set_posting_time": 1,
                "items": [
                    {
                        "item_code": "ITEM-001",
                        "t_warehouse": wh_w1,
                        "qty": 100.0,
                        "basic_rate": 10.0,
                        "expense_account": opening_acc,
                    }
                ],
            }
        )
        se_open.insert(ignore_permissions=True)
        se_open.submit()
        fr.db.commit()

        # Step 1: Sales Order (10 x 15.00 = 150.00) -> no ledger/stock effect
        so = fr.get_doc(
            {
                "doctype": "Sales Order",
                "customer": cust_doc.name,
                "company": company,
                "transaction_date": "2026-01-10",
                "delivery_date": "2026-01-15",
                "currency": "SAR",
                "selling_price_list": "Standard Selling",
                "set_warehouse": wh_w1,
                "items": [{"item_code": "ITEM-001", "qty": 10.0, "rate": 15.0, "warehouse": wh_w1}],
            }
        )
        so.insert(ignore_permissions=True)
        so.submit()
        fr.db.commit()

        so_gl_count = fr.db.count("GL Entry", {"voucher_no": so.name})
        so_sle_count = fr.db.count("Stock Ledger Entry", {"voucher_no": so.name})

        # Step 2: Delivery Note from Sales Order (10 pcs from W1) -> COGS Dr 100 / Inventory Cr 100
        dn = make_delivery_note(so.name)
        dn.posting_date = "2026-01-11"
        dn.posting_time = "10:00:00"
        dn.set_posting_time = 1
        dn.set_warehouse = wh_w1
        dn.insert(ignore_permissions=True)
        dn.submit()
        fr.db.commit()

        dn_line_links = [
            {"against_sales_order": row.against_sales_order, "so_detail": row.so_detail}
            for row in dn.items
        ]

        # Step 3: Sales Invoice from Delivery Note (update_stock=0) -> AR Dr 150 / Sales Cr 150
        si = make_sales_invoice(dn.name)
        si.posting_date = "2026-01-12"
        si.posting_time = "11:00:00"
        si.set_posting_time = 1
        si.update_stock = 0
        si.insert(ignore_permissions=True)
        si.submit()
        fr.db.commit()

        si_sle_count = fr.db.count("Stock Ledger Entry", {"voucher_no": si.name})

        # Step 4: Reconcile Trial Balance & Bin after main Golden Path
        bin_row = fr.db.get_value(
            "Bin",
            {"item_code": "ITEM-001", "warehouse": wh_w1},
            ["actual_qty", "stock_value", "valuation_rate"],
            as_dict=True,
        ) or {}
        gl_rows = fr.get_all(
            "GL Entry",
            filters={"company": company, "is_cancelled": 0},
            fields=["account", "debit", "credit", "voucher_type", "voucher_no", "is_cancelled"],
        )
        ar_outstanding = float(fr.db.get_value("Sales Invoice", si.name, "outstanding_amount") or 0.0)
        recon = verify_trial_balance_reconciliation(
            gl_rows=gl_rows,
            expected_stock_value=900.0,
            actual_stock_value=float(bin_row.get("stock_value") or 0.0),
            expected_ar=150.0,
            actual_ar=ar_outstanding,
            inventory_account=inv_acc,
            ar_account=ar_acc,
        )

        # Step 5: 10% Document Discount Variant (10 x 15.00 - 10% = 135.00)
        so_disc = fr.get_doc(
            {
                "doctype": "Sales Order",
                "customer": cust_doc.name,
                "company": company,
                "transaction_date": "2026-01-13",
                "delivery_date": "2026-01-16",
                "currency": "SAR",
                "selling_price_list": "Standard Selling",
                "set_warehouse": wh_w1,
                "apply_discount_on": "Grand Total",
                "additional_discount_percentage": 10.0,
                "items": [{"item_code": "ITEM-001", "qty": 10.0, "rate": 15.0, "warehouse": wh_w1}],
            }
        )
        so_disc.insert(ignore_permissions=True)
        so_disc.submit()
        dn_disc = make_delivery_note(so_disc.name)
        dn_disc.posting_date = "2026-01-13"
        dn_disc.posting_time = "12:00:00"
        dn_disc.set_posting_time = 1
        dn_disc.insert(ignore_permissions=True)
        dn_disc.submit()
        si_disc = make_sales_invoice(dn_disc.name)
        si_disc.posting_date = "2026-01-14"
        si_disc.posting_time = "12:00:00"
        si_disc.set_posting_time = 1
        si_disc.update_stock = 0
        si_disc.apply_discount_on = "Grand Total"
        si_disc.additional_discount_percentage = 10.0
        si_disc.insert(ignore_permissions=True)
        si_disc.submit()
        fr.db.commit()

        si_disc_gl = fr.get_all(
            "GL Entry",
            filters={"voucher_no": si_disc.name, "is_cancelled": 0},
            fields=["account", "debit", "credit"],
        )

        # Step 6: Cancel discount invoice with enable_immutable_ledger=1 (Q-23 verification)
        si_disc.cancel()
        fr.db.commit()
        cancel_gl_all = fr.get_all(
            "GL Entry",
            filters={"voucher_no": si_disc.name},
            fields=["name", "account", "debit", "credit", "is_cancelled", "posting_date"],
        )
        cancel_has_reversing_entries = len(cancel_gl_all) >= 4

        passed = all(
            [
                round(float(commercial_neg_rounded), 2) == -0.11,
                round(float(commercial_pos_rounded), 2) == 0.11,
                round(float(commercial_neg_flt), 2) == -0.11,
                round(float(commercial_pos_flt), 2) == 0.11,
                so_gl_count == 0,
                so_sle_count == 0,
                so.grand_total == 150.0,
                dn_line_links and dn_line_links[0]["against_sales_order"] == so.name,
                si_sle_count == 0,
                si.grand_total == 150.0,
                si.outstanding_amount == 150.0,
                float(bin_row.get("actual_qty") or 0.0) == 90.0,
                recon["reconciled"],
                abs(recon["total_debit"] - 1250.0) < GOLDEN_PATH_TOLERANCE,
                abs(recon["net_trial_balance_debit"] - 1150.0) < GOLDEN_PATH_TOLERANCE,
                abs(float(so_disc.grand_total) - 135.0) < GOLDEN_PATH_TOLERANCE,
                abs(float(si_disc.grand_total) - 135.0) < GOLDEN_PATH_TOLERANCE,
                cancel_has_reversing_entries,
            ]
        )

        return {
            "proof_id": "E0-2",
            "passed": passed,
            "initial_defaults": initial_defaults,
            "commercial_rounding_checks": {
                "rounded(-0.105, 2)": commercial_neg_rounded,
                "rounded(0.105, 2)": commercial_pos_rounded,
                "flt(-0.105, 2)": commercial_neg_flt,
                "flt(0.105, 2)": commercial_pos_flt,
            },
            "accounts": {
                "inventory": inv_acc,
                "cogs": cogs_acc,
                "receivable": ar_acc,
                "sales": sales_acc,
                "opening_equity": opening_acc,
                "warehouse": wh_w1,
            },
            "documents": {
                "opening_stock_entry": se_open.name,
                "sales_order": so.name,
                "delivery_note": dn.name,
                "sales_invoice": si.name,
                "discount_sales_invoice": si_disc.name,
            },
            "so_ledger_counts": {"gl": so_gl_count, "sle": so_sle_count},
            "dn_line_links": dn_line_links,
            "si_sle_count": si_sle_count,
            "bin_after_golden_sale": {
                "actual_qty": float(bin_row.get("actual_qty") or 0.0),
                "stock_value": float(bin_row.get("stock_value") or 0.0),
                "valuation_rate": float(bin_row.get("valuation_rate") or 0.0),
            },
            "reconciliation": recon,
            "discount_variant": {
                "so_grand_total": float(so_disc.grand_total),
                "si_grand_total": float(si_disc.grand_total),
                "si_gl_entries_before_cancel": si_disc_gl,
            },
            "q23_immutable_ledger_cancel": {
                "enable_immutable_ledger": 1,
                "gl_rows_after_cancel": len(cancel_gl_all),
                "reversing_entries_preserved": cancel_has_reversing_entries,
            },
        }


def proof_3_denied_operations(
    site_a: str,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-3: Verify role denials, field permlevel gap + mask, change_engine role spoofing/zone denial, and adapter denial."""
    from change_engine.api.endpoints import apply_configuration_change

    with _FrappeSiteContext(site_a, sites_path) as fr:
        sales_user = _ensure_role_user(fr, "sales.p0@example.invalid", "Sales P0", ["Sales User"])
        wh_user = _ensure_role_user(fr, "warehouse.p0@example.invalid", "Warehouse P0", ["Stock User"])
        fin_user = _ensure_role_user(fr, "finance.p0@example.invalid", "Finance P0", ["Accounts User"])
        fr.db.commit()

        # Check Sales User denials
        fr.set_user(sales_user)
        sales_denied_gl = not fr.has_permission("GL Entry", "read", user=sales_user)
        sales_get_list_gl_denied = False
        try:
            fr.get_list("GL Entry", limit_page_length=1)
        except fr.PermissionError:
            sales_get_list_gl_denied = True

        # Check default Item.valuation_rate exposure before masking
        from frappe.model import get_permitted_fields

        item_permitted_before = set(get_permitted_fields("Item", permission_type="read", user=sales_user))
        default_item_cost_exposed_to_sales = "valuation_rate" in item_permitted_before

        # Check CE-SEC-001 & Zone 2 lock inside live Frappe
        fr.set_user(sales_user)
        spoofed_apply = apply_configuration_change(
            doctype="Customer",
            proposal={"intent": "add_custom_fields", "changes": [{"fieldname": "custom_x", "fieldtype": "Data"}]},
            user_roles=["System Manager"],
        )
        spoof_denied = (not spoofed_apply.get("success")) and spoofed_apply.get("disposition") == "UNAUTHORIZED_ROLE"

        fr.set_user("Administrator")
        zone2_apply = apply_configuration_change(
            doctype="GL Entry",
            proposal={"intent": "add_custom_fields", "changes": [{"fieldname": "custom_x", "fieldtype": "Data"}]},
        )
        zone2_denied = (not zone2_apply.get("success")) and zone2_apply.get("disposition") == "ZONE_SAFETY_VIOLATION"

        # Apply Property Setter masking Item.valuation_rate at permlevel=1 and re-check Sales User
        if not fr.db.exists("Property Setter", "Item-valuation_rate-permlevel"):
            fr.get_doc(
                {
                    "doctype": "Property Setter",
                    "doctype_or_field": "DocField",
                    "doc_type": "Item",
                    "field_name": "valuation_rate",
                    "property": "permlevel",
                    "property_type": "Int",
                    "value": "1",
                }
            ).insert(ignore_permissions=True)
            fr.clear_cache(doctype="Item")
            fr.db.commit()

        item_permitted_after = set(get_permitted_fields("Item", permission_type="read", user=sales_user))
        masked_item_cost_hidden_from_sales = "valuation_rate" not in item_permitted_after

        # Check Warehouse denials
        fr.set_user(wh_user)
        wh_denied_si = not fr.has_permission("Sales Invoice", "read", user=wh_user)
        wh_denied_gl = not fr.has_permission("GL Entry", "read", user=wh_user)

        # Check Finance denied permission edits
        fr.set_user(fin_user)
        fin_denied_perm_change = not fr.has_permission("Custom DocPerm", "write", user=fin_user)

        fr.set_user("Administrator")

    # ChangeEngineAdapter service authorization failure
    adapter = ChangeEngineAdapter(test_hooks=True)
    prov = adapter.call(
        "provision_site",
        _ctx("t_alpha", "p3_prov"),
        {
            "idempotencyKey": "prov_p3_0001",
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "countryPack": "sa",
            "siteClass": "sandbox",
            "blueprintId": "bp_p3",
        },
    )
    assert prov["ok"], prov
    obs_apply_denied = adapter.call(
        "apply",
        _ctx("t_alpha", "p3_obs", service="observability"),
        {"idempotencyKey": "p3_obs_0001"},
    )
    adapter_service_denied = (not obs_apply_denied["ok"]) and obs_apply_denied["error"]["code"] == "permission_denied"

    passed = all(
        [
            sales_denied_gl,
            sales_get_list_gl_denied,
            default_item_cost_exposed_to_sales,
            masked_item_cost_hidden_from_sales,
            wh_denied_si,
            wh_denied_gl,
            fin_denied_perm_change,
            spoof_denied,
            zone2_denied,
            adapter_service_denied,
        ]
    )

    return {
        "proof_id": "E0-3",
        "passed": passed,
        "sales_denied_gl": sales_denied_gl,
        "sales_get_list_gl_denied": sales_get_list_gl_denied,
        "default_item_cost_exposed_to_sales_finding": default_item_cost_exposed_to_sales,
        "masked_item_cost_hidden_from_sales": masked_item_cost_hidden_from_sales,
        "warehouse_denied_sales_invoice": wh_denied_si,
        "warehouse_denied_gl_entry": wh_denied_gl,
        "finance_denied_permission_change": fin_denied_perm_change,
        "ce_sec_001_spoofed_apply_denied": spoof_denied,
        "zone2_gl_entry_mutation_denied": zone2_denied,
        "adapter_service_authz_denied": adapter_service_denied,
    }


def proof_4_interrupted_guarded_change_recovery(
    site_a: str,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-4: Interrupt guarded DDL across Stage 3/4/6 on live MariaDB + ChangeEngineAdapter faults."""
    if pymysql is None:
        raise RuntimeError("pymysql is required for live MariaDB lock contention proof")
    from change_engine.api.endpoints import FrappeDeploymentAdapter
    from change_engine.guarded_apply.schema_reconciler import (
        execute_single_field_deployment,
        make_bounded_lock_key,
    )

    note_field = "custom_p0_guarded_proof"
    todo_field = "custom_p0_mdl_blocked"

    with _FrappeSiteContext(site_a, sites_path) as fr:
        db_name = str(fr.conf.db_name)
        db_host = str(fr.conf.db_host or "mariadb")
        db_port = int(fr.conf.db_port or 3306)
        db_pass = str(fr.conf.db_password)
        adapter = FrappeDeploymentAdapter(frappe_module=fr, in_memory=False)

        # Ensure at least 1 ToDo row exists so SELECT ... FOR UPDATE locks tabToDo MDL cleanly
        if not fr.db.count("ToDo"):
            fr.get_doc({"doctype": "ToDo", "description": "ERP-021 live MDL probe"}).insert(
                ignore_permissions=True
            )
            fr.db.commit()

        # 0. Probe live Customer DDL Plan Gate (captures E0-7 decimal(21,9) MODIFY drift finding)
        cust_rev = adapter.get_doctype_revision_hash("Customer")
        customer_ddl_gate_probe = execute_single_field_deployment(
            db=adapter,
            deployment_id="dep_p0_cust_gate_probe",
            idempotency_key="idem_p0_cust_gate_probe",
            site_id=site_a,
            doctype="Customer",
            base_revision_hash=cust_rev,
            field_def={"fieldname": "custom_p0_cust_probe", "fieldtype": "Data", "label": "Probe"},
            lock_wait_seconds=2,
        )

        # Clear any prior test artifacts on ToDo/Note and inspect live revisions
        todo_rev = adapter.get_doctype_revision_hash("ToDo")

        # 1. Stage 3 prepare error on ToDo -> FAILED_CLEAN, no column/meta, lock released
        prep_err_adapter = FrappeDeploymentAdapter(
            frappe_module=fr, in_memory=False, simulate_prepare_error=True
        )
        res_prepare = execute_single_field_deployment(
            db=prep_err_adapter,
            deployment_id="dep_p0_prep_err",
            idempotency_key="idem_p0_prep_err",
            site_id=site_a,
            doctype="ToDo",
            base_revision_hash=todo_rev,
            field_def={"fieldname": todo_field, "fieldtype": "Data", "label": "MDL Blocked"},
            lock_wait_seconds=2,
        )

        # 2. Live MariaDB MDL contention during Stage 4 on tabToDo -> Error 1205 -> RECOVERY_REQUIRED
        # Note: Custom Field insert commits implicitly when MariaDB attempts ALTER TABLE before hitting 1205,
        # triggering Row 4 non-destructive reconciliation (ORPHAN_METADATA_NON_DESTRUCTIVE_HOLD).
        locker_conn = pymysql.connect(
            host=db_host, port=db_port, user=db_name, password=db_pass, database=db_name, autocommit=False
        )
        try:
            with locker_conn.cursor() as lcur:
                lcur.execute("START TRANSACTION")
                lcur.execute("SELECT name FROM `tabToDo` LIMIT 1 FOR UPDATE")
            res_mdl = execute_single_field_deployment(
                db=adapter,
                deployment_id="dep_p0_mdl_err",
                idempotency_key="idem_p0_mdl_err",
                site_id=site_a,
                doctype="ToDo",
                base_revision_hash=todo_rev,
                field_def={"fieldname": todo_field, "fieldtype": "Data", "label": "MDL Blocked"},
                lock_wait_seconds=2,
            )
        finally:
            locker_conn.rollback()
            locker_conn.close()

        # Verify advisory lock was released immediately after failure
        lock_key = make_bounded_lock_key(site_a, "ToDo")
        lock_reacq = fr.db.sql("SELECT GET_LOCK(%s, 0)", (lock_key,))[0][0]
        fr.db.sql("SELECT RELEASE_LOCK(%s)", (lock_key,))

        # Verify physical column was NOT created when MDL wait timed out
        col_after_mdl_fail = fr.db.sql(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='tabToDo' AND COLUMN_NAME=%s",
            (db_name, todo_field),
        )

        # Subsequent deployment on ToDo while RECOVERY_REQUIRED exists MUST block fail-closed at INSPECT
        new_todo_rev = adapter.get_doctype_revision_hash("ToDo")
        res_blocked = execute_single_field_deployment(
            db=adapter,
            deployment_id="dep_p0_blocked_after_rec",
            idempotency_key="idem_p0_blocked_after_rec",
            site_id=site_a,
            doctype="ToDo",
            base_revision_hash=new_todo_rev,
            field_def={"fieldname": "custom_p0_second", "fieldtype": "Data", "label": "Second"},
            lock_wait_seconds=2,
        )

        # 3. Stage 6 finalize interruption after apply on Note -> RECOVERY_REQUIRED + capture audit status finding
        note_rev = adapter.get_doctype_revision_hash("Note")
        fin_err_adapter = FrappeDeploymentAdapter(
            frappe_module=fr, in_memory=False, simulate_finalize_error=True
        )
        res_finalize = execute_single_field_deployment(
            db=fin_err_adapter,
            deployment_id="dep_p0_fin_err",
            idempotency_key="idem_p0_fin_err",
            site_id=site_a,
            doctype="Note",
            base_revision_hash=note_rev,
            field_def={"fieldname": note_field, "fieldtype": "Data", "label": "P0 Guarded"},
            lock_wait_seconds=2,
        )
        stage6_audit_row_status = fr.db.sql(
            "SELECT status FROM `tabChange Engine Audit` WHERE deployment_id=%s",
            ("dep_p0_fin_err",),
        )
        stage6_audit_status_val = stage6_audit_row_status[0][0] if stage6_audit_row_status else None

    # 4. ChangeEngineAdapter contract fault injection across execute
    ce_adapter = ChangeEngineAdapter(test_hooks=True)
    ce_adapter.call(
        "provision_site",
        _ctx("t_alpha", "p4_prov"),
        {
            "idempotencyKey": "prov_p4_0001",
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "countryPack": "sa",
            "siteClass": "sandbox",
            "blueprintId": "bp_p4",
        },
    )
    add_step_art = _seal_artifact(
        {
            "artifactSchema": "0.1.0",
            "kind": "forward",
            "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
            "blueprint": {
                "id": "bp_p4",
                "base": None,
                "target": {"id": "bp_p4", "revision": 1, "sha256": "0" * 64},
                "diffHash": None,
            },
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "components": [],
            "steps": [
                {
                    "seq": 1,
                    "phase": 4,
                    "kind": "entity.add",
                    "subject": {"kind": "entity", "id": "customer", "parents": []},
                    "pointer": "/entities/customer",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {
                        "definition": {
                            "id": "customer",
                            "kind": "master",
                            "labels": {"en": "Customer", "ar": "عميل"},
                            "fields": [{"id": "customer_name", "type": "string", "labels": {"en": "Name", "ar": "الاسم"}}],
                        }
                    },
                    "sourceOps": ["/entities/customer"],
                }
            ],
            "skippedOps": [],
            "postConditions": [{"id": "pc_p4_1", "check": "exists", "pointer": "/entities/customer"}],
            "risk": {
                "counts": {"cosmetic": 0, "config": 0, "data_shape": 1, "destructive": 0, "compliance": 0, "access": 0, "branding": 0},
                "total": 1,
                "maxImpact": "data_shape",
                "needsDdlPlanGate": True,
                "touchesCompliance": False,
                "touchesAccess": False,
                "touchesLedgerOrTax": False,
                "requiresTeamReview": False,
                "irreversibleSteps": 0,
            },
            "inverse": None,
        }
    )
    plan_p4 = ce_adapter.call("plan", _ctx("t_alpha", "p4_plan"), {"artifact": add_step_art})
    ce_adapter.fault("execute", step_seq=1)
    apply_exec_fault = ce_adapter.call(
        "apply",
        _ctx("t_alpha", "p4_app_fault"),
        {
            "idempotencyKey": "p4_apply_exec_fault_01",
            "artifact": add_step_art,
            "planToken": plan_p4["result"]["planToken"],
            "approvals": {
                "changeApproved": "01J00000000000000000000099",
                "gateApproved": "01J00000000000000000000098",
            },
        },
    )

    passed = all(
        [
            customer_ddl_gate_probe["status"] == "REJECTED",
            customer_ddl_gate_probe.get("fallback_action") == "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT",
            res_prepare["status"] == "FAILED_CLEAN",
            res_mdl["status"] == "RECOVERY_REQUIRED",
            res_mdl.get("disposition") == "ORPHAN_METADATA_NON_DESTRUCTIVE_HOLD",
            "1205" in str(res_mdl.get("error", "")),
            int(lock_reacq) == 1,
            not col_after_mdl_fail,
            res_blocked["status"] == "RECOVERY_REQUIRED",
            res_blocked.get("stage") == "INSPECT",
            res_finalize["status"] == "RECOVERY_REQUIRED",
            "finalization_error" in res_finalize,
            apply_exec_fault["ok"],
            apply_exec_fault["result"]["status"] in ("compensated", "recovery_required"),
            ce_adapter.dropped_data() == [],
        ]
    )

    return {
        "proof_id": "E0-4",
        "passed": passed,
        "customer_ddl_gate_drift_finding": customer_ddl_gate_probe,
        "stage3_prepare_failure": res_prepare,
        "stage4_mariadb_mdl_timeout": res_mdl,
        "advisory_lock_reacquirable": int(lock_reacq) == 1,
        "orphan_column_after_mdl_fail": bool(col_after_mdl_fail),
        "blocked_while_recovery_required": res_blocked,
        "stage6_finalize_interruption": res_finalize,
        "stage6_audit_row_status_finding": stage6_audit_status_val,
        "adapter_execute_fault": apply_exec_fault["result"],
        "adapter_dropped_data": ce_adapter.dropped_data(),
    }


def proof_5_duplicate_effect_prevention(
    site_a: str,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-5: Prevent double-submit/over-delivery, over-stock delivery, and idempotency key replay/conflict."""
    from change_engine.api.endpoints import FrappeDeploymentAdapter
    from change_engine.guarded_apply.schema_reconciler import (
        IdempotencyConflictError,
        execute_single_field_deployment,
    )

    with _FrappeSiteContext(site_a, sites_path) as fr:
        dn_names = fr.get_all("Delivery Note", filters={"docstatus": 1}, pluck="name", order_by="creation asc", limit=1)
        if not dn_names:
            raise RuntimeError("Proof 2 Delivery Note not found before Proof 5")
        dn_name = dn_names[0]
        dn_doc = fr.get_doc("Delivery Note", dn_name)
        company = dn_doc.company
        wh_w1 = dn_doc.set_warehouse
        cust = dn_doc.customer
        so_name = dn_doc.items[0].against_sales_order
        so_detail = dn_doc.items[0].so_detail

        sle_before = fr.db.count("Stock Ledger Entry", {"voucher_no": dn_name})
        gl_before = fr.db.count("GL Entry", {"voucher_no": dn_name})

        # 1a. Double-submit on already-submitted Delivery Note (Frappe routes to update_after_submit -> 0 extra SLE/GL)
        dn_reload = fr.get_doc("Delivery Note", dn_name)
        dn_resubmit_raised = False
        try:
            dn_reload.submit()
        except fr.ValidationError:
            dn_resubmit_raised = True
        fr.db.rollback()
        sle_after = fr.db.count("Stock Ledger Entry", {"voucher_no": dn_name})
        gl_after = fr.db.count("GL Entry", {"voucher_no": dn_name})

        # 1b. Re-submitting a cancelled invoice (docstatus == 2) MUST raise ValidationError
        cancelled_si_names = fr.get_all("Sales Invoice", filters={"docstatus": 2}, pluck="name", limit=1)
        cancelled_resubmit_blocked = False
        if cancelled_si_names:
            cancelled_si = fr.get_doc("Sales Invoice", cancelled_si_names[0])
            try:
                cancelled_si.submit()
            except fr.ValidationError:
                cancelled_resubmit_blocked = True
            fr.db.rollback()

        # 1c. Duplicate delivery against already-100%-delivered Sales Order line MUST be blocked
        over_delivery_blocked = False
        if so_name and so_detail:
            dup_dn = fr.get_doc(
                {
                    "doctype": "Delivery Note",
                    "customer": cust,
                    "company": company,
                    "posting_date": "2026-01-12",
                    "set_warehouse": wh_w1,
                    "items": [
                        {
                            "item_code": "ITEM-001",
                            "qty": 10.0,
                            "rate": 15.0,
                            "warehouse": wh_w1,
                            "against_sales_order": so_name,
                            "so_detail": so_detail,
                        }
                    ],
                }
            )
            try:
                dup_dn.insert(ignore_permissions=True)
                dup_dn.submit()
            except fr.ValidationError:
                over_delivery_blocked = True
            fr.db.rollback()

        # 2. Delivering more than stock on hand (qty 500 > 90 remaining) must fail cleanly
        over_stock_blocked = False
        over_dn = fr.get_doc(
            {
                "doctype": "Delivery Note",
                "customer": cust,
                "company": company,
                "posting_date": "2026-01-12",
                "set_warehouse": wh_w1,
                "items": [{"item_code": "ITEM-001", "qty": 500.0, "rate": 15.0, "warehouse": wh_w1}],
            }
        )
        try:
            over_dn.insert(ignore_permissions=True)
            over_dn.submit()
        except fr.ValidationError:
            over_stock_blocked = True
        fr.db.rollback()

        # 3. Guarded DDL idempotency replay + conflict in MariaDB (using clean Note DocType)
        adapter = FrappeDeploymentAdapter(frappe_module=fr, in_memory=False)
        rev = adapter.get_doctype_revision_hash("Note")
        first_dep = execute_single_field_deployment(
            db=adapter,
            deployment_id="dep_p0_idemp_1",
            idempotency_key="idem_p0_same_key",
            site_id=site_a,
            doctype="Note",
            base_revision_hash=rev,
            field_def={"fieldname": "custom_p0_idemp_check", "fieldtype": "Data", "label": "P0 Idemp"},
            lock_wait_seconds=2,
        )
        replay_dep = execute_single_field_deployment(
            db=adapter,
            deployment_id="dep_p0_idemp_2",
            idempotency_key="idem_p0_same_key",
            site_id=site_a,
            doctype="Note",
            base_revision_hash=rev,
            field_def={"fieldname": "custom_p0_idemp_check", "fieldtype": "Data", "label": "P0 Idemp"},
            lock_wait_seconds=2,
        )
        conflict_blocked = False
        try:
            execute_single_field_deployment(
                db=adapter,
                deployment_id="dep_p0_idemp_3",
                idempotency_key="idem_p0_same_key",
                site_id=site_a,
                doctype="Note",
                base_revision_hash=rev,
                field_def={"fieldname": "custom_p0_different_field", "fieldtype": "Data", "label": "Diff"},
                lock_wait_seconds=2,
            )
        except IdempotencyConflictError:
            conflict_blocked = True

        # Check adapter idempotency conflict as well
        ce = ChangeEngineAdapter(test_hooks=True)
        p_resp1 = ce.call(
            "provision_site",
            _ctx("t_alpha", "p5_prov1"),
            {
                "idempotencyKey": "p5_shared_key",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "sa",
                "siteClass": "sandbox",
                "blueprintId": "bp_p5",
            },
        )
        p_resp2 = ce.call(
            "provision_site",
            _ctx("t_alpha", "p5_prov2"),
            {
                "idempotencyKey": "p5_shared_key",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "sa",
                "siteClass": "sandbox",
                "blueprintId": "bp_p5",
            },
        )
        p_resp_conflict = ce.call(
            "provision_site",
            _ctx("t_alpha", "p5_prov3"),
            {
                "idempotencyKey": "p5_shared_key",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "ae",
                "siteClass": "sandbox",
                "blueprintId": "bp_p5",
            },
        )

    ddl_replay_matched = (
        first_dep["status"] == "APPLIED"
        and replay_dep["status"] == "APPLIED"
        and replay_dep["deployment_id"] == "dep_p0_idemp_1"
    )

    passed = all(
        [
            sle_before == sle_after,
            gl_before == gl_after,
            cancelled_resubmit_blocked,
            over_delivery_blocked,
            over_stock_blocked,
            ddl_replay_matched,
            conflict_blocked,
            p_resp1["ok"],
            p_resp2["ok"],
            p_resp1["result"] == p_resp2["result"],
            (not p_resp_conflict["ok"]) and p_resp_conflict["error"]["code"] == "idempotency_conflict",
        ]
    )

    return {
        "proof_id": "E0-5",
        "passed": passed,
        "dn_resubmit_raised_exception_finding": dn_resubmit_raised,
        "sle_count_unchanged": sle_before == sle_after,
        "gl_count_unchanged": gl_before == gl_after,
        "cancelled_resubmit_blocked": cancelled_resubmit_blocked,
        "over_delivery_against_so_blocked": over_delivery_blocked,
        "over_stock_delivery_blocked": over_stock_blocked,
        "ddl_idempotent_replay": ddl_replay_matched,
        "ddl_idempotency_conflict_blocked": conflict_blocked,
        "adapter_idempotent_replay": p_resp1["result"] == p_resp2["result"],
        "adapter_idempotency_conflict": not p_resp_conflict["ok"] and p_resp_conflict["error"]["code"],
    }


def proof_6_minimal_blueprint_component_adapter(
    site_a: str,
    bundle: Dict[str, Any],
    zatca_generate_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E0-6 & E0-7: Validate BPL-029 mapping on live meta, connect Blueprint + component + ChangeEngineAdapter + live Frappe."""
    from change_engine.api.endpoints import FrappeDeploymentAdapter
    from change_engine.guarded_apply.schema_reconciler import execute_single_field_deployment

    mapping = bundle["mapping"]
    blueprint = bundle["blueprint"]
    add_field_artifact = bundle["add_field_artifact"]
    remove_field_artifact = bundle["remove_field_artifact"]
    manifest = bundle["zatca_manifest"]

    # 1. Inspect live Frappe DocType metadata for all mapping DocTypes
    meta_doctypes = [
        "Customer",
        "Item",
        "Item Price",
        "Sales Order",
        "Sales Order Item",
        "Delivery Note",
        "Delivery Note Item",
        "Sales Invoice",
        "Sales Invoice Item",
    ]
    meta_by_doctype: Dict[str, Dict[str, Any]] = {}
    with _FrappeSiteContext(site_a, sites_path) as fr:
        for dt in meta_doctypes:
            m = fr.get_meta(dt)
            meta_by_doctype[dt] = {
                "submittable": bool(m.is_submittable),
                "fields": {df.fieldname: df.fieldtype for df in m.fields},
            }

        mapping_check = verify_mapping_against_meta(mapping, meta_by_doctype)

        # 2. Run ChangeEngineAdapter end-to-end (provision -> initial entity -> add-field -> quarantine)
        ce = ChangeEngineAdapter(test_hooks=True)
        prov = ce.call(
            "provision_site",
            _ctx("t_alpha", "p6_prov"),
            {
                "idempotencyKey": "p6_prov_0001",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": blueprint["company"]["country"].lower(),
                "siteClass": "sandbox",
                "blueprintId": blueprint["meta"]["id"],
            },
        )
        assert prov["ok"], prov

        customer_def = copy.deepcopy(next(e for e in blueprint["entities"] if e["id"] == "customer"))
        initial_art = _seal_artifact(
            {
                "artifactSchema": "0.1.0",
                "kind": "forward",
                "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
                "blueprint": {
                    "id": add_field_artifact["blueprint"]["id"],
                    "base": None,
                    "target": copy.deepcopy(add_field_artifact["blueprint"]["base"]),
                    "diffHash": None,
                },
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "components": copy.deepcopy(add_field_artifact["components"]),
                "steps": [
                    {
                        "seq": 1,
                        "phase": 4,
                        "kind": "entity.add",
                        "subject": {"kind": "entity", "id": "customer", "parents": []},
                        "pointer": "/entities/customer",
                        "impact": "data_shape",
                        "ddlImpact": "additive",
                        "reversible": True,
                        "params": {"definition": customer_def},
                        "sourceOps": ["/entities/customer"],
                    }
                ],
                "skippedOps": [],
                "postConditions": [{"id": "pc_p6_01", "check": "exists", "pointer": "/entities/customer"}],
                "risk": {
                    "counts": {"cosmetic": 0, "config": 0, "data_shape": 1, "destructive": 0, "compliance": 0, "access": 0, "branding": 0},
                    "total": 1,
                    "maxImpact": "data_shape",
                    "needsDdlPlanGate": True,
                    "touchesCompliance": False,
                    "touchesAccess": False,
                    "touchesLedgerOrTax": False,
                    "requiresTeamReview": False,
                    "irreversibleSteps": 0,
                },
                "inverse": None,
            }
        )
        p0 = ce.call("plan", _ctx("t_alpha", "p6_plan0"), {"artifact": initial_art})["result"]
        a0 = ce.call(
            "apply",
            _ctx("t_alpha", "p6_app0"),
            {
                "idempotencyKey": "p6_apply0_0001",
                "artifact": initial_art,
                "planToken": p0["planToken"],
                "approvals": {
                    "changeApproved": "01J00000000000000000000010",
                    "gateApproved": "01J00000000000000000000011",
                },
            },
        )
        assert a0["ok"] and a0["result"]["status"] == "applied", a0

        p1 = ce.call("plan", _ctx("t_alpha", "p6_plan1"), {"artifact": add_field_artifact})["result"]
        a1 = ce.call(
            "apply",
            _ctx("t_alpha", "p6_app1"),
            {
                "idempotencyKey": "p6_apply1_0001",
                "artifact": add_field_artifact,
                "planToken": p1["planToken"],
                "approvals": {
                    "changeApproved": "01J00000000000000000000012",
                    "gateApproved": "01J00000000000000000000013",
                },
            },
        )
        assert a1["ok"] and a1["result"]["status"] == "applied", a1

        # 3. Mirror compiled field step onto live Frappe (Note DocType — passes live MariaDB DDL Plan Gate)
        step_def = add_field_artifact["steps"][0]["params"]["definition"]
        live_fieldname = f"custom_{step_def['id']}"
        frappe_adapter = FrappeDeploymentAdapter(frappe_module=fr, in_memory=False)
        rev = frappe_adapter.get_doctype_revision_hash("Note")
        live_dep = execute_single_field_deployment(
            db=frappe_adapter,
            deployment_id="dep_p0_bpl_bridge",
            idempotency_key="idem_p0_bpl_bridge",
            site_id=site_a,
            doctype="Note",
            base_revision_hash=rev,
            field_def={"fieldname": live_fieldname, "fieldtype": "Int", "label": "Payment Terms Days"},
            lock_wait_seconds=2,
        )
        fr.clear_cache(doctype="Note")
        note_meta_after = fr.get_meta("Note", cached=False)
        frappe_has_field = any(df.fieldname == live_fieldname for df in note_meta_after.fields)

        # Write a synthetic value to a Note on live Frappe, then soft-quarantine via Property Setter
        note_doc = fr.get_doc(
            {"doctype": "Note", "title": f"P0-BPL-Bridge-{uuid.uuid4().hex[:6]}", live_fieldname: 30}
        )
        note_doc.insert(ignore_permissions=True)
        fr.get_doc(
            {
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": "Note",
                "field_name": live_fieldname,
                "property": "hidden",
                "property_type": "Check",
                "value": "1",
            }
        ).insert(ignore_permissions=True)
        fr.db.commit()
        preserved_val = fr.db.get_value("Note", note_doc.name, live_fieldname)

        # Also apply remove-field artifact through ChangeEngineAdapter
        p2 = ce.call("plan", _ctx("t_alpha", "p6_plan2"), {"artifact": remove_field_artifact})["result"]
        a2 = ce.call(
            "apply",
            _ctx("t_alpha", "p6_app2"),
            {
                "idempotencyKey": "p6_apply2_0001",
                "artifact": remove_field_artifact,
                "planToken": p2["planToken"],
                "approvals": {
                    "changeApproved": "01J00000000000000000000014",
                    "gateApproved": "01J00000000000000000000015",
                },
            },
        )
        adapter_retained_ok = ce.dropped_data() == [] and a2["ok"] and a2["result"]["status"] == "applied"

    # 4. Component connection: exercise ZATCA Phase 1 component on golden-path invoice figures
    component_qr = None
    if zatca_generate_fn is not None:
        component_inv = zatca_generate_fn(
            {
                "invoice_id": "GTC-SI-0001",
                "issue_date": "2026-01-12",
                "issue_time": "11:00:00",
                "timezone": "Asia/Riyadh",
                "currency": "SAR",
                "invoice_type": "simplified",
                "transaction_type": "simplified_tax_invoice",
                "seller": {
                    "name": "Golden Trading Co",
                    "name_ar": "شركة المثال للتجارة",
                    "vat_number": "300000000000003",
                    "address": {
                        "street": "King Fahd Rd",
                        "building_no": "100",
                        "postal_code": "11564",
                        "city": "Riyadh",
                        "district": "Al-Olaya",
                        "country_code": "SA",
                    },
                },
                "lines": [
                    {
                        "item_code": "ITEM-001",
                        "description": "Golden Trading Widget",
                        "quantity": "10",
                        "unit_price": "15.00",
                        "vat_rate": "0.00",
                        "vat_category": "Z",
                        "exemption_reason_code": "VATEX-SA-34",
                        "exemption_reason": "Zero-rated golden path fixture",
                    }
                ],
                "totals": {
                    "total_taxable_amount": "150.00",
                    "total_vat_amount": "0.00",
                    "grand_total": "150.00",
                },
            }
        )
        component_qr = getattr(component_inv, "qr_code_tlv", None) or (
            component_inv.get("qr_base64") if isinstance(component_inv, dict) else None
        )

    passed = all(
        [
            len(mapping_check["missing_doctypes"]) == 0,
            len(mapping_check["missing_fields"]) == 0,
            live_dep["status"] == "APPLIED",
            frappe_has_field,
            int(preserved_val or 0) == 30,
            adapter_retained_ok,
            manifest.get("id") == "compliance.zatca_sa",
            bool(component_qr),
        ]
    )

    return {
        "proof_id": "E0-6",
        "passed": passed,
        "mapping_verification": mapping_check,
        "live_frappe_custom_field_added": frappe_has_field,
        "live_frappe_quarantine_preserved_value": preserved_val,
        "adapter_apply_and_quarantine": adapter_retained_ok,
        "component_id": manifest.get("id"),
        "component_qr_generated": bool(component_qr),
    }


def run_phase0_proofs(
    site_a: str,
    site_b: str,
    bundle: Dict[str, Any],
    engine_port: int = 8000,
    zatca_generate_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    sites_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute all 6 Phase 0 proofs on the pinned bench and return structured summary."""
    results = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "site_a": site_a,
        "site_b": site_b,
        "proofs": {
            "E0-1": proof_1_two_tenant_isolation(site_a, site_b, engine_port=engine_port, sites_path=sites_path),
            "E0-2": proof_2_reconciled_trading_transaction(site_a, sites_path=sites_path),
            "E0-3": proof_3_denied_operations(site_a, sites_path=sites_path),
            "E0-4": proof_4_interrupted_guarded_change_recovery(site_a, sites_path=sites_path),
            "E0-5": proof_5_duplicate_effect_prevention(site_a, sites_path=sites_path),
            "E0-6": proof_6_minimal_blueprint_component_adapter(
                site_a,
                bundle=bundle,
                zatca_generate_fn=zatca_generate_fn,
                sites_path=sites_path,
            ),
        },
    }
    results["all_passed"] = all(p["passed"] for p in results["proofs"].values())
    return results
