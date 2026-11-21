"""CE-SEC-005: live security regressions over real HTTP RPC against the pinned bench.

HTTP assertions go through the running Gunicorn worker (``/api/method/...``) with
the internal gateway credential and a user API token, exercising the route guard,
Frappe's request handling, session and whitelist dispatch. Same skip and
fail-closed rules as ``test_ce_sec_005_real_bench`` (``CE_SEC_005_REAL_BENCH=1``).
"""
from __future__ import annotations

import inspect
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from change_engine.tests.test_ce_sec_005_real_bench import RealBenchTestCase

try:
    import frappe  # type: ignore[import-not-found]
except ImportError:
    frappe = None

if frappe is not None:
    from change_engine.api import endpoints
    from change_engine.guarded_apply import rollback_engine
    from change_engine.guarded_apply.policy_enforcer import policy_catalog

METHOD = "change_engine.api.endpoints."
WORKFLOW_ROLE = "Accounts Manager"


class TestCeSec005LiveHttp(RealBenchTestCase):
    """CE-SEC-001..004 regressions through the live HTTP worker."""

    _tokens: Dict[str, str] = {}

    # ------------------------------------------------------------------ helpers
    @classmethod
    def _token_user(cls, label: str, role: str) -> str:
        if label in cls._tokens:
            return cls._tokens[label]
        email = f"ce005-{label}-{cls._run_tag}@example.invalid"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": f"CE005 {label}",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        api_key = frappe.generate_hash(length=15)
        api_secret = frappe.generate_hash(length=15)
        user.api_key = api_key
        user.api_secret = api_secret
        user.save(ignore_permissions=True)
        frappe.db.commit()  # the HTTP worker is another process
        cls._tokens[label] = f"token {api_key}:{api_secret}"
        return cls._tokens[label]

    def _rpc(
        self, method: str, auth: Optional[str], *, with_internal_token: bool = True, **kwargs: Any
    ) -> Tuple[int, Dict[str, Any]]:
        """Send an adapter RPC with the gateway credential unless testing ingress denial."""
        port = os.environ.get("ENGINE_PORT", "8000")
        headers = {"Host": self._site, "Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers["Authorization"] = auth
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/method/{method}",
            data=json.dumps(kwargs).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        if with_internal_token:
            req.add_unredirected_header("X-Internal-Token", os.environ["ENGINE_INTERNAL_TOKEN"])
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            body = err.read() or b"{}"
            try:
                return err.code, json.loads(body)
            except ValueError:
                return err.code, {"raw": body.decode("utf-8", "replace")[:500]}

    def _staff(self) -> str:
        return self._token_user("staff", "Sales User")

    def _admin(self) -> str:
        return self._token_user("sysmgr", "System Manager")

    def _assert_unauthorized(self, method: str, **kwargs: Any) -> Dict[str, Any]:
        for supplied in ({}, {"caller_roles": ["System Manager"]}, {"user_roles": ["System Manager"]}):
            status, body = self._rpc(METHOD + method, self._staff(), **kwargs, **supplied)
            self.assertEqual(status, 200, body)
            out = body["message"]
            self.assertEqual(out.get("disposition"), "UNAUTHORIZED_ROLE", out)
            self.assertIs(out["success"], False, out)
            # The roles the decision used are from the authenticated session.
            used = re.search(r"(?:Found: |User roles )(\[[^\]]*\])", out.get("reason", ""))
            self.assertIsNotNone(used, out)
            self.assertIn("Sales User", used.group(1))
            self.assertNotIn("System Manager", used.group(1))
        return out

    # ------------------------------------------------------------------ CE-SEC-001 / 002 over HTTP
    def test_adapter_method_requires_the_internal_token(self) -> None:
        status, body = self._rpc(METHOD + "get_runtime_policies", self._admin(), with_internal_token=False)
        self.assertEqual(status, 404, body)
        self.assertEqual(body, {"raw": "Not Found"})

    def test_01_token_auth_positive_control(self) -> None:
        status, body = self._rpc(METHOD + "get_runtime_policies", self._admin())
        self.assertEqual(status, 200, body)
        status, body = self._rpc(METHOD + "revert_configuration_change", self._admin(), deployment_id="dep_ce005_none")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["message"]["disposition"], "DEPLOYMENT_NOT_FOUND", body)

    def test_02_staff_cannot_apply_or_revert_over_http(self) -> None:
        tag = self._run_tag
        self._assert_unauthorized(
            "apply_configuration_change",
            doctype="Customer",
            field_def={"fieldname": f"custom_ce005_http_{tag}", "fieldtype": "Data", "label": "CE005 field"},
        )
        self._assert_unauthorized(
            "apply_property_setter_change",
            doctype="Customer",
            fieldname="customer_name",
            property_name="bold",
            value="1",
            property_type="Check",
        )
        self._assert_unauthorized(
            "apply_workflow_change",
            doctype="ToDo",
            workflow_def={"workflow_name": f"CE005 HTTP {tag}", "document_type": "ToDo", "states": [], "transitions": []},
        )
        self._assert_unauthorized(
            "apply_report_change",
            doctype="ToDo",
            report_def={"report_name": f"CE005 HTTP {tag}", "ref_doctype": "ToDo", "columns": []},
        )
        out = self._assert_unauthorized("revert_configuration_change", deployment_id="dep_ce005_none")
        self.assertEqual(out["status"], "REJECTED")
        # Nothing was written by the refused calls.
        self.assertFalse(frappe.db.exists("Custom Field", {"dt": "Customer", "fieldname": f"custom_ce005_http_{tag}"}))

    def test_03_staff_proposal_reports_missing_workflow_role(self) -> None:
        # The proposal validator warns when a workflow refers to a role the caller lacks.
        workflow = {
            "intent": "create_workflow",
            "workflow_def": {
                "workflow_name": f"CE005 Propose {self._run_tag}",
                "document_type": "ToDo",
                "states": [
                    {"state": "Open", "doc_status": 0, "allow_edit": WORKFLOW_ROLE},
                    {"state": "Closed", "doc_status": 0, "allow_edit": WORKFLOW_ROLE},
                ],
                "transitions": [{"state": "Open", "action": "Close", "next_state": "Closed", "allowed": WORKFLOW_ROLE}],
            },
        }
        status, body = self._rpc(
            METHOD + "propose_configuration_change",
            self._staff(),
            doctype="ToDo",
            proposal_payload=workflow,
        )
        self.assertEqual(status, 200, body)
        warnings = body["message"]["validation"]["warnings"]
        self.assertTrue(any(WORKFLOW_ROLE in w for w in warnings), warnings)

    # ------------------------------------------------------------------ CE-SEC-003 non-admin
    def _policy(self, suffix: str) -> Dict[str, Any]:
        return {
            "policy_id": f"POL_CE005_{suffix}_{self._run_tag}",
            "doctype": "ToDo",
            "policy_type": "INVARIANT_GUARD",
            "condition_expr": f"description == 'CE005_{suffix}'",
            "error_message": "CE005 non-admin probe",
        }

    def test_04_non_admin_cannot_register_or_unregister_policy(self) -> None:
        existing = self._policy("EXISTING")
        status, body = self._rpc(METHOD + "register_runtime_policy", self._admin(), policy_data=existing)
        self.assertEqual(status, 200)
        self.assertEqual(body["message"]["action"], "CREATED")
        staff_email = f"ce005-staff-{self._run_tag}@example.invalid"
        self._staff()
        try:
            # In process, as a real non-admin session, without caller_roles.
            frappe.set_user(staff_email)
            with self.assertRaisesRegex(PermissionError, "admin permission required"):
                endpoints.register_runtime_policy(self._policy("NEW"))
            with self.assertRaisesRegex(PermissionError, "admin permission required"):
                endpoints.unregister_runtime_policy(existing["policy_id"], doctype="ToDo")
            frappe.set_user("Administrator")

            # Over HTTP, as the same non-admin user, without caller_roles.
            status, body = self._rpc(METHOD + "register_runtime_policy", self._staff(), policy_data=self._policy("HTTP"))
            self.assertNotEqual(status, 200, body)
            self.assertEqual(body.get("exc_type"), "PermissionError")
            self.assertIn("admin permission required", json.dumps(body))
            status, body = self._rpc(
                METHOD + "unregister_runtime_policy", self._staff(), policy_id=existing["policy_id"], doctype="ToDo"
            )
            self.assertNotEqual(status, 200, body)
            self.assertEqual(body.get("exc_type"), "PermissionError")
            self.assertIn("admin permission required", json.dumps(body))

            # The existing policy is untouched and the refused ones were never stored.
            frappe.db.rollback()  # start a fresh read after the HTTP transactions
            ids = {p["policy_id"] for p in endpoints.get_runtime_policies(doctype="ToDo")}
            self.assertIn(existing["policy_id"], ids)
            self.assertNotIn(self._policy("NEW")["policy_id"], ids)
            self.assertNotIn(self._policy("HTTP")["policy_id"], ids)
            revisions = endpoints.get_policy_revisions(existing["policy_id"])
            self.assertEqual([row["revision"] for row in revisions], [1])
            status, body = self._rpc(
                METHOD + "unregister_runtime_policy", self._admin(), policy_id=existing["policy_id"], doctype="ToDo"
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["message"]["success"])
        finally:
            frappe.set_user("Administrator")
            endpoints.unregister_runtime_policy(existing["policy_id"], doctype="ToDo")
            frappe.db.commit()

    def test_05_policy_update_cross_worker_and_site_scoping(self) -> None:
        v1 = self._policy("V1")
        v2 = dict(v1, condition_expr="description == 'CE005_V2'")
        other = self._policy("OTHERSITE")
        try:
            endpoints.register_runtime_policy(v1)
            endpoints.register_runtime_policy(v2)  # revision 2 replaces revision 1
            endpoints.register_runtime_policy(other)
            # Move one policy to another site's rows: this site must no longer enforce it.
            frappe.db.sql(
                "UPDATE `tabChange Engine Policy` SET site_id = %s WHERE policy_id = %s AND site_id = %s",
                ("other-tenant.localhost", other["policy_id"], self._site),
            )
            frappe.db.commit()
            policy_catalog.reset()

            # The HTTP worker reads revision 2 from MariaDB through the policy evaluation RPC.
            for description, allowed in (("CE005_V2", False), ("CE005_V1", True), ("CE005_OTHERSITE", True)):
                with self.subTest(description=description):
                    status, body = self._rpc(
                        METHOD + "evaluate_document_policies", self._admin(),
                        doctype="ToDo", doc={"description": description},
                    )
                    self.assertEqual(status, 200, body)
                    self.assertIs(body["message"]["allowed"], allowed, body)
                    self.assertEqual(body["message"]["violated_policies"], [] if allowed else [v1["policy_id"]])
        finally:
            frappe.db.sql(
                "DELETE FROM `tabChange Engine Policy` WHERE site_id = %s AND policy_id = %s",
                ("other-tenant.localhost", other["policy_id"]),
            )
            frappe.db.commit()
            endpoints.unregister_runtime_policy(v1["policy_id"], doctype="ToDo")
            frappe.db.commit()

    # ------------------------------------------------------------------ CE-SEC-002 holes (fixed)
    def test_06_rollback_role_lookup_fails_closed(self) -> None:
        orig = rollback_engine.frappe.get_roles
        try:
            def _broken(_user=None):
                raise RuntimeError("simulated role lookup outage")

            rollback_engine.frappe.get_roles = _broken
            out = rollback_engine.execute_rollback("dep_ce005_none", caller_roles=None)
            self.assertEqual(out["disposition"], "UNAUTHORIZED_ROLE", out)
        finally:
            rollback_engine.frappe.get_roles = orig

    def test_07_site_context_without_session_user_is_denied(self) -> None:
        session = frappe.local.session
        try:
            frappe.local.session = frappe._dict(user=None)
            self.assertEqual(endpoints._resolve_caller_roles({}), [])
            out = endpoints.apply_configuration_change(
                doctype="Customer",
                field_def={"fieldname": f"custom_ce005_nouser_{self._run_tag}", "fieldtype": "Data", "label": "No user"},
            )
            self.assertEqual(out["disposition"], "UNAUTHORIZED_ROLE", out)
            self.assertEqual(rollback_engine.execute_rollback("dep_ce005_none")["disposition"], "UNAUTHORIZED_ROLE")
        finally:
            frappe.local.session = session

    # ------------------------------------------------------------------ CE-SEC-004
    def test_08_no_llm_endpoint_or_client_key_parameter(self) -> None:
        engine_fns = [fn for fn in frappe.whitelisted if fn.__module__.startswith("change_engine.")]
        self.assertIn(endpoints.register_runtime_policy, engine_fns)
        for fn in engine_fns:
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(params & {"api_key", "base_url", "llm_api_key", "llm_base_url"}, fn.__qualname__)

    def test_09_submit_and_update_after_submit_hooks(self) -> None:
        """Each hook must reject its own stage and permit the valid transition."""
        from change_engine.guarded_apply.policy_enforcer import RuntimePolicyViolation

        dt = f"CE005 Record {self._run_tag}"
        frappe.get_doc({
            "doctype": "DocType", "name": dt, "module": "Custom", "custom": 1, "is_submittable": 1,
            "fields": [{"fieldname": "memo", "fieldtype": "Data", "label": "Memo", "allow_on_submit": 1}],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1}],
        }).insert()
        doc = frappe.get_doc({"doctype": dt, "memo": "draft"}).insert()
        for stage in ("submit", "update_after_submit"):
            policy = dict(self._policy(stage), doctype=dt, stage=stage, condition_expr="memo == 'hold'")
            endpoints.register_runtime_policy(policy)
            frappe.db.commit()
            try:
                doc.memo = "hold"
                with self.assertRaisesRegex(RuntimePolicyViolation, re.escape(f"[{policy['policy_id']}]")):
                    if stage == "submit":
                        doc.submit()
                    else:
                        doc.save()
                frappe.db.rollback()
                doc.reload()
                self.assertEqual(doc.memo, "draft" if stage == "submit" else "released")
                doc.memo = "released" if stage == "submit" else "updated"
                if stage == "submit":
                    doc.submit()
                else:
                    doc.save()
                self.assertEqual(doc.reload().docstatus, 1)
            finally:
                endpoints.unregister_runtime_policy(policy["policy_id"], doctype=dt)
                frappe.db.commit()


if __name__ == "__main__":
    import unittest

    unittest.main()
