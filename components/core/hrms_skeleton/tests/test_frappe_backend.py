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
from components.core.hrms_skeleton.specs import SPECS, STANDARD_COLUMNS

# Mandatory fields of the pinned schemas that the caller must supply (the engine defaults the rest,
# for example `status` and `company`). UNVERIFIED against a live bench (Q-280).
PINNED_MANDATORY = {
    "Employee": ("first_name", "gender", "date_of_birth", "date_of_joining"),
    "Salary Structure": ("name",),  # naming rule "Prompt"
}
# Fields that exist on the pinned doctypes beyond the spec's own (set by the engine or the service).
EXTRA_FIELDS = {"Leave Application": {"status", "applicant_user"}}


def schema_fields(doctype):
    spec = SPECS[doctype]
    return (set(spec.fields) - STANDARD_COLUMNS) | set(spec.children) | EXTRA_FIELDS.get(doctype, set())


class MandatoryError(Exception):
    pass


class FakeDoc:
    def __init__(self, frappe, data):
        self.frappe, self.data, self.saved = frappe, dict(data), False

    def insert(self):
        missing = [f for f in PINNED_MANDATORY.get(self.data["doctype"], ()) if not self.data.get(f)]
        if missing:
            raise MandatoryError(missing)
        self.frappe.insert_calls += 1
        if self.frappe.duplicate_next:
            self.frappe.duplicate_next -= 1
            raise self.frappe.DuplicateEntryError("exists")
        self.data.setdefault("name", f"DOC-{len(self.frappe.docs) + 1}")
        self.frappe.docs[(self.data["doctype"], self.data["name"])] = self.data
        self.frappe.inserted.append(self.data)

    def update(self, values):
        self.data.update(values)

    def save(self):
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
        return SimpleNamespace(permlevel=self.levels.get(name, 0))


class FakeFrappe:
    def __init__(self, user="hr@example.invalid", roles=("HR Manager",), site="tenant-a"):
        self.session = SimpleNamespace(user=user)
        self.local = SimpleNamespace(site=site)
        self.roles, self.docs, self.inserted, self.saved = list(roles), {}, [], []
        self.can_read, self.perms, self.companies, self.restricted = True, True, {"Acme"}, []
        self.levels = {"base": 1}
        self.conf = SimpleNamespace(db_type="mariadb")
        self.sql_log, self.lock_result, self.commits = [], 1, 0
        self.insert_calls, self.duplicate_next = 0, 0
        self.db = SimpleNamespace(exists=lambda dt, name: name in self.companies, sql=self._sql, commit=self._commit)

        class DuplicateEntryError(Exception):
            pass

        self.DuplicateEntryError = DuplicateEntryError

    def _sql(self, query, values=None):
        self.sql_log.append((query.split("(")[0].strip(), values))
        return ((self.lock_result,),)

    def _commit(self):
        self.commits += 1

    def get_roles(self, user):
        return list(self.roles)

    def get_all(self, doctype, filters=None, pluck=None):
        assert doctype == "User Permission"
        return list(self.restricted)

    def has_permission(self, doctype, ptype=None, user=None):
        return self.perms

    def get_meta(self, doctype):
        return FakeMeta(doctype, self.levels)

    def get_list(self, doctype, filters=None, pluck=None, limit_page_length=None):
        rows = [d for (dt, _), d in self.docs.items() if dt == doctype and all(d.get(k) == v for k, v in filters.items())]
        return [r["name"] for r in rows][:limit_page_length]

    def get_doc(self, *args):
        if isinstance(args[0], dict):
            return FakeDoc(self, args[0])
        return FakeDoc(self, self.docs[(args[0], args[1])])


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
        self.assertEqual(f.commits, 1)

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


if __name__ == "__main__":
    unittest.main()
