"""The engine adapters, against a fake engine module (not yet run on the real bench; Q-280)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from components.core.hrms_skeleton import HrmsError, HrmsService
from components.core.hrms_skeleton.frappe_backend import FrappeSession, FrappeStore


class FakeDoc:
    def __init__(self, frappe, data):
        self.frappe, self.data, self.saved = frappe, dict(data), False

    def insert(self):
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
    def __init__(self, levels):
        self.levels = levels

    def get_permlevel_access(self, ptype):
        return [0]

    def get_field(self, name):
        if name.startswith("unknown"):
            return None
        return SimpleNamespace(permlevel=self.levels.get(name, 0))


class FakeFrappe:
    def __init__(self, user="hr@example.invalid", roles=("HR Manager",), site="tenant-a"):
        self.session = SimpleNamespace(user=user)
        self.local = SimpleNamespace(site=site)
        self.roles, self.docs, self.inserted, self.saved = list(roles), {}, [], []
        self.can_read, self.perms, self.companies, self.restricted = True, True, {"Acme"}, []
        self.db = SimpleNamespace(exists=lambda dt, name: name in self.companies)
        self.levels = {"base": 1}

    def get_roles(self, user):
        return list(self.roles)

    def get_all(self, doctype, filters=None, pluck=None):
        assert doctype == "User Permission"
        return list(self.restricted)

    def has_permission(self, doctype, ptype=None, user=None):
        return self.perms

    def get_meta(self, doctype):
        return FakeMeta(self.levels)

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


if __name__ == "__main__":
    unittest.main()
