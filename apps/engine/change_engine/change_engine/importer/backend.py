"""Transactional reference backend, following the adapter's SQLite store pattern.

This store is an executable offline backend, not a native ledger posting adapter.
A runtime implementation must keep journal and business writes in one transaction;
DDL, external sends, and independently committing posting methods are forbidden.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Callable, ContextManager, Protocol

from .errors import ImportFailure
from .validation import canonical


class ImportBackend(Protocol):
    """Trusted server dependency; no request may inject a backend or session.

    transaction serializes competing batches and rolls back ALL writes, including
    updates and the journal, on exceptions. A failed rollback must raise recovery.
    write must preserve Decimal values, use native permission checks in a runtime
    implementation, and must not commit. Journal uniqueness is tenant/batch.
    """

    def identity(self) -> dict: ...
    def transaction(self) -> ContextManager: ...
    def journal(self, tenant_id: str, batch_id: str) -> dict | None: ...
    def write(self, tenant_id: str, company: str, entity: str, key: str, row: dict) -> None: ...
    def commit_batch(self, plan: dict, plan_hash: str, user_id: str) -> None: ...
    def record_failure(self, tenant_id: str, batch_id: str, plan_hash: str, code: str) -> None: ...


class SQLiteImportBackend:
    """Durable atomic reference store with no default authenticated identity.

    A trusted session callback resolves the current backend-authenticated user on
    every apply; it is construction-time configuration, never caller payload data.
    Use a file database for restart durability, :memory: for isolated simulations.
    """

    def __init__(self, path: str = ":memory:", *, session: Callable[[], dict] | None = None):
        self._session = session
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS import_records (
                tenant_id TEXT NOT NULL, company TEXT NOT NULL, entity TEXT NOT NULL,
                business_key TEXT NOT NULL, row_json TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company, entity, business_key));
            CREATE TABLE IF NOT EXISTS import_batches (
                tenant_id TEXT NOT NULL, batch_id TEXT NOT NULL, company TEXT NOT NULL,
                plan_hash TEXT NOT NULL, confirmed_by TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY (tenant_id, batch_id));
            CREATE TABLE IF NOT EXISTS import_failures (
                seq INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, batch_id TEXT NOT NULL,
                plan_hash TEXT NOT NULL, code TEXT NOT NULL);
        """)

    def identity(self) -> dict:
        """Resolve the trusted session; callback errors never grant permissions."""
        try:
            return self._session() if self._session else {}
        except Exception:
            raise ImportFailure("IMP-AUTH") from None

    @contextmanager
    def transaction(self):
        """Serialize writers across threads/processes and atomically roll back."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.conn.commit()
            except BaseException:
                try:
                    self.conn.rollback()
                except Exception:
                    raise ImportFailure("IMP-RECOVERY") from None
                raise

    def journal(self, tenant_id: str, batch_id: str) -> dict | None:
        """Read the committed identity (caller holds transaction during apply)."""
        row = self.conn.execute("SELECT * FROM import_batches WHERE tenant_id=? AND batch_id=?",
                                (tenant_id, batch_id)).fetchone()
        return dict(row) if row else None

    def write(self, tenant_id: str, company: str, entity: str, key: str, row: dict) -> None:
        """Upsert a master or batch-scoped opening record without committing."""
        self.conn.execute("""INSERT INTO import_records VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id,company,entity,business_key) DO UPDATE SET row_json=excluded.row_json""",
                          (tenant_id, company, entity, key, canonical(row)))

    def commit_batch(self, plan: dict, plan_hash: str, user_id: str) -> None:
        """Journal confirmation in the SAME transaction as the business writes."""
        self.conn.execute("INSERT INTO import_batches VALUES (?, ?, ?, ?, ?, 'applied')",
                          (plan["tenant_id"], plan["batch_id"], plan["company"], plan_hash, user_id))

    def record_failure(self, tenant_id: str, batch_id: str, plan_hash: str, code: str) -> None:
        """Persist a sanitized failed-attempt record after successful rollback."""
        with self._lock:
            self.conn.execute("INSERT INTO import_failures(tenant_id,batch_id,plan_hash,code) VALUES(?,?,?,?)",
                              (tenant_id, batch_id, plan_hash, code))

    def records(self, tenant_id: str, company: str) -> list:
        """Internal, tenant-filtered probe for the offline conformance harness."""
        rows = self.conn.execute("""SELECT entity,business_key,row_json FROM import_records
            WHERE tenant_id=? AND company=? ORDER BY entity,business_key""", (tenant_id, company)).fetchall()
        return [{"entity": r["entity"], "key": r["business_key"], "row": json.loads(r["row_json"])} for r in rows]

    def failures(self, tenant_id: str) -> list:
        """Internal sanitized failure trail; never contains source cells."""
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM import_failures WHERE tenant_id=? ORDER BY seq", (tenant_id,))]

    def close(self):
        """Release the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
