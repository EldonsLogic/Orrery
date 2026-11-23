"""BPL-008 tests: Rollback to a previous Blueprint version."""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from unittest import mock
from pathlib import Path

from change_engine.adapter import (
    ADAPTER_ID,
    ChangeEngineAdapter,
    FrappeRuntimeBackend,
    SimulatedFrappeRuntime,
)
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import engine_state_name
from change_engine.api.endpoints import (
    FrappeDeploymentAdapter,
    apply_configuration_change,
    apply_property_setter_change,
    apply_report_change,
    revert_configuration_change,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
EXAMPLES_DIR = REPO_ROOT / "contracts" / "examples"
SERVICES_BP_DIR = REPO_ROOT / "services" / "blueprint"


def _ctx(tenant: str = "t_alpha", service: str = "control_plane", who: dict | None = None) -> dict:
    return {
        "contractVersion": "0.1.2",
        "requestId": "01J00000000000000000000001",
        "correlationId": "corr_bpl008_01",
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


def _make_artifact(
    *,
    bp_id: str,
    kind: str,
    base: dict | None,
    target: dict,
    steps: list[dict],
    post_conditions: list[dict],
    inverse: dict | None = None,
    diff_hash: str | None = None,
    requires_team_review: bool = False,
) -> dict:
    payload = {
        "artifactSchema": "0.1.0",
        "kind": kind,
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {
            "id": bp_id,
            "base": copy.deepcopy(base),
            "target": copy.deepcopy(target),
            "diffHash": diff_hash,
        },
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [
            {"id": "compliance.zatca_sa", "version": "0.1.0"},
            {"id": "core.customer", "version": "0.1.0"},
            {"id": "core.sales_order", "version": "0.1.0"},
        ],
        "steps": steps,
        "skippedOps": [],
        "postConditions": post_conditions,
        "risk": {
            "counts": {
                "cosmetic": 0,
                "config": len(steps),
                "data_shape": 0,
                "destructive": 0,
                "compliance": 0,
                "access": 0,
                "branding": 0,
            },
            "total": len(steps),
            "maxImpact": "data_shape" if any(s["kind"].endswith(".add") for s in steps) else "config",
            "needsDdlPlanGate": any(s["ddlImpact"] != "none" for s in steps),
            "touchesCompliance": False,
            "touchesAccess": any(s["kind"].startswith(("role.", "workflow.")) for s in steps),
            "touchesLedgerOrTax": False,
            "requiresTeamReview": requires_team_review,
            "irreversibleSteps": sum(1 for s in steps if not s.get("reversible", True)),
        },
        "inverse": inverse,
    }
    return _seal(payload)


def _k(suffix: str) -> str:
    return f"idemp_bpl008_{suffix}"


def _apply(adapter: ChangeEngineAdapter, tenant: str, artifact: dict, key: str, approvals: dict | None = None) -> dict:
    plan = adapter.call("plan", _ctx(tenant), {"artifact": artifact})
    assert plan["ok"], plan
    assert plan["result"]["verdict"] != "rejected", plan
    req_approvals = approvals or {"changeApproved": "01J00000000000000000000010"}
    if plan["result"]["verdict"] == "needs_gate_approval" and "gateApproved" not in req_approvals:
        req_approvals["gateApproved"] = "01J00000000000000000000011"
    if artifact["risk"]["requiresTeamReview"] and "teamReviewed" not in req_approvals:
        req_approvals["teamReviewed"] = "01J00000000000000000000012"
    res = adapter.call(
        "apply",
        _ctx(tenant),
        {
            "idempotencyKey": _k(key) if len(key) < 16 else key,
            "artifact": artifact,
            "planToken": plan["result"]["planToken"],
            "approvals": req_approvals,
        },
    )
    return res


_ENV_PATCH = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})


def setUpModule():
    _ENV_PATCH.start()  # ERP-027: the offline DDL simulator is refused unless CHANGE_ENGINE_ENV is dev or test


def tearDownModule():
    _ENV_PATCH.stop()


class TestBpl008BlueprintRollback(unittest.TestCase):
    def setUp(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def tearDown(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def _provision_v1(self, tenant: str = "t_alpha"):
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True, offline_ddl_simulator=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        prov = adapter.call(
            "provision_site",
            _ctx(tenant),
            {
                "idempotencyKey": _k(f"prov_{tenant}"),
                "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
                "blueprintId": "example-trading-001",
                "siteClass": "production",
                "countryPack": "sa",
            },
        )
        self.assertTrue(prov["ok"], prov)

        bp = _load_example("blueprint-trading-minimal.json")
        customer = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "customer"))
        sales_order = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "sales_order"))
        role_sales = copy.deepcopy(next(r for r in bp["roles"] if r["id"] == "sales_rep"))
        wf_init = copy.deepcopy(bp["workflows"][0])
        wf_init["entity"] = "sales_order"
        add_field_ex = _load_example("compiled-artifact-add-field.json")
        rev1 = copy.deepcopy(add_field_ex["blueprint"]["base"])

        v1_steps = [
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
            {
                "seq": 4,
                "phase": 8,
                "kind": "workflow.upsert",
                "subject": {"kind": "workflow", "id": wf_init["id"], "parents": []},
                "pointer": f"/workflows/{wf_init['id']}",
                "impact": "access",
                "ddlImpact": "none",
                "reversible": True,
                "params": {"definition": wf_init},
                "sourceOps": [f"/workflows/{wf_init['id']}"],
            },
        ]
        v1 = _make_artifact(
            bp_id="example-trading-001",
            kind="forward",
            base=None,
            target=rev1,
            steps=v1_steps,
            post_conditions=[
                {"id": "pc_001", "check": "exists", "pointer": "/entities/customer"},
                {"id": "pc_002", "check": "exists", "pointer": f"/workflows/{wf_init['id']}"},
            ],
            inverse=None,
        )
        res = _apply(adapter, tenant, v1, "apply_v1")
        self.assertTrue(res["ok"] and res["result"]["status"] == "applied", res)
        return sim, backend, adapter, v1, rev1

    def test_01_multi_version_rollback_chain_and_reapply_preserves_byte_identical_exports(self) -> None:
        sim, _backend, adapter, v1, rev1 = self._provision_v1("t_alpha")
        site_db = sim.sites["t-alpha.localhost"]
        v1_hash = adapter.call("export_config", _ctx("t_alpha"), {})["result"]["exportHash"]

        # v2: Add required Custom Field + set description property + update workflow
        rev2 = {"hash": "sha256:" + ("2" * 64), "revision": 2}
        vat_zone_def = {
            "id": "vat_zone",
            "type": "string",
            "required": True,
            "labels": {"en": "VAT Zone"},
        }
        v2_inv = _make_artifact(
            bp_id="example-trading-001",
            kind="inverse",
            base=rev2,
            target=rev1,
            diff_hash="sha256:" + ("a" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 15,
                    "kind": "field.quarantine",
                    "subject": {"kind": "field", "id": "vat_zone", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/vat_zone",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": vat_zone_def},
                    "sourceOps": ["/entities/customer/fields/vat_zone"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "quarantined", "pointer": "/entities/customer/fields/vat_zone"},
            ],
        )
        v2 = _make_artifact(
            bp_id="example-trading-001",
            kind="forward",
            base=rev1,
            target=rev2,
            diff_hash="sha256:" + ("b" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 5,
                    "kind": "field.add",
                    "subject": {"kind": "field", "id": "vat_zone", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/vat_zone",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {"definition": vat_zone_def},
                    "sourceOps": ["/entities/customer/fields/vat_zone"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "exists", "pointer": "/entities/customer/fields/vat_zone"},
            ],
            inverse=v2_inv,
        )
        res2 = _apply(adapter, "t_alpha", v2, "apply_v2")
        self.assertTrue(res2["ok"] and res2["result"]["status"] == "applied", res2)
        v2_hash = res2["result"]["exportHash"]

        # Write real data & verify meta reflects reqd=1
        adapter.data_probe("t_alpha", "/entities/customer/fields/vat_zone", "KSA-RIYADH")
        meta_v2 = sim.get_meta("Customer").get_field("custom_vat_zone")
        self.assertIsNotNone(meta_v2)
        self.assertEqual(meta_v2.reqd, 1)

        # v3: Set i18n locale, set /readOnly on custom_vat_zone, add a report
        rev3 = {"hash": "sha256:" + ("3" * 64), "revision": 3}
        rep_def = {
            "id": "customer_vat_summary",
            "kind": "summary",
            "entity": "customer",
            "labels": {"en": "Customer VAT Summary"},
            "metrics": [{"id": "cust_count", "op": "count", "groupBy": ["customer_name"]}],
            "visibleToRoles": ["sales_rep"],
        }
        v3_inv = _make_artifact(
            bp_id="example-trading-001",
            kind="inverse",
            base=rev3,
            target=rev2,
            diff_hash="sha256:" + ("c" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 1,
                    "kind": "settings.set",
                    "subject": {"kind": "i18n", "id": None, "parents": []},
                    "pointer": "/i18n",
                    "impact": "config",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"property": "/defaultLocale", "before": "en"},  # unset -> restore country_pack default "ar"
                    "sourceOps": ["/i18n/defaultLocale"],
                },
                {
                    "seq": 2,
                    "phase": 6,
                    "kind": "field.set_property",
                    "subject": {"kind": "field", "id": "vat_zone", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/vat_zone",
                    "impact": "cosmetic",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"property": "/readOnly", "before": True},  # unset -> delete Property Setter
                    "sourceOps": ["/entities/customer/fields/vat_zone/readOnly"],
                },
                {
                    "seq": 3,
                    "phase": 11,
                    "kind": "report.disable",
                    "subject": {"kind": "report", "id": "customer_vat_summary", "parents": []},
                    "pointer": "/reports/customer_vat_summary",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": rep_def},
                    "sourceOps": ["/reports/customer_vat_summary"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "disabled", "pointer": "/reports/customer_vat_summary"},
            ],
        )
        v3 = _make_artifact(
            bp_id="example-trading-001",
            kind="forward",
            base=rev2,
            target=rev3,
            diff_hash="sha256:" + ("d" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 1,
                    "kind": "settings.set",
                    "subject": {"kind": "i18n", "id": None, "parents": []},
                    "pointer": "/i18n",
                    "impact": "config",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"property": "/defaultLocale", "after": "en"},
                    "sourceOps": ["/i18n/defaultLocale"],
                },
                {
                    "seq": 2,
                    "phase": 6,
                    "kind": "field.set_property",
                    "subject": {"kind": "field", "id": "vat_zone", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/vat_zone",
                    "impact": "cosmetic",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"property": "/readOnly", "after": True},
                    "sourceOps": ["/entities/customer/fields/vat_zone/readOnly"],
                },
                {
                    "seq": 3,
                    "phase": 10,
                    "kind": "report.upsert",
                    "subject": {"kind": "report", "id": "customer_vat_summary", "parents": []},
                    "pointer": "/reports/customer_vat_summary",
                    "impact": "config",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": rep_def},
                    "sourceOps": ["/reports/customer_vat_summary"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "exists", "pointer": "/reports/customer_vat_summary"},
                {
                    "id": "pc_002",
                    "check": "property_equals",
                    "pointer": "/i18n",
                    "property": "/defaultLocale",
                    "expected": "en",
                },
                {
                    "id": "pc_003",
                    "check": "property_equals",
                    "pointer": "/entities/customer/fields/vat_zone",
                    "property": "/readOnly",
                    "expected": True,
                },
            ],
            inverse=v3_inv,
        )
        res3 = _apply(adapter, "t_alpha", v3, "apply_v3")
        self.assertTrue(res3["ok"] and res3["result"]["status"] == "applied", res3)
        self.assertEqual(site_db.singles["System Settings"]["language"], "en")
        self.assertEqual(site_db.rows["tabReport"]["customer_vat_summary"]["disabled"], 0)
        self.assertEqual(int(sim.get_meta("Customer").get_field("custom_vat_zone").read_only), 1)

        # Rolling back v2 while v3 is latest must be rejected with not_latest
        bad_rb = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_v2_too_early"),
                "forwardArtifact": v2,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000020"},
            },
        )
        self.assertEqual(bad_rb["result"]["status"], "rejected")
        self.assertEqual(bad_rb["result"]["error"]["code"], "rollback_not_possible")
        self.assertEqual(bad_rb["result"]["error"]["details"]["reasonCode"], "not_latest")

        # Rollback v3 -> v2
        rb3 = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_v3"),
                "forwardArtifact": v3,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000021"},
            },
        )
        self.assertTrue(rb3["ok"] and rb3["result"]["status"] == "applied", rb3)
        self.assertEqual(rb3["result"]["exportHash"], v2_hash)
        self.assertEqual(rb3["result"]["site"]["applied"], {"artifactId": v2["artifactId"], "revision": rev2})
        # Settings reverted to country_pack default "ar", report disabled, read_only PS DELETED, cache cleared
        self.assertEqual(site_db.singles["System Settings"]["language"], "ar")
        self.assertEqual(site_db.rows["tabReport"]["customer_vat_summary"]["disabled"], 1)
        self.assertIn("Customer", site_db.cleared_caches)
        ps_ro = [
            r
            for r in site_db.rows["tabProperty Setter"].values()
            if r["doc_type"] == "Customer" and r["field_name"] == "custom_vat_zone" and r["property"] == "read_only"
        ]
        self.assertEqual(ps_ro, [])

        # Rollback v2 -> v1
        rb2 = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_v2"),
                "forwardArtifact": v2,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000022"},
            },
        )
        self.assertTrue(rb2["ok"] and rb2["result"]["status"] == "applied", rb2)
        self.assertEqual(rb2["result"]["exportHash"], v1_hash)
        self.assertEqual(rb2["result"]["site"]["applied"], {"artifactId": v1["artifactId"], "revision": rev1})

        # Quarantined required field MUST have hidden=1 & reqd=0 and preserved stored data
        meta_q = sim.get_meta("Customer").get_field("custom_vat_zone")
        self.assertEqual(meta_q.hidden, 1)
        self.assertEqual(meta_q.reqd, 0)
        # Stored data preserved across quarantine
        self.assertEqual(adapter.data_probe("t_alpha", "/entities/customer/fields/vat_zone"), "KSA-RIYADH")
        self.assertEqual(adapter.dropped_data(), [])

        # Re-apply v2 after rollback -> restores hidden=0, reqd=1, and stored data
        res2_reapply = _apply(adapter, "t_alpha", v2, "reapply_v2")
        self.assertTrue(res2_reapply["ok"] and res2_reapply["result"]["status"] == "applied", res2_reapply)
        self.assertEqual(res2_reapply["result"]["exportHash"], v2_hash)
        meta_restored = sim.get_meta("Customer").get_field("custom_vat_zone")
        self.assertEqual(meta_restored.hidden, 0)
        self.assertEqual(meta_restored.reqd, 1)
        self.assertEqual(adapter.data_probe("t_alpha", "/entities/customer/fields/vat_zone"), "KSA-RIYADH")

    def test_02_workflow_rollback_replaces_child_tables_without_stale_states(self) -> None:
        sim, _backend, adapter, _v1, _rev1 = self._provision_v1("t_alpha")
        site_db = sim.sites["t-alpha.localhost"]
        pre_hash = adapter.call("export_config", _ctx("t_alpha"), {})["result"]["exportHash"]
        pre_transitions = len(site_db.rows["tabWorkflow"]["sales_order_flow"]["transitions"])

        wf_art = _load_example("compiled-artifact-add-workflow-state.json")
        res = _apply(
            adapter,
            "t_alpha",
            wf_art,
            "apply_wf_on_hold",
            approvals={"changeApproved": "01J00000000000000000000030", "teamReviewed": "01J00000000000000000000031"},
        )
        self.assertTrue(res["ok"] and res["result"]["status"] == "applied", res)
        wf_doc = site_db.rows["tabWorkflow"]["sales_order_flow"]
        self.assertEqual(len(wf_doc["states"]), 6)
        self.assertTrue(any(s["state"] == engine_state_name("on_hold") for s in wf_doc["states"]))  # ADR-0051 name
        self.assertGreater(len(wf_doc["transitions"]), pre_transitions)

        rb = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_wf_on_hold"),
                "forwardArtifact": wf_art,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000032"},
            },
        )
        self.assertTrue(rb["ok"] and rb["result"]["status"] == "applied", rb)
        self.assertEqual(rb["result"]["exportHash"], pre_hash)
        wf_doc_after = site_db.rows["tabWorkflow"]["sales_order_flow"]
        self.assertEqual(len(wf_doc_after["states"]), 5)
        self.assertFalse(any(s["state"] == engine_state_name("on_hold") for s in wf_doc_after["states"]))
        self.assertEqual(len(wf_doc_after["transitions"]), pre_transitions)

    def test_03_restarted_adapter_hydrates_persisted_state_and_rolls_back(self) -> None:
        sim, backend, adapter1, v1, rev1 = self._provision_v1("t_alpha")
        v1_hash = adapter1.call("export_config", _ctx("t_alpha"), {})["result"]["exportHash"]

        add_field = _load_example("compiled-artifact-add-field.json")
        res = _apply(adapter1, "t_alpha", add_field, "apply_add_before_restart")
        self.assertTrue(res["ok"] and res["result"]["status"] == "applied", res)
        v2_hash = res["result"]["exportHash"]

        # Simulate process restart with fresh :memory: SQLite backed by the same Frappe backend
        adapter2 = ChangeEngineAdapter(test_hooks=True, db_path=":memory:", frappe_backend=backend)
        # Unprovisioned tenant still fails closed with tenant_not_found
        missing = adapter2.call("site_status", _ctx("t_unknown"), {})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "tenant_not_found")

        # Existing tenant hydrates seamlessly and rolls back to v1 byte-identically
        exp = adapter2.call("export_config", _ctx("t_alpha"), {})
        self.assertTrue(exp["ok"])
        self.assertEqual(exp["result"]["exportHash"], v2_hash)

        rb = adapter2.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_after_restart"),
                "forwardArtifact": add_field,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000040"},
            },
        )
        self.assertTrue(rb["ok"] and rb["result"]["status"] == "applied", rb)
        self.assertEqual(rb["result"]["exportHash"], v1_hash)
        self.assertEqual(rb["result"]["site"]["applied"], {"artifactId": v1["artifactId"], "revision": rev1})

    def test_04_rollback_fault_compensation_and_recovery_required_gate(self) -> None:
        sim, _backend, adapter, _v1, rev1 = self._provision_v1("t_alpha")
        rev2 = {"hash": "sha256:" + ("5" * 64), "revision": 2}
        field_a = {"id": "route_code", "type": "string", "labels": {"en": "Route Code"}}
        rep_b = {
            "id": "route_rep",
            "kind": "summary",
            "entity": "customer",
            "labels": {"en": "Route Report"},
            "metrics": [{"id": "cnt", "op": "count", "groupBy": ["customer_name"]}],
            "visibleToRoles": ["sales_rep"],
        }
        fwd_inv = _make_artifact(
            bp_id="example-trading-001",
            kind="inverse",
            base=rev2,
            target=rev1,
            steps=[
                {
                    "seq": 1,
                    "phase": 11,
                    "kind": "report.disable",
                    "subject": {"kind": "report", "id": "route_rep", "parents": []},
                    "pointer": "/reports/route_rep",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": rep_b},
                    "sourceOps": ["/reports/route_rep"],
                },
                {
                    "seq": 2,
                    "phase": 15,
                    "kind": "field.quarantine",
                    "subject": {"kind": "field", "id": "route_code", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/route_code",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": field_a},
                    "sourceOps": ["/entities/customer/fields/route_code"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "disabled", "pointer": "/reports/route_rep"},
                {"id": "pc_002", "check": "quarantined", "pointer": "/entities/customer/fields/route_code"},
            ],
        )
        fwd = _make_artifact(
            bp_id="example-trading-001",
            kind="forward",
            base=rev1,
            target=rev2,
            steps=[
                {
                    "seq": 1,
                    "phase": 5,
                    "kind": "field.add",
                    "subject": {"kind": "field", "id": "route_code", "parents": [{"kind": "entity", "id": "customer"}]},
                    "pointer": "/entities/customer/fields/route_code",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {"definition": field_a},
                    "sourceOps": ["/entities/customer/fields/route_code"],
                },
                {
                    "seq": 2,
                    "phase": 10,
                    "kind": "report.upsert",
                    "subject": {"kind": "report", "id": "route_rep", "parents": []},
                    "pointer": "/reports/route_rep",
                    "impact": "config",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": rep_b},
                    "sourceOps": ["/reports/route_rep"],
                },
            ],
            post_conditions=[
                {"id": "pc_001", "check": "exists", "pointer": "/entities/customer/fields/route_code"},
                {"id": "pc_002", "check": "exists", "pointer": "/reports/route_rep"},
            ],
            inverse=fwd_inv,
        )
        res = _apply(adapter, "t_alpha", fwd, "apply_for_comp_test")
        self.assertTrue(res["ok"] and res["result"]["status"] == "applied", res)
        pre_rb_hash = res["result"]["exportHash"]

        # Inject fault on rollback execute step 2 -> step 1 compensated cleanly
        adapter.fault("execute", step_seq=2)
        rb_comp = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_comp_1"),
                "forwardArtifact": fwd,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000050"},
            },
        )
        self.assertTrue(rb_comp["ok"])
        self.assertEqual(rb_comp["result"]["status"], "compensated")
        self.assertEqual(rb_comp["result"]["exportHash"], pre_rb_hash)
        self.assertEqual(sim.sites["t-alpha.localhost"].rows["tabReport"]["route_rep"]["disabled"], 0)
        self.assertEqual(rb_comp["result"]["site"]["applied"], {"artifactId": fwd["artifactId"], "revision": rev2})

        # Inject compensation fault during rollback -> recovery_required blocks subsequent calls
        adapter.fault("execute", step_seq=2, during_compensation=True)
        rb_rec = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_comp_2"),
                "forwardArtifact": fwd,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000051"},
            },
        )
        self.assertEqual(rb_rec["result"]["status"], "recovery_required")
        blocked = adapter.call(
            "rollback",
            _ctx("t_alpha"),
            {
                "idempotencyKey": _k("rb_comp_3"),
                "forwardArtifact": fwd,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000052"},
            },
        )
        self.assertEqual(blocked["result"]["status"], "rejected")
        self.assertEqual(blocked["result"]["error"]["code"], "recovery_required")

    def test_05_direct_rpc_rollback_property_setter_quarantine_and_report(self) -> None:
        adapter = FrappeDeploymentAdapter()
        # 1. Property Setter add (no prior PS) -> rollback deletes PS
        ps_out = apply_property_setter_change(
            doctype="Customer",
            deployment_id="dep_bpl008_ps_1",
            fieldname="customer_name",
            property_name="description",
            value="Legal entity name",
            idempotency_key="idemp_bpl008_ps_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(ps_out["success"], ps_out)
        self.assertEqual(adapter.get_property_setter("Customer", "customer_name", "description")["value"], "Legal entity name")

        ps_rb = revert_configuration_change("dep_bpl008_ps_1", adapter=adapter, caller_roles=["System Manager"])
        self.assertEqual(ps_rb["status"], "ROLLED_BACK")
        self.assertEqual(ps_rb["disposition"], "PROPERTY_SETTER_REMOVED")
        self.assertIsNone(adapter.get_property_setter("Customer", "customer_name", "description"))

        # 2. Custom Field + reqd=1 Property Setter -> rollback soft-quarantines (hidden=1, reqd=0) without dropping column
        cf_out = apply_configuration_change(
            doctype="Sales Order",
            deployment_id="dep_bpl008_cf_1",
            field_def={"fieldname": "custom_delivery_slot", "label": "Delivery Slot", "fieldtype": "Data", "reqd": 0},
            idempotency_key="idemp_bpl008_cf_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(cf_out["success"], cf_out)
        reqd_out = apply_property_setter_change(
            doctype="Sales Order",
            deployment_id="dep_bpl008_cf_reqd",
            fieldname="custom_delivery_slot",
            property_name="reqd",
            value=1,
            idempotency_key="idemp_bpl008_cf_reqd",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(reqd_out["success"], reqd_out)
        cf_rb = revert_configuration_change("dep_bpl008_cf_1", adapter=adapter, caller_roles=["System Manager"])
        self.assertEqual(cf_rb["status"], "QUARANTINED")
        self.assertFalse(cf_rb["physical_column_dropped"])
        self.assertEqual(int(adapter.get_property_setter("Sales Order", "custom_delivery_slot", "hidden")["value"]), 1)
        self.assertEqual(int(adapter.get_property_setter("Sales Order", "custom_delivery_slot", "reqd")["value"]), 0)

        # 3. Report -> rollback soft-disables report
        rep_out = apply_report_change(
            doctype="Customer",
            deployment_id="dep_bpl008_rep_1",
            report_def={
                "report_name": "Customer Directory",
                "ref_doctype": "Customer",
                "columns": [{"fieldname": "name", "label": "ID"}],
                "roles": ["System Manager"],
            },
            idempotency_key="idemp_bpl008_rep_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(rep_out["success"], rep_out)
        rep_rb = revert_configuration_change("dep_bpl008_rep_1", adapter=adapter, caller_roles=["System Manager"])
        self.assertEqual(rep_rb["status"], "ROLLED_BACK")
        self.assertEqual(rep_rb["disposition"], "REPORT_DISABLED")
        self.assertEqual(adapter.get_report("Customer Directory")["disabled"], 1)

    @unittest.skipUnless(SERVICES_BP_DIR.is_dir(), "services/blueprint package not present")
    def test_06_compiled_blueprint_initial_build_diff_apply_and_rollback(self) -> None:
        if str(SERVICES_BP_DIR) not in sys.path:
            sys.path.insert(0, str(SERVICES_BP_DIR))
        diff_dir = SERVICES_BP_DIR / "diff"
        if str(diff_dir) not in sys.path:
            sys.path.insert(0, str(diff_dir))
        from bpdiff import diff as bp_diff  # type: ignore[import-not-found]
        from compiler import compile_blueprint  # type: ignore[import-not-found]
        from registry import Registry  # type: ignore[import-not-found]

        bp_v1 = json.loads(
            (SERVICES_BP_DIR / "fixtures" / "trading-distribution.blueprint.json").read_text(encoding="utf-8")
        )
        for ent in bp_v1["entities"]:
            for fld in ent["fields"]:
                if fld["type"] == "attachment":
                    fld["type"] = "string"
        manifests = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((SERVICES_BP_DIR / "fixtures" / "registry").glob("*.json"))
        ]
        reg = Registry.from_manifests(manifests)
        eng_map = json.loads((EXAMPLES_DIR / "engine-mapping-golden-path.json").read_text(encoding="utf-8"))

        # Compile v1 initial build with the real BPL-004 compiler
        c1 = compile_blueprint(bp_v1, reg, eng_map, environment="sandbox")
        self.assertTrue(c1.ok, [str(e) for e in c1.errors])
        self.assertEqual(c1.artifact["kind"], "forward")
        self.assertIsNone(c1.artifact["blueprint"]["base"])

        # Compute forward & inverse Blueprint diffs between v1 and v2
        bp_v2 = copy.deepcopy(bp_v1)
        bp_v2["meta"]["revision"] = 2
        bp_v2["entities"][0]["fields"].append(
            {"id": "delivery_notes", "type": "string", "labels": {"en": "Delivery Notes", "ar": "ملاحظات التوصيل"}}
        )
        d_fwd = bp_diff(bp_v1, bp_v2)
        d_inv = bp_diff(bp_v2, bp_v1)
        ent_id = bp_v1["entities"][0]["id"]
        self.assertEqual(
            [op["op"] for op in d_fwd["ops"] if op["pointer"] == f"/entities/{ent_id}/fields/delivery_notes"],
            ["add"],
        )
        self.assertEqual(
            [op["op"] for op in d_inv["ops"] if op["pointer"] == f"/entities/{ent_id}/fields/delivery_notes"],
            ["remove"],
        )

        # Normalize engineTarget to Frappe adapter & prove compiled steps execute + roll back cleanly
        compiled_art = copy.deepcopy(c1.artifact)
        compiled_art["engineTarget"] = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
        compiled_art = _seal(compiled_art)

        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True, offline_ddl_simulator=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        prov = adapter.call(
            "provision_site",
            _ctx("t_compile"),
            {
                "idempotencyKey": _k("prov_t_compile"),
                "engineTarget": compiled_art["engineTarget"],
                "blueprintId": compiled_art["blueprint"]["id"],
                "siteClass": "sandbox",
                "countryPack": "sa",
            },
        )
        self.assertTrue(prov["ok"], prov)
        r1 = _apply(adapter, "t_compile", compiled_art, "apply_compiled_v1")
        self.assertTrue(r1["ok"] and r1["result"]["status"] == "applied", r1)

        # Verify diff-derived v2 forward + inverse rollback preserves compiled v1 exportHash
        v1_hash = r1["result"]["exportHash"]
        v1_rev = compiled_art["blueprint"]["target"]
        v2_rev = {"hash": "sha256:" + ("9" * 64), "revision": 2}
        new_field = {"id": "delivery_notes", "type": "string", "labels": {"en": "Delivery Notes", "ar": "ملاحظات التوصيل"}}
        v2_inv = _make_artifact(
            bp_id=compiled_art["blueprint"]["id"],
            kind="inverse",
            base=v2_rev,
            target=v1_rev,
            diff_hash="sha256:" + ("8" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 15,
                    "kind": "field.quarantine",
                    "subject": {"kind": "field", "id": "delivery_notes", "parents": [{"kind": "entity", "id": ent_id}]},
                    "pointer": f"/entities/{ent_id}/fields/delivery_notes",
                    "impact": "destructive",
                    "ddlImpact": "none",
                    "reversible": True,
                    "params": {"definition": new_field},
                    "sourceOps": [f"/entities/{ent_id}/fields/delivery_notes"],
                }
            ],
            post_conditions=[{"id": "pc_001", "check": "quarantined", "pointer": f"/entities/{ent_id}/fields/delivery_notes"}],
        )
        v2_fwd = _make_artifact(
            bp_id=compiled_art["blueprint"]["id"],
            kind="forward",
            base=v1_rev,
            target=v2_rev,
            diff_hash="sha256:" + ("7" * 64),
            steps=[
                {
                    "seq": 1,
                    "phase": 5,
                    "kind": "field.add",
                    "subject": {"kind": "field", "id": "delivery_notes", "parents": [{"kind": "entity", "id": ent_id}]},
                    "pointer": f"/entities/{ent_id}/fields/delivery_notes",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {"definition": new_field},
                    "sourceOps": [f"/entities/{ent_id}/fields/delivery_notes"],
                }
            ],
            post_conditions=[{"id": "pc_001", "check": "exists", "pointer": f"/entities/{ent_id}/fields/delivery_notes"}],
            inverse=v2_inv,
        )
        r2 = _apply(adapter, "t_compile", v2_fwd, "apply_compiled_v2")
        self.assertTrue(r2["ok"] and r2["result"]["status"] == "applied", r2)
        rb2 = adapter.call(
            "rollback",
            _ctx("t_compile"),
            {
                "idempotencyKey": _k("rb_compiled_v2"),
                "forwardArtifact": v2_fwd,
                "reason": "owner_request",
                "approvals": {"rollbackApproved": "01J00000000000000000000060"},
            },
        )
        self.assertTrue(rb2["ok"] and rb2["result"]["status"] == "applied", rb2)
        self.assertEqual(rb2["result"]["exportHash"], v1_hash)
        self.assertEqual(rb2["result"]["site"]["applied"], {"artifactId": compiled_art["artifactId"], "revision": v1_rev})


if __name__ == "__main__":
    unittest.main()
