"""In-memory `Session` and `Store` for tests and local simulation (no engine, no data kept)."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence


class StaticSession:
    """A fixed, already-authenticated caller. Roles are given by the test harness, never a request."""

    def __init__(
        self,
        user: str,
        roles: Sequence[str],
        tenant: str,
        companies: Sequence[str] = (),
        denied: Mapping[str, Sequence[str]] | None = None,
        permissions: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.user = user
        self.tenant = tenant
        self._roles = frozenset(roles)
        self._companies = frozenset(companies)
        self._denied = {k: tuple(v) for k, v in (denied or {}).items()}
        self._permissions = None if permissions is None else {k: frozenset(v) for k, v in permissions.items()}

    def roles(self) -> frozenset[str]:
        return self._roles

    def company_permitted(self, company: str) -> bool:
        return company in self._companies

    def has_permission(self, doctype: str, ptype: str) -> bool:
        if self._permissions is None:
            return True
        return ptype in self._permissions.get(doctype, frozenset())

    def denied_fields(self, doctype: str, fields: Sequence[str]) -> list[str]:
        blocked = set(self._denied.get(doctype, ()))
        return [f for f in fields if f in blocked]


class InMemoryStore:
    """Keeps records in a dict, bound to one tenant. `name` is assigned on insert."""

    def __init__(self, tenant: str) -> None:
        self.tenant = tenant
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.writes = 0

    def find(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = self.rows.get(doctype, {}).values()
        hits = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
        return [copy.deepcopy(r) for r in hits[:2]]

    def insert(self, doctype: str, values: Mapping[str, Any]) -> dict[str, Any]:
        table = self.rows.setdefault(doctype, {})
        name = str(values.get("name") or f"{doctype[:3].upper()}-{len(table) + 1:05d}")
        record = {**copy.deepcopy(dict(values)), "name": name}
        table[name] = record
        self.writes += 1
        return copy.deepcopy(record)

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> dict[str, Any]:
        record = self.rows[doctype][name]
        record.update(copy.deepcopy(dict(values)))
        self.writes += 1
        return copy.deepcopy(record)
