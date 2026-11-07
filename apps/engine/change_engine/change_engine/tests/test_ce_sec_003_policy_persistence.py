"""
Unit and regression tests for CE-SEC-003:
Per-site runtime policy persistence, revision tracking, durable audit trail,
and admin permission gating.
"""

import types
import unittest
from typing import Any, Dict, List

from change_engine.api import endpoints
from change_engine.guarded_apply.policy_enforcer import (
    PolicyType,
    RuntimePolicy,
    RuntimePolicyViolation,
    policy_catalog,
)
from change_engine.guarded_apply.policy_store import policy_store


def _fake_frappe(user="staff@example.invalid", roles=("Sales User",), site="tenant_a.localhost"):
    f = types.SimpleNamespace()
    f.session = types.SimpleNamespace(user=user)
    f.local = types.SimpleNamespace(site=site)

    def get_roles(_user):
        return list(roles)

    f.get_roles = get_roles
    return f


class MockFrappeDoc:
    def __init__(self, doctype: str, docstatus: int = 0, **fields: Any):
        self.doctype = doctype
        self.docstatus = docstatus
        self._changed_fields = set()
        for k, v in fields.items():
            setattr(self, k, v)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def set(self, key: str, value: Any) -> None:
        setattr(self, key, value)
        self._changed_fields.add(key)

    def has_value_changed(self, fieldname: str) -> bool:
        return fieldname in self._changed_fields


class TestCESec003PolicyPersistence(unittest.TestCase):
    def setUp(self):
        self._orig_frappe = endpoints.frappe
        policy_catalog.reset()
        policy_store.reset_store()

    def tearDown(self):
        endpoints.frappe = self._orig_frappe
        policy_catalog.reset()
        policy_store.reset_store()

    # --------------------------------------------------------------------------
    # 1. Admin permission checks
    # --------------------------------------------------------------------------
    def test_01_non_admin_cannot_register_inside_frappe(self):
        """Non-admin user session inside Frappe fails closed with PermissionError."""
        endpoints.frappe = _fake_frappe(roles=("Sales User",))
        policy = RuntimePolicy(
            policy_id="POL_CUSTOM_DISCOUNT",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 15",
            required_role="Finance Director",
            error_message="Discount over 15% requires Finance Director approval.",
        )
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(policy)

    def test_02_non_admin_cannot_register_standalone(self):
        """Standalone caller with non-admin roles fails closed with PermissionError."""
        endpoints.frappe = None
        policy = RuntimePolicy(
            policy_id="POL_CUSTOM_DISCOUNT",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 15",
            required_role="Finance Director",
            error_message="Discount over 15% requires Finance Director approval.",
        )
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(policy, caller_roles=["Sales User"])

    def test_03_admin_registers_and_creates_revision_1(self):
        """Admin caller (System Manager) can register a policy with revision 1."""
        endpoints.frappe = _fake_frappe(user="admin@example.invalid", roles=("System Manager",), site="tenant_1")
        policy = RuntimePolicy(
            policy_id="POL_CUSTOM_DISCOUNT",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 15",
            required_role="Finance Director",
            error_message="Discount over 15% requires Finance Director approval.",
        )
        out = endpoints.register_runtime_policy(policy)
        self.assertTrue(out["success"])
        self.assertEqual(out["policy_id"], "POL_CUSTOM_DISCOUNT")
        self.assertEqual(out["revision"], 1)
        self.assertEqual(out["action"], "CREATED")
        self.assertTrue(out["audit_id"].startswith("aud_pol_"))

    # --------------------------------------------------------------------------
    # 2. Revision tracking and audit trail
    # --------------------------------------------------------------------------
    def test_04_revision_increments_on_update(self):
        """Registering an update to an existing policy increments the revision number."""
        endpoints.frappe = _fake_frappe(roles=("Finance Director",), site="tenant_1")
        policy_v1 = RuntimePolicy(
            policy_id="POL_CREDIT_CAP",
            doctype="Sales Order",
            policy_type=PolicyType.THRESHOLD_GATE,
            condition_expr="grand_total > 50000",
            required_role="Finance Director",
            error_message="Orders over 50,000 require Finance Director.",
        )
        res1 = endpoints.register_runtime_policy(policy_v1)
        self.assertEqual(res1["revision"], 1)
        self.assertEqual(res1["action"], "CREATED")

        # Update condition to threshold 75,000
        policy_v2 = RuntimePolicy(
            policy_id="POL_CREDIT_CAP",
            doctype="Sales Order",
            policy_type=PolicyType.THRESHOLD_GATE,
            condition_expr="grand_total > 75000",
            required_role="Finance Director",
            error_message="Orders over 75,000 require Finance Director.",
        )
        res2 = endpoints.register_runtime_policy(policy_v2)
        self.assertEqual(res2["revision"], 2)
        self.assertEqual(res2["action"], "UPDATED")

        # Verify revision history endpoint
        revisions = endpoints.get_policy_revisions("POL_CREDIT_CAP")
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0]["revision"], 1)
        self.assertEqual(revisions[1]["revision"], 2)
        self.assertEqual(revisions[1]["condition_expr"], "grand_total > 75000")

    def test_05_audit_trail_captures_actor_and_diffs(self):
        """Audit trail logs who changed the policy, when, and captures before/after states."""
        endpoints.frappe = _fake_frappe(user="director@example.invalid", roles=("Operations Director",), site="tenant_1")
        policy = RuntimePolicy(
            policy_id="POL_MARGIN_GATE",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            condition_expr="margin < 5",
            required_role="Operations Director",
            error_message="Low margin requires Operations Director.",
        )
        endpoints.register_runtime_policy(policy)

        # Update policy
        policy_updated = RuntimePolicy(
            policy_id="POL_MARGIN_GATE",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            condition_expr="margin < 8",
            required_role="Operations Director",
            error_message="Margin under 8% requires Operations Director.",
        )
        endpoints.register_runtime_policy(policy_updated)

        audit_trail = endpoints.get_policy_audit_trail(policy_id="POL_MARGIN_GATE")
        self.assertEqual(len(audit_trail), 2)

        # Check creation record
        created_rec = audit_trail[0]
        self.assertEqual(created_rec["action"], "CREATED")
        self.assertEqual(created_rec["changed_by"], "director@example.invalid")
        self.assertIsNone(created_rec["payload_before"])
        self.assertEqual(created_rec["payload_after"]["revision"], 1)

        # Check update record
        updated_rec = audit_trail[1]
        self.assertEqual(updated_rec["action"], "UPDATED")
        self.assertEqual(updated_rec["changed_by"], "director@example.invalid")
        self.assertEqual(updated_rec["payload_before"]["condition_expr"], "margin < 5")
        self.assertEqual(updated_rec["payload_after"]["condition_expr"], "margin < 8")
        self.assertEqual(updated_rec["payload_after"]["revision"], 2)

    # --------------------------------------------------------------------------
    # 3. Per-site isolation
    # --------------------------------------------------------------------------
    def test_06_per_site_policy_isolation(self):
        """Policies registered on tenant_alpha do NOT leak into tenant_beta."""
        # Register on tenant_alpha
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_alpha")
        alpha_policy = RuntimePolicy(
            policy_id="POL_ALPHA_ONLY",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            condition_expr="grand_total > 1000",
            required_role="System Manager",
            error_message="Alpha special rule",
        )
        endpoints.register_runtime_policy(alpha_policy)

        # Register on tenant_beta
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_beta")
        beta_policy = RuntimePolicy(
            policy_id="POL_BETA_ONLY",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            condition_expr="grand_total > 2000",
            required_role="System Manager",
            error_message="Beta special rule",
        )
        endpoints.register_runtime_policy(beta_policy)

        # Query tenant_alpha
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_alpha")
        alpha_policies = endpoints.get_runtime_policies(doctype="Sales Order")
        alpha_ids = {p["policy_id"] for p in alpha_policies}
        self.assertIn("POL_ALPHA_ONLY", alpha_ids)
        self.assertNotIn("POL_BETA_ONLY", alpha_ids)

        # Query tenant_beta
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_beta")
        beta_policies = endpoints.get_runtime_policies(doctype="Sales Order")
        beta_ids = {p["policy_id"] for p in beta_policies}
        self.assertIn("POL_BETA_ONLY", beta_ids)
        self.assertNotIn("POL_ALPHA_ONLY", beta_ids)

    # --------------------------------------------------------------------------
    # 4. Live document lifecycle enforcement of persisted policies
    # --------------------------------------------------------------------------
    def test_07_persisted_policy_enforcement_in_document_hooks(self):
        """A custom persisted policy is evaluated and enforces invariants during document lifecycle."""
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_live")
        custom_so_policy = RuntimePolicy(
            policy_id="POL_MAX_DISCOUNT_PERCENT",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            target_field="discount_percentage",
            condition_expr="discount_percentage > 25",
            required_role="Finance Director",
            error_message="Discounts over 25% strictly require Finance Director authorization.",
        )
        endpoints.register_runtime_policy(custom_so_policy)

        # Document with high discount by standard Sales User
        doc_violating = MockFrappeDoc(
            doctype="Sales Order",
            docstatus=0,
            discount_percentage=30,
        )

        with self.assertRaises(RuntimePolicyViolation) as ctx:
            policy_catalog.evaluate_validate(doc_violating, user_roles=["Sales User"])
        self.assertEqual(ctx.exception.policy_id, "POL_MAX_DISCOUNT_PERCENT")

        # Document within permitted threshold passes
        doc_ok = MockFrappeDoc(
            doctype="Sales Order",
            docstatus=0,
            discount_percentage=20,
        )
        res_ok = policy_catalog.evaluate_validate(doc_ok, user_roles=["Sales User"])
        self.assertTrue(res_ok.allowed)

        # Document with high discount by authorized Finance Director passes
        res_auth = policy_catalog.evaluate_validate(doc_violating, user_roles=["Finance Director"])
        self.assertTrue(res_auth.allowed)

    # --------------------------------------------------------------------------
    # 5. Unregistration and deactivation audit
    # --------------------------------------------------------------------------
    def test_08_unregistration_requires_admin_and_logs_deletion(self):
        """Unregistering a policy requires admin role and writes an audit record."""
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_live")
        policy = RuntimePolicy(
            policy_id="POL_TEMP_RULE",
            doctype="Sales Order",
            policy_type=PolicyType.FIELD_CONSTRAINT,
            condition_expr="grand_total > 5000",
            error_message="Temporary limit",
        )
        endpoints.register_runtime_policy(policy)

        # Non-admin attempt to unregister fails
        endpoints.frappe = _fake_frappe(roles=("Sales User",), site="tenant_live")
        with self.assertRaises(PermissionError):
            endpoints.unregister_runtime_policy("POL_TEMP_RULE")

        # Admin unregister succeeds
        endpoints.frappe = _fake_frappe(roles=("System Manager",), site="tenant_live")
        del_out = endpoints.unregister_runtime_policy("POL_TEMP_RULE")
        self.assertTrue(del_out["success"])

        # Policy is no longer in active policies
        active_policies = endpoints.get_runtime_policies(doctype="Sales Order")
        self.assertNotIn("POL_TEMP_RULE", {p["policy_id"] for p in active_policies})

        # Audit trail records DELETED action
        audit_trail = endpoints.get_policy_audit_trail(policy_id="POL_TEMP_RULE")
        self.assertEqual(len(audit_trail), 2)
        self.assertEqual(audit_trail[-1]["action"], "DELETED")
        self.assertIsNotNone(audit_trail[-1]["payload_before"])
        self.assertIsNone(audit_trail[-1]["payload_after"])


if __name__ == "__main__":
    unittest.main()
