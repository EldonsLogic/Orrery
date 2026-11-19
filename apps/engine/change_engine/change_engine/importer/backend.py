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
from .validation import MASTER_FIELDS, OPENING_FIELDS, canonical


class ImportBackend(Protocol):
    """Trusted server dependency; no request may inject a backend or session.

    transaction serializes competing batches and rolls back ALL writes, including
    updates and the journal, on exceptions. A failed rollback must raise recovery.
    write must preserve Decimal values, use native permission checks in a runtime
    implementation, and must not commit. Journal uniqueness is tenant/batch;
    claim_opening must also serialize opening claims per tenant/company (including
    any legacy postings). identity exposes mapped capabilities, not engine roles.
    master reads and prior-value audit snapshots share that transaction.
    """

    def identity(self) -> dict: ...
    def master(self, tenant_id: str, company: str, entity: str, key: str) -> dict | None: ...
    def claim_opening(self, tenant_id: str, company: str, batch_id: str) -> None: ...
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
            CREATE TABLE IF NOT EXISTS import_openings (
                tenant_id TEXT NOT NULL, company TEXT NOT NULL, batch_id TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company));
            CREATE TABLE IF NOT EXISTS import_master_changes (
                tenant_id TEXT NOT NULL, batch_id TEXT NOT NULL, entity TEXT NOT NULL,
                business_key TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
                PRIMARY KEY (tenant_id, batch_id, entity, business_key));
            CREATE TABLE IF NOT EXISTS import_failures (
                seq INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, batch_id TEXT NOT NULL,
                plan_hash TEXT NOT NULL, code TEXT NOT NULL);
        """)
        # Older offline databases keep their journal; missing source evidence fails
        # closed on retries. Existing opening records are checked by claim_opening.
        if "source_digest" not in {r[1] for r in self.conn.execute("PRAGMA table_info(import_batches)")}:
            self.conn.execute("ALTER TABLE import_batches ADD COLUMN source_digest TEXT")

    def identity(self) -> dict:
        """Resolve the trusted session; callback errors never grant permissions."""
        try:
            session = self._session() if self._session else {}
            if not isinstance(session, dict):
                return {}
            identity = dict(session)
            # Offline compatibility mapping only. Live mapping needs Q-303 /
            # ADR-0039 verification; no role/capability is accepted from payloads.
            roles = identity.get("roles", ())
            if "capabilities" not in identity:
                identity["capabilities"] = (["opening_import"] if isinstance(roles, (list, tuple, set, frozenset))
                                             and {"Accounts Manager", "System Manager"}.intersection(roles) else [])
            return identity
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
        if not row:
            return None
        result = dict(row)
        result["master_changes"] = [{"entity": r["entity"], "key": r["business_key"],
                                     "before": json.loads(r["before_json"]), "after": json.loads(r["after_json"])}
                                    for r in self.conn.execute("""SELECT * FROM import_master_changes
                                        WHERE tenant_id=? AND batch_id=? ORDER BY entity,business_key""", (tenant_id, batch_id))]
        return result

    def master(self, tenant_id: str, company: str, entity: str, key: str) -> dict | None:
        """Read one exact master key, scoped to the authenticated company."""
        if entity not in MASTER_FIELDS:
            raise ImportFailure("IMP-REFERENCE")
        with self._lock:
            row = self.conn.execute("""SELECT row_json FROM import_records
                WHERE tenant_id=? AND company=? AND entity=? AND business_key=?""",
                                    (tenant_id, company, entity, key)).fetchone()
        return json.loads(row[0]) if row else None

    def claim_opening(self, tenant_id: str, company: str, batch_id: str) -> None:
        """Claim once per company inside the write transaction, including old DBs.

        No supersede/reversal path is implemented; a later opening fails closed.
        Master-only imports do not claim an opening.
        """
        placeholders = ",".join("?" for _ in OPENING_FIELDS)
        legacy = self.conn.execute(f"""SELECT 1 FROM import_records
            WHERE tenant_id=? AND company=? AND entity IN ({placeholders}) LIMIT 1""",
                                   (tenant_id, company, *OPENING_FIELDS)).fetchone()
        if legacy:
            raise ImportFailure("IMP-OPENING-CONFLICT")
        try:
            self.conn.execute("INSERT INTO import_openings VALUES (?,?,?)", (tenant_id, company, batch_id))
        except sqlite3.IntegrityError:
            raise ImportFailure("IMP-OPENING-CONFLICT") from None

    def write(self, tenant_id: str, company: str, entity: str, key: str, row: dict) -> None:
        """Upsert a master or batch-scoped opening record without committing."""
        self.conn.execute("""INSERT INTO import_records VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id,company,entity,business_key) DO UPDATE SET row_json=excluded.row_json""",
                          (tenant_id, company, entity, key, canonical(row)))

    def commit_batch(self, plan: dict, plan_hash: str, user_id: str) -> None:
        """Journal confirmation in the SAME transaction as the business writes."""
        self.conn.execute("""INSERT INTO import_batches
            (tenant_id,batch_id,company,plan_hash,confirmed_by,status,source_digest) VALUES (?, ?, ?, ?, ?, 'applied', ?)""",
                          (plan["tenant_id"], plan["batch_id"], plan["company"], plan_hash, user_id, plan["source_digest"]))
        for change in plan["master_changes"]:
            self.conn.execute("INSERT INTO import_master_changes VALUES (?,?,?,?,?,?)",
                              (plan["tenant_id"], plan["batch_id"], change["entity"], change["key"],
                               canonical(change["before"]), canonical(change["after"])))

    def record_failure(self, tenant_id: str, batch_id: str, plan_hash: str, code: str) -> None:
        """Persist a sanitized failed-attempt record after successful rollback."""
        with self.transaction():
            self.conn.execute("INSERT INTO import_failures(tenant_id,batch_id,plan_hash,code) VALUES(?,?,?,?)",
                              (tenant_id, batch_id, plan_hash, code))
            # Bounded ring per tenant; validation/auth refusals never reach here.
            self.conn.execute("""DELETE FROM import_failures WHERE tenant_id=? AND seq NOT IN
                (SELECT seq FROM import_failures WHERE tenant_id=? ORDER BY seq DESC LIMIT 256)""",
                              (tenant_id, tenant_id))

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
