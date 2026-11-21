"""Tenant and company scope, backend roles, native permissions, keyed idempotency and leave
decisions for core.hrms_skeleton (ERP-010)."""

from __future__ import annotations

import copy
import unittest

from components.core.hrms_skeleton import HrmsError, HrmsService
from components.core.hrms_skeleton.memory import InMemoryStore, StaticSession

T, CO = "tenant-a", "Acme Trading"
EMP = {"employee_number": "E-100", "first_name": "Lina", "gender": "Female", "date_of_birth": "1990-04-02",
       "date_of_joining": "2026-01-05", "user_id": "lina@example.invalid"}
APPLICATION = {"employee": "EMP-00001", "leave_type": "Annual", "from_date": "2026-03-01", "to_date": "2026-03-05"}


def make(roles=("HR Manager",), user="hr@example.invalid", tenant=T, company=CO, store=None, **session_kw):
    store = store if store is not None else InMemoryStore(tenant)
    session = StaticSession(user, roles, tenant, [company], **session_kw)
    return HrmsService(session, store, tenant=tenant, company=company), store, session


def refused(testcase, code, fn, *args, **kwargs):
    with testcase.assertRaises(HrmsError) as ctx:
        fn(*args, **kwargs)
    testcase.assertEqual(ctx.exception.code, code)
    return ctx.exception


def seed_employee(svc):
    return svc.upsert("Employee", EMP)  # becomes EMP-00001 in the in-memory store (first Employee)


class ScopeContextTests(unittest.TestCase):
    def test_tenant_must_match_session_and_store(self):
        store = InMemoryStore("tenant-b")
        session = StaticSession("hr@example.invalid", ["HR Manager"], T, [CO])
        refused(self, "tenant_mismatch", HrmsService, session, store, tenant=T, company=CO)
        refused(self, "tenant_mismatch", HrmsService, session, InMemoryStore(T), tenant="tenant-b", company=CO)
        for bad in ("", "  ", None, 5):
            refused(self, "tenant_mismatch", HrmsService, session, InMemoryStore(T), tenant=bad, company=CO)

    def test_company_required_and_permitted(self):
        session = StaticSession("hr@example.invalid", ["HR Manager"], T, [CO])
        for bad in ("", " ", None):
            refused(self, "company_missing", HrmsService, session, InMemoryStore(T), tenant=T, company=bad)
        refused(self, "company_not_permitted", HrmsService, session, InMemoryStore(T), tenant=T, company="Other Co")

    def test_unauthenticated_session_is_refused(self):
        for user in ("", "Guest", "guest", None):
            session = StaticSession(user, ["System Manager"], T, [CO])
            refused(self, "session_invalid", HrmsService, session, InMemoryStore(T), tenant=T, company=CO)

    def test_session_failures_fail_closed(self):
        class Broken(StaticSession):
            def roles(self):
                raise RuntimeError("lookup failed")

        svc = HrmsService(Broken("hr@example.invalid", [], T, [CO]), InMemoryStore(T), tenant=T, company=CO)
        refused(self, "operation_failed", svc.upsert, "Branch", {"branch": "HQ"})

    def test_payload_company_must_equal_scoped_company(self):
        svc, store, _ = make()
        refused(self, "company_mismatch", svc.upsert, "Employee", {**EMP, "company": "Other Co"})
        self.assertEqual(store.writes, 0)

    def test_a_service_only_touches_its_own_company(self):
        store = InMemoryStore(T)
        a = HrmsService(StaticSession("hr@example.invalid", ["HR Manager"], T, [CO, "Beta Co"]), store, tenant=T, company=CO)
        b = HrmsService(StaticSession("hr@example.invalid", ["HR Manager"], T, [CO, "Beta Co"]), store, tenant=T, company="Beta Co")
        a.upsert("Employee", EMP)
        refused(self, "employee_not_found", b.upsert, "Leave Allocation",
                {"employee": "EMP-00001", "leave_type": "Annual", "from_date": "2026-01-01",
                 "to_date": "2026-12-31", "new_leaves_allocated": "21"})
        result = b.upsert("Employee", EMP)  # same business key in another company is a separate record
        self.assertEqual(result.action, "created")
        self.assertEqual(len(store.rows["Employee"]), 2)

    def test_two_tenants_never_share_records(self):
        svc_a, store_a, _ = make(tenant="tenant-a")
        svc_b, store_b, _ = make(tenant="tenant-b")
        svc_a.upsert("Branch", {"branch": "HQ"})
        self.assertEqual(svc_b.upsert("Branch", {"branch": "HQ"}).action, "created")
        self.assertEqual(len(store_a.rows["Branch"]), 1)
        self.assertEqual(len(store_b.rows["Branch"]), 1)


class ScopeAndIdentityTests(unittest.TestCase):
    def test_out_of_scope_doctypes_refused_before_any_work(self):
        svc, store, _ = make(roles=("System Manager",))
        for name in ("Salary Slip", "Payroll Entry", "Attendance", "Expense Claim", "Gratuity", "Nope", None):
            refused(self, "doctype_not_allowed", svc.upsert, name, {})
        refused(self, "doctype_not_allowed", svc.apply_configuration, [{"doctype": "Salary Slip", "values": {}}])
        self.assertEqual(store.writes, 0)

    def test_roles_cannot_be_supplied_by_the_caller(self):
        svc, store, _ = make(roles=("Employee",))
        refused(self, "caller_identity_not_accepted", svc.upsert, "Salary Component",
                {"salary_component": "Basic", "type": "Earning", "roles": ["System Manager"]})
        refused(self, "role_not_permitted", svc.upsert, "Salary Component",
                {"salary_component": "Basic", "type": "Earning"})
        self.assertEqual(store.writes, 0)


class RoleTests(unittest.TestCase):
    PAYLOADS = {
        "Employee": EMP,
        "Leave Policy": {"title": "Standard", "leave_policy_details": [{"leave_type": "Annual", "annual_allocation": "21"}]},
        "Salary Component": {"salary_component": "Basic", "type": "Earning"},
        "Salary Structure": {"name": "Standard"},
    }

    def test_admin_only_doctypes(self):
        for doctype, payload in self.PAYLOADS.items():
            for roles in (("Employee",), ("HR User",), ("Leave Approver",), ("Sales User", "Accounts Manager"), ()):
                svc, store, _ = make(roles=roles)
                refused(self, "role_not_permitted", svc.upsert, doctype, payload)
                self.assertEqual(store.writes, 0, (doctype, roles))
            for roles in (("HR Manager",), ("System Manager",)):
                svc, _, _ = make(roles=roles)
                self.assertEqual(svc.upsert(doctype, payload).action, "created", (doctype, roles))

    def test_salary_structure_assignment_and_leave_allocation_need_admin(self):
        hr, store, _ = make()
        seed_employee(hr)
        ssa = {"employee": "EMP-00001", "salary_structure": "Standard", "from_date": "2026-01-01", "base": "9000"}
        alloc = {"employee": "EMP-00001", "leave_type": "Annual", "from_date": "2026-01-01",
                 "to_date": "2026-12-31", "new_leaves_allocated": "21"}
        user, _, _ = make(roles=("HR User",), store=store)
        refused(self, "role_not_permitted", user.upsert, "Salary Structure Assignment", ssa)
        refused(self, "role_not_permitted", user.upsert, "Leave Allocation", alloc)
        self.assertEqual(hr.upsert("Salary Structure Assignment", ssa).action, "created")
        self.assertEqual(hr.upsert("Leave Allocation", alloc).action, "created")

    def test_setup_masters_allow_hr_user(self):
        svc, _, _ = make(roles=("HR User",))
        for doctype, payload in {"Department": {"department_name": "Sales"}, "Designation": {"designation_name": "Rep"},
                                 "Branch": {"branch": "HQ"}, "Leave Type": {"leave_type_name": "Annual"},
                                 "Leave Period": {"from_date": "2026-01-01", "to_date": "2026-12-31"}}.items():
            self.assertEqual(svc.upsert(doctype, payload).action, "created", doctype)

    def test_pay_affecting_leave_fields_require_hr_admin(self):
        hr, store, _ = make()
        user, _, _ = make(roles=("HR User",), store=store)
        for field, value, cleared in (
            ("is_lwp", True, False),
            ("is_ppl", True, False),
            ("fraction_of_daily_salary_per_leave", "0.5", "0"),
        ):
            with self.subTest(field=field):
                payload = {"leave_type_name": field, field: value}
                refused(self, "role_not_permitted", user.upsert, "Leave Type", payload)
                created = hr.upsert("Leave Type", payload)
                self.assertEqual(created.action, "created")
                refused(self, "role_not_permitted", user.upsert, "Leave Type", payload)
                refused(self, "role_not_permitted", user.upsert, "Leave Type", {"leave_type_name": field, field: cleared})
                self.assertEqual(
                    user.upsert("Leave Type", {"leave_type_name": field, "max_leaves_allowed": "10"}).action,
                    "updated",
                )
                self.assertEqual(store.rows["Leave Type"][created.name][field], value)

    def test_batch_preflights_pay_affecting_leave_fields_before_writing(self):
        user, store, _ = make(roles=("HR User",))
        refused(self, "role_not_permitted", user.apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}},
            {"doctype": "Leave Type", "values": {"leave_type_name": "Unpaid", "is_lwp": True}},
        ])
        self.assertEqual(store.writes, 0)

    def test_native_permission_and_permlevel_are_also_enforced(self):
        svc, store, _ = make(permissions={"Employee": []})
        refused(self, "permission_denied", svc.upsert, "Employee", EMP)
        svc, store, _ = make(denied={"Salary Component": ["amount"]})
        refused(self, "field_permission_denied", svc.upsert, "Salary Component",
                {"salary_component": "Basic", "type": "Earning", "amount": "100"})
        self.assertEqual(svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning"}).action, "created")
        svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning"})
        refused(self, "field_permission_denied", svc.upsert, "Salary Component",
                {"salary_component": "Basic", "type": "Earning", "amount": "100"})
        self.assertNotIn("amount", store.rows["Salary Component"]["SAL-00001"])


class IdempotencyTests(unittest.TestCase):
    def test_reapplying_never_duplicates_or_rewrites(self):
        svc, store, _ = make()
        payload = {"salary_component": "Basic", "type": "Earning", "amount": "9000.00"}
        first = svc.upsert("Salary Component", payload)
        writes = store.writes
        second = svc.upsert("Salary Component", payload)
        self.assertEqual((first.action, second.action), ("created", "unchanged"))
        self.assertEqual(first.name, second.name)
        self.assertEqual(len(store.rows["Salary Component"]), 1)
        self.assertEqual(store.writes, writes)

    def test_changed_value_updates_only_changed_fields(self):
        svc, store, _ = make()
        svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning", "amount": "9000"})
        result = svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning", "amount": "9500.5"})
        self.assertEqual((result.action, result.changed), ("updated", ("amount",)))
        self.assertEqual(len(store.rows["Salary Component"]), 1)

    def test_engine_typing_does_not_cause_phantom_updates(self):
        svc, store, _ = make()
        svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning", "amount": "9000.00"})
        store.rows["Salary Component"]["SAL-00001"]["amount"] = 9000.0  # the engine returns floats
        self.assertEqual(svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning",
                                                          "amount": "9000"}).action, "unchanged")

    def test_child_rows_idempotent_and_replaced_on_change(self):
        svc, store, _ = make()
        payload = {"name": "Standard", "earnings": [{"salary_component": "Basic", "amount": "9000"}]}
        self.assertEqual(svc.upsert("Salary Structure", payload).action, "created")
        store.rows["Salary Structure"]["Standard"]["earnings"][0].update({"name": "row1", "idx": 1, "amount": 9000.0})
        self.assertEqual(svc.upsert("Salary Structure", payload).action, "unchanged")
        changed = {**payload, "earnings": [{"salary_component": "Basic", "amount": "9100"}]}
        self.assertEqual(svc.upsert("Salary Structure", changed).changed, ("earnings",))

    def test_duplicate_key_in_store_fails_closed(self):
        svc, store, _ = make()
        svc.upsert("Branch", {"branch": "HQ"})
        store.rows["Branch"]["BRA-99999"] = {"name": "BRA-99999", "branch": "HQ"}
        refused(self, "ambiguous_key", svc.upsert, "Branch", {"branch": "HQ"})

    def test_apply_configuration_orders_validates_first_and_is_replayable(self):
        svc, store, _ = make()
        config = [
            {"doctype": "Salary Structure Assignment", "values": {"employee": "EMP-00001", "salary_structure": "Standard",
                                                                    "from_date": "2026-01-01", "base": "9000"}},
            {"doctype": "Employee", "values": EMP},
            {"doctype": "Salary Structure", "values": {"name": "Standard"}},
            {"doctype": "Branch", "values": {"branch": "HQ"}},
        ]
        results = svc.apply_configuration(config)
        self.assertEqual([r.doctype for r in results],
                         ["Branch", "Employee", "Salary Structure", "Salary Structure Assignment"])
        self.assertEqual({r.action for r in results}, {"created"})
        snapshot, writes = copy.deepcopy(store.rows), store.writes
        again = svc.apply_configuration(config)
        self.assertEqual({r.action for r in again}, {"unchanged"})
        self.assertEqual((store.rows, store.writes), (snapshot, writes))

    def test_recovery_after_a_run_cut_short(self):
        svc, store, _ = make()
        svc.upsert("Branch", {"branch": "HQ"})  # the part that applied before the interruption
        results = svc.apply_configuration([
            {"doctype": "Branch", "values": {"branch": "HQ"}}, {"doctype": "Designation", "values": {"designation_name": "Rep"}}])
        self.assertEqual({r.doctype: r.action for r in results}, {"Branch": "unchanged", "Designation": "created"})
        self.assertEqual(sum(len(t) for t in store.rows.values()), 2)

    def test_one_bad_record_means_no_writes(self):
        svc, store, _ = make()
        refused(self, "invalid_decimal", svc.apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}},
            {"doctype": "Salary Component", "values": {"salary_component": "Basic", "type": "Earning", "amount": 1.5}}])
        refused(self, "role_not_permitted", make(roles=("HR User",))[0].apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}},
            {"doctype": "Salary Component", "values": {"salary_component": "Basic", "type": "Earning"}}])
        refused(self, "duplicate_row", svc.apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}}, {"doctype": "Branch", "values": {"branch": "HQ"}}])
        self.assertEqual(store.writes, 0)

    def test_apply_configuration_rejects_malformed_input(self):
        svc, _, _ = make()
        refused(self, "payload_invalid", svc.apply_configuration, "Branch")
        refused(self, "payload_invalid", svc.apply_configuration, [{"doctype": "Branch"}])
        refused(self, "payload_invalid", svc.apply_configuration, [{"doctype": "Branch", "values": {}, "x": 1}])
        refused(self, "payload_invalid", svc.apply_configuration, ["Branch"])


class LeaveApplicationTests(unittest.TestCase):
    def setUp(self):
        self.hr, self.store, _ = make()
        seed_employee(self.hr)  # EMP-00001, user lina@example.invalid

    def apply(self, roles=("Employee",), user="lina@example.invalid", **extra):
        svc, _, _ = make(roles=roles, user=user, store=self.store)
        return svc, svc.upsert("Leave Application", {**APPLICATION, **extra})

    def test_employee_can_file_only_for_themselves(self):
        svc, result = self.apply()
        self.assertEqual(result.action, "created")
        self.assertEqual(self.store.rows["Leave Application"][result.name]["status"], "Open")
        other, _, _ = make(roles=("Employee",), user="someone@example.invalid", store=self.store)
        refused(self, "role_not_permitted", other.upsert, "Leave Application", {**APPLICATION, "to_date": "2026-03-06"})

    def test_status_cannot_be_set_through_upsert(self):
        refused(self, "field_not_allowed", self.hr.upsert, "Leave Application", {**APPLICATION, "status": "Approved"})

    def test_self_service_cannot_distinguish_missing_employee_from_someone_elses(self):
        svc, _, _ = make(roles=("Employee",), user="someone@example.invalid", store=self.store)
        for employee in ("EMP-00001", "missing"):
            with self.subTest(employee=employee):
                error = refused(self, "role_not_permitted", svc.upsert,
                                "Leave Application", {**APPLICATION, "employee": employee})
                self.assertEqual((error.field, error.doctype), (None, "Leave Application"))
        refused(self, "employee_not_found", self.hr.upsert, "Leave Application", {**APPLICATION, "employee": "missing"})

    def test_edits_only_while_open(self):
        svc, result = self.apply()
        self.assertEqual(svc.upsert("Leave Application", {**APPLICATION, "description": "Family"}).action, "updated")
        self.store.rows["Leave Application"][result.name]["status"] = "Approved"
        refused(self, "leave_application_not_open", svc.upsert, "Leave Application", {**APPLICATION, "description": "x"})

    def decide(self, decision="approve", roles=("HR Manager",), user="boss@example.invalid"):
        svc, _, _ = make(roles=roles, user=user, store=self.store)
        return svc.decide_leave_application(APPLICATION, decision)

    def test_authorised_approver_can_approve_and_reject(self):
        self.apply()
        self.assertEqual(self.decide("approve").action, "approved")
        self.assertEqual(self.decide("approve").action, "unchanged")
        refused(self, "leave_application_already_decided", self.decide, "reject")
        self.hr.upsert("Leave Application", {**APPLICATION, "to_date": "2026-03-06", "leave_approver": "boss@example.invalid"})
        key = {**APPLICATION, "to_date": "2026-03-06"}
        svc, _, _ = make(roles=("Leave Approver",), user="boss@example.invalid", store=self.store)
        self.assertEqual(svc.decide_leave_application(key, "reject").action, "rejected")

    def test_decision_needs_an_approving_role(self):
        self.apply()
        for roles in (("Employee",), ("HR User",), ("Sales User",), ()):
            refused(self, "role_not_permitted", self.decide, "approve", roles)
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_self_approval_forbidden_for_every_approving_role(self):
        self.apply()
        for roles in (("HR Manager",), ("System Manager",), ("Leave Approver",), ("HR Manager", "System Manager", "Leave Approver")):
            for decision in ("approve", "reject"):
                for user in ("lina@example.invalid", "LINA@Example.Invalid"):
                    refused(self, "self_approval_forbidden", self.decide, decision, roles, user)
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_self_approval_is_refused_even_after_another_person_decided(self):
        self.apply()
        self.decide("approve")
        refused(self, "self_approval_forbidden", self.decide, "approve", ("HR Manager",), "lina@example.invalid")

    def test_designated_approver_is_binding_for_the_approver_role_only(self):
        self.apply(leave_approver="boss@example.invalid")
        refused(self, "not_designated_approver", self.decide, "approve", ("Leave Approver",), "other@example.invalid")
        self.assertEqual(self.decide("approve", ("HR Manager",), "other@example.invalid").action, "approved")

    def test_invalid_decisions_and_missing_records(self):
        self.apply()
        refused(self, "decision_invalid", self.decide, "Approve")
        refused(self, "decision_invalid", self.decide, None)
        svc, _, _ = make(store=self.store, user="boss@example.invalid")
        refused(self, "record_not_found", svc.decide_leave_application, {**APPLICATION, "to_date": "2026-04-01"}, "approve")
        refused(self, "payload_invalid", svc.decide_leave_application, {**APPLICATION, "description": "x"}, "approve")
        refused(self, "caller_identity_not_accepted", svc.decide_leave_application, {**APPLICATION, "approver": "me"}, "approve")

    def test_decision_does_not_cross_companies_or_tenants(self):
        self.apply()
        other_store = InMemoryStore("tenant-b")
        svc, _, _ = make(tenant="tenant-b", user="boss@example.invalid", store=other_store)
        refused(self, "record_not_found", svc.decide_leave_application, APPLICATION, "approve")
        other_co, _, _ = make(company="Beta Co", user="boss@example.invalid", store=self.store)
        refused(self, "record_not_found", other_co.decide_leave_application, APPLICATION, "approve")

    def test_unknown_applicant_fails_closed(self):
        self.apply()
        del self.store.rows["Employee"]["EMP-00001"]
        refused(self, "employee_not_found", self.decide, "approve")


if __name__ == "__main__":
    unittest.main()
