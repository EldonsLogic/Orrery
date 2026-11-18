"""ERP-012 tests for FrappeRuntimeBackend & ChangeEngineAdapter Frappe integration."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from change_engine.adapter import (
    ADAPTER_ID,
    ChangeEngineAdapter,
    ChangeEngineHarness,
    FrappeRuntimeBackend,
    FrappeSiteResolver,
    SimulatedFrappeRuntime,
    make_frappe_adapter,
    make_frappe_harness,
)
from change_engine.adapter import contracts_support as cs

REPO_ROOT = Path(__file__).resolve().parents[5]
EXAMPLES_DIR = REPO_ROOT / "contracts" / "examples"


def _ctx(tenant: str = "t_alpha", service: str = "control_plane", who: dict | None = None) -> dict:
    return {
        "contractVersion": "0.1.2",
        "requestId": "01J00000000000000000000001",
        "correlationId": "corr_erp012_01",
        "tenantId": tenant,
        "caller": {
            "service": service,
            "onBehalfOf": who if who is not None else {"kind": "user", "id": "usr_owner"},
        },
        "deadlineMs": 30000,
    }


def _seal(art: dict) -> dict:
    art = copy.deepcopy(art)
    if art.get("inverse"):
        art["inverse"] = _seal(art["inverse"])
    digest, art_id = cs.artifact_hashes(art)
    art["artifactId"] = art_id
    art["integrity"] = {"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None}
    return art


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _make_initial_build() -> dict:
    bp = _load_example("blueprint-trading-minimal.json")
    customer = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "customer"))
    sales_order = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "sales_order"))
    role_sales = copy.deepcopy(next(r for r in bp["roles"] if r["id"] == "sales_rep"))
    add_field = _load_example("compiled-artifact-add-field.json")
    return _seal(
        {
            "artifactSchema": "0.1.0",
            "kind": "forward",
            "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
            "blueprint": {
                "id": add_field["blueprint"]["id"],
                "base": None,
                "target": copy.deepcopy(add_field["blueprint"]["base"]),
                "diffHash": None,
            },
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "components": copy.deepcopy(add_field["components"]),
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
                    "params": {"definition": customer},
                    "sourceOps": ["/entities/customer"],
                },
                {
                    "seq": 2,
                    "phase": 4,
                    "kind": "entity.add",
                    "subject": {"kind": "entity", "id": "sales_order", "parents": []},
                    "pointer": "/entities/sales_order",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {"definition": sales_order},
                    "sourceOps": ["/entities/sales_order"],
                },
                {
                    "seq": 3,
                    "phase": 7,
                    "kind": "role.upsert",
                    "subject": {"kind": "role", "id": "sales_rep", "parents": []},
                    "pointer": "/roles/sales_rep",
                    "impact": "access",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": role_sales},
                    "sourceOps": ["/roles/sales_rep"],
                },
            ],
            "skippedOps": [],
            "postConditions": [
                {"id": "pc_001", "check": "exists", "pointer": "/entities/customer"},
                {"id": "pc_002", "check": "exists", "pointer": "/entities/sales_order"},
            ],
            "risk": {
                "counts": {
                    "cosmetic": 0,
                    "config": 0,
                    "data_shape": 2,
                    "destructive": 0,
                    "compliance": 0,
                    "access": 1,
                    "branding": 0,
                },
                "total": 3,
                "maxImpact": "access",
                "needsDdlPlanGate": True,
                "touchesCompliance": False,
                "touchesAccess": True,
                "touchesLedgerOrTax": False,
                "requiresTeamReview": False,
                "irreversibleSteps": 0,
            },
            "inverse": None,
        }
    )


def _provision_and_build(adapter: ChangeEngineAdapter, tenant: str = "t_alpha", country: str = "sa") -> dict:
    res = adapter.call(
        "provision_site",
        _ctx(tenant),
        {
            "idempotencyKey": f"prov_{tenant}_000001",
            "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
            "blueprintId": "example-trading-001",
            "siteClass": "production",
            "countryPack": country,
        },
    )
    assert res["ok"], res
    init_art = _make_initial_build()
    plan = adapter.call("plan", _ctx(tenant), {"artifact": init_art})
    assert plan["ok"], plan
    app = adapter.call(
        "apply",
        _ctx(tenant),
        {
            "idempotencyKey": f"init_{tenant}_000001",
            "artifact": init_art,
            "planToken": plan["result"]["planToken"],
            "approvals": {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011"},
        },
    )
    assert app["ok"] and app["result"]["status"] == "applied", app
    return init_art


class TestErp012FrappeAdapter(unittest.TestCase):
    def test_fail_closed_when_real_frappe_absent(self):
        adapter = make_frappe_adapter(simulated=False, test_hooks=True)
        res = adapter.call(
            "provision_site",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "prov_fail_closed_01",
                "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
                "blueprintId": "example-trading-001",
                "siteClass": "production",
                "countryPack": "sa",
            },
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"]["code"], "engine_unavailable")
        self.assertNotIn("frappe", json.dumps(res).lower())
        # Must not persist half-provisioned site on fail-closed
        status = adapter.call("site_status", _ctx("t_alpha"), {})
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"]["code"], "tenant_not_found")

    def test_make_frappe_harness_factory(self):
        h = make_frappe_harness()
        self.assertIsInstance(h, ChangeEngineHarness)
        self.assertIsNotNone(h.adapter.frappe_backend)
        h_no_hooks = h.without_test_hooks()
        self.assertIs(h_no_hooks.adapter.frappe_backend, h.adapter.frappe_backend)

    def test_provision_defaults_valuation_rounding_immutable_ledger_and_item_permlevel(self):
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        _provision_and_build(adapter, "t_alpha", "sa")

        site_db = sim.sites["t-alpha.localhost"]
        self.assertEqual(site_db.singles["Stock Settings"]["valuation_method"], "Moving Average")
        self.assertEqual(site_db.singles["Stock Settings"]["allow_negative_stock"], 0)
        self.assertEqual(site_db.singles["System Settings"]["rounding_method"], "Commercial Rounding")
        self.assertEqual(site_db.singles["System Settings"]["country"], "Saudi Arabia")
        self.assertEqual(site_db.singles["System Settings"]["language"], "ar")
        self.assertEqual(site_db.singles["System Settings"]["time_zone"], "Asia/Riyadh")
        self.assertEqual(site_db.singles["Accounts Settings"]["enable_immutable_ledger"], 1)

        # Item.valuation_rate must have permlevel=1 Property Setter (E0-7 #4)
        ps_rows = site_db.rows["tabProperty Setter"]
        val_perm = [
            r
            for r in ps_rows.values()
            if r["doc_type"] == "Item" and r["field_name"] == "valuation_rate" and r["property"] == "permlevel"
        ]
        self.assertEqual(len(val_perm), 1)
        self.assertEqual(int(val_perm[0]["value"]), 1)

    def test_guarded_field_add_quarantine_preserve_data_and_restore(self):
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        _provision_and_build(adapter, "t_alpha")

        add_field = _load_example("compiled-artifact-add-field.json")
        p1 = adapter.call("plan", _ctx("t_alpha"), {"artifact": add_field})
        self.assertTrue(p1["ok"])
        self.assertEqual(p1["result"]["verdict"], "auto_approved")

        a1 = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "apply_custom_field_0001",
                "artifact": add_field,
                "planToken": p1["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000012"},
            },
        )
        self.assertTrue(a1["ok"] and a1["result"]["status"] == "applied", a1)

        site_db = sim.sites["t-alpha.localhost"]
        # Real Custom Field and ALTER TABLE ADD COLUMN occurred
        self.assertTrue(any(r["dt"] == "Customer" and r["fieldname"] == "custom_payment_terms_days" for r in site_db.rows["tabCustom Field"].values()))
        self.assertTrue(any(c.name == "custom_payment_terms_days" for c in site_db.table_columns["tabCustomer"]))
        self.assertTrue(any("ADD COLUMN `custom_payment_terms_days`" in stmt for stmt in site_db.ddl_statements))

        # Write real data into the column
        ptr = "/entities/customer/fields/payment_terms_days"
        adapter.data_probe("t_alpha", ptr, 45)
        self.assertEqual(adapter.data_probe("t_alpha", ptr), 45)

        # Quarantine field (remove-field artifact) -> non-destructive Property Setter hidden=1, reqd=0; data stays!
        rem_field = _load_example("compiled-artifact-remove-field.json")
        p2 = adapter.call("plan", _ctx("t_alpha"), {"artifact": rem_field})
        a2 = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "apply_quarantine_0001",
                "artifact": rem_field,
                "planToken": p2["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000013"},
            },
        )
        self.assertTrue(a2["ok"] and a2["result"]["status"] == "applied", a2)
        self.assertEqual(adapter.data_probe("t_alpha", ptr), 45)
        self.assertEqual(adapter.dropped_data(), [])
        hidden_ps = [
            r
            for r in site_db.rows["tabProperty Setter"].values()
            if r["doc_type"] == "Customer" and r["field_name"] == "custom_payment_terms_days" and r["property"] == "hidden"
        ]
        self.assertEqual(int(hidden_ps[-1]["value"]), 1)

        # Rollback restore -> hidden=0 Property Setter and data remains intact
        rb = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "rollback_quarantine_0001",
                "forwardArtifact": rem_field,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000014"},
            },
        )
        self.assertTrue(rb["ok"] and rb["result"]["status"] == "applied", rb)
        self.assertEqual(adapter.data_probe("t_alpha", ptr), 45)
        hidden_ps_after = [
            r
            for r in site_db.rows["tabProperty Setter"].values()
            if r["doc_type"] == "Customer" and r["field_name"] == "custom_payment_terms_days" and r["property"] == "hidden"
        ]
        self.assertEqual(int(hidden_ps_after[-1]["value"]), 0)

    def test_decimal_field_add_and_workflow_and_report_deployment(self):
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        init_art = _provision_and_build(adapter, "t_alpha")

        # Deploy workflow artifact (compiled-artifact-add-workflow-state.json)
        wf_art = _load_example("compiled-artifact-add-workflow-state.json")
        pwf = adapter.call("plan", _ctx("t_alpha"), {"artifact": wf_art})
        self.assertTrue(pwf["ok"], pwf)
        self.assertEqual(pwf["result"]["verdict"], "auto_approved")
        awf = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "apply_workflow_0001",
                "artifact": wf_art,
                "planToken": pwf["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000015", "teamReviewed": "01J00000000000000000000016"},
            },
        )
        self.assertTrue(awf["ok"] and awf["result"]["status"] == "applied", awf)
        site_db = sim.sites["t-alpha.localhost"]
        self.assertIn("sales_order_flow", site_db.rows["tabWorkflow"])

        # Deploy decimal(21,9) money field + report artifact
        rev2_target = wf_art["blueprint"]["target"]
        rev3_target = {"hash": "sha256:" + ("c" * 64), "revision": 3}
        dec_steps = [
            {
                "seq": 1,
                "phase": 5,
                "kind": "field.add",
                "subject": {"kind": "field", "id": "credit_cap", "parents": [{"kind": "entity", "id": "customer"}]},
                "pointer": "/entities/customer/fields/credit_cap",
                "impact": "data_shape",
                "ddlImpact": "additive",
                "reversible": True,
                "params": {"definition": {"id": "credit_cap", "type": "money", "labels": {"en": "Credit Cap"}}},
                "sourceOps": ["/entities/customer/fields/credit_cap"],
            },
            {
                "seq": 2,
                "phase": 10,
                "kind": "report.upsert",
                "subject": {"kind": "report", "id": "so_daily_summary", "parents": []},
                "pointer": "/reports/so_daily_summary",
                "impact": "config",
                "ddlImpact": "none",
                "reversible": True,
                "params": {
                    "definition": {
                        "id": "so_daily_summary",
                        "kind": "summary",
                        "entity": "sales_order",
                        "labels": {"en": "SO Daily Summary"},
                        "metrics": [{"id": "orders", "op": "count", "groupBy": ["customer"]}],
                        "visibleToRoles": ["sales_rep"],
                    }
                },
                "sourceOps": ["/reports/so_daily_summary"],
            },
        ]
        dec_inv = {
            "artifactSchema": "0.1.0",
            "kind": "inverse",
            "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
            "blueprint": {
                "id": init_art["blueprint"]["id"],
                "base": copy.deepcopy(rev3_target),
                "target": copy.deepcopy(rev2_target),
                "diffHash": "sha256:" + ("d" * 64),
            },
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "components": copy.deepcopy(init_art["components"]),
            "steps": [
                {
                    "seq": 1,
                    "phase": 11,
                    "kind": "report.disable",
                    "subject": {"kind": "report", "id": "so_daily_summary", "parents": []},
                    "pointer": "/reports/so_daily_summary",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": copy.deepcopy(dec_steps[1]["params"]["definition"])},
                    "sourceOps": ["/reports/so_daily_summary"],
                },
                {
                    "seq": 2,
                    "phase": 15,
                    "kind": "field.quarantine",
                    "subject": {"kind": "field", "id": "credit_cap", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/credit_cap",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": copy.deepcopy(dec_steps[0]["params"]["definition"])},
                    "sourceOps": ["/entities/customer/fields/credit_cap"],
                },
            ],
            "skippedOps": [],
            "postConditions": [
                {"id": "pc_001", "check": "quarantined", "pointer": "/entities/customer/fields/credit_cap"},
                {"id": "pc_002", "check": "disabled", "pointer": "/reports/so_daily_summary"},
            ],
            "risk": {
                "counts": {
                    "cosmetic": 0,
                    "config": 0,
                    "data_shape": 0,
                    "destructive": 2,
                    "compliance": 0,
                    "access": 0,
                    "branding": 0,
                },
                "total": 2,
                "maxImpact": "destructive",
                "needsDdlPlanGate": False,
                "touchesCompliance": False,
                "touchesAccess": False,
                "touchesLedgerOrTax": False,
                "requiresTeamReview": False,
                "irreversibleSteps": 0,
            },
            "inverse": None,
        }
        dec_art = _seal(
            {
                "artifactSchema": "0.1.0",
                "kind": "forward",
                "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
                "blueprint": {
                    "id": init_art["blueprint"]["id"],
                    "base": copy.deepcopy(rev2_target),
                    "target": copy.deepcopy(rev3_target),
                    "diffHash": "sha256:" + ("e" * 64),
                },
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "components": copy.deepcopy(init_art["components"]),
                "steps": dec_steps,
                "skippedOps": [],
                "postConditions": [
                    {"id": "pc_001", "check": "exists", "pointer": "/entities/customer/fields/credit_cap"},
                    {"id": "pc_002", "check": "exists", "pointer": "/reports/so_daily_summary"},
                ],
                "risk": {
                    "counts": {
                        "cosmetic": 0,
                        "config": 1,
                        "data_shape": 1,
                        "destructive": 0,
                        "compliance": 0,
                        "access": 0,
                        "branding": 0,
                    },
                    "total": 2,
                    "maxImpact": "data_shape",
                    "needsDdlPlanGate": True,
                    "touchesCompliance": False,
                    "touchesAccess": False,
                    "touchesLedgerOrTax": False,
                    "requiresTeamReview": False,
                    "irreversibleSteps": 0,
                },
                "inverse": dec_inv,
            }
        )
        pdec = adapter.call("plan", _ctx("t_alpha"), {"artifact": dec_art})
        self.assertTrue(pdec["ok"] and pdec["result"]["verdict"] == "auto_approved", pdec)
        adec = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "apply_decimal_report_0001",
                "artifact": dec_art,
                "planToken": pdec["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000017"},
            },
        )
        self.assertTrue(adec["ok"] and adec["result"]["status"] == "applied", adec)
        self.assertTrue(any("`custom_credit_cap` decimal(21,9)" in stmt for stmt in site_db.ddl_statements))
        self.assertIn("so_daily_summary", site_db.rows["tabReport"])

    def test_sync_members_shadow_users_and_t36_impersonation(self):
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        _provision_and_build(adapter, "t_alpha")

        # Seed a low-privilege Item record with valuation_rate
        site_db = sim.sites["t-alpha.localhost"]
        site_db.rows["tabItem"]["ITEM-001"] = {
            "name": "ITEM-001",
            "item_code": "ITEM-001",
            "item_name": "Widget",
            "valuation_rate": 12.50,
            "standard_rate": 25.00,
        }

        # Sync shadow members (with displayName PII supplied in input that must NOT enter User)
        sync_res = adapter.call(
            "sync_members",
            _ctx("t_alpha", service="identity"),
            {
                "idempotencyKey": "sync_members_batch_0001",
                "mode": "full",
                "syncVersion": 1,
                "members": [
                    {"memberRef": "m_sales001", "status": "active", "roleIds": ["sales_rep"], "displayName": "Alice SecretPII"},
                    {"memberRef": "m_locked01", "status": "disabled", "roleIds": ["sales_rep"], "displayName": "Bob Disabled"},
                ],
            },
        )
        self.assertTrue(sync_res["ok"], sync_res)
        self.assertEqual(sync_res["result"]["created"], 2)

        # Auth & action probes reflect real Frappe User + __Auth + Email Queue
        self.assertEqual(adapter.auth_probe("t_alpha", "m_sales001"), {"exists": True, "canAuthenticate": False, "emailSent": False})
        self.assertEqual(adapter.action_probe("t_alpha", "m_sales001"), {"allowed": True})
        self.assertEqual(adapter.action_probe("t_alpha", "m_locked01"), {"allowed": False})
        self.assertEqual(len(site_db.email_queue), 0)
        self.assertEqual(len(site_db.auth_table), 0)
        user_dump = json.dumps(site_db.rows["tabUser"])
        self.assertNotIn("Alice SecretPII", user_dump)
        self.assertNotIn("Bob Disabled", user_dump)

        # T36 caller impersonation: active sales_rep sees permitted fields but valuation_rate (permlevel=1) is stripped
        rows = adapter.execute_as_caller(
            "t_alpha",
            {"service": "operate_gateway", "onBehalfOf": {"kind": "user", "id": "m_sales001"}},
            lambda f: f.get_list("Item", fields=["item_code", "standard_rate", "valuation_rate"]),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["standard_rate"], 25.00)
        self.assertNotIn("valuation_rate", rows[0])

        # T36: sales_rep cannot read GL Entry -> permission_denied (no Administrator fallback)
        with self.assertRaises(Exception) as gl_exc:
            adapter.execute_as_caller(
                "t_alpha",
                {"service": "operate_gateway", "onBehalfOf": {"kind": "user", "id": "m_sales001"}},
                lambda f: f.get_list("GL Entry", fields=["account", "debit"]),
            )
        self.assertEqual(getattr(gl_exc.exception, "code", None), "permission_denied")

        # T36: disabled user, unknown user, and non-human agent principal must fail closed
        for bad_caller in (
            None,
            {"service": "operate_gateway", "onBehalfOf": {"kind": "agent", "id": "ag_01"}},
            {"service": "operate_gateway", "onBehalfOf": {"kind": "user", "id": "m_unknown"}},
            {"service": "operate_gateway", "onBehalfOf": {"kind": "user", "id": "m_locked01"}},
        ):
            with self.assertRaises(Exception) as bad_exc:
                adapter.execute_as_caller("t_alpha", bad_caller, lambda f: f.get_list("Item"))
            self.assertEqual(getattr(bad_exc.exception, "code", None), "permission_denied")

    def test_multi_tenant_isolation_and_stale_prepared_health(self):
        sim = SimulatedFrappeRuntime()
        resolver = FrappeSiteResolver(site_map={"t_alpha": "alpha.localhost", "t_beta": "beta.localhost"})
        backend = FrappeRuntimeBackend(site_resolver=resolver, frappe_factory=lambda: sim, auto_create_sites=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)

        _provision_and_build(adapter, "t_alpha", "sa")
        _provision_and_build(adapter, "t_beta", "ae")

        self.assertEqual(sim.sites["alpha.localhost"].singles["System Settings"]["country"], "Saudi Arabia")
        self.assertEqual(sim.sites["beta.localhost"].singles["System Settings"]["country"], "United Arab Emirates")

        # Apply field to t_alpha only; t_beta must remain untouched
        add_field = _load_example("compiled-artifact-add-field.json")
        p1 = adapter.call("plan", _ctx("t_alpha"), {"artifact": add_field})
        a1 = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "apply_isolation_0001",
                "artifact": add_field,
                "planToken": p1["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000020"},
            },
        )
        self.assertTrue(a1["ok"])
        self.assertTrue(any(c.name == "custom_payment_terms_days" for c in sim.sites["alpha.localhost"].table_columns["tabCustomer"]))
        self.assertFalse(any(c.name == "custom_payment_terms_days" for c in sim.sites["beta.localhost"].table_columns["tabCustomer"]))

        # E0-7 #2: Stale unfinalized PREPARED audit row on alpha flags recovery: down on alpha, ok on beta
        sim.sites["alpha.localhost"].rows["tabChange Engine Audit"]["dep_stale"] = {
            "name": "dep_stale",
            "deployment_id": "dep_stale",
            "status": "PREPARED",
        }
        h_alpha = adapter.call("health", _ctx("t_alpha", service="observability"), {})
        h_beta = adapter.call("health", _ctx("t_beta", service="observability"), {})
        self.assertEqual(h_alpha["result"]["status"], "down")
        self.assertEqual(dict((c["name"], c["status"]) for c in h_alpha["result"]["checks"])["recovery"], "down")
        self.assertEqual(h_beta["result"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
