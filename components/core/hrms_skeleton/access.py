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

    def find_current(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Like `find`, but a current read: it must see the latest committed state and wait behind
        any other writer's uncommitted write to the same rows, whatever snapshot the caller's
        transaction already holds. Used only inside `key_lock`, for the lookup before a write. It
        never commits or resets the caller's transaction."""

    def key_lock(self, doctype: str, scope: Sequence[str]) -> ContextManager[None]:
        """Serialise every writer of one business key (`scope` is the company, or "", then the key
        values) inside this tenant. Lookup (`find_current`) and write both happen while it is held.
        It never commits: the caller owns the transaction, and a writer's uncommitted rows stay
        locked until the caller commits, so the next holder's `find_current` waits on them. Fails
        (raises) rather than proceeding unlocked."""

    def insert(self, doctype: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """May raise `DuplicateKeyError` when the backend enforces uniqueness itself."""

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> dict[str, Any]: ...

    def record_applicant_identity(self, doctype: str, name: str, principal: str) -> None:
        """Persist a leave application's applicant principal in a protected store, once.
        Raises if one is already recorded. It is the only writer of that value."""

    def get_applicant_identity(self, doctype: str, name: str) -> Any:
        """The recorded applicant principal, or None or an empty string when absent."""
