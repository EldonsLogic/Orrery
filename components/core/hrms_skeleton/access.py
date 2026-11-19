"""Caller identity, tenant and company scope, and the interfaces the component needs.

The component never accepts roles, a user or a tenant from a request. A `Session` supplies them
from the authenticated backend session, and a `Store` reads and writes records inside one tenant.
Both are small protocols so the service can be tested without an engine; `frappe_backend.py` has
the real adapters and `memory.py` the in-memory ones.
"""

from __future__ import annotations

from typing import Any, ContextManager, Mapping, Protocol, Sequence


class DuplicateKeyError(Exception):
    """Raised by `Store.insert` when the backend itself finds the record already exists."""


class Session(Protocol):
    """The authenticated caller, resolved by the backend (never by the request)."""

    @property
    def user(self) -> str: ...

    @property
    def tenant(self) -> str: ...

    def roles(self) -> frozenset[str]: ...

    def company_permitted(self, company: str) -> bool: ...

    def has_permission(self, doctype: str, ptype: str) -> bool:
        """The engine's own document permission (`create`, `write`, `read`) for this user."""

    def denied_fields(self, doctype: str, fields: Sequence[str]) -> list[str]:
        """Fields this user may not write because of their permission level."""


class Store(Protocol):
    """Records of one tenant. `find` matches every filter exactly."""

    @property
    def tenant(self) -> str: ...

    def find(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return up to two matching records, so a duplicate is detected rather than hidden."""

    def key_lock(self, doctype: str, scope: Sequence[str]) -> ContextManager[None]:
        """Serialise every writer of one business key (`scope` is the company, or "", then the key
        values) inside this tenant. Lookup and write both happen while it is held, and the write is
        visible to the next holder when it is released. Fails (raises) rather than proceeding
        unlocked."""

    def insert(self, doctype: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """May raise `DuplicateKeyError` when the backend enforces uniqueness itself."""

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> dict[str, Any]: ...
