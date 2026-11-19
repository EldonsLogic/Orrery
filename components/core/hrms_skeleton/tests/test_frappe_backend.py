"""The engine adapters, against a fake engine module (not yet run on the real bench; Q-280).

The fake follows the pinned engine's metadata rules, so it cannot hide a schema mismatch:
`get_field("name")` is None (standard column, frappe v15.126.0 Meta), only declared fields exist,
and Employee refuses an insert missing its mandatory fields (ERPNext v15.124.5 employee.json).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from components.core.hrms_skeleton import HrmsError, HrmsService
from components.core.hrms_skeleton.frappe_backend import FrappeSession, FrappeStore
from components.core.hrms_skeleton.specs import (
    APPLICANT_IDENTITY_FIELD, PLATFORM_CUSTOM_FIELDS, SPECS, STANDARD_COLUMNS,
)

# Mandatory fields of the pinned schemas that the caller must supply (the engine defaults the rest,
# for example `status` and `company`). UNVERIFIED against a live bench (Q-280).
PINNED_MANDATORY = {
    "Employee": ("first_name", "gender", "date_of_birth", "date_of_joining"),
    "Salary Structure": ("name",),  # naming rule "Prompt"
}
# Fields that exist on the pinned doctypes beyond the spec's own (set by the engine or the service).
# `applicant_user` is deliberately NOT here: the engine ships no such column, so persistence drops it.
# The captured applicant lives in the platform custom field declared in `PLATFORM_CUSTOM_FIELDS`.
EXTRA_FIELDS = {"Leave Application": {"status", APPLICANT_IDENTITY_FIELD}}


def schema_fields(doctype):
    spec = SPECS[doctype]
    return (set(spec.fields) - STANDARD_COLUMNS) | set(spec.children) | EXTRA_FIELDS.get(doctype, set())


class MandatoryError(Exception):
    pass


class FakeDoc:
    def __init__(self, frappe, data):
        self.frappe, self.data, self.saved = frappe, dict(data), False

    def _persist(self, stored=None):
        """What the pinned engine keeps: valid columns only. A field above the caller's permission
        level is reset: to the stored value on an existing document, to nothing on a new one."""
        doctype, writable = self.data["doctype"], self.frappe.get_meta(self.data["doctype"]).get_permlevel_access("write")
        keep = schema_fields(doctype) | {"doctype", "name"}
        kept = {k: v for k, v in self.data.items() if k in keep and self.frappe.levels.get(k, 0) in writable}
        for k in keep:
            if self.frappe.levels.get(k, 0) not in writable and stored and k in stored:
                kept[k] = stored[k]
        self.data = kept

    def insert(self):
        missing = [f for f in PINNED_MANDATORY.get(self.data["doctype"], ()) if not self.data.get(f)]
        if missing:
            raise MandatoryError(missing)
        self.frappe.insert_calls += 1
        self._persist()
        if self.frappe.duplicate_next:
            self.frappe.duplicate_next -= 1
            raise self.frappe.DuplicateEntryError("exists")
        self.data.setdefault("name", f"DOC-{len(self.frappe.docs) + 1}")
        self.frappe.docs[(self.data["doctype"], self.data["name"])] = self.data
        self.frappe.inserted.append(self.data)

    def update(self, values):
        self.data.update(values)

    def save(self):
        self._persist(self.frappe.docs.get((self.data["doctype"], self.data["name"])))
        self.frappe.docs[(self.data["doctype"], self.data["name"])] = self.data
        self.frappe.saved.append(self.data)

    def check_permission(self, ptype):
        if not self.frappe.can_read:
            raise PermissionError(ptype)

    def as_dict(self):
        return dict(self.data)


class FakeMeta:
    def __init__(self, doctype, levels):
        self.doctype, self.levels = doctype, levels

    def get_permlevel_access(self, ptype):
        return [0]

    def get_field(self, name):
        if name not in schema_fields(self.doctype):  # includes "name": a column, not a DocField
            return None
        level = self.levels.get(name, 0)
        return SimpleNamespace(permlevel=level, read_only=1 if level else 0)


class FakeFrappe:
    def __init__(self, user="hr@example.invalid", roles=("HR Manager",), site="tenant-a"):
        self.session = SimpleNamespace(user=user)
        self.local = SimpleNamespace(site=site)
        self.roles, self.docs, self.inserted, self.saved = list(roles), {}, [], []
        self.can_read, self.perms, self.companies, self.restricted = True, True, {"Acme"}, []
        self.levels = {"base": 1, APPLICANT_IDENTITY_FIELD: 2}
        self.conf = SimpleNamespace(db_type="mariadb")
        self.sql_log, self.lock_result, self.commits = [], 1, 0
        self.lock_held, self.reads, self.snapshot = False, [], None
        self.caller_pending, self.committed = [], []  # the enclosing transaction: the caller's, not ours
        self.insert_calls, self.duplicate_next = 0, 0
        self.db = SimpleNamespace(
            exists=lambda dt, name: name in self.companies, sql=self._sql, commit=self._commit,
            rollback=self._rollback, get_value=self._get_value, set_value=self._set_value,
        )

        class DuplicateEntryError(Exception):
            pass

        self.DuplicateEntryError = DuplicateEntryError

    def _sql(self, query, values=None):
        self.sql_log.append((query.split("(")[0].strip(), values))
        self.lock_held = "release" not in query and "unlock" not in query and self.lock_result == 1
        return ((self.lock_result,),)

    def _commit(self):
        self.commits += 1
        self.committed += self.caller_pending
        self.caller_pending = []

    def _rollback(self):
        self.caller_pending = []

    def freeze_snapshot(self):
        """Simulate REPEATABLE-READ: later plain reads see only what existed now."""
        self.snapshot = {k: dict(v) for k, v in self.docs.items()}

    def _visible(self, for_update):
        return self.docs if for_update or self.snapshot is None else self.snapshot

    def _get_value(self, doctype, name, field, for_update=False):
        self.reads.append(("get_value", doctype, bool(for_update), self.lock_held))
        return self.docs[(doctype, name)].get(field)

    def _set_value(self, doctype, name, field, value, update_modified=True):
        if field not in schema_fields(doctype):
            raise KeyError(f"Unknown column {field}")  # the engine rejects a column that does not exist
        self.docs[(doctype, name)][field] = value  # a direct column write: no document permission levels

    def get_roles(self, user):
        return list(self.roles)

    def get_all(self, doctype, filters=None, pluck=None):
        assert doctype == "User Permission"
        return list(self.restricted)

    def has_permission(self, doctype, ptype=None, user=None):
        return self.perms

    def get_meta(self, doctype):
        return FakeMeta(doctype, self.levels)

    def get_list(self, doctype, filters=None, pluck=None, limit_page_length=None, for_update=False):
        self.reads.append(("get_list", doctype, bool(for_update), self.lock_held))
        rows = [d for (dt, _), d in self._visible(for_update).items() if dt == doctype and all(d.get(k) == v for k, v in filters.items())]
        return [r["name"] for r in rows][:limit_page_length]

    def get_doc(self, *args, for_update=False):
        if isinstance(args[0], dict):
            return FakeDoc(self, args[0])
        self.reads.append(("get_doc", args[0], bool(for_update), self.lock_held))
        return FakeDoc(self, self._visible(for_update)[(args[0], args[1])])


class FrappeSessionTests(unittest.TestCase):
    def test_identity_comes_from_the_server_session(self):
        f = FakeFrappe(roles=("HR Manager",))
        s = FrappeSession(f)
        self.assertEqual((s.user, s.tenant, s.roles()), ("hr@example.invalid", "tenant-a", frozenset({"HR Manager"})))

    def test_guest_or_missing_user_is_refused(self):
        for user in ("Guest", "", None):
            with self.assertRaises(HrmsError) as ctx:
                FrappeSession(FakeFrappe(user=user)).user
            self.assertEqual(ctx.exception.code, "session_invalid")

    def test_company_must_exist_and_respect_user_permissions(self):
        f = FakeFrappe()
        s = FrappeSession(f)
        self.assertTrue(s.company_permitted("Acme"))
        self.assertFalse(s.company_permitted("Nope"))
        f.companies, f.restricted = {"Acme", "Beta"}, ["Beta"]
        self.assertFalse(s.company_permitted("Acme"))
        self.assertTrue(s.company_permitted("Beta"))

    def test_permission_and_permlevel(self):
        f = FakeFrappe()
        s = FrappeSession(f)
        self.assertTrue(s.has_permission("Employee", "write"))
        f.perms = False
        self.assertFalse(s.has_permission("Employee", "write"))
        self.assertEqual(s.denied_fields("Employee", ["first_name", "base", "unknown_field"]), ["base", "unknown_field"])


class FrappeStoreTests(unittest.TestCase):
    def test_find_insert_update_use_caller_permissions(self):
        f = FakeFrappe()
        store = FrappeStore(f)
        self.assertEqual(store.tenant, "tenant-a")
        created = store.insert("Branch", {"branch": "HQ"})
        self.assertEqual(store.find("Branch", {"branch": "HQ"}), [created])
        store.update("Branch", created["name"], {"branch": "HQ2"})
        self.assertEqual(f.saved[-1]["branch"], "HQ2")
        f.can_read = False
        with self.assertRaises(PermissionError):
            store.find("Branch", {"branch": "HQ2"})

    def test_service_end_to_end_over_the_adapters(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = HrmsService(FrappeSession(f), FrappeStore(f), tenant="tenant-a", company="Acme")
        data = {"designation_name": "Rep"}
        self.assertEqual(svc.upsert("Designation", data).action, "created")
        self.assertEqual(svc.upsert("Designation", data).action, "unchanged")
        self.assertEqual(len(f.inserted), 1)

    def test_store_errors_become_a_refusal_not_a_pass(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.can_read = False
        svc = HrmsService(FrappeSession(f), FrappeStore(f), tenant="tenant-a", company="Acme")
        svc.upsert("Designation", {"designation_name": "Rep"})  # nothing to read yet, so it inserts
        with self.assertRaises(HrmsError) as ctx:
            svc.upsert("Designation", {"designation_name": "Rep"})
        self.assertEqual(ctx.exception.code, "operation_failed")


EMPLOYEE = {"employee_number": "E-100", "first_name": "Lina", "gender": "Female", "date_of_birth": "1990-04-02",
            "date_of_joining": "2026-01-05", "user_id": "lina@example.invalid"}


def service(f, company="Acme"):
    return HrmsService(FrappeSession(f), FrappeStore(f), tenant="tenant-a", company=company)


def refused(testcase, code, fn, *args, **kwargs):
    with testcase.assertRaises(HrmsError) as ctx:
        fn(*args, **kwargs)
    testcase.assertEqual(ctx.exception.code, code)


class PinnedSchemaTests(unittest.TestCase):
    """Review finding 6: the fake no longer hides standard-schema incompatibilities."""

    def test_fake_metadata_matches_the_pinned_rules(self):
        meta = FakeFrappe().get_meta("Salary Structure")
        self.assertIsNone(meta.get_field("name"))  # frappe v15.126.0: `name` is a column, not a DocField
        self.assertIsNone(meta.get_field("not_a_field"))
        self.assertIsNotNone(meta.get_field("company"))

    def test_standard_name_column_is_writable_with_document_level_access(self):
        s = FrappeSession(FakeFrappe())
        self.assertEqual(s.denied_fields("Salary Structure", ["name", "company", "earnings"]), [])
        self.assertEqual(s.denied_fields("Salary Structure", ["name", "bogus"]), ["bogus"])

    def test_name_is_refused_when_document_level_write_is_missing(self):
        f = FakeFrappe()
        f.get_meta = lambda doctype: SimpleNamespace(get_permlevel_access=lambda ptype: [1], get_field=lambda n: None)
        self.assertEqual(FrappeSession(f).denied_fields("Salary Structure", ["name"]), ["name"])

    def test_salary_structure_with_a_name_is_created_over_the_adapters(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        payload = {"name": "Standard", "earnings": [{"salary_component": "Basic", "amount": "9000"}]}
        self.assertEqual(svc.upsert("Salary Structure", payload).action, "created")
        self.assertEqual(svc.upsert("Salary Structure", payload).action, "unchanged")
        self.assertEqual(f.inserted[0]["name"], "Standard")

    def test_every_pinned_mandatory_field_can_be_supplied_and_is_required(self):
        for doctype, mandatory in PINNED_MANDATORY.items():
            spec = SPECS[doctype]
            for name in mandatory:
                self.assertIn(name, spec.fields, (doctype, name))
                self.assertIn(name, spec.required, (doctype, name))

    def test_employee_is_created_over_the_adapters_with_gender_and_birth_date(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        self.assertEqual(svc.upsert("Employee", EMPLOYEE).action, "created")
        self.assertEqual(f.inserted[0]["gender"], "Female")
        self.assertEqual(f.inserted[0]["date_of_birth"], "1990-04-02")
        for missing in ("gender", "date_of_birth"):
            partial = {k: v for k, v in EMPLOYEE.items() if k != missing}
            refused(self, "field_required", svc.upsert, "Employee", partial)
        self.assertEqual(f.insert_calls, 1)


class KeyLockTests(unittest.TestCase):
    """Review finding 4 at the adapter: one lock per key, held until commit, always released."""

    def test_lock_is_taken_before_and_released_after_the_write_and_commits(self):
        f = FakeFrappe(roles=("HR Manager",))
        service(f).upsert("Designation", {"designation_name": "Rep"})
        self.assertEqual([q for q, _ in f.sql_log], ["select get_lock", "select release_lock"])
        self.assertEqual(f.sql_log[0][1][0], f.sql_log[1][1][0])  # same lock name
        self.assertLessEqual(len(f.sql_log[0][1][0]), 64)
        self.assertEqual(f.commits, 0)  # the caller owns commit and rollback, never this component

    def test_lock_names_differ_by_key_company_and_doctype_but_never_expose_the_key(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.companies = {"Acme", "Beta"}
        service(f).upsert("Designation", {"designation_name": "Rep"})
        service(f).upsert("Designation", {"designation_name": "Lead"})
        service(f).upsert("Branch", {"branch": "Rep"})
        service(f, "Beta").upsert("Department", {"department_name": "Rep"})
        names = [v[0] for q, v in f.sql_log if q == "select get_lock"]
        self.assertEqual(len(set(names)), 4)
        self.assertFalse(any("Rep" in n for n in names))

    def test_postgres_uses_an_advisory_lock(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.conf.db_type = "postgres"
        service(f).upsert("Designation", {"designation_name": "Rep"})
        self.assertEqual([q for q, _ in f.sql_log], ["select pg_advisory_lock", "select pg_advisory_unlock"])

    def test_lock_not_obtained_refuses_the_write_and_releases_nothing(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.lock_result = 0
        refused(self, "operation_failed", service(f).upsert, "Designation", {"designation_name": "Rep"})
        self.assertEqual(f.insert_calls, 0)
        self.assertEqual([q for q, _ in f.sql_log], ["select get_lock"])

    def test_unknown_database_type_fails_closed(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.conf.db_type = "sqlite"
        refused(self, "operation_failed", service(f).upsert, "Designation", {"designation_name": "Rep"})
        self.assertEqual(f.insert_calls, 0)

    def test_lock_is_released_when_the_write_fails(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.perms = False
        refused(self, "permission_denied", service(f).upsert, "Designation", {"designation_name": "Rep"})
        self.assertEqual([q for q, _ in f.sql_log], ["select get_lock", "select release_lock"])
        self.assertEqual(f.commits, 0)

    def test_duplicate_entry_from_the_engine_is_retried_as_an_update_path(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        real_insert = FakeDoc.insert

        def lose_the_race(doc):  # another process inserts the same key first, then ours collides
            if f.duplicate_next:
                other = dict(doc.data, name="DOC-OTHER")
                f.docs[(other["doctype"], "DOC-OTHER")] = other
            real_insert(doc)

        FakeDoc.insert = lose_the_race
        try:
            f.duplicate_next = 1
            result = svc.upsert("Designation", {"designation_name": "Rep"})
        finally:
            FakeDoc.insert = real_insert
        self.assertEqual((result.action, result.name), ("unchanged", "DOC-OTHER"))
        self.assertEqual(len([k for k in f.docs if k[0] == "Designation"]), 1)

    def test_persistent_duplicate_entry_is_refused_not_looped(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.duplicate_next = 5
        refused(self, "ambiguous_key", service(f).upsert, "Designation", {"designation_name": "Rep"})
        self.assertEqual(f.insert_calls, 2)  # one retry, then stop


LINA, BOSS = EMPLOYEE["user_id"], "boss@example.invalid"
FILING = {"employee": "EMP-1", "leave_type": "Annual", "from_date": "2026-03-01", "to_date": "2026-03-05"}


class TransactionOwnershipTests(unittest.TestCase):
    """Review (round 2) MED: the component never commits the caller's enclosing transaction."""

    def test_a_no_op_upsert_leaves_unrelated_caller_work_to_roll_back(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        svc.upsert("Designation", {"designation_name": "Rep"})
        f.caller_pending.append("unrelated pending row")  # the caller's own uncommitted work
        self.assertEqual(svc.upsert("Designation", {"designation_name": "Rep"}).action, "unchanged")
        f.db.rollback()  # the caller decides
        self.assertEqual((f.caller_pending, f.committed, f.commits), ([], [], 0))

    def test_no_path_commits_on_create_update_refusal_or_failure(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        f.caller_pending.append("unrelated pending row")
        self.assertEqual(svc.upsert("Salary Structure", {"name": "S", "payroll_frequency": "Monthly"}).action, "created")
        self.assertEqual(svc.upsert("Salary Structure", {"name": "S", "payroll_frequency": "Weekly"}).action, "updated")
        f.perms = False
        refused(self, "permission_denied", svc.upsert, "Designation", {"designation_name": "Other"})
        f.lock_result = 0
        refused(self, "operation_failed", svc.upsert, "Designation", {"designation_name": "Other"})
        self.assertEqual((f.commits, f.committed, f.caller_pending), (0, [], ["unrelated pending row"]))

    def test_the_adapter_source_has_no_commit_or_rollback_call(self):
        import inspect
        from components.core.hrms_skeleton import frappe_backend
        code = inspect.getsource(frappe_backend)
        self.assertNotRegex(code, r"\.(commit|rollback)\(")


class CurrentReadTests(unittest.TestCase):
    """Review (round 2) MED: under REPEATABLE-READ the lookup inside the lock is a locking current read."""

    def test_lookups_inside_the_lock_are_for_update_and_outside_it_are_not(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        svc.upsert("Designation", {"designation_name": "Rep"})
        svc.upsert("Designation", {"designation_name": "Rep"})
        reads = [r for r in f.reads if r[1] == "Designation"]
        self.assertTrue(reads)
        self.assertTrue(all(for_update and lock_held for _, _, for_update, lock_held in reads), reads)
        self.assertEqual(f.commits, 0)

    def test_the_company_check_outside_the_lock_is_a_plain_read(self):
        f = FakeFrappe(roles=("HR Manager",))
        FrappeStore(f).find("Branch", {"branch": "HQ"})
        self.assertEqual([r[2] for r in f.reads], [False])

    def test_a_stale_snapshot_does_not_hide_another_writers_row(self):
        f = FakeFrappe(roles=("HR Manager",))
        first, second = service(f), service(f)
        f.freeze_snapshot()  # the second request's transaction already holds its read snapshot
        self.assertEqual(first.upsert("Designation", {"designation_name": "Rep"}).action, "created")
        self.assertEqual(second.upsert("Designation", {"designation_name": "Rep"}).action, "unchanged")
        self.assertEqual(len([k for k in f.docs if k[0] == "Designation"]), 1)
        # A plain read in the same state really is stale: the fake does model the problem.
        self.assertEqual(FrappeStore(f).find("Designation", {"designation_name": "Rep"}), [])

    def test_a_stale_snapshot_does_not_make_a_second_policy_or_an_ambiguous_key(self):
        f = FakeFrappe(roles=("HR Manager",))
        payload = {"title": "Standard", "leave_policy_details": [{"leave_type": "Annual", "annual_allocation": "21"}]}
        a, b = service(f), service(f)
        f.freeze_snapshot()
        self.assertEqual(a.upsert("Leave Policy", payload).action, "created")
        self.assertEqual(b.upsert("Leave Policy", payload).action, "unchanged")
        self.assertEqual(b.upsert("Leave Policy", payload).action, "unchanged")  # the retry is not ambiguous
        self.assertEqual(len([k for k in f.docs if k[0] == "Leave Policy"]), 1)

    def test_updates_load_the_document_with_a_current_read(self):
        f = FakeFrappe(roles=("HR Manager",))
        svc = service(f)
        svc.upsert("Salary Structure", {"name": "S", "payroll_frequency": "Monthly"})
        f.reads.clear()
        svc.upsert("Salary Structure", {"name": "S", "payroll_frequency": "Weekly"})
        self.assertTrue(all(r[2] for r in f.reads if r[0] == "get_doc"))

    def test_the_database_unique_constraint_is_still_the_backstop(self):
        f = FakeFrappe(roles=("HR Manager",))
        f.duplicate_next = 1
        self.assertEqual(service(f).upsert("Designation", {"designation_name": "Rep"}).action in ("created", "unchanged"), True)
        self.assertEqual(f.insert_calls, 2)


class ApplicantIdentityPersistenceTests(unittest.TestCase):
    """Review (round 2) MED: the applicant principal survives save and reload without an invented
    column. The fake keeps valid columns only and resets fields above the caller's permission level."""

    def setUp(self):
        self.f = FakeFrappe(user=BOSS, roles=("HR Manager",))
        service(self.f).upsert("Employee", EMPLOYEE)
        self.name = next(n for (dt, n) in self.f.docs if dt == "Employee")
        self.filing = {**FILING, "employee": self.name}

    def stored(self):
        """The application as persisted now (saves replace the stored dict, so never cache it)."""
        return next(d for (dt, _), d in self.f.docs.items() if dt == "Leave Application")

    def as_user(self, user, roles):
        self.f.session.user, self.f.roles = user, list(roles)
        return service(self.f)  # a fresh service and store: nothing carried over from filing

    def file_as_lina(self, roles=("Employee",)):
        return self.as_user(LINA, roles).upsert("Leave Application", self.filing)

    def test_the_fake_drops_an_unknown_column_and_a_protected_field_on_save(self):
        doc = self.f.get_doc({"doctype": "Leave Application", "employee": "E", "applicant_user": LINA,
                              APPLICANT_IDENTITY_FIELD: LINA})
        doc.insert()
        self.assertNotIn("applicant_user", doc.data)
        self.assertNotIn(APPLICANT_IDENTITY_FIELD, doc.data)  # permission level 2: reset for this caller

    def test_the_protected_field_is_declared_read_only_above_level_one(self):
        (field,) = PLATFORM_CUSTOM_FIELDS["Leave Application"]
        self.assertEqual(field["fieldname"], APPLICANT_IDENTITY_FIELD)
        self.assertTrue(field["read_only"] and field["permlevel"] >= 2)
        df = self.f.get_meta("Leave Application").get_field(APPLICANT_IDENTITY_FIELD)
        self.assertTrue(df.read_only and df.permlevel == 2)

    def test_filing_then_reload_then_an_independent_hr_manager_decision_succeeds(self):
        self.assertEqual(self.file_as_lina().action, "created")
        self.assertEqual(self.stored()[APPLICANT_IDENTITY_FIELD], LINA)
        self.assertNotIn("applicant_user", self.stored())
        result = self.as_user(BOSS, ("HR Manager",)).decide_leave_application(self.filing, "approve")
        self.assertEqual(result.action, "approved")
        self.assertEqual(self.stored()["status"], "Approved")

    def test_the_applicant_cannot_approve_her_own_application_after_reload(self):
        self.file_as_lina()
        refused(self, "self_approval_forbidden", self.as_user(LINA, ("HR Manager",)).decide_leave_application,
                self.filing, "approve")
        self.assertEqual(self.stored()["status"], "Open")

    def test_rewriting_the_employee_link_or_the_field_through_the_document_api_fails_closed(self):
        self.file_as_lina()
        # The document API cannot change the protected field (reset above the caller's level)...
        FrappeStore(self.f).update("Leave Application", self.stored()["name"], {APPLICANT_IDENTITY_FIELD: BOSS})
        self.assertEqual(self.stored()[APPLICANT_IDENTITY_FIELD], LINA)
        # ...and re-linking the employee record behind the service's back no longer matches it.
        self.f.docs[("Employee", self.name)]["user_id"] = "other@example.invalid"
        refused(self, "applicant_identity_unresolved", self.as_user(BOSS, ("HR Manager",)).decide_leave_application,
                self.filing, "approve")
        self.assertEqual(self.stored()["status"], "Open")

    def test_the_recorded_principal_is_written_once(self):
        self.file_as_lina()
        with self.assertRaises(HrmsError) as ctx:
            FrappeStore(self.f).record_applicant_identity("Leave Application", self.stored()["name"], BOSS)
        self.assertEqual(ctx.exception.code, "identity_binding_protected")
        self.assertEqual(self.stored()[APPLICANT_IDENTITY_FIELD], LINA)

    def test_a_bench_without_the_protected_field_refuses_filing_and_every_decision(self):
        # Field not declared (unknown column): the write raises, the filing is refused, no decision passes.
        import components.core.hrms_skeleton.tests.test_frappe_backend as me
        keep = me.EXTRA_FIELDS["Leave Application"]
        me.EXTRA_FIELDS["Leave Application"] = {"status"}
        try:
            refused(self, "operation_failed", self.as_user(LINA, ("Employee",)).upsert, "Leave Application", self.filing)
        finally:
            me.EXTRA_FIELDS["Leave Application"] = keep

    def test_an_unprotected_field_is_not_trusted(self):
        for level in (0,):  # declared but editable: refuse rather than rely on it
            self.f.levels[APPLICANT_IDENTITY_FIELD] = level
            refused(self, "operation_failed", self.as_user(LINA, ("Employee",)).upsert, "Leave Application", self.filing)

    def test_an_application_filed_before_the_field_existed_cannot_be_decided(self):
        self.file_as_lina()
        self.stored()[APPLICANT_IDENTITY_FIELD] = None
        refused(self, "applicant_identity_unresolved", self.as_user(BOSS, ("HR Manager",)).decide_leave_application,
                self.filing, "approve")


if __name__ == "__main__":
    unittest.main()
