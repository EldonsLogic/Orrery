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
from .specs import APPLICANT_IDENTITY_FIELD, PLATFORM_CUSTOM_FIELDS, STANDARD_COLUMNS


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
        lock around the lookup and the write. UNVERIFIED on the pinned bench (Q-280).

        It never commits, rolls back or resets the caller's transaction: commit and rollback belong
        to the caller, even when this component writes nothing. So the advisory lock alone does not
        make the next writer see this writer's row. Two things do: the lookup is a locking current
        read (`find_current`, `SELECT ... FOR UPDATE`), which under MariaDB's default REPEATABLE-READ
        reads the latest committed row instead of the transaction's old snapshot and waits behind
        another writer's uncommitted row locks; and the database's own unique index on the key turns
        a lost race into `DuplicateEntryError`, which the service retries once. Failing to take the
        lock refuses the write; it never runs unlocked."""
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
            finally:
                self._f.db.sql(*drop)
        finally:
            local.release()

    @property
    def tenant(self) -> str:
        return str(self._f.local.site)

    def find(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        return self._read(doctype, filters, current=False)

    def find_current(self, doctype: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        """A locking current read (`for_update`), used inside `key_lock`. A plain read here could
        return the caller's stale REPEATABLE-READ snapshot and miss a row another writer just
        wrote. Parameterised by the engine; no SQL is built here. UNVERIFIED on the bench (Q-280)."""
        return self._read(doctype, filters, current=True)

    def _read(self, doctype: str, filters: Mapping[str, Any], current: bool) -> list[dict[str, Any]]:
        extra = {"for_update": True} if current else {}
        names = self._f.get_list(doctype, filters=dict(filters), pluck="name", limit_page_length=2, **extra)
        out = []
        for name in names:
            doc = self._f.get_doc(doctype, name, **extra)
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
        doc = self._f.get_doc(doctype, name, for_update=True)
        doc.update(dict(values))
        doc.save()
        return doc.as_dict()

    # -- applicant identity: a protected custom field, written only here ---------------------
    def _identity_field(self, doctype: str) -> str:
        """The declared protected field, or a refusal. A missing or unprotected field never falls
        back to an ordinary column: the engine drops unknown columns, and an editable one could be
        rewritten by the applicant."""
        declared = {f["fieldname"] for f in PLATFORM_CUSTOM_FIELDS.get(doctype, ())}
        if APPLICANT_IDENTITY_FIELD not in declared:
            raise HrmsError("operation_failed")
        df = self._f.get_meta(doctype).get_field(APPLICANT_IDENTITY_FIELD)
        if df is None or not getattr(df, "read_only", 0) or int(getattr(df, "permlevel", 0) or 0) < 1:
            raise HrmsError("operation_failed")
        return APPLICANT_IDENTITY_FIELD

    def record_applicant_identity(self, doctype: str, name: str, principal: str) -> None:
        """Write the applicant principal once, with a direct column write (the document API would
        clear a permission-level field for a caller without access to it). Part of the caller's
        transaction; nothing is committed here."""
        field = self._identity_field(doctype)
        if self._f.db.get_value(doctype, name, field, for_update=True) not in (None, ""):
            raise HrmsError("identity_binding_protected", doctype=doctype)
        self._f.db.set_value(doctype, name, field, principal, update_modified=False)

    def get_applicant_identity(self, doctype: str, name: str) -> Any:
        field = self._identity_field(doctype)
        return self._f.db.get_value(doctype, name, field, for_update=True)
