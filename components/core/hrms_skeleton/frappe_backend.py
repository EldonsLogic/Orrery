"""Adapters that run `HrmsService` inside the engine, as the calling user (ERP-010).

Everything runs with the caller's own permissions: no `ignore_permissions`, no elevated user.
UNVERIFIED: not yet run against the pinned bench (Q-280); the unit tests use a fake `frappe`.
Any failure to resolve identity, roles or permissions fails closed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import HrmsError


class FrappeSession:
    """The authenticated engine session. Roles and tenant come from the server, never the request."""

    def __init__(self, frappe: Any) -> None:
        self._f = frappe

    @property
    def user(self) -> str:
        user = getattr(self._f.session, "user", None)
        if not isinstance(user, str) or not user or user == "Guest":
            raise HrmsError("session_invalid")
        return user

    @property
    def tenant(self) -> str:
        return str(self._f.local.site)  # one site per tenant (ADR-0006)

    def roles(self) -> frozenset[str]:
        return frozenset(self._f.get_roles(self.user))

    def company_permitted(self, company: str) -> bool:
        if not self._f.db.exists("Company", company):
            return False
        restricted = self._f.get_all(
            "User Permission", filters={"user": self.user, "allow": "Company"}, pluck="for_value"
        )
        return not restricted or company in restricted

    def has_permission(self, doctype: str, ptype: str) -> bool:
        return bool(self._f.has_permission(doctype, ptype=ptype, user=self.user))

    def denied_fields(self, doctype: str, fields: Sequence[str]) -> list[str]:
        meta = self._f.get_meta(doctype)
        writable = set(meta.get_permlevel_access("write"))
        denied = []
        for name in fields:
            df = meta.get_field(name)
            if df is None or int(getattr(df, "permlevel", 0) or 0) not in writable:
                denied.append(name)
        return denied


class FrappeStore:
    """Reads and writes through the engine's document layer with the caller's permissions."""

    def __init__(self, frappe: Any) -> None:
        self._f = frappe

    @property
    def tenant(self) -> str:
        return str(self._f.local.site)

    def find(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        names = self._f.get_list(doctype, filters=dict(filters), pluck="name", limit_page_length=2)
        out = []
        for name in names:
            doc = self._f.get_doc(doctype, name)
            doc.check_permission("read")
            out.append(doc.as_dict())
        return out

    def insert(self, doctype: str, values: Mapping[str, Any]) -> dict[str, Any]:
        doc = self._f.get_doc({"doctype": doctype, **values})
        doc.insert()
        return doc.as_dict()

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> dict[str, Any]:
        doc = self._f.get_doc(doctype, name)
        doc.update(dict(values))
        doc.save()
        return doc.as_dict()
