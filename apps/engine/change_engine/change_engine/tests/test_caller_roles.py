"""
Regression tests for CE-SEC-001, CE-SEC-002, CE-SEC-003 (partial) and CE-SEC-004.

Run from apps/engine/change_engine:
    PYTHONPATH=. python3 -m unittest change_engine.tests.test_caller_roles
"""

import types
import unittest

from change_engine.api import endpoints
from change_engine.guarded_apply import rollback_engine


def _fake_frappe(user="staff@example.invalid", roles=("Sales User",), fail=False):
    f = types.SimpleNamespace()
    f.session = types.SimpleNamespace(user=user)

    def get_roles(_user):
        if fail:
            raise RuntimeError("role lookup failed")
        return list(roles)

    f.get_roles = get_roles
    return f


class CallerRoleTests(unittest.TestCase):
    def setUp(self):
        self._orig = endpoints.frappe

    def tearDown(self):
        endpoints.frappe = self._orig

    def test_client_supplied_roles_ignored_inside_frappe(self):
        endpoints.frappe = _fake_frappe(roles=("Sales User",))
        roles = endpoints._resolve_caller_roles({"user_roles": ["System Manager"], "caller_roles": ["System Manager"]})
        self.assertEqual(roles, ["Sales User"])

    def test_role_lookup_failure_fails_closed(self):
        endpoints.frappe = _fake_frappe(fail=True)
        self.assertEqual(endpoints.get_current_user_roles(), [])
        self.assertEqual(endpoints._resolve_caller_roles({"user_roles": ["System Manager"]}), [])

    def test_standalone_mode_honours_explicit_roles(self):
        endpoints.frappe = None
        self.assertEqual(endpoints._resolve_caller_roles({"user_roles": ["Finance Director"]}), ["Finance Director"])
        self.assertEqual(endpoints._resolve_caller_roles({}), [])  # no implicit System Manager

    def test_unauthorised_session_cannot_deploy(self):
        endpoints.frappe = _fake_frappe(roles=("Sales User",))
        out = endpoints.apply_configuration_change(
            doctype="Delivery Note",
            field_def={"fieldname": "custom_container_no", "fieldtype": "Data", "label": "Container No"},
            user_roles=["System Manager"],  # forged by the client
        )
        self.assertFalse(out.get("success"))
        self.assertEqual(out.get("disposition"), "UNAUTHORIZED_ROLE")

    def test_read_endpoints_require_authorised_role(self):
        endpoints.frappe = _fake_frappe(roles=("Sales User",))
        with self.assertRaises(PermissionError):
            endpoints.get_runtime_policies()
        with self.assertRaises(PermissionError):
            endpoints.evaluate_document_policies("Sales Order", {})

    def test_frappe_site_without_session_user_ignores_client_roles(self):
        # CE-SEC-002 hole: a Frappe site context with no session user fell through to the
        # caller-supplied roles. It must resolve to no roles instead.
        f = _fake_frappe(user=None)
        f.local = types.SimpleNamespace(site="tenant_a.localhost")
        endpoints.frappe = f
        self.assertEqual(endpoints._resolve_caller_roles({"user_roles": ["System Manager"]}), [])
        self.assertEqual(endpoints._resolve_caller_roles({"caller_roles": ["System Manager"]}), [])
        out = endpoints.apply_configuration_change(
            doctype="Delivery Note",
            field_def={"fieldname": "custom_container_no", "fieldtype": "Data", "label": "Container No"},
            user_roles=["System Manager"],
        )
        self.assertEqual(out.get("disposition"), "UNAUTHORIZED_ROLE")

    def test_llm_endpoints_removed(self):
        self.assertFalse(hasattr(endpoints, "test_llm_connection"))
        self.assertFalse(hasattr(endpoints, "get_llm_config"))


class RollbackFailClosedTests(unittest.TestCase):
    """CE-SEC-002 hole: execute_rollback granted System Manager when the role lookup failed."""

    def setUp(self):
        self._orig = rollback_engine.frappe

    def tearDown(self):
        rollback_engine.frappe = self._orig

    def _rollback(self):
        return rollback_engine.execute_rollback("dep_missing", caller_roles=None, db=types.SimpleNamespace(audit_journal={}))

    def test_role_lookup_failure_denies_rollback(self):
        rollback_engine.frappe = _fake_frappe(fail=True)
        out = self._rollback()
        self.assertEqual(out["disposition"], "UNAUTHORIZED_ROLE")

    def test_missing_session_user_denies_rollback(self):
        rollback_engine.frappe = _fake_frappe(user=None, roles=("System Manager",))
        self.assertEqual(self._rollback()["disposition"], "UNAUTHORIZED_ROLE")

    def test_no_frappe_and_no_roles_denies_rollback(self):
        rollback_engine.frappe = None
        self.assertEqual(self._rollback()["disposition"], "UNAUTHORIZED_ROLE")

    def test_session_roles_still_authorise_rollback(self):
        rollback_engine.frappe = _fake_frappe(roles=("Finance Director",))
        self.assertEqual(self._rollback()["disposition"], "DEPLOYMENT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
