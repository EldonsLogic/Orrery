"""Test helper (SEC-022, BPL-032): a simulated engine whose record names match without case, like MariaDB.

The shared SimulatedFrappeRuntime matches names exactly, so it cannot show the collision the real engine has
(`utf8mb4_unicode_ci`: a lookup of "auditor" returns the built-in "Auditor"). This subclass makes every
name lookup case-insensitive, rejects an insert whose name already exists in another case (the real engine
raises a duplicate-entry error), seeds built-in roles, workflow states and standard permission rules, and
exposes `permissions.setup_custom_perms` and `is_submittable` like the real engine. Synthetic data only.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from change_engine.adapter.simulated_frappe import SimulatedFrappeDB, SimulatedFrappeRuntime, SimulatedMeta

BUILTIN_ROLES = ("Administrator", "System Manager", "All", "Guest", "Auditor", "Sales User", "Sales Manager")
BUILTIN_STATES = ("Approved", "Pending", "Rejected", "Draft", "Cancelled")
# A built-in role with standard rules on a mapped document type (the old test_06 "one grant via a built-in").
STANDARD_PERMS = (
    {"parent": "Customer", "role": "Auditor", "permlevel": 0, "read": 1},
    {"parent": "Customer", "role": "Sales User", "permlevel": 0, "read": 1, "write": 1, "create": 1},
    {"parent": "Item", "role": "Sales User", "permlevel": 0, "read": 1},
)
SUBMITTABLE = frozenset({"Sales Order", "Sales Invoice", "Delivery Note", "Purchase Order", "Purchase Receipt", "Purchase Invoice"})
# Engine document types that exist on every real site (custom=0) and are outside the reviewed mapping: a
# Blueprint grant on any of them must be refused (ADR-0051 item 3). Property Setter and Custom Field sit in the
# engine's own "Custom" module, so the module alone never makes a document type the adapter's.
ENGINE_DOCTYPES = {
    "Server Script": "Core", "User Permission": "Core", "Property Setter": "Custom", "Custom Field": "Custom",
    "Role Profile": "Core", "Has Role": "Core", "Webhook": "Integrations", "File": "Core", "Data Import": "Core",
    "Payment Entry": "Accounts", "Session": "Core", "GL Entry": "Accounts",
}


class DuplicateEntryError(Exception):
    """Stands in for the engine's duplicate-entry error on a case-insensitive unique name."""


def _ci_key(rows: dict[str, Any], name: Any) -> str | None:
    if name is None:
        return None
    want = str(name).casefold()
    return next((k for k in rows if k.casefold() == want), None)


class _CaseInsensitiveDB(SimulatedFrappeDB):
    def exists(self, doctype: str, name_or_filters: Any = None) -> Any:
        if isinstance(name_or_filters, dict) or doctype in self._site.singles:
            return super().exists(doctype, name_or_filters)
        return _ci_key(self._site.rows.get(f"tab{doctype}", {}), name_or_filters)

    def get_value(self, doctype: str, filters: Any, fieldname: Any = "name", as_dict: bool = False) -> Any:
        if not isinstance(filters, dict) and doctype not in self._site.singles:
            filters = _ci_key(self._site.rows.get(f"tab{doctype}", {}), filters)
            if filters is None:
                return None
        return super().get_value(doctype, filters, fieldname, as_dict)

    def set_value(self, doctype: str, name: str, fieldname: str, value: Any) -> None:
        if doctype not in self._site.singles:
            name = _ci_key(self._site.rows.get(f"tab{doctype}", {}), name) or name
        super().set_value(doctype, name, fieldname, value)


class CaseInsensitiveEngine(SimulatedFrappeRuntime):
    """One-site simulated engine with case-insensitive names, built-ins and standard permission rules."""

    def __init__(self, site_name: str = "ci.localhost", submittable: frozenset[str] = SUBMITTABLE) -> None:
        super().__init__()
        self.db = _CaseInsensitiveDB(self)
        self.submittable = set(submittable)
        self.permissions = SimpleNamespace(setup_custom_perms=self._setup_custom_perms)
        site = self.ensure_site(site_name)
        self.local.site = site_name
        plain_upsert = site.upsert_doc

        def upsert_doc(data: dict[str, Any], is_insert: bool) -> dict[str, Any]:
            dt = data["doctype"]
            if is_insert and dt not in site.singles:
                name = site._doc_name(dt, data)
                clash = _ci_key(site.rows.get(f"tab{dt}", {}), name)
                if clash is not None and clash != name:
                    raise DuplicateEntryError(f"{dt} {name!r} exists as {clash!r}")
            return plain_upsert(data, is_insert)

        site.upsert_doc = upsert_doc  # type: ignore[method-assign]
        for role in BUILTIN_ROLES:
            site.rows["tabRole"][role] = {"doctype": "Role", "name": role, "role_name": role, "disabled": 0}
        for state in BUILTIN_STATES:
            site.rows["tabWorkflow State"][state] = {"doctype": "Workflow State", "name": state, "workflow_state_name": state}
        site.rows.setdefault("tabDocPerm", {})
        site.rows.setdefault("tabCustom DocPerm", {})
        for i, perm in enumerate(STANDARD_PERMS):
            site.rows["tabDocPerm"][f"std{i}"] = {"doctype": "DocPerm", "name": f"std{i}", **perm}
        for dt, module in ENGINE_DOCTYPES.items():
            self.add_doctype(dt, module=module, custom=0)

    def get_doc(self, arg1: Any, arg2: str | None = None) -> Any:
        if not isinstance(arg1, dict) and arg2 is not None:
            arg2 = _ci_key(self.current_site_db().rows.get(f"tab{arg1}", {}), arg2) or arg2
        return super().get_doc(arg1, arg2)

    def get_all(self, doctype: str, fields: list[str] | None = None, filters: dict[str, Any] | None = None, **kw: Any) -> list[dict[str, Any]]:
        return super().get_all(doctype, fields=None if fields == ["*"] else fields, filters=filters, **kw)

    def get_meta(self, doctype: str) -> SimulatedMeta:
        meta = super().get_meta(doctype)
        meta.is_submittable = int(doctype in self.submittable)
        return meta

    def _setup_custom_perms(self, parent: str) -> bool:
        """Same contract as the engine's frappe.permissions.setup_custom_perms: copy standard rules once."""
        site = self.current_site_db()
        if any(r.get("parent") == parent for r in site.rows["tabCustom DocPerm"].values()):
            return False
        for r in list(site.rows["tabDocPerm"].values()):
            if r.get("parent") == parent:
                row = copy.deepcopy(r)
                row.update(doctype="Custom DocPerm", name=f"c_{r['name']}")
                site.rows["tabCustom DocPerm"][row["name"]] = row
        return True

    # Direct readers used by the tests (independent of the adapter under test).
    def rows(self, doctype: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(r) for r in self.current_site_db().rows.get(f"tab{doctype}", {}).values()]

    def add_field(self, doctype: str, fieldname: str, permlevel: int = 0) -> None:
        spec = self.current_site_db().doctype_meta.setdefault(doctype, {"issingle": 0, "fields": [], "perms": {}})
        spec["fields"].append({"fieldname": fieldname, "fieldtype": "Data", "permlevel": permlevel})

    def add_doctype(self, doctype: str, *, module: str, custom: int) -> None:
        """A document type the adapter did not create (an engine one, or one made by hand in the desk)."""
        site = self.current_site_db()
        site.rows["tabDocType"][doctype] = {"doctype": "DocType", "name": doctype, "module": module, "custom": custom}
        site.table_columns.setdefault(f"tab{doctype}", [])
        site.rows.setdefault(f"tab{doctype}", {})


__all__ = ["BUILTIN_ROLES", "BUILTIN_STATES", "CaseInsensitiveEngine", "DuplicateEntryError", "ENGINE_DOCTYPES", "STANDARD_PERMS",
           "SUBMITTABLE"]
