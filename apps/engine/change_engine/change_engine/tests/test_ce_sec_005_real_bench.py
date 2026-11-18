"""CE-SEC-005: Real Frappe bench integration & security regression suite.

Runs ONLY against a live pinned Frappe/ERPNext/HRMS/change_engine bench with
real MariaDB 11.4 and Redis — NO mocks, NO SimulatedFrappeRuntime, NO fake
frappe namespaces.

- When ``CE_SEC_005_REAL_BENCH=1`` is set, missing Frappe/DB/apps MUST fail
  closed (never skip).
- When running in offline unit-test environments without ``CE_SEC_005_REAL_BENCH=1``
  and without an active Frappe site connection, the suite skips cleanly.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
import urllib.request
import uuid
from typing import Any, Dict, Optional

try:
    import frappe  # type: ignore[import-not-found]
except ImportError:
    frappe = None

if frappe is not None:
    from change_engine.adapter import (
        ADAPTER_ID,
        ChangeEngineAdapter,
        FrappeRuntimeBackend,
        FrappeSiteResolver,
    )
    from change_engine.adapter import contracts_support as cs
    from change_engine.api import endpoints
    from change_engine.guarded_apply.policy_enforcer import (
        PolicyType,
        RuntimePolicy,
        RuntimePolicyViolation,
        policy_catalog,
    )
    from change_engine.guarded_apply.policy_expression import PolicyExpressionError
    from change_engine.guarded_apply.policy_store import get_current_site_id, policy_store

EXPECTED_APPS = ("frappe", "erpnext", "hrms", "change_engine")
EXPECTED_VERSIONS = {
    "frappe": "15.126.0",
    "erpnext": "15.124.5",
    "hrms": "15.64.8",
    "change_engine": "0.1.0",
}
EXPECTED_MARIADB_SERIES = "11.4."
REQUIRE_REAL_BENCH = os.environ.get("CE_SEC_005_REAL_BENCH") == "1"


def _has_active_frappe_db() -> bool:
    if frappe is None:
        return False
    try:
        site = getattr(getattr(frappe, "local", None), "site", None)
        db = getattr(frappe, "db", None)
        return bool(site and db is not None and callable(getattr(db, "sql", None)))
    except Exception:
        return False


def _resolve_sites_path() -> str:
    env_path = os.environ.get("FRAPPE_SITES_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path
    cwd = os.getcwd()
    if os.path.basename(cwd) == "sites" and os.path.isfile(os.path.join(cwd, "common_site_config.json")):
        return cwd
    cand = os.path.join(cwd, "sites")
    if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "common_site_config.json")):
        return cand
    bench_sites = os.path.expanduser("~/frappe-bench/sites")
    if os.path.isdir(bench_sites):
        return bench_sites
    return cwd


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


def _adapter_ctx(tenant: str, suffix: str) -> Dict[str, Any]:
    digest = hashlib.sha256(f"{tenant}:{suffix}".encode("utf-8")).hexdigest()[:23].upper()
    return {
        "contractVersion": "0.1.2",
        "requestId": f"01J{digest}",
        "correlationId": f"corr_ce005_{suffix}",
        "tenantId": tenant,
        "caller": {
            "service": "control_plane",
            "onBehalfOf": {"kind": "user", "id": "usr_ce005_owner"},
        },
        "deadlineMs": 30000,
    }


def _build_initial_customer_artifact() -> Dict[str, Any]:
    rev1_target = {"hash": "sha256:" + ("a" * 64), "revision": 1}
    forward = {
        "artifactSchema": "0.1.0",
        "kind": "forward",
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {
            "id": "bp_ce005_init",
            "base": None,
            "target": rev1_target,
            "diffHash": None,
        },
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [{"id": "core.customer", "version": "0.1.0"}],
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
                "params": {"definition": {"id": "customer", "fields": []}},
                "sourceOps": ["/entities/customer"],
            }
        ],
        "skippedOps": [],
        "postConditions": [
            {"id": "pc_init_001", "check": "exists", "pointer": "/entities/customer"},
        ],
        "risk": {
            "counts": {
                "cosmetic": 0,
                "config": 0,
                "data_shape": 1,
                "destructive": 0,
                "compliance": 0,
                "access": 0,
                "branding": 0,
            },
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
    return _seal_artifact(forward)


def _build_add_field_artifact(
    field_id: str,
    label: str = "CE005 Test Field",
    blueprint_id: str | None = None,
) -> Dict[str, Any]:
    bp_id = blueprint_id or f"bp_ce005_{field_id}"
    base_target = {"hash": "sha256:" + ("a" * 64), "revision": 1}
    next_target = {"hash": "sha256:" + ("b" * 64), "revision": 2}
    defn = {
        "id": field_id,
        "type": "string",
        "labels": {"en": label},
        "required": False,
        "readOnly": False,
    }
    step = {
        "seq": 1,
        "phase": 5,
        "kind": "field.add",
        "subject": {"kind": "field", "id": field_id, "parents": [{"kind": "entity", "id": "customer"}]},
        "pointer": f"/entities/customer/fields/{field_id}",
        "impact": "data_shape",
        "ddlImpact": "additive",
        "reversible": True,
        "params": {"definition": defn},
        "sourceOps": [f"/entities/customer/fields/{field_id}"],
    }
    inverse = {
        "artifactSchema": "0.1.0",
        "kind": "inverse",
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {
            "id": bp_id,
            "base": next_target,
            "target": base_target,
            "diffHash": "sha256:" + ("c" * 64),
        },
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [{"id": "core.customer", "version": "0.1.0"}],
        "steps": [
            {
                "seq": 1,
                "phase": 15,
                "kind": "field.quarantine",
                "subject": {"kind": "field", "id": field_id, "parents": [{"kind": "entity", "id": "customer"}]},
                "pointer": f"/entities/customer/fields/{field_id}",
                "impact": "destructive",
                "ddlImpact": "none",
                "reversible": True,
                "params": {"definition": defn},
                "sourceOps": [f"/entities/customer/fields/{field_id}"],
            }
        ],
        "skippedOps": [],
        "postConditions": [
            {"id": "pc_q_001", "check": "quarantined", "pointer": f"/entities/customer/fields/{field_id}"},
        ],
        "risk": {
            "counts": {
                "cosmetic": 0,
                "config": 0,
                "data_shape": 0,
                "destructive": 1,
                "compliance": 0,
                "access": 0,
                "branding": 0,
            },
            "total": 1,
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
    forward = {
        "artifactSchema": "0.1.0",
        "kind": "forward",
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {
            "id": bp_id,
            "base": base_target,
            "target": next_target,
            "diffHash": "sha256:" + ("d" * 64),
        },
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [{"id": "core.customer", "version": "0.1.0"}],
        "steps": [step],
        "skippedOps": [],
        "postConditions": [
            {"id": "pc_a_001", "check": "exists", "pointer": f"/entities/customer/fields/{field_id}"},
        ],
        "risk": {
            "counts": {
                "cosmetic": 0,
                "config": 0,
                "data_shape": 1,
                "destructive": 0,
                "compliance": 0,
                "access": 0,
                "branding": 0,
            },
            "total": 1,
            "maxImpact": "data_shape",
            "needsDdlPlanGate": True,
            "touchesCompliance": False,
            "touchesAccess": False,
            "touchesLedgerOrTax": False,
            "requiresTeamReview": False,
            "irreversibleSteps": 0,
        },
        "inverse": inverse,
    }
    return _seal_artifact(forward)


class RealBenchTestCase(unittest.TestCase):
    """Connects to the live pinned Frappe bench (shared by the CE-SEC-005 live suites)."""

    _connected_here: bool = False
    _prev_cwd: Optional[str] = None
    _site: str = ""
    _sites_path: str = ""
    _run_tag: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._run_tag = uuid.uuid4().hex[:8]
        if frappe is None:
            if REQUIRE_REAL_BENCH:
                raise AssertionError("CE_SEC_005_REAL_BENCH=1 requires real Frappe runtime, but frappe import failed.")
            raise unittest.SkipTest("Offline environment without Frappe runtime; set CE_SEC_005_REAL_BENCH=1 in bench CI.")

        if not _has_active_frappe_db():
            site = os.environ.get("CE_SEC_005_SITE") or os.environ.get("SITE_NAME") or ""
            if not site:
                if REQUIRE_REAL_BENCH:
                    raise AssertionError(
                        "CE_SEC_005_REAL_BENCH=1 requires CE_SEC_005_SITE or SITE_NAME when Frappe is not pre-connected."
                    )
                raise unittest.SkipTest("No active Frappe site connection; skipping offline real-bench tests.")

            cls._sites_path = _resolve_sites_path()
            cls._prev_cwd = os.getcwd()
            os.chdir(cls._sites_path)
            frappe.init(site=site, sites_path=".")
            frappe.connect()
            cls._connected_here = True

        cls._sites_path = cls._sites_path or _resolve_sites_path()
        cls._site = str(frappe.local.site)
        frappe.set_user("Administrator")

        # Verify this is genuinely real MariaDB 11.4 (never SQLite or a mock)
        row = frappe.db.sql("SELECT VERSION()")
        db_ver = str(row[0][0]) if row and row[0] else ""
        if not db_ver.startswith(EXPECTED_MARIADB_SERIES):
            raise AssertionError(f"Expected real MariaDB {EXPECTED_MARIADB_SERIES}x, got {db_ver!r}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if frappe is not None and _has_active_frappe_db():
                frappe.set_user("Administrator")
        finally:
            if cls._connected_here and frappe is not None:
                try:
                    frappe.destroy()
                except Exception:
                    pass
            if cls._prev_cwd:
                try:
                    os.chdir(cls._prev_cwd)
                except Exception:
                    pass
        super().tearDownClass()

    def setUp(self) -> None:
        frappe.set_user("Administrator")

    def tearDown(self) -> None:
        frappe.set_user("Administrator")


class TestCeSec005RealBench(RealBenchTestCase):
    """End-to-end change engine verification inside a live pinned Frappe bench."""

    # ------------------------------------------------------------------ 1. Pinned bench & tables
    def test_01_pinned_versions_services_and_policy_tables_live(self) -> None:
        installed = set(frappe.get_installed_apps())
        self.assertTrue(
            set(EXPECTED_APPS).issubset(installed),
            f"Missing apps on site {self._site}: {set(EXPECTED_APPS) - installed}",
        )

        import erpnext  # type: ignore[import-not-found]
        import hrms  # type: ignore[import-not-found]
        import change_engine

        actual_versions = {
            "frappe": frappe.__version__,
            "erpnext": erpnext.__version__,
            "hrms": hrms.__version__,
            "change_engine": change_engine.__version__,
        }
        self.assertEqual(actual_versions, EXPECTED_VERSIONS)

        # Redis cache ping
        self.assertTrue(frappe.cache().ping())

        # CE-SEC-003 migration/before_install tables exist in MariaDB
        tables = {
            r[0]
            for r in frappe.db.sql(
                """
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN ('tabChange Engine Policy', 'tabChange Engine Policy Audit')
                """
            )
        }
        self.assertEqual(tables, {"tabChange Engine Policy", "tabChange Engine Policy Audit"})

        # Live Frappe HTTP worker answers for the site
        port = os.environ.get("ENGINE_PORT", "8000")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/method/ping",
            headers={"Host": self._site},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"pong", resp.read())

    # ------------------------------------------------------------------ 2. Plan & DDL gate
    def test_02_plan_ddl_gate_and_zone_guardrails_against_live_schema(self) -> None:
        fieldname = f"custom_ce005_plan_{self._run_tag}"
        res = endpoints.propose_configuration_change(
            "Customer",
            {
                "intent": "add_custom_fields",
                "changes": [
                    {
                        "fieldname": fieldname,
                        "fieldtype": "Data",
                        "label": "CE005 Plan Field",
                    }
                ],
            },
        )
        self.assertTrue(res["success"], res)
        self.assertEqual(res["status"], "PROPOSED")
        ddl_plan = res["ddl_plan"]
        self.assertIsNotNone(ddl_plan)
        self.assertTrue(ddl_plan["inspectable"])
        self.assertTrue(ddl_plan["is_approved_additive_only"])
        self.assertEqual(len(ddl_plan["statements"]), 1)
        self.assertIn(f"ALTER TABLE `tabCustomer` ADD COLUMN `{fieldname}`", ddl_plan["statements"][0])
        self.assertEqual(
            res["base_revision_hash"],
            endpoints.FrappeDeploymentAdapter().get_doctype_revision_hash("Customer"),
        )

        # Negative plan: unique constraint / index rejected by DDL gate
        rejected_unique = endpoints.propose_configuration_change(
            "Customer",
            {
                "intent": "add_custom_fields",
                "changes": [
                    {
                        "fieldname": f"custom_ce005_uniq_{self._run_tag}",
                        "fieldtype": "Data",
                        "label": "Unique Disallowed",
                        "unique": 1,
                    }
                ],
            },
        )
        self.assertFalse(rejected_unique["success"])
        self.assertEqual(rejected_unique["status"], "REJECTED")

        # Negative plan: SQL injection attempt in fieldname rejected
        rejected_sqli = endpoints.propose_configuration_change(
            "Customer",
            {
                "intent": "add_custom_fields",
                "changes": [
                    {
                        "fieldname": "custom_bad; DROP TABLE tabCustomer;--",
                        "fieldtype": "Data",
                        "label": "Bad",
                    }
                ],
            },
        )
        self.assertFalse(rejected_sqli["success"])
        self.assertEqual(rejected_sqli["status"], "REJECTED")

        # Negative plan: Zone 2 locked doctype & prohibited destructive intent refused
        for bad_dt, bad_payload in (
            ("GL Entry", {"intent": "add_custom_fields", "changes": [{"fieldname": fieldname, "fieldtype": "Data"}]}),
            ("User", {"intent": "add_custom_fields", "changes": [{"fieldname": fieldname, "fieldtype": "Data"}]}),
            ("Customer", {"intent": "drop_table"}),
        ):
            rej = endpoints.propose_configuration_change(bad_dt, bad_payload)
            self.assertFalse(rej["success"], f"{bad_dt} should be rejected")
            self.assertEqual(rej["disposition"], "ZONE_SAFETY_VIOLATION")

    # ------------------------------------------------------------------ 3. Apply, idempotency, rollback
    def _ensure_customer(self, suffix: str) -> str:
        cust_name = f"CE005 Customer {suffix}"
        if frappe.db.exists("Customer", cust_name):
            return cust_name
        group = frappe.get_all("Customer Group", pluck="name", limit=1)
        territory = frappe.get_all("Territory", pluck="name", limit=1)
        if not group:
            frappe.get_doc({"doctype": "Customer Group", "customer_group_name": "All Customer Groups"}).insert(
                ignore_permissions=True
            )
            group = ["All Customer Groups"]
        if not territory:
            frappe.get_doc({"doctype": "Territory", "territory_name": "All Territories"}).insert(
                ignore_permissions=True
            )
            territory = ["All Territories"]
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": cust_name,
                "customer_type": "Company",
                "customer_group": group[0],
                "territory": territory[0],
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def test_03_apply_idempotency_and_soft_quarantine_rollback_real_db(self) -> None:
        fieldname = f"custom_ce005_tag_{self._run_tag}"
        field_def = {
            "fieldname": fieldname,
            "fieldtype": "Data",
            "label": "CE005 External Tag",
            "reqd": 0,
            "read_only": 0,
        }
        proposal = endpoints.propose_configuration_change(
            "Customer",
            {"intent": "add_custom_fields", "changes": [field_def]},
        )
        self.assertTrue(proposal["success"], proposal)

        dep_id = f"dep_ce005_{self._run_tag}"
        idemp_key = f"idemp_ce005_{self._run_tag}"
        apply_res = endpoints.apply_configuration_change(
            doctype="Customer",
            deployment_id=dep_id,
            field_def=field_def,
            idempotency_key=idemp_key,
            proposal=proposal,
        )
        self.assertTrue(apply_res["success"], apply_res)
        self.assertEqual(apply_res["status"], "APPLIED")

        # Physical verification in MariaDB Custom Field + information_schema + Audit table
        cf_name = frappe.db.get_value("Custom Field", {"dt": "Customer", "fieldname": fieldname}, "name")
        self.assertIsNotNone(cf_name)
        cols = frappe.db.sql(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tabCustomer' AND COLUMN_NAME = %s
            """,
            (fieldname,),
        )
        self.assertEqual(len(cols), 1, "Physical column was not created on tabCustomer")

        audit_row = endpoints.FrappeDeploymentAdapter().get_deployment_record(dep_id)
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["status"], "APPLIED")

        # Write synthetic data into the new physical column on a real Customer document
        cust_name = self._ensure_customer(self._run_tag)
        sentinel_val = f"ce005-val-{self._run_tag}"
        frappe.db.set_value("Customer", cust_name, fieldname, sentinel_val)
        frappe.db.commit()
        self.assertEqual(frappe.db.get_value("Customer", cust_name, fieldname), sentinel_val)

        # Idempotent replay (exact same key + payload) returns original outcome without re-running DDL
        replay_res = endpoints.apply_configuration_change(
            doctype="Customer",
            deployment_id=f"{dep_id}_replay",
            field_def=field_def,
            idempotency_key=idemp_key,
        )
        self.assertEqual(replay_res["status"], "APPLIED")
        self.assertEqual(replay_res["deployment_id"], dep_id)

        # Idempotency conflict (same key + altered payload) rejects cleanly
        conflict_res = endpoints.apply_configuration_change(
            doctype="Customer",
            deployment_id=f"{dep_id}_conflict",
            field_def={**field_def, "label": "Tampered Label"},
            idempotency_key=idemp_key,
        )
        self.assertFalse(conflict_res["success"])
        self.assertEqual(conflict_res["disposition"], "IDEMPOTENCY_CONFLICT")

        # Soft-quarantine rollback preserves column and customer data while hiding field
        rb_res = endpoints.revert_configuration_change(deployment_id=dep_id)
        self.assertTrue(rb_res["success"], rb_res)
        self.assertEqual(rb_res["status"], "QUARANTINED")

        ps_rows = frappe.db.sql(
            """
            SELECT property, value
            FROM `tabProperty Setter`
            WHERE doc_type = 'Customer' AND field_name = %s
            """,
            (fieldname,),
            as_dict=True,
        )
        ps_map = {r["property"]: str(r["value"]) for r in ps_rows}
        self.assertEqual(ps_map.get("hidden"), "1")
        self.assertEqual(ps_map.get("reqd"), "0")

        # Column and data MUST remain intact (zero destructive DROP COLUMN)
        cols_after = frappe.db.sql(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tabCustomer' AND COLUMN_NAME = %s
            """,
            (fieldname,),
        )
        self.assertEqual(len(cols_after), 1)
        self.assertEqual(frappe.db.get_value("Customer", cust_name, fieldname), sentinel_val)

        # Property Setter deployment + exact rollback
        ps_dep_id = f"dep_ps_ce005_{self._run_tag}"
        ps_apply = endpoints.apply_property_setter_change(
            doctype="Customer",
            deployment_id=ps_dep_id,
            fieldname="customer_name",
            property_name="description",
            value=f"CE005 Desc {self._run_tag}",
            property_type="Text",
        )
        self.assertEqual(ps_apply["status"], "APPLIED", ps_apply)
        ps_rb = endpoints.revert_configuration_change(deployment_id=ps_dep_id)
        self.assertTrue(ps_rb["success"], ps_rb)
        self.assertEqual(ps_rb["status"], "ROLLED_BACK")

    # ------------------------------------------------------------------ 4. Adapter FrappeRuntimeBackend
    def test_04_change_engine_adapter_with_real_frappe_backend(self) -> None:
        tenant = f"t_ce005_{self._run_tag}"
        backend = FrappeRuntimeBackend(
            site_resolver=FrappeSiteResolver(site_map={tenant: self._site}),
            sites_path=self._sites_path,
        )
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)

        bp_id = "bp_ce005_init"
        prov = adapter.call(
            "provision_site",
            _adapter_ctx(tenant, "prov"),
            {
                "idempotencyKey": f"prov_{self._run_tag}_0001",
                "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
                "blueprintId": bp_id,
                "siteClass": "production",
                "countryPack": "sa",
            },
        )
        self.assertTrue(prov["ok"], prov)

        health = adapter.call("health", _adapter_ctx(tenant, "health"), {})
        self.assertTrue(health["ok"], health)
        checks = {c["name"]: c["status"] for c in health["result"]["checks"]}
        self.assertEqual(checks.get("database"), "ok")
        self.assertEqual(checks.get("site_lock"), "ok")
        self.assertEqual(checks.get("recovery"), "ok")

        # Initial build from base=None to revision 1
        init_art = _build_initial_customer_artifact()
        init_plan = adapter.call("plan", _adapter_ctx(tenant, "init_plan"), {"artifact": init_art})
        self.assertTrue(init_plan["ok"], init_plan)
        init_apply = adapter.call(
            "apply",
            _adapter_ctx(tenant, "init_apply"),
            {
                "idempotencyKey": f"apply_init_{self._run_tag}_0001",
                "artifact": init_art,
                "planToken": init_plan["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000009"},
            },
        )
        self.assertTrue(init_apply["ok"] and init_apply["result"]["status"] == "applied", init_apply)

        # Forward additive field deployment (revision 1 -> revision 2)
        field_id = f"ce005_note_{self._run_tag}"
        frappe_col = f"custom_{field_id}"
        artifact = _build_add_field_artifact(field_id, label="CE005 Adapter Note", blueprint_id=bp_id)

        plan_res = adapter.call("plan", _adapter_ctx(tenant, "plan"), {"artifact": artifact})
        self.assertTrue(plan_res["ok"], plan_res)
        self.assertEqual(plan_res["result"]["verdict"], "auto_approved", plan_res)

        apply_res = adapter.call(
            "apply",
            _adapter_ctx(tenant, "apply"),
            {
                "idempotencyKey": f"apply_bp_{self._run_tag}_0001",
                "artifact": artifact,
                "planToken": plan_res["result"]["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000010"},
            },
        )
        self.assertTrue(apply_res["ok"] and apply_res["result"]["status"] == "applied", apply_res)

        col_exists = frappe.db.sql(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tabCustomer' AND COLUMN_NAME = %s
            """,
            (frappe_col,),
        )
        self.assertEqual(len(col_exists), 1)

        # Write real data into the column on an existing customer and rollback (quarantine)
        cust_name = self._ensure_customer(f"adp_{self._run_tag}")
        frappe.db.set_value("Customer", cust_name, frappe_col, "preserved-adapter-data")
        frappe.db.commit()

        # A fresh adapter must reload the applied revision from the site.
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)
        rb_res = adapter.call(
            "rollback",
            _adapter_ctx(tenant, "rb"),
            {
                "idempotencyKey": f"rb_bp_{self._run_tag}_0001",
                "forwardArtifact": artifact,
                "reason": "ce_sec_005_verification",
                "approvals": {"rollbackApproved": "01J00000000000000000000011"},
            },
        )
        self.assertTrue(rb_res["ok"] and rb_res["result"]["status"] == "applied", rb_res)
        self.assertEqual(frappe.db.get_value("Customer", cust_name, frappe_col), "preserved-adapter-data")

        ps_hidden = frappe.db.get_value(
            "Property Setter",
            {"doc_type": "Customer", "field_name": frappe_col, "property": "hidden"},
            "value",
        )
        self.assertEqual(str(ps_hidden), "1")

    # ------------------------------------------------------------------ 5. Policy DB persistence & hooks.py
    def test_05_runtime_policy_persistence_audit_and_doc_events_hook(self) -> None:
        policy_id = f"POL_CE005_TODO_{self._run_tag}".upper()
        role_policy_id = f"POL_CE005_ROLE_{self._run_tag}".upper()
        pol_v1 = {
            "policy_id": policy_id,
            "doctype": "ToDo",
            "policy_type": "INVARIANT_GUARD",
            "condition_expr": "description == 'FORBIDDEN_CE005_V1'",
            "required_role": None,
            "error_message": "Blocked by CE-SEC-005 runtime policy v1.",
        }
        pol_v2 = {
            "policy_id": policy_id,
            "doctype": "ToDo",
            "policy_type": "INVARIANT_GUARD",
            "condition_expr": "description == 'FORBIDDEN_CE005_V2'",
            "required_role": None,
            "error_message": "Blocked by CE-SEC-005 runtime policy v2.",
        }
        pol_role = {
            "policy_id": role_policy_id,
            "doctype": "ToDo",
            "policy_type": "INVARIANT_GUARD",
            "condition_expr": "description == 'ADMIN_ONLY_CE005'",
            "required_role": "System Manager",
            "error_message": "Requires System Manager role.",
        }

        created_todos = []
        staff_email = self._ensure_staff_user()
        try:
            res1 = endpoints.register_runtime_policy(pol_v1)
            self.assertTrue(res1["success"])
            self.assertEqual(res1["revision"], 1)
            self.assertEqual(res1["action"], "CREATED")

            res2 = endpoints.register_runtime_policy(pol_v2)
            self.assertTrue(res2["success"])
            self.assertEqual(res2["revision"], 2)
            self.assertEqual(res2["action"], "UPDATED")

            endpoints.register_runtime_policy(pol_role)
            frappe.db.commit()

            # Verify DB persistence & audit trail in MariaDB
            revs = endpoints.get_policy_revisions(policy_id)
            self.assertEqual([r["revision"] for r in revs], [1, 2])
            audit = endpoints.get_policy_audit_trail(policy_id=policy_id)
            self.assertEqual([a["action"] for a in audit], ["CREATED", "UPDATED"])

            # Clear in-memory policy cache to simulate fresh worker reading from MariaDB
            policy_catalog.reset()

            # Real Frappe doc.insert() triggers hooks.py doc_events['*']['validate']
            bad_todo = frappe.get_doc({"doctype": "ToDo", "description": "FORBIDDEN_CE005_V2"})
            with self.assertRaises((RuntimePolicyViolation, frappe.ValidationError)):
                bad_todo.insert(ignore_permissions=True)

            good_todo = frappe.get_doc({"doctype": "ToDo", "description": f"Allowed CE005 {self._run_tag}"})
            good_todo.insert(ignore_permissions=True)
            created_todos.append(good_todo.name)

            # Role-gated policy allows Administrator (System Manager) but blocks Sales User
            admin_only_ok = frappe.get_doc({"doctype": "ToDo", "description": "ADMIN_ONLY_CE005"})
            admin_only_ok.insert(ignore_permissions=True)
            created_todos.append(admin_only_ok.name)
            frappe.db.commit()

            frappe.set_user(staff_email)
            blocked_for_staff = frappe.get_doc({"doctype": "ToDo", "description": "ADMIN_ONLY_CE005"})
            with self.assertRaises((RuntimePolicyViolation, frappe.ValidationError)):
                blocked_for_staff.insert(ignore_permissions=True)
            frappe.set_user("Administrator")

            # Site isolation: explicit different site is refused inside live Frappe
            self.assertEqual(get_current_site_id(), self._site)
            with self.assertRaises(PermissionError):
                get_current_site_id("other-tenant.localhost")
            with self.assertRaises(PermissionError):
                policy_store.get_policies(site_id="other-tenant.localhost")
        finally:
            frappe.set_user("Administrator")
            for name in created_todos:
                if frappe.db.exists("ToDo", name):
                    frappe.delete_doc("ToDo", name, ignore_permissions=True, force=True)
            endpoints.unregister_runtime_policy(policy_id, doctype="ToDo")
            endpoints.unregister_runtime_policy(role_policy_id, doctype="ToDo")
            frappe.db.commit()

    # ------------------------------------------------------------------ 6. Negative security regressions
    def _ensure_staff_user(self) -> str:
        email = f"ce005-staff-{self._run_tag}@example.invalid"
        if not frappe.db.exists("User", email):
            u = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "CE005 Staff",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                    "roles": [{"role": "Sales User"}],
                }
            )
            u.insert(ignore_permissions=True)
            frappe.db.commit()
        return email

    def test_06_negative_security_regressions_real_session_and_fail_closed(self) -> None:
        staff_email = self._ensure_staff_user()

        # CE-SEC-004: no LLM endpoint in the module or among the whitelisted functions.
        # frappe.whitelisted holds function objects, so resolve each to its dotted path.
        self.assertFalse(hasattr(endpoints, "test_llm_connection"))
        self.assertFalse(hasattr(endpoints, "get_llm_config"))
        whitelisted = {f"{fn.__module__}.{fn.__qualname__}" for fn in frappe.whitelisted}
        # Positive control: the resolution finds the change engine's own endpoints.
        self.assertIn("change_engine.api.endpoints.apply_configuration_change", whitelisted)
        engine_llm = sorted(p for p in whitelisted if p.startswith("change_engine.") and "llm" in p.lower())
        self.assertEqual(engine_llm, [])

        # CE-SEC-001 & CE-SEC-003 under a real non-admin Frappe user session
        try:
            frappe.set_user(staff_email)
            self.assertNotIn("System Manager", endpoints.get_current_user_roles())

            spoofed_apply = endpoints.apply_configuration_change(
                doctype="Customer",
                field_def={"fieldname": f"custom_ce005_spoof_{self._run_tag}", "fieldtype": "Data", "label": "Spoof"},
                user_roles=["System Manager"],
            )
            self.assertFalse(spoofed_apply["success"])
            self.assertEqual(spoofed_apply["disposition"], "UNAUTHORIZED_ROLE")

            # No caller_roles here: the admin permission check itself must refuse the call
            # (with caller_roles, _reject_caller_context would refuse it first).
            with self.assertRaisesRegex(PermissionError, "admin permission required"):
                endpoints.register_runtime_policy(
                    {
                        "policy_id": f"POL_SPOOF_{self._run_tag}",
                        "doctype": "ToDo",
                        "policy_type": "INVARIANT_GUARD",
                        "condition_expr": "description == 'x'",
                    }
                )
            with self.assertRaises(PermissionError):
                endpoints.get_runtime_policies()
            with self.assertRaises(PermissionError):
                endpoints.get_policy_audit_trail()
            with self.assertRaises(PermissionError):
                endpoints.evaluate_document_policies("ToDo", {"description": "x"})
        finally:
            frappe.set_user("Administrator")

        # CE-SEC-002: Role lookup error fails closed (returns [], denies deploy & policy write)
        orig_get_roles = frappe.get_roles
        try:
            def _broken_roles(_user):
                raise RuntimeError("simulated DB role lookup outage")

            frappe.get_roles = _broken_roles
            self.assertEqual(endpoints.get_current_user_roles(), [])
            fail_closed_apply = endpoints.apply_configuration_change(
                doctype="Customer",
                field_def={"fieldname": f"custom_ce005_fc_{self._run_tag}", "fieldtype": "Data", "label": "FailClosed"},
                user_roles=["System Manager"],
            )
            self.assertFalse(fail_closed_apply["success"])
            self.assertEqual(fail_closed_apply["disposition"], "UNAUTHORIZED_ROLE")
            with self.assertRaises(PermissionError):
                endpoints.register_runtime_policy(
                    {
                        "policy_id": f"POL_FC_{self._run_tag}",
                        "doctype": "ToDo",
                        "policy_type": "INVARIANT_GUARD",
                        "condition_expr": "description == 'x'",
                    }
                )
        finally:
            frappe.get_roles = orig_get_roles

        # CE-SEC-003: Admin cannot override Tier 0, supply forbidden context params, or inject eval
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(
                RuntimePolicy(
                    policy_id="TIER0_SO_CREDIT_LIMIT_BYPASS",
                    doctype="Sales Order",
                    policy_type=PolicyType.INVARIANT_GUARD,
                    governance_tier=1,
                    condition_expr="1 == 2",
                    error_message="Should fail",
                )
            )
        with self.assertRaises(PermissionError):
            endpoints.unregister_runtime_policy("TIER0_SI_GL_POSTING_PROTECTION")
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(
                {
                    "policy_id": f"POL_CTX_{self._run_tag}",
                    "doctype": "ToDo",
                    "policy_type": "INVARIANT_GUARD",
                    "condition_expr": "description == 'x'",
                },
                site_id="tenant-b.localhost",
            )
        with self.assertRaises(PolicyExpressionError):
            endpoints.register_runtime_policy(
                {
                    "policy_id": f"POL_EVAL_{self._run_tag}",
                    "doctype": "ToDo",
                    "policy_type": "INVARIANT_GUARD",
                    "condition_expr": "__import__('os').system('id')",
                }
            )


if __name__ == "__main__":
    unittest.main()
