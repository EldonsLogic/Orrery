"""Adapters that run `HrmsService` inside the engine, as the calling user (ERP-010).

Everything runs with the caller's own permissions: no `ignore_permissions`, no elevated user.
UNVERIFIED: not yet run against the pinned bench (Q-280); the unit tests use a fake `frappe`.
Any failure to resolve identity, roles or permissions fails closed.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from .access import DuplicateKeyError
from .errors import HrmsError
from .specs import STANDARD_COLUMNS


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
            if name in STANDARD_COLUMNS:
                # `name` is a standard column, not a DocField: `get_field("name")` returns None.
                # It is the document's own identifier, writable only with document-level (0) access.
                if 0 not in writable:
                    denied.append(name)
                continue
            df = meta.get_field(name)
            if df is None or int(getattr(df, "permlevel", 0) or 0) not in writable:
                denied.append(name)
        return denied


_LOCK_WAIT_SECONDS = 10
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_MUTEX = threading.Lock()


def _local_lock(name: str) -> threading.Lock:
    with _LOCAL_LOCKS_MUTEX:
        return _LOCAL_LOCKS.setdefault(name, threading.Lock())


class FrappeStore:
    """Reads and writes through the engine's document layer with the caller's permissions."""

    def __init__(self, frappe: Any) -> None:
        self._f = frappe

    @contextmanager
    def key_lock(self, doctype: str, scope: Sequence[str]) -> Iterator[None]:
        """One writer per (tenant, company, doctype, key): a process lock plus a database advisory
        lock, held until the write is committed so the next writer's lookup sees it. UNVERIFIED on
        the pinned bench (Q-280). Failing to take the lock refuses the write; it never runs unlocked."""
        digest = hashlib.sha256(json.dumps([self.tenant, doctype, *scope]).encode()).hexdigest()[:48]
        name = f"hrms:{digest}"  # short enough for a MariaDB lock name (64 characters)
        db_type = getattr(getattr(self._f, "conf", None), "db_type", None) or "mariadb"
        if db_type == "mariadb":
            take = ("select get_lock(%s, %s)", (name, _LOCK_WAIT_SECONDS))
            drop = ("select release_lock(%s)", (name,))
        elif db_type == "postgres":
            take = ("select pg_advisory_lock(hashtext(%s))", (name,))
            drop = ("select pg_advisory_unlock(hashtext(%s))", (name,))
        else:
            raise HrmsError("operation_failed")
        local = _local_lock(name)
        if not local.acquire(timeout=_LOCK_WAIT_SECONDS):
            raise HrmsError("operation_failed")
        try:
            rows = self._f.db.sql(*take)
            if db_type == "mariadb" and (not rows or rows[0][0] != 1):
                raise HrmsError("operation_failed")
            try:
                yield
                self._f.db.commit()
            finally:
                self._f.db.sql(*drop)
        finally:
            local.release()

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
        duplicate = getattr(self._f, "DuplicateEntryError", None)
        try:
            doc.insert()
        except Exception as error:
            if isinstance(duplicate, type) and isinstance(error, duplicate):
                raise DuplicateKeyError() from None
            raise
        return doc.as_dict()

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> dict[str, Any]:
        doc = self._f.get_doc(doctype, name)
        doc.update(dict(values))
        doc.save()
        return doc.as_dict()
