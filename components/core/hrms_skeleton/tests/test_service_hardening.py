"""Regressions for the cross-model review of ERP-010 (PR #201): applicant identity, live context,
designated approver, atomic keyed upsert and exact decimals."""

from __future__ import annotations

import decimal
import threading
import unittest

from components.core.hrms_skeleton import HrmsError, HrmsService
from components.core.hrms_skeleton.access import DuplicateKeyError
from components.core.hrms_skeleton.memory import InMemoryStore, StaticSession
from components.core.hrms_skeleton.specs import DAYS, MONEY, SPECS
from components.core.hrms_skeleton.validation import canonical_decimal, normalise_record, normalise_value, parse_decimal

from .test_service import APPLICATION, CO, EMP, T, make, refused, seed_employee

LINA, BOSS = "lina@example.invalid", "boss@example.invalid"
APP_KEY = ("Leave Application", "LEA-00001")


class ApplicantIdentityTests(unittest.TestCase):
    """Finding 1: a mutable Employee.user_id must not defeat self-approval protection."""

    def setUp(self):
        self.hr, self.store, _ = make()
        seed_employee(self.hr)
        # Lina holds HR Manager as well and files her own request.
        self.lina, _, self.lina_session = make(roles=("HR Manager",), user=LINA, store=self.store)
        self.lina.upsert("Leave Application", APPLICATION)

    def test_the_applicant_principal_is_captured_when_the_application_is_filed(self):
        self.assertEqual(self.store.applicant_identities[APP_KEY], LINA)
        self.assertNotIn("applicant_user", self.store.rows["Leave Application"]["LEA-00001"])  # not a payload column

    def test_the_applicant_cannot_rebind_her_own_employee_record_then_approve(self):
        refused(self, "identity_binding_protected", self.lina.upsert, "Employee", {**EMP, "user_id": "someone@example.invalid"})
        self.assertEqual(self.store.rows["Employee"]["EMP-00001"]["user_id"], LINA)
        refused(self, "self_approval_forbidden", self.lina.decide_leave_application, APPLICATION, "approve")
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_no_caller_can_change_an_existing_link_through_upsert(self):
        refused(self, "identity_binding_protected", self.hr.upsert, "Employee", {**EMP, "user_id": "other@example.invalid"})
        self.assertEqual(self.hr.upsert("Employee", EMP).action, "unchanged")  # re-applying the same link is fine
        self.assertEqual(self.store.rows["Employee"]["EMP-00001"]["user_id"], LINA)

    def test_rebinding_behind_the_services_back_still_cannot_unlock_a_self_decision(self):
        # The employee record is edited directly (another path) after the application was filed.
        self.store.rows["Employee"]["EMP-00001"]["user_id"] = "someone@example.invalid"
        refused(self, "self_approval_forbidden", self.lina.decide_leave_application, APPLICATION, "approve")
        # Nobody else may decide on an identity that no longer agrees with the filed one.
        boss, _, _ = make(roles=("HR Manager",), user=BOSS, store=self.store)
        refused(self, "applicant_identity_unresolved", boss.decide_leave_application, APPLICATION, "approve")
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_unresolved_applicant_identity_fails_closed(self):
        boss, _, _ = make(roles=("HR Manager",), user=BOSS, store=self.store)
        for bad in (None, "", "   ", 5, ["lina@example.invalid"], {"id": LINA}):
            self.store.rows["Employee"]["EMP-00001"]["user_id"] = bad
            refused(self, "applicant_identity_unresolved", boss.decide_leave_application, APPLICATION, "approve")
        del self.store.rows["Employee"]["EMP-00001"]["user_id"]
        refused(self, "applicant_identity_unresolved", boss.decide_leave_application, APPLICATION, "reject")
        self.store.rows["Employee"]["EMP-00001"]["user_id"] = LINA
        for bad in (None, "", 5):
            self.store.applicant_identities[APP_KEY] = bad
            refused(self, "applicant_identity_unresolved", boss.decide_leave_application, APPLICATION, "approve")
        del self.store.applicant_identities[APP_KEY]  # filed before this guard existed
        refused(self, "applicant_identity_unresolved", boss.decide_leave_application, APPLICATION, "approve")
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_an_application_for_an_unlinked_employee_is_not_accepted(self):
        for bad in (None, "", 5):
            self.store.rows["Employee"]["EMP-00001"]["user_id"] = bad
            refused(self, "applicant_identity_unresolved", self.hr.upsert, "Leave Application",
                    {**APPLICATION, "to_date": "2026-03-09"})
        self.assertEqual(len(self.store.rows["Leave Application"]), 1)

    def test_a_caller_cannot_link_their_own_account_to_an_employee(self):
        refused(self, "identity_binding_protected", self.hr.upsert, "Employee",
                {**EMP, "employee_number": "E-200", "user_id": "HR@Example.Invalid"})
        self.hr.upsert("Employee", {**EMP, "employee_number": "E-201", "user_id": "new@example.invalid"})
        self.assertEqual(len(self.store.rows["Employee"]), 2)

    def test_first_link_of_an_unlinked_employee_is_allowed_for_a_different_account(self):
        self.store.rows["Employee"]["EMP-00001"]["user_id"] = None
        self.assertEqual(self.hr.upsert("Employee", EMP).action, "updated")
        self.assertEqual(self.store.rows["Employee"]["EMP-00001"]["user_id"], LINA)

    def test_the_filed_principal_cannot_be_supplied_or_changed_by_a_caller(self):
        refused(self, "caller_identity_not_accepted", self.hr.upsert, "Leave Application",
                {**APPLICATION, "to_date": "2026-03-09", "applicant_user": BOSS})
        refused(self, "caller_identity_not_accepted", self.lina.upsert, "Leave Application",
                {**APPLICATION, "applicant_user": BOSS})
        for field in ("applicant_user", "custom_applicant_user"):
            refused(self, "caller_identity_not_accepted", self.lina.upsert, "Leave Application",
                    {**APPLICATION, field: BOSS})
        self.assertEqual(self.store.applicant_identities[APP_KEY], LINA)

    def test_the_filed_principal_is_recorded_once_and_never_overwritten(self):
        with self.assertRaises(ValueError):
            self.store.record_applicant_identity("Leave Application", "LEA-00001", BOSS)
        self.assertEqual(self.store.applicant_identities[APP_KEY], LINA)

    def test_an_independent_hr_manager_can_decide_and_the_applicant_still_cannot(self):
        boss, _, _ = make(roles=("HR Manager",), user=BOSS, store=self.store)
        refused(self, "self_approval_forbidden", self.lina.decide_leave_application, APPLICATION, "approve")
        self.assertEqual(boss.decide_leave_application(APPLICATION, "approve").action, "approved")


class LiveContextTests(unittest.TestCase):
    """Finding 2: identity, tenants and company authorisation are re-read on every operation."""

    def setUp(self):
        self.svc, self.store, self.session = make(roles=("HR Manager",), user=BOSS)
        seed_employee(self.svc)
        self.svc.upsert("Leave Application", APPLICATION)

    def test_switching_the_caller_from_boss_to_applicant_refuses_the_decision(self):
        self.session.user = LINA  # the same instance now answers for the applicant
        refused(self, "session_invalid", self.svc.decide_leave_application, APPLICATION, "approve")
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_switching_the_caller_refuses_every_operation(self):
        self.session.user = "other@example.invalid"
        refused(self, "session_invalid", self.svc.upsert, "Branch", {"branch": "HQ"})
        refused(self, "session_invalid", self.svc.apply_configuration, [{"doctype": "Branch", "values": {"branch": "HQ"}}])
        refused(self, "session_invalid", self.svc.decide_leave_application, APPLICATION, "reject")
        self.assertNotIn("Branch", self.store.rows)

    def test_a_signed_out_caller_is_refused(self):
        for gone in ("Guest", "", None):
            self.session.user = gone
            refused(self, "session_invalid", self.svc.upsert, "Branch", {"branch": "HQ"})

    def test_session_tenant_switch_is_refused(self):
        self.session.tenant = "tenant-b"
        refused(self, "tenant_mismatch", self.svc.upsert, "Branch", {"branch": "HQ"})
        refused(self, "tenant_mismatch", self.svc.decide_leave_application, APPLICATION, "approve")
        self.assertNotIn("Branch", self.store.rows)

    def test_store_tenant_switch_is_refused(self):
        self.store.tenant = "tenant-b"
        refused(self, "tenant_mismatch", self.svc.upsert, "Branch", {"branch": "HQ"})
        refused(self, "tenant_mismatch", self.svc.decide_leave_application, APPLICATION, "approve")
        self.assertNotIn("Branch", self.store.rows)

    def test_revoked_company_authorisation_is_refused(self):
        self.session.revoke_company(CO)
        refused(self, "company_not_permitted", self.svc.upsert, "Branch", {"branch": "HQ"})
        refused(self, "company_not_permitted", self.svc.decide_leave_application, APPLICATION, "approve")
        self.assertNotIn("Branch", self.store.rows)

    def test_roles_are_read_live_for_each_operation(self):
        self.session._roles = frozenset({"Employee"})
        refused(self, "role_not_permitted", self.svc.upsert, "Branch", {"branch": "HQ"})

    def test_drift_during_a_long_apply_stops_the_rest_of_the_run(self):
        session = self.session

        class Revoking(InMemoryStore):
            def insert(self, doctype, values):
                created = super().insert(doctype, values)
                session.revoke_company(CO)  # access withdrawn right after the first write
                return created

        store = Revoking(T)
        svc = HrmsService(session, store, tenant=T, company=CO)
        session._companies = frozenset({CO})
        refused(self, "company_not_permitted", svc.apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}}, {"doctype": "Designation", "values": {"designation_name": "Rep"}}])
        self.assertEqual(store.writes, 1)

    def test_a_role_withdrawn_mid_run_stops_the_rest_of_the_run(self):
        session = self.session

        class Demoting(InMemoryStore):
            def insert(self, doctype, values):
                created = super().insert(doctype, values)
                session._roles = frozenset({"Employee"})
                return created

        store = Demoting(T)
        svc = HrmsService(session, store, tenant=T, company=CO)
        refused(self, "role_not_permitted", svc.apply_configuration, [
            {"doctype": "Branch", "values": {"branch": "HQ"}}, {"doctype": "Designation", "values": {"designation_name": "Rep"}}])
        self.assertEqual(store.writes, 1)


class DesignatedApproverTests(unittest.TestCase):
    """Finding 3: a non-admin Leave Approver must be the named approver; an absent one grants nothing."""

    def setUp(self):
        self.hr, self.store, _ = make()
        seed_employee(self.hr)

    def decide(self, roles, user, decision="approve"):
        svc, _, _ = make(roles=roles, user=user, store=self.store)
        return svc.decide_leave_application(APPLICATION, decision)

    def test_unrelated_leave_approver_is_denied_when_no_approver_is_designated(self):
        self.hr.upsert("Leave Application", APPLICATION)
        refused(self, "not_designated_approver", self.decide, ("Leave Approver",), "stranger@example.invalid")
        self.assertEqual(self.store.rows["Leave Application"]["LEA-00001"]["status"], "Open")

    def test_empty_blank_or_malformed_designation_denies_a_leave_approver(self):
        self.hr.upsert("Leave Application", APPLICATION)
        for bad in (None, "", "   ", 5, ["boss@example.invalid"]):
            self.store.rows["Leave Application"]["LEA-00001"]["leave_approver"] = bad
            refused(self, "not_designated_approver", self.decide, ("Leave Approver",), BOSS)

    def test_the_named_approver_and_the_administrators_still_decide(self):
        self.hr.upsert("Leave Application", {**APPLICATION, "leave_approver": "Boss@Example.Invalid"})
        refused(self, "not_designated_approver", self.decide, ("Leave Approver",), "stranger@example.invalid")
        self.assertEqual(self.decide(("Leave Approver",), BOSS).action, "approved")
        # administrators need no designation
        self.store.rows["Leave Application"]["LEA-00001"].update(status="Open", leave_approver=None)
        self.assertEqual(self.decide(("HR Manager",), "admin@example.invalid", "reject").action, "rejected")


class AtomicUpsertTests(unittest.TestCase):
    """Finding 4: concurrent upserts of one key produce one record, never two creates."""

    class Racing(InMemoryStore):
        """Makes both writers finish their lookup before either inserts, if nothing serialises them."""

        def __init__(self, tenant, parties):
            super().__init__(tenant)
            self.barrier = threading.Barrier(parties)

        def find(self, doctype, filters):
            rows = super().find(doctype, filters)
            try:
                self.barrier.wait(timeout=0.3)
            except threading.BrokenBarrierError:
                pass  # the other writer is held back by the lock, as intended
            return rows

    def run_pair(self, doctype, payload):
        store = self.Racing(T, 2)
        services = [make(store=store)[0] for _ in range(2)]
        results, errors = [], []

        def work(svc):
            try:
                results.append(svc.upsert(doctype, payload))
            except Exception as error:  # noqa: BLE001 - the test reports whatever happened
                errors.append(error)

        threads = [threading.Thread(target=work, args=(svc,)) for svc in services]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        return store, results, errors

    def test_two_simultaneous_upserts_make_one_record(self):
        payload = {"title": "Standard", "leave_policy_details": [{"leave_type": "Annual", "annual_allocation": "21"}]}
        store, results, errors = self.run_pair("Leave Policy", payload)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(r.action for r in results), ["created", "unchanged"])
        self.assertEqual(len(store.rows["Leave Policy"]), 1)
        self.assertEqual(len({r.name for r in results}), 1)
        again = make(store=store)[0].upsert("Leave Policy", payload)  # a retry is not ambiguous
        self.assertEqual(again.action, "unchanged")

    def test_two_simultaneous_upserts_of_a_company_keyed_record_make_one_record(self):
        store, results, errors = self.run_pair("Department", {"department_name": "Sales"})
        self.assertEqual((errors, sorted(r.action for r in results)), ([], ["created", "unchanged"]))
        self.assertEqual(len(store.rows["Department"]), 1)

    def test_different_keys_do_not_block_each_other(self):
        store = InMemoryStore(T)
        svc = make(store=store)[0]
        with store.key_lock("Branch", ("", "HQ")):
            self.assertEqual(svc.upsert("Branch", {"branch": "Other"}).action, "created")

    def test_the_lock_is_released_after_a_refusal(self):
        svc, store, _ = make(permissions={"Branch": []})
        refused(self, "permission_denied", svc.upsert, "Branch", {"branch": "HQ"})
        self.assertTrue(store._key_locks[("Branch", "", "HQ")].acquire(blocking=False))

    def test_a_lock_that_cannot_be_taken_refuses_the_write(self):
        class Broken(InMemoryStore):
            def key_lock(self, doctype, scope):
                raise RuntimeError("no lock available")

        svc = make(store=Broken(T))[0]
        refused(self, "operation_failed", svc.upsert, "Branch", {"branch": "HQ"})

    def test_a_duplicate_found_by_the_backend_is_retried_as_an_update(self):
        class LosesRace(InMemoryStore):
            lost = False

            def insert(self, doctype, values):
                if not self.lost:
                    self.lost = True
                    super().insert(doctype, values)  # the other writer's record lands first
                    raise DuplicateKeyError()
                return super().insert(doctype, values)

        svc, store, _ = make(store=LosesRace(T))
        result = svc.upsert("Branch", {"branch": "HQ"})
        self.assertEqual((result.action, len(store.rows["Branch"])), ("unchanged", 1))

    def test_a_backend_that_keeps_reporting_duplicates_is_refused(self):
        class Always(InMemoryStore):
            def insert(self, doctype, values):
                raise DuplicateKeyError()

        refused(self, "ambiguous_key", make(store=Always(T))[0].upsert, "Branch", {"branch": "HQ"})


class ExactDecimalTests(unittest.TestCase):
    """Finding 5: validation and serialisation never round under the ambient decimal context."""

    LONG = "0.1200000000000000000000000000000000000000000000000000001"

    def test_long_significand_is_refused_not_rounded_to_a_shorter_value(self):
        for spec_rule in (MONEY, DAYS):
            for value in (self.LONG, decimal.Decimal(self.LONG)):
                with self.assertRaises(HrmsError) as ctx:
                    normalise_value(value, spec_rule, "amount")
                self.assertEqual(ctx.exception.code, "decimal_precision_exceeded")

    def test_default_context_keeps_exact_values_and_trailing_zeros_are_not_extra_places(self):
        self.assertEqual(normalise_value("0.120", MONEY, "m"), "0.12")
        self.assertEqual(normalise_value(decimal.Decimal("12.5000000000000000000000000000000000000000000"), MONEY, "m"), "12.5")
        self.assertEqual(normalise_value(decimal.Decimal("1E+3"), MONEY, "m"), "1000")
        self.assertEqual(normalise_value(decimal.Decimal("-0"), MONEY, "m"), "0")
        self.assertEqual(normalise_value("999999999999", MONEY, "m"), "999999999999")

    def test_altered_ambient_precision_does_not_change_the_result(self):
        for prec in (1, 4, 6):
            with decimal.localcontext() as ctx:
                ctx.prec = prec
                self.assertEqual(normalise_value("1234.56", MONEY, "m"), "1234.56", prec)
                self.assertEqual(normalise_value(decimal.Decimal("1234.56"), MONEY, "m"), "1234.56", prec)
                self.assertEqual(normalise_value("123456789012.34", MONEY, "m"), "123456789012.34", prec)
                self.assertEqual(parse_decimal("1234.56", MONEY, "m"), decimal.Decimal("1234.56"), prec)
                self.assertEqual(canonical_decimal(decimal.Decimal("0.0001234500")), "0.00012345", prec)
                with self.assertRaises(HrmsError) as ctx2:
                    normalise_value("0.123", MONEY, "m")
                self.assertEqual(ctx2.exception.code, "decimal_precision_exceeded")

    def test_records_validate_the_same_under_a_low_precision_context(self):
        with decimal.localcontext() as ctx:
            ctx.prec = 4
            rec = normalise_record(SPECS["Salary Component"],
                                   {"salary_component": "Basic", "type": "Earning", "amount": "1234.56"}, CO)
        self.assertEqual(rec["amount"], "1234.56")

    def test_stored_values_compare_exactly_under_a_low_precision_context(self):
        svc, store, _ = make()
        svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning", "amount": "1234.56"})
        store.rows["Salary Component"]["SAL-00001"]["amount"] = 1234.56  # the engine returns a float
        with decimal.localcontext() as ctx:
            ctx.prec = 4
            self.assertEqual(svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning",
                                                              "amount": "1234.56"}).action, "unchanged")
            self.assertEqual(svc.upsert("Salary Component", {"salary_component": "Basic", "type": "Earning",
                                                              "amount": "1235"}).action, "updated")
        self.assertEqual(store.rows["Salary Component"]["SAL-00001"]["amount"], "1235")

    def test_canonical_form_edge_cases(self):
        D = decimal.Decimal
        for raw, want in (("0", "0"), ("0.00", "0"), ("100", "100"), ("100.50", "100.5"), ("0.05", "0.05"),
                          ("0.5", "0.5"), ("10.000", "10"), ("-1.20", "-1.2"), ("1E-2", "0.01"), ("12E+2", "1200")):
            self.assertEqual(canonical_decimal(D(raw)), want, raw)
        with self.assertRaises(ValueError):
            canonical_decimal(D("NaN"))


if __name__ == "__main__":
    unittest.main()
