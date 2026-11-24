"""BPL-007 tests: Apply with preview and DDL plan gate (change engine)."""
from __future__ import annotations

import os
import sys
import types
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if "frappe" not in sys.modules:
    try:
        import frappe  # noqa: F401
    except ImportError:
        f = types.ModuleType("frappe")
        f.utils = types.ModuleType("frappe.utils")
        f.utils.cstr = lambda x: str(x)
        f.local = types.SimpleNamespace(site="test_site.local")
        sys.modules["frappe"] = f
        sys.modules["frappe.utils"] = f.utils

from change_engine.api.endpoints import (
    FrappeDeploymentAdapter,
    apply_configuration_change,
    propose_configuration_change,
)
from change_engine.guarded_apply.ddl_plan_gate import (
    ColumnDesc,
    DDLPlanInspection,
    SimulatedDbColumn,
    SimulatedMariaDBTable,
    _normalize_zero_decimal_defaults,
    inspect_frappe_ddl_plan,
    validate_ddl_plan,
)
from change_engine.guarded_apply.schema_reconciler import (
    ExhaustiveSnapshot,
    execute_single_field_deployment,
)


class _DummyFrappeDbCol:
    def __init__(self, fieldname: str, fieldtype: str, default: object = None):
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self.default = default


class _PreviewDriftedAdapter(FrappeDeploymentAdapter):
    """Test adapter that can inject drifted DDL plans or Stage 6 persistence failures."""

    def __init__(self, *, forced_plan: DDLPlanInspection | None = None, fail_finalize: bool = False):
        super().__init__()
        self.forced_plan = forced_plan
        self.fail_finalize = fail_finalize

    def inspect_ddl_plan(self, doctype: str, field_def: dict) -> DDLPlanInspection:
        if self.forced_plan is not None:
            return self.forced_plan
        return super().inspect_ddl_plan(doctype, field_def)

    def persist_final_outcome_and_audit(self, deployment_id: str, outcome: dict) -> None:
        if self.fail_finalize:
            raise RuntimeError("Simulated Stage 6 finalization failure")
        super().persist_final_outcome_and_audit(deployment_id, outcome)


class TestBpl007ApplyPreviewAndDdlGate(unittest.TestCase):
    def setUp(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def tearDown(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def test_01_decimal_types_approved_and_multi_clause_injection_rejected(self) -> None:
        for fieldtype, expected_col in (
            ("Float", "decimal(21,9) not null default 0"),
            ("Currency", "decimal(21,9) not null default 0"),
            ("Percent", "decimal(21,9) not null default 0"),
        ):
            res = inspect_frappe_ddl_plan(
                "Sales Order",
                {"fieldname": f"custom_num_{fieldtype.lower()}", "fieldtype": fieldtype},
                offline_simulator=True,
            )
            self.assertTrue(res.inspectable)
            self.assertTrue(res.is_approved_additive_only, res.rejection_reason)
            self.assertEqual(
                res.statements,
                [f"ALTER TABLE `tabSales Order` ADD COLUMN `custom_num_{fieldtype.lower()}` {expected_col}"],
            )

        # Injection / multi-clause attempts inside ADD COLUMN tail must stay rejected
        ok_drop, reason_drop = validate_ddl_plan(
            ["ALTER TABLE `tabCustomer` ADD COLUMN `custom_x` varchar(140), DROP COLUMN `credit_limit`"]
        )
        self.assertFalse(ok_drop)
        self.assertIsNotNone(reason_drop)

        ok_modify, reason_modify = validate_ddl_plan(
            ["ALTER TABLE `tabCustomer` ADD COLUMN `custom_x` decimal(21,9), MODIFY COLUMN `total` varchar(20)"]
        )
        self.assertFalse(ok_modify)
        self.assertIn("MODIFY", reason_modify or "")

        ok_multi_decimal, _ = validate_ddl_plan(
            ["ALTER TABLE `tabCustomer` ADD COLUMN `custom_x` decimal(21,9), decimal(21,9)"]
        )
        self.assertFalse(ok_multi_decimal)

    def test_02_normalize_zero_decimal_defaults_suppresses_phantom_drift_only(self) -> None:
        table_cols = {
            "total": _DummyFrappeDbCol("total", "Currency", default=None),
            "custom_new_pct": _DummyFrappeDbCol("custom_new_pct", "Float", default=None),
        }
        current_cols = {
            "total": ColumnDesc(name="total", type="decimal(21,9)", default="0.000000000", nullable=False),
        }
        _normalize_zero_decimal_defaults(table_cols, current_cols, exclude_fieldname="custom_new_pct")
        self.assertIsNone(current_cols["total"]["default"])

        # Non-zero DB default must NOT be normalized away so real drift stays blocked
        real_drift_cols = {
            "total": ColumnDesc(name="total", type="decimal(21,9)", default="5.000000000", nullable=False),
        }
        _normalize_zero_decimal_defaults(table_cols, real_drift_cols, exclude_fieldname="custom_new_pct")
        self.assertEqual(real_drift_cols["total"]["default"], "5.000000000")

        # Simulator also verifies real column type drift produces MODIFY and fails gate
        sim = SimulatedMariaDBTable("Sales Order")
        sim.current_columns = {
            "name": ColumnDesc(name="name", type="varchar(140)"),
            "total": ColumnDesc(name="total", type="decimal(18,6)", default="0"),
        }
        drifted = SimulatedDbColumn(sim, "total", "Currency", default=None)
        sim.columns["total"] = drifted
        sim.columns["custom_probe"] = SimulatedDbColumn(sim, "custom_probe", "Data")
        stmts = sim.alter()
        ok, reason = validate_ddl_plan(stmts)
        self.assertFalse(ok)
        self.assertIn("MODIFY", reason or "")

    def test_03_propose_emits_preview_and_fails_closed_on_gate_or_guardrail(self) -> None:
        adapter = FrappeDeploymentAdapter()
        field_def = {"fieldname": "custom_delivery_window", "label": "Delivery Window", "fieldtype": "Data"}
        payload = {"intent": "add_custom_fields", "changes": [field_def]}

        p1 = propose_configuration_change("Sales Order", dict(payload), adapter=adapter, user_roles=["System Manager"])
        p2 = propose_configuration_change("Sales Order", dict(payload), adapter=adapter, user_roles=["System Manager"])

        self.assertTrue(p1["success"])
        self.assertEqual(p1["status"], "PROPOSED")
        self.assertEqual(p1["preview_digest"], p2["preview_digest"])
        self.assertEqual(p1["preview"]["statements"], p1["ddl_plan"]["statements"])
        self.assertTrue(p1["preview"]["ddl_gate_passed"])
        self.assertTrue(p1["ddl_plan"]["is_approved_additive_only"])

        # Zone 2 violation must fail closed with structured REJECTED payload
        z2 = propose_configuration_change(
            "GL Entry",
            {"intent": "add_custom_fields", "changes": [field_def]},
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(z2["success"])
        self.assertEqual(z2["status"], "REJECTED")
        self.assertEqual(z2["disposition"], "ZONE_SAFETY_VIOLATION")

        # Existing table drift / unapproved MODIFY must fail closed at propose time
        adapter.table_columns["Sales Order"] = [
            ColumnDesc(name="name", type="varchar(140)"),
            ColumnDesc(name="custom_delivery_window", type="text"),
        ]
        bad_ddl = propose_configuration_change(
            "Sales Order",
            {"intent": "add_custom_fields", "changes": [field_def]},
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(bad_ddl["success"])
        self.assertEqual(bad_ddl["status"], "REJECTED")
        self.assertEqual(bad_ddl["disposition"], "DDL_PLAN_REJECTED")
        self.assertEqual(bad_ddl["fallback_action"], "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT")

    def test_04_apply_verifies_preview_binding_and_blocks_drift(self) -> None:
        adapter = _PreviewDriftedAdapter()
        field_def = {"fieldname": "custom_region_code", "label": "Region Code", "fieldtype": "Float"}
        preview = propose_configuration_change(
            "Customer",
            {"intent": "add_custom_fields", "changes": [field_def]},
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(preview["success"])

        # Drifted field_def against preview digest -> PREVIEW_MISMATCH before any Stage 3/4 mutation
        tampered = dict(field_def, label="Different Label")
        mismatch = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_bpl007_mismatch_1",
            field_def=tampered,
            proposal=preview["proposal"],
            preview_digest=preview["preview_digest"],
            expected_ddl_plan_statements=preview["ddl_plan"]["statements"],
            idempotency_key="idemp_bpl007_mismatch_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(mismatch["success"])
        self.assertEqual(mismatch["status"], "REJECTED")
        self.assertEqual(mismatch["disposition"], "PREVIEW_MISMATCH")
        self.assertEqual(adapter.audit_journal, {})

        # Drifted field_def passed without proposal envelope also fails digest check
        mismatch_no_prop = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_bpl007_mismatch_2",
            field_def=tampered,
            preview_digest=preview["preview_digest"],
            expected_ddl_plan_statements=preview["ddl_plan"]["statements"],
            idempotency_key="idemp_bpl007_mismatch_2",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(mismatch_no_prop["success"])
        self.assertEqual(mismatch_no_prop["status"], "REJECTED")
        self.assertEqual(mismatch_no_prop["disposition"], "PREVIEW_MISMATCH")

        # Unapproved live DDL plan during apply -> DDL_PLAN_REJECTED before Stage 3
        bad_plan_adapter = _PreviewDriftedAdapter(
            forced_plan=DDLPlanInspection(
                inspectable=True,
                statements=["ALTER TABLE `tabCustomer` MODIFY `total` varchar(20)"],
                is_approved_additive_only=False,
                rejection_reason="Unapproved MODIFY COLUMN detected in updatedb() diff",
            )
        )
        rej = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_bpl007_badplan_1",
            proposal=preview,
            idempotency_key="idemp_bpl007_badplan_1",
            adapter=bad_plan_adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(rej["success"])
        self.assertEqual(rej["status"], "REJECTED")
        self.assertEqual(rej["disposition"], "DDL_PLAN_REJECTED")
        self.assertEqual(bad_plan_adapter.audit_journal, {})

        # Drifted live revision without explicit base_revision_hash -> PREVIEW_MISMATCH
        adapter.revision_hashes["Customer"] = "rev_drifted_999"
        rev_mismatch = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_bpl007_revmismatch_1",
            proposal=preview,
            idempotency_key="idemp_bpl007_revmismatch_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(rev_mismatch["success"])
        self.assertEqual(rev_mismatch["status"], "REJECTED")
        self.assertEqual(rev_mismatch["disposition"], "PREVIEW_MISMATCH")

        # Matching preview envelope applies cleanly to Customer
        adapter.revision_hashes["Customer"] = preview["base_revision_hash"]
        applied = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_bpl007_ok_1",
            proposal=preview,
            idempotency_key="idemp_bpl007_ok_1",
            adapter=adapter,
            user_roles=["System Manager"],
        )
        self.assertTrue(applied["success"], applied)
        self.assertEqual(applied["status"], "APPLIED")
        self.assertIn(("Customer", "custom_region_code"), adapter.custom_fields)

    def test_05_stage6_finalize_failure_marks_recovery_and_stale_prepared_blocks(self) -> None:
        adapter = _PreviewDriftedAdapter(fail_finalize=True)
        field_def = {"fieldname": "custom_fin_probe", "label": "Fin Probe", "fieldtype": "Data"}
        base_rev = adapter.get_doctype_revision_hash("Sales Order")

        outcome = execute_single_field_deployment(
            db=adapter,
            deployment_id="dep_bpl007_stage6_fail",
            idempotency_key="idemp_bpl007_stage6_fail",
            site_id="site_bpl007.localhost",
            doctype="Sales Order",
            base_revision_hash=base_rev,
            field_def=field_def,
        )
        self.assertEqual(outcome["status"], "RECOVERY_REQUIRED")
        self.assertIn("finalization_error", outcome)
        self.assertEqual(
            adapter.audit_journal["dep_bpl007_stage6_fail"]["status"],
            "RECOVERY_REQUIRED",
        )
        self.assertTrue(adapter.is_target_in_recovery_required("site_bpl007.localhost", "Sales Order"))

        # Even if mark_recovery_required were unavailable leaving an unresolved PREPARED row,
        # is_target_in_recovery_required must still block subsequent deploys fail-closed.
        stale_adapter = FrappeDeploymentAdapter()
        stale_adapter.persist_prepare_and_audit_intent(
            {
                "deployment_id": "dep_stale_prepared",
                "idempotency_key": "idemp_stale_prepared",
                "payload_hash": "abc",
                "site_id": "site_bpl007.localhost",
                "doctype": "Customer",
                "fieldname": "custom_stale",
                "base_revision_hash": "rev_1",
                "ddl_plan_statements": [],
                "status": "PREPARED",
            }
        )
        self.assertTrue(stale_adapter.is_target_in_recovery_required("site_bpl007.localhost", "Customer"))
        blocked = apply_configuration_change(
            doctype="Customer",
            deployment_id="dep_after_stale",
            field_def={"fieldname": "custom_next", "label": "Next", "fieldtype": "Data"},
            idempotency_key="idemp_after_stale",
            site_id="site_bpl007.localhost",
            adapter=stale_adapter,
            user_roles=["System Manager"],
        )
        self.assertFalse(blocked["success"])
        self.assertEqual(blocked["status"], "RECOVERY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
