"""SEC-004: Adapter-level (mocked/simulated runtime) cross-tenant isolation regression tests.

Proves tenant keying, plan-token binding, idempotency scoping, member sync, collision-free
site resolution, and SQL/in-memory PolicyStore site isolation in the adapter and change_engine
layers. These tests run against SQLite and SimulatedFrappeRuntime; live Frappe/MariaDB/Redis
isolation (including Host header routing) is tested separately by
`live_sec_004_bench_attacks.py` via `infra/dev/docker/isolation/run_isolation_suite.py`.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import sys
import types
import unittest
from pathlib import Path

from change_engine.adapter import (
    ChangeEngineAdapter,
    FrappeBackendError,
    FrappeRuntimeBackend,
    FrappeSiteResolver,
    SimulatedFrappeRuntime,
    make_frappe_adapter,
)
from change_engine.adapter import contracts_support as cs
from change_engine.api import endpoints
from change_engine.guarded_apply.policy_enforcer import (
    PolicyType,
    RuntimePolicy,
    policy_catalog,
)
from change_engine.guarded_apply.policy_store import PolicyStore, get_current_site_id, policy_store


REPO_ROOT = Path(__file__).resolve().parents[5]
EXAMPLES_DIR = REPO_ROOT / "contracts" / "examples"


def _ctx(tenant: str, *, service: str = "control_plane", who: dict | None = None, req: str = "01J00000000000000000000001") -> dict:
    return {
        "contractVersion": "0.1.2",
        "requestId": req,
        "correlationId": f"corr_sec004_{tenant}",
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


def _initial_trading_artifact(bp_id: str) -> dict:
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
                "id": bp_id,
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
                "maxImpact": "data_shape",
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


def _add_credit_days_artifact(bp_id: str, field_id: str = "credit_days") -> dict:
    add_field = _load_example("compiled-artifact-add-field.json")
    art = copy.deepcopy(add_field)
    art["blueprint"]["id"] = bp_id
    step = art["steps"][0]
    step["subject"]["id"] = field_id
    step["pointer"] = f"/entities/customer/fields/{field_id}"
    step["params"]["definition"]["id"] = field_id
    art["postConditions"][0]["pointer"] = step["pointer"]
    return _seal(art)


def _provision(adapter: ChangeEngineAdapter, tenant: str, *, key: str) -> None:
    bp_id = f"bp-{tenant.replace('_', '-')}"
    res = adapter.call(
        "provision_site",
        _ctx(tenant),
        {
            "idempotencyKey": key,
            "siteClass": "sandbox",
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "blueprintId": bp_id,
            "countryPack": "sa",
        },
    )
    assert res["ok"], res


def _fake_frappe(site: str, *, user: str = "admin@example.invalid", roles: tuple[str, ...] = ("System Manager",)):
    f = types.SimpleNamespace()
    f.session = types.SimpleNamespace(user=user)
    f.local = types.SimpleNamespace(site=site)
    f.get_roles = lambda _u: list(roles)
    return f


class TestAdapterCrossTenantIsolation(unittest.TestCase):
    """Adapter-level (mocked/simulated runtime) tenant isolation: state, idempotency, plan tokens, members, data, and audits."""

    def _run_suite_on_adapter(self, adapter: ChangeEngineAdapter) -> None:
        _provision(adapter, "t_alpha", key="prov_alpha_000001")
        _provision(adapter, "t_beta", key="prov_beta_0000001")

        init_alpha = _initial_trading_artifact("bp-t-alpha")
        init_beta = _initial_trading_artifact("bp-t-beta")

        p_a0 = adapter.call("plan", _ctx("t_alpha"), {"artifact": init_alpha})
        self.assertTrue(p_a0["ok"], p_a0)
        ap_a0 = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "shared_idemp_init_01",
                "planToken": p_a0["result"]["planToken"],
                "artifact": init_alpha,
                "approvals": {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011"},
            },
        )
        self.assertTrue(ap_a0["ok"], ap_a0)
        self.assertEqual(ap_a0["result"]["status"], "applied")

        # Tenant B's config export must still be blank even after Tenant A applied trading entities.
        exp_b_before = adapter.call("export_config", _ctx("t_beta"), {})
        self.assertTrue(exp_b_before["ok"])
        self.assertEqual(exp_b_before["result"]["export"]["sections"]["entities"], [])

        # Cross-tenant planToken reuse must fail closed (planToken issued for t_alpha cannot be used on t_beta).
        alpha_field_art = _add_credit_days_artifact("bp-t-alpha", "alpha_only_col")
        beta_field_art = _add_credit_days_artifact("bp-t-beta", "alpha_only_col")
        p_a1 = adapter.call("plan", _ctx("t_alpha"), {"artifact": alpha_field_art})
        self.assertTrue(p_a1["ok"], p_a1)
        cross_token_apply = adapter.call(
            "apply",
            _ctx("t_beta"),
            {
                "idempotencyKey": "cross_token_attempt_01",
                "planToken": p_a1["result"]["planToken"],
                "artifact": beta_field_art,
                "approvals": {"changeApproved": "01J00000000000000000000012"},
            },
        )
        self.assertTrue(cross_token_apply["ok"], cross_token_apply)
        self.assertEqual(cross_token_apply["result"]["status"], "rejected")
        self.assertEqual(cross_token_apply["result"]["error"]["code"], "plan_token_invalid")

        # Same idempotencyKey used on t_beta must NOT replay t_alpha's cached outcome.
        p_b0 = adapter.call("plan", _ctx("t_beta"), {"artifact": init_beta})
        self.assertTrue(p_b0["ok"], p_b0)
        ap_b0 = adapter.call(
            "apply",
            _ctx("t_beta"),
            {
                "idempotencyKey": "shared_idemp_init_01",
                "planToken": p_b0["result"]["planToken"],
                "artifact": init_beta,
                "approvals": {"changeApproved": "01J00000000000000000000013", "gateApproved": "01J00000000000000000000014"},
            },
        )
        self.assertTrue(ap_b0["ok"], ap_b0)
        self.assertFalse(ap_b0["replayed"])
        self.assertEqual(ap_b0["result"]["artifactId"], init_beta["artifactId"])
        self.assertNotEqual(init_alpha["artifactId"], init_beta["artifactId"])

        # Apply alpha-only custom field & data probe; verify t_beta neither sees the field nor the data.
        ap_a1 = adapter.call(
            "apply",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "alpha_add_field_0001",
                "planToken": p_a1["result"]["planToken"],
                "artifact": alpha_field_art,
                "approvals": {"changeApproved": "01J00000000000000000000015"},
            },
        )
        self.assertTrue(ap_a1["ok"], ap_a1)
        adapter.data_probe("t_alpha", "/entities/customer/fields/alpha_only_col", 45)
        self.assertEqual(adapter.data_probe("t_alpha", "/entities/customer/fields/alpha_only_col"), 45)

        exp_b_after = adapter.call("export_config", _ctx("t_beta"), {})
        b_cust = next(e for e in exp_b_after["result"]["export"]["sections"]["entities"] if e["id"] == "customer")
        self.assertNotIn("alpha_only_col", [f["id"] for f in b_cust["fields"]])
        with self.assertRaises(ValueError):
            adapter.data_probe("t_beta", "/entities/customer/fields/alpha_only_col", 99)

        # Member sync isolation: syncing shadow member into t_alpha leaves t_beta without that member.
        sync_a = adapter.call(
            "sync_members",
            _ctx("t_alpha"),
            {
                "idempotencyKey": "sync_alpha_00000001",
                "syncVersion": 1,
                "mode": "full",
                "members": [
                    {"memberRef": "m_AlphaCanary01", "status": "active", "roleIds": ["sales_rep"], "displayName": "Alpha Rep"}
                ],
            },
        )
        self.assertTrue(sync_a["ok"], sync_a)
        self.assertTrue(adapter.auth_probe("t_alpha", "m_AlphaCanary01")["exists"])
        self.assertFalse(adapter.auth_probe("t_beta", "m_AlphaCanary01")["exists"])
        self.assertFalse(adapter.action_probe("t_beta", "m_AlphaCanary01")["allowed"])

        # Unknown / reserved 'platform' tenant fails closed.
        unknown = adapter.call("site_status", _ctx("t_nonexistent"), {})
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["error"]["code"], "tenant_not_found")
        plat = adapter.call("site_status", _ctx("platform"), {})
        self.assertFalse(plat["ok"])
        self.assertEqual(plat["error"]["code"], "tenant_not_found")

        # Audit entries remain strictly attributed to the calling tenant.
        alpha_audits = [row for row in adapter.audit_log() if row["tenant"] == "t_alpha"]
        beta_audits = [row for row in adapter.audit_log() if row["tenant"] == "t_beta"]
        self.assertTrue(alpha_audits)
        self.assertTrue(beta_audits)
        self.assertFalse({a["auditId"] for a in alpha_audits} & {b["auditId"] for b in beta_audits})

    def test_sqlite_adapter_cross_tenant_isolation(self) -> None:
        adapter = ChangeEngineAdapter(test_hooks=True)
        self._run_suite_on_adapter(adapter)

    def test_frappe_backend_simulated_runtime_cross_tenant_isolation(self) -> None:
        runtime = SimulatedFrappeRuntime()
        adapter = make_frappe_adapter(
            frappe_factory=lambda: runtime,
            auto_create_sites=True,
            site_resolver=FrappeSiteResolver(site_map={"t_alpha": "alpha.localhost", "t_beta": "beta.localhost"}),
            test_hooks=True,
        )
        self._run_suite_on_adapter(adapter)

        # Verify underlying Frappe sites inside SimulatedFrappeRuntime kept separate Custom Fields and Users.
        alpha_fields = {r["fieldname"] for r in runtime.sites["alpha.localhost"].rows["tabCustom Field"].values()}
        beta_fields = {r["fieldname"] for r in runtime.sites["beta.localhost"].rows["tabCustom Field"].values()}
        self.assertIn("custom_alpha_only_col", alpha_fields)
        self.assertNotIn("custom_alpha_only_col", beta_fields)
        self.assertEqual(len(runtime.sites["alpha.localhost"].rows["tabUser"]), 1)
        self.assertEqual(len(runtime.sites["beta.localhost"].rows["tabUser"]), 0)

        # Restarted adapter hydration restores each tenant into its own site record only.
        restarted = make_frappe_adapter(
            frappe_factory=lambda: runtime,
            auto_create_sites=True,
            site_resolver=FrappeSiteResolver(site_map={"t_alpha": "alpha.localhost", "t_beta": "beta.localhost"}),
            test_hooks=True,
        )
        exp_a = restarted.call("export_config", _ctx("t_alpha"), {})
        exp_b = restarted.call("export_config", _ctx("t_beta"), {})
        self.assertTrue(exp_a["ok"] and exp_b["ok"])
        a_cust = next(e for e in exp_a["result"]["export"]["sections"]["entities"] if e["id"] == "customer")
        b_cust = next(e for e in exp_b["result"]["export"]["sections"]["entities"] if e["id"] == "customer")
        self.assertIn("alpha_only_col", [f["id"] for f in a_cust["fields"]])
        self.assertNotIn("alpha_only_col", [f["id"] for f in b_cust["fields"]])


class _SqlDbShim:
    """Minimal SQLite shim implementing Frappe's db.sql(%s, params, as_dict=True) for PolicyStore SQL tests."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.executed_queries: list[str] = []
        self.conn.execute(
            """
            CREATE TABLE `tabChange Engine Policy` (
                name TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                doctype TEXT NOT NULL,
                policy_type TEXT NOT NULL,
                target_field TEXT,
                governance_tier INTEGER NOT NULL,
                condition_expr TEXT NOT NULL,
                required_role TEXT,
                error_message TEXT,
                stage TEXT,
                active INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                created_by TEXT,
                created_at TEXT,
                updated_by TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE `tabChange Engine Policy Audit` (
                name TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                doctype TEXT NOT NULL,
                revision INTEGER NOT NULL,
                action TEXT NOT NULL,
                changed_by TEXT,
                payload_before TEXT,
                payload_after TEXT,
                timestamp TEXT
            )
            """
        )

    def sql(self, query: str, values: tuple = (), as_dict: bool = False):
        self.executed_queries.append(query)
        sql_text = query.replace(" FOR UPDATE", "").replace("%s", "?")
        cur = self.conn.execute(sql_text, values)
        if as_dict:
            return [dict(row) for row in cur.fetchall()]
        return cur.fetchall()

    def commit(self) -> None:
        self.conn.commit()


class TestSiteResolverAndPolicyStoreIsolation(unittest.TestCase):
    """Adapter-level (mocked) site resolution and PolicyStore SQL/context site isolation tests.

    NOTE: Real HTTP Host header -> frappe.local.site binding is proven only by the live bench
    suite (`live_sec_004_bench_attacks.py`), not by these unit tests.
    """

    def setUp(self) -> None:
        self._orig_frappe = endpoints.frappe
        policy_catalog.reset()
        policy_store.reset_store()

    def tearDown(self) -> None:
        endpoints.frappe = self._orig_frappe
        policy_catalog.reset()
        policy_store.reset_store()

    def test_site_resolver_rejects_traversal_collisions_and_invalid_tenants(self) -> None:
        resolver = FrappeSiteResolver()
        for bad in (
            "",
            "platform",
            "../etc/passwd",
            "tenant..a",
            "t/a",
            "t a",
            "tenant;id",
            "acme-1",
            "acme_1",
            "t_a",
            "t_acme.1",
            "t_acme-1",
            "T_acme_1",
            "t_acme_1_",
            "t__acme",
            "t_acme_1\n",
        ):
            with self.subTest(tenant_id=bad):
                with self.assertRaises(FrappeBackendError):
                    resolver.resolve(bad)

        resolved = {
            tid: resolver.resolve(tid)
            for tid in ("t_acme_1", "t_acme_2", "t_acme__1", "t_alpha", "t_beta")
        }
        self.assertEqual(resolved["t_acme_1"], "t-acme-1.localhost")
        self.assertEqual(resolved["t_acme_2"], "t-acme-2.localhost")
        self.assertEqual(resolved["t_acme__1"], "t-acme--1.localhost")
        self.assertEqual(len(set(resolved.values())), len(resolved))

        with self.assertRaises(FrappeBackendError):
            FrappeSiteResolver(site_map={"t_alpha": "dup.localhost", "t_beta": "DUP.localhost."})

    def test_runtime_policy_store_isolates_sites_and_blocks_cross_site_addressing(self) -> None:
        pol = RuntimePolicy(
            policy_id="POL_ALPHA_ONLY",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 5",
            required_role="Finance Director",
            error_message="Alpha max discount is 5%.",
        )
        endpoints.frappe = _fake_frappe("alpha.localhost")
        out = endpoints.register_runtime_policy(pol)
        self.assertTrue(out["success"])
        self.assertEqual(get_current_site_id(), "alpha.localhost")

        # Attempting to explicitly address beta.localhost while request context is alpha.localhost must fail closed.
        with self.assertRaises(PermissionError):
            get_current_site_id(explicit_site="beta.localhost")

        # Switching active site context to beta.localhost must not expose alpha.localhost's policy,
        # and addressing alpha.localhost from beta.localhost's context must also fail closed.
        endpoints.frappe = _fake_frappe("beta.localhost")
        self.assertEqual(get_current_site_id(), "beta.localhost")
        beta_policies = policy_store.get_policies(site_id="beta.localhost")
        self.assertEqual(len(beta_policies), 0)
        with self.assertRaises(PermissionError):
            policy_store.get_policies(site_id="alpha.localhost")

        endpoints.frappe = _fake_frappe("alpha.localhost")
        alpha_policies = policy_store.get_policies(site_id="alpha.localhost")
        self.assertEqual(len(alpha_policies), 1)

    def test_policy_store_sql_path_enforces_where_site_id_isolation(self) -> None:
        """Exercise PolicyStore's live SQL code path (WHERE site_id = %s) across two sites in one table."""
        db_shim = _SqlDbShim()
        fake_frappe = _fake_frappe("alpha.localhost")
        fake_frappe.db = db_shim
        store = PolicyStore(frappe_module=fake_frappe)
        self.assertTrue(store.is_live_frappe)

        pol_a = RuntimePolicy(
            policy_id="POL_SQL_ALPHA",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 5",
            required_role="Finance Director",
            error_message="Alpha SQL canary.",
        )
        pol_b = RuntimePolicy(
            policy_id="POL_SQL_BETA",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 10",
            required_role="Finance Director",
            error_message="Beta SQL canary.",
        )

        endpoints.frappe = fake_frappe
        store.save_policy(pol_a, actor="alpha_admin")

        fake_frappe.local.site = "beta.localhost"
        store.save_policy(pol_b, actor="beta_admin")

        # Beta's SQL reads see only Beta's policy and audit rows, never Alpha's.
        self.assertIsNone(store.get_policy("POL_SQL_ALPHA"))
        self.assertEqual([p.policy_id for p in store.get_policies()], ["POL_SQL_BETA"])
        self.assertEqual([a["policy_id"] for a in store.get_audit_trail()], ["POL_SQL_BETA"])
        with self.assertRaises(PermissionError):
            store.get_policies(site_id="alpha.localhost")

        # Alpha's SQL reads see only Alpha's policy and audit rows, never Beta's.
        fake_frappe.local.site = "alpha.localhost"
        self.assertIsNone(store.get_policy("POL_SQL_BETA"))
        self.assertEqual([p.policy_id for p in store.get_policies()], ["POL_SQL_ALPHA"])
        self.assertEqual([a["policy_id"] for a in store.get_audit_trail()], ["POL_SQL_ALPHA"])
        with self.assertRaises(PermissionError):
            store.get_policy("POL_SQL_BETA", site_id="beta.localhost")

        # Confirm the SQL WHERE site_id = %s queries actually executed against the DB shim.
        self.assertTrue(any("WHERE site_id = %s" in q for q in db_shim.executed_queries))


if __name__ == "__main__":
    unittest.main()
