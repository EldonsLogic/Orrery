"""SQLite-backed durable state and non-destructive tenant data store for ChangeEngineAdapter."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator


def _safe_table_name(tenant_id: str, entity_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\x00{entity_id}".encode("utf-8")).hexdigest()[:24]
    return f"tstore_{digest}"


def _safe_col_name(pointer: str) -> str:
    digest = hashlib.sha256(pointer.encode("utf-8")).hexdigest()[:24]
    return f"col_{digest}"


class IdempotencyConflict(RuntimeError):
    """A key is already bound to a different input hash; the binding is never rewritten."""


class TenantMismatch(RuntimeError):
    """A store bound to one tenant was asked about another one (a misrouted connection); nothing is read or written."""


PLATFORM_TENANT = "platform"  # the platform's own id (never a customer site; the engine refuses to provision it)


class _Locked(Exception):
    """Internal: the site lock was not free; rolls the key reservation back."""


class _SqliteConn:
    """sqlite3-shaped shim: autocommit outside `with`, BEGIN IMMEDIATE at depth 0, SAVEPOINTs when nested, thread-safe."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        self.raw, self.depth, self._lock = raw, 0, threading.RLock()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        with self._lock:
            return self.raw.execute(sql, params)

    def executescript(self, script: str) -> None:
        with self._lock:
            self.raw.executescript(script)

    def __enter__(self) -> "_SqliteConn":
        self._lock.acquire()
        self.raw.execute("BEGIN IMMEDIATE" if self.depth == 0 else f"SAVEPOINT sp{self.depth}")
        self.depth += 1
        return self

    def __exit__(self, exc_type: Any, *_: Any) -> None:
        try:
            self.depth -= 1
            if self.depth == 0:
                self.raw.execute("ROLLBACK" if exc_type is not None else "COMMIT")
            else:
                if exc_type is not None:
                    self.raw.execute(f"ROLLBACK TO SAVEPOINT sp{self.depth}")
                self.raw.execute(f"RELEASE SAVEPOINT sp{self.depth}")
        finally:
            self._lock.release()

    def close(self) -> None:
        self.raw.close()


class SiteRecord:
    """In-session representation synchronized cleanly with SQLite persistence."""

    def __init__(self, tenant_id: str, params: dict[str, Any]):
        self.tenant_id = tenant_id
        self.state = "ready"
        self.site_class = params["siteClass"]
        self.engine_target = copy.deepcopy(params["engineTarget"])
        self.blueprint_id = params["blueprintId"]
        self.country_pack = params["countryPack"]
        self.applied: dict[str, Any] | None = None
        self.applied_ids: set[str] = set()
        self.history: list[dict[str, Any]] = []
        self.lock: str | None = None
        self.config: dict[str, Any] = {
            "settings": {},
            "components": [],
            "locations": [],
            "entities": [],
            "roles": [],
            "workflows": [],
            "approvals": [],
            "reports": [],
        }
        self.retained: dict[str, dict[str, Any]] = {}
        self.sync_version: int = 0

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "siteClass": self.site_class,
            "engineTarget": copy.deepcopy(self.engine_target),
            "blueprintId": self.blueprint_id,
            "applied": copy.deepcopy(self.applied),
            "lockedBy": self.lock,
        }


class SQLiteAdapterStore:
    """Durable relational store backing sites, idempotency, plan evidence, journal, audit, events, members, and tenant field data."""

    # A SQLite file is durable but sits outside the tenant database backup boundary (ADR-0041): dev and tests only.
    production_grade = False
    _FOR_UPDATE = ""

    def __init__(self, db_path: str = ":memory:", tenant_id: str | None = None) -> None:
        self.db_path = db_path
        self.bound_tenant = tenant_id
        self.volatile = db_path in (":memory:", "")  # lost on restart; refused in production (ERP-026)
        raw = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        raw.row_factory = sqlite3.Row
        self.conn = _SqliteConn(raw)
        self.clock = time.time
        self.dropped_data: list[str] = []
        self._init_schema()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group several store calls into one commit; an exception rolls all of them back."""
        with self.conn:
            yield

    def _check_tenant(self, tenant_id: str | None) -> None:
        """Tenant binding (ADR-0041): a store built with tenant_id refuses every other tenant, so a misrouted connection
        can neither read nor write across tenants. The platform id is allowed (health and capabilities use it); an
        unbound store (dev, tests, the conformance harness) serves any tenant."""
        if self.bound_tenant is not None and tenant_id is not None and tenant_id not in (self.bound_tenant, PLATFORM_TENANT):
            raise TenantMismatch("this adapter store is bound to another tenant")

    def lock_site_row(self, tenant_id: str) -> None:
        """Take the database row lock on the tenant's site row until the surrounding transaction ends, so two writers of
        the same tenant (sync_members) run one after the other. Needs an open store.transaction()."""
        self._check_tenant(tenant_id)
        if self.conn.depth == 0:
            raise RuntimeError("lock_site_row needs an open store.transaction(): the lock lasts until it ends")
        self.conn.execute("SELECT tenant_id FROM adapter_sites WHERE tenant_id = ?" + self._FOR_UPDATE, (tenant_id,)).fetchall()

    @staticmethod
    def _site_from_row(row: Any) -> SiteRecord:
        params = {
            "siteClass": row["site_class"],
            "engineTarget": json.loads(row["engine_target_json"]),
            "blueprintId": row["blueprint_id"],
            "countryPack": row["country_pack"],
        }
        site = SiteRecord(row["tenant_id"], params)
        site.state = row["state"]
        site.applied = json.loads(row["applied_json"]) if row["applied_json"] else None
        site.applied_ids = set(json.loads(row["applied_ids_json"]))
        site.history = json.loads(row["history_json"])
        site.lock = row["lock_id"]
        site.sync_version = int(row["sync_version"])
        site.config = json.loads(row["config_json"])
        site.retained = json.loads(row["retained_json"])
        return site

    def _init_schema(self) -> None:
        self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS adapter_sites (
                    tenant_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    site_class TEXT NOT NULL,
                    engine_target_json TEXT NOT NULL,
                    blueprint_id TEXT NOT NULL,
                    country_pack TEXT NOT NULL,
                    applied_json TEXT,
                    applied_ids_json TEXT NOT NULL,
                    history_json TEXT NOT NULL,
                    lock_id TEXT,
                    sync_version INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    retained_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adapter_idempotency (
                    tenant_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'done',
                    operation_id TEXT,
                    lease_expires_at INTEGER,
                    meta_json TEXT,
                    PRIMARY KEY (tenant_id, operation, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS adapter_plan_tokens (
                    tenant_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    issued_at INTEGER NOT NULL,
                    PRIMARY KEY (tenant_id, token)
                );
                CREATE TABLE IF NOT EXISTS adapter_plan_evidence (
                    tenant_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    statements_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, evidence_ref)
                );
                CREATE TABLE IF NOT EXISTS adapter_prepare_intents (
                    operation_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adapter_execution_journal (
                    seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    step_seq INTEGER NOT NULL,
                    phase TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adapter_audit_log (
                    seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT UNIQUE NOT NULL,
                    operation TEXT NOT NULL,
                    request_id TEXT,
                    correlation_id TEXT,
                    tenant_id TEXT,
                    service TEXT,
                    on_behalf_of_json TEXT,
                    input_hash TEXT,
                    artifact_id TEXT,
                    result TEXT
                );
                CREATE TABLE IF NOT EXISTS adapter_events (
                    seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT,
                    event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adapter_members (
                    tenant_id TEXT NOT NULL,
                    member_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    role_ids_json TEXT NOT NULL,
                    display_name TEXT,
                    can_authenticate INTEGER NOT NULL DEFAULT 0,
                    email_sent INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, member_ref)
                );
                """
            )

    def reset(self) -> None:
        self.dropped_data.clear()
        cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'tstore_%'")
        dynamic_tables = [row["name"] for row in cur.fetchall()]
        with self.conn:
            for tbl in dynamic_tables:
                self.conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
            for tbl in (
                "adapter_sites",
                "adapter_idempotency",
                "adapter_plan_tokens",
                "adapter_plan_evidence",
                "adapter_prepare_intents",
                "adapter_execution_journal",
                "adapter_audit_log",
                "adapter_events",
                "adapter_members",
            ):
                self.conn.execute(f"DELETE FROM {tbl}")

    # ------------------------------------------------------------------ sites
    _SITE_COLS = (
        "tenant_id, state, site_class, engine_target_json, blueprint_id, country_pack, applied_json, "
        "applied_ids_json, history_json, lock_id, sync_version, config_json, retained_json"
    )

    def get_site(self, tenant_id: str) -> SiteRecord | None:
        """Always read from the database: another worker may have changed the row (no in-process cache)."""
        self._check_tenant(tenant_id)
        row = self.conn.execute(f"SELECT {self._SITE_COLS} FROM adapter_sites WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return self._site_from_row(row) if row is not None else None

    def hydrate_site(self, site: SiteRecord) -> SiteRecord:
        self.save_site(site)
        return site

    def create_site(self, tenant_id: str, params: dict[str, Any]) -> SiteRecord:
        self._check_tenant(tenant_id)
        site = SiteRecord(tenant_id, params)
        self.save_site(site)
        return site

    def save_site(self, site: SiteRecord) -> None:
        """Upsert the site. sync_version is only set on insert; it moves through set_sync_version (compare and set)."""
        self._check_tenant(site.tenant_id)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_sites (
                    tenant_id, state, site_class, engine_target_json, blueprint_id,
                    country_pack, applied_json, applied_ids_json, history_json,
                    lock_id, sync_version, config_json, retained_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    state = excluded.state,
                    site_class = excluded.site_class,
                    engine_target_json = excluded.engine_target_json,
                    blueprint_id = excluded.blueprint_id,
                    country_pack = excluded.country_pack,
                    applied_json = excluded.applied_json,
                    applied_ids_json = excluded.applied_ids_json,
                    history_json = excluded.history_json,
                    lock_id = excluded.lock_id,
                    config_json = excluded.config_json,
                    retained_json = excluded.retained_json
                """,
                (
                    site.tenant_id,
                    site.state,
                    site.site_class,
                    json.dumps(site.engine_target),
                    site.blueprint_id,
                    site.country_pack,
                    json.dumps(site.applied) if site.applied is not None else None,
                    json.dumps(sorted(site.applied_ids)),
                    json.dumps(site.history),
                    site.lock,
                    site.sync_version,
                    json.dumps(site.config),
                    json.dumps(site.retained),
                ),
            )

    def set_sync_version(self, tenant_id: str, version: int) -> bool:
        """Compare and set: only moves the version forward. False when another worker already holds a newer or equal one."""
        self._check_tenant(tenant_id)
        with self.conn:
            cur = self.conn.execute(
                "UPDATE adapter_sites SET sync_version = ? WHERE tenant_id = ? AND sync_version < ?", (version, tenant_id, version)
            )
            return cur.rowcount == 1

    # ------------------------------------------------------------------ idempotency (reserve, complete, recover)
    def _insert_reservation(self, row: tuple) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO adapter_idempotency (tenant_id, operation, idempotency_key, input_hash, outcome_json, "
            "status, operation_id, lease_expires_at, meta_json) VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, ?)",
            row,
        )
        return cur.rowcount == 1

    def acquire_operation(
        self,
        tenant_id: str,
        operation: str,
        key: str,
        input_hash: str,
        operation_id: str,
        pending: dict[str, Any],
        meta: dict[str, Any],
        *,
        lock: bool,
        lease_seconds: int,
    ) -> tuple[str, Any]:
        """Atomically bind the key to its input and, when asked, take the site lock, in one committed transaction.

        Returns ("acquired", info), ("replay", stored outcome), ("in_progress", {"outcome", "expired"}),
        ("conflict", None) for the same key with other input, or ("locked", None) when the site lock is held. With
        lock=True, info is {"ready_before": bool}: True when this call moved the site from ready (or an orphaned
        applying, left by no lock holder) to applying, so the run knows it must put it back; decided in the same
        transaction as the lock, never from an earlier read. Without a lock, info is None.
        Two workers racing on one key: the unique key lets exactly one INSERT succeed; no in-process state is consulted.
        """
        self._check_tenant(tenant_id)
        now = int(self.clock())
        row = (tenant_id, operation, key, input_hash, json.dumps(pending), operation_id, now + int(lease_seconds), json.dumps(meta))
        try:
            with self.conn:
                if self._insert_reservation(row):
                    if lock:
                        prior = self.conn.execute(
                            "SELECT state FROM adapter_sites WHERE tenant_id = ?" + self._FOR_UPDATE, (tenant_id,)
                        ).fetchone()
                        cur = self.conn.execute(
                            "UPDATE adapter_sites SET lock_id = ?, "
                            "state = CASE WHEN state IN ('ready', 'applying') THEN 'applying' ELSE state END "
                            "WHERE tenant_id = ? AND lock_id IS NULL",
                            (operation_id, tenant_id),
                        )
                        if cur.rowcount != 1:
                            raise _Locked()
                        return "acquired", {"ready_before": prior is not None and prior["state"] in ("ready", "applying")}
                    return "acquired", None
                found = self.conn.execute(
                    "SELECT input_hash, status, outcome_json, lease_expires_at FROM adapter_idempotency "
                    "WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?" + self._FOR_UPDATE,
                    (tenant_id, operation, key),
                ).fetchone()
        except _Locked:
            return "locked", None
        if found["input_hash"] != input_hash:
            return "conflict", None
        outcome = json.loads(found["outcome_json"])
        if found["status"] == "done":
            return "replay", outcome
        expired = found["lease_expires_at"] is not None and int(found["lease_expires_at"]) < now
        return "in_progress", {"outcome": outcome, "expired": expired}

    def idem_complete(self, tenant_id: str, operation: str, key: str, operation_id: str, outcome: dict[str, Any]) -> bool:
        """Store the final outcome; compare and set on the reservation, so a worker that lost its lease gets False."""
        self._check_tenant(tenant_id)
        with self.conn:
            cur = self.conn.execute(
                "UPDATE adapter_idempotency SET outcome_json = ?, status = 'done', lease_expires_at = NULL "
                "WHERE tenant_id = ? AND operation = ? AND idempotency_key = ? AND operation_id = ? AND status = 'in_progress'",
                (json.dumps(outcome), tenant_id, operation, key, operation_id),
            )
            return cur.rowcount == 1

    def idem_release(self, tenant_id: str, operation: str, key: str, operation_id: str) -> None:
        """Drop an unfinished reservation (a refusal before the operation record exists stores nothing, contract 5.6.1)."""
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                "DELETE FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ? "
                "AND operation_id = ? AND status = 'in_progress'",
                (tenant_id, operation, key, operation_id),
            )

    def operation_owned(self, tenant_id: str, operation: str, key: str, operation_id: str) -> bool:
        """True while this worker still owns the operation: its reservation is in_progress with an unexpired lease and the
        site lock still names it. A worker checks before every engine step and stops at once when this turns False."""
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT 1 AS ok FROM adapter_idempotency i JOIN adapter_sites s ON s.tenant_id = i.tenant_id "
            "WHERE i.tenant_id = ? AND i.operation = ? AND i.idempotency_key = ? AND i.operation_id = ? "
            "AND i.status = 'in_progress' AND i.lease_expires_at >= ? AND s.lock_id = ?",
            (tenant_id, operation, key, operation_id, int(self.clock()), operation_id),
        ).fetchone()
        return row is not None

    def idem_status(self, tenant_id: str, operation: str, key: str) -> tuple[str, dict[str, Any]] | None:
        """(status, outcome) of a key: 'done' with the stored outcome, or 'in_progress' with the pending one."""
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT status, outcome_json FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?",
            (tenant_id, operation, key),
        ).fetchone()
        return None if row is None else (row["status"], json.loads(row["outcome_json"]))

    def expired_operations(self) -> list[dict[str, Any]]:
        where, args = ("AND tenant_id = ? ", (self.bound_tenant,)) if self.bound_tenant is not None else ("", ())
        rows = self.conn.execute(
            "SELECT tenant_id, operation, idempotency_key, operation_id, outcome_json, meta_json FROM adapter_idempotency "
            "WHERE status = 'in_progress' " + where + "AND lease_expires_at < ?",
            (*args, int(self.clock())),
        ).fetchall()
        return [
            {
                "tenant": r["tenant_id"],
                "operation": r["operation"],
                "key": r["idempotency_key"],
                "operationId": r["operation_id"],
                "pending": json.loads(r["outcome_json"]),
                "meta": json.loads(r["meta_json"] or "{}"),
            }
            for r in rows
        ]

    def recover_operation(self, rec: dict[str, Any], final: dict[str, Any] | None) -> bool:
        """Close an expired operation exactly once. With `final`, store it as the outcome and put the site in
        recovery_required (lock cleared); without, release the reservation. False when another worker got there first."""
        self._check_tenant(rec["tenant"])
        with self.conn:
            if final is None:
                cur = self.conn.execute(
                    "DELETE FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ? "
                    "AND operation_id = ? AND status = 'in_progress'",
                    (rec["tenant"], rec["operation"], rec["key"], rec["operationId"]),
                )
            else:
                cur = self.conn.execute(
                    "UPDATE adapter_idempotency SET outcome_json = ?, status = 'done', lease_expires_at = NULL "
                    "WHERE tenant_id = ? AND operation = ? AND idempotency_key = ? AND operation_id = ? AND status = 'in_progress'",
                    (json.dumps(final), rec["tenant"], rec["operation"], rec["key"], rec["operationId"]),
                )
            if cur.rowcount != 1:
                return False
            if final is not None:
                self.conn.execute(
                    "UPDATE adapter_sites SET state = 'recovery_required', lock_id = NULL WHERE tenant_id = ? AND lock_id = ?",
                    (rec["tenant"], rec["operationId"]),
                )
            return True

    def idem_get(self, tenant_id: str, operation: str, key: str) -> tuple[str, dict[str, Any]] | None:
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT input_hash, outcome_json FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?",
            (tenant_id, operation, key),
        ).fetchone()
        if row is None:
            return None
        return row["input_hash"], json.loads(row["outcome_json"])

    def idem_put(self, tenant_id: str, operation: str, key: str, input_hash: str, outcome: dict[str, Any]) -> None:
        """Insert a finished key. The same key with the same input updates the outcome; other input raises, never rebinds."""
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO adapter_idempotency (tenant_id, operation, idempotency_key, input_hash, outcome_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (tenant_id, operation, key, input_hash, json.dumps(outcome)),
            )
            cur = self.conn.execute(
                "UPDATE adapter_idempotency SET outcome_json = ?, status = 'done' "
                "WHERE tenant_id = ? AND operation = ? AND idempotency_key = ? AND input_hash = ?",
                (json.dumps(outcome), tenant_id, operation, key, input_hash),
            )
            if cur.rowcount != 1:
                raise IdempotencyConflict(f"{operation}/{key} is bound to a different input")

    # ------------------------------------------------------------------ tokens and evidence
    def save_token(self, tenant_id: str, token: str, issued_at: int) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_plan_tokens (tenant_id, token, issued_at)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id, token) DO UPDATE SET issued_at = excluded.issued_at
                """,
                (tenant_id, token, issued_at),
            )

    def get_token_issued_at(self, tenant_id: str, token: str) -> int | None:
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT issued_at FROM adapter_plan_tokens WHERE tenant_id = ? AND token = ?",
            (tenant_id, token),
        ).fetchone()
        return int(row["issued_at"]) if row is not None else None

    def save_evidence(self, tenant_id: str, evidence_ref: str, statements: list[str]) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_plan_evidence (tenant_id, evidence_ref, statements_json)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id, evidence_ref) DO UPDATE SET statements_json = excluded.statements_json
                """,
                (tenant_id, evidence_ref, json.dumps(statements)),
            )

    def get_evidence(self, tenant_id: str, evidence_ref: str) -> list[str]:
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT statements_json FROM adapter_plan_evidence WHERE tenant_id = ? AND evidence_ref = ?",
            (tenant_id, evidence_ref),
        ).fetchone()
        if row is None:
            raise KeyError(evidence_ref)
        return list(json.loads(row["statements_json"]))

    # ------------------------------------------------------------------ prepare & journal
    def save_prepare_intent(self, operation_id: str, tenant_id: str, artifact_id: str, payload: dict[str, Any]) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_prepare_intents (operation_id, tenant_id, artifact_id, payload_json, status)
                VALUES (?, ?, ?, ?, 'PREPARED')
                ON CONFLICT(operation_id) DO UPDATE SET payload_json = excluded.payload_json, status = excluded.status
                """,
                (operation_id, tenant_id, artifact_id, json.dumps(payload)),
            )

    def append_journal(self, tenant_id: str, artifact_id: str, seq: int, phase: str) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                "INSERT INTO adapter_execution_journal (tenant_id, artifact_id, step_seq, phase) VALUES (?, ?, ?, ?)",
                (tenant_id, artifact_id, seq, phase),
            )

    def execution_journal(self) -> list[dict[str, Any]]:
        where, args = ("WHERE tenant_id = ? ", (self.bound_tenant,)) if self.bound_tenant is not None else ("", ())
        rows = self.conn.execute(
            "SELECT artifact_id, step_seq, phase FROM adapter_execution_journal " + where + "ORDER BY seq_id ASC", args
        ).fetchall()
        return [{"artifactId": r["artifact_id"], "seq": int(r["step_seq"]), "phase": r["phase"]} for r in rows]

    # ------------------------------------------------------------------ audit & events
    def insert_audit(self, record: dict[str, Any]) -> None:
        self._check_tenant(record["tenant"])
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_audit_log (
                    audit_id, operation, request_id, correlation_id, tenant_id,
                    service, on_behalf_of_json, input_hash, artifact_id, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["auditId"],
                    record["operation"],
                    record["requestId"],
                    record["correlationId"],
                    record["tenant"],
                    record["service"],
                    json.dumps(record["onBehalfOf"]) if record["onBehalfOf"] is not None else None,
                    record["inputHash"],
                    record["artifactId"],
                    record["result"],
                ),
            )

    def update_audit(self, record: dict[str, Any]) -> None:
        self._check_tenant(record["tenant"])
        with self.conn:
            self.conn.execute(
                """
                UPDATE adapter_audit_log SET
                    request_id = ?, correlation_id = ?, tenant_id = ?, service = ?,
                    on_behalf_of_json = ?, input_hash = ?, artifact_id = ?, result = ?
                WHERE audit_id = ?
                """,
                (
                    record["requestId"],
                    record["correlationId"],
                    record["tenant"],
                    record["service"],
                    json.dumps(record["onBehalfOf"]) if record["onBehalfOf"] is not None else None,
                    record["inputHash"],
                    record["artifactId"],
                    record["result"],
                    record["auditId"],
                ),
            )

    def audit_log(self) -> list[dict[str, Any]]:
        where, args = ("WHERE tenant_id = ? ", (self.bound_tenant,)) if self.bound_tenant is not None else ("", ())
        rows = self.conn.execute(
            "SELECT audit_id, operation, request_id, correlation_id, tenant_id, service, on_behalf_of_json, input_hash, artifact_id, result "
            "FROM adapter_audit_log " + where + "ORDER BY seq_id ASC", args
        ).fetchall()
        return [
            {
                "auditId": r["audit_id"],
                "operation": r["operation"],
                "requestId": r["request_id"],
                "correlationId": r["correlation_id"],
                "tenant": r["tenant_id"],
                "service": r["service"],
                "onBehalfOf": json.loads(r["on_behalf_of_json"]) if r["on_behalf_of_json"] else None,
                "inputHash": r["input_hash"],
                "artifactId": r["artifact_id"],
                "result": r["result"],
            }
            for r in rows
        ]

    def append_event(self, event_id: str, event_type: str, data: dict[str, Any], tenant_id: str | None = None) -> None:
        """Append an event for a tenant. A bound store stamps its own tenant when none is given."""
        self._check_tenant(tenant_id)
        tenant_id = tenant_id if tenant_id is not None else self.bound_tenant
        with self.conn:
            self.conn.execute(
                "INSERT INTO adapter_events (tenant_id, event_id, event_type, data_json) VALUES (?, ?, ?, ?)",
                (tenant_id, event_id, event_type, json.dumps(data)),
            )

    def events(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """Events of one tenant. A bound store only ever returns its own tenant's; an unbound one returns every tenant's
        unless a tenant_id is given (dev, tests and the conformance harness read the whole stream)."""
        self._check_tenant(tenant_id)
        scope = tenant_id if tenant_id is not None else self.bound_tenant
        where, args = ("WHERE tenant_id = ? ", (scope,)) if scope is not None else ("", ())
        rows = self.conn.execute(
            "SELECT event_id, event_type, data_json FROM adapter_events " + where + "ORDER BY seq_id ASC", args
        ).fetchall()
        return [{"eventId": r["event_id"], "type": r["event_type"], "data": json.loads(r["data_json"])} for r in rows]

    # ------------------------------------------------------------------ members (shadow users)
    def get_members(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        self._check_tenant(tenant_id)
        rows = self.conn.execute(
            "SELECT member_ref, status, role_ids_json, display_name, can_authenticate, email_sent FROM adapter_members WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        return {
            r["member_ref"]: {
                "status": r["status"],
                "roleIds": json.loads(r["role_ids_json"]),
                "displayName": r["display_name"],
                "canAuthenticate": bool(r["can_authenticate"]),
                "emailSent": bool(r["email_sent"]),
            }
            for r in rows
        }

    def replace_members(self, tenant_id: str, members: dict[str, dict[str, Any]]) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            for ref, rec in members.items():
                self.conn.execute(
                    """
                    INSERT INTO adapter_members (tenant_id, member_ref, status, role_ids_json, display_name, can_authenticate, email_sent)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                    ON CONFLICT(tenant_id, member_ref) DO UPDATE SET
                        status = excluded.status,
                        role_ids_json = excluded.role_ids_json,
                        display_name = excluded.display_name,
                        can_authenticate = 0,
                        email_sent = 0
                    """,
                    (tenant_id, ref, rec["status"], json.dumps(rec["roleIds"]), rec.get("displayName")),
                )

    def get_member(self, tenant_id: str, member_ref: str) -> dict[str, Any] | None:
        self._check_tenant(tenant_id)
        row = self.conn.execute(
            "SELECT status, role_ids_json, display_name, can_authenticate, email_sent FROM adapter_members WHERE tenant_id = ? AND member_ref = ?",
            (tenant_id, member_ref),
        ).fetchone()
        if row is None:
            return None
        return {
            "status": row["status"],
            "roleIds": json.loads(row["role_ids_json"]),
            "displayName": row["display_name"],
            "canAuthenticate": bool(row["can_authenticate"]),
            "emailSent": bool(row["email_sent"]),
        }

    # ------------------------------------------------------------------ additive tenant data storage (zero-drop)
    def ensure_entity_table(self, tenant_id: str, entity_id: str) -> str:
        self._check_tenant(tenant_id)
        tbl = _safe_table_name(tenant_id, entity_id)
        with self.conn:
            self.conn.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" (row_id TEXT PRIMARY KEY)')
        return tbl

    def ensure_field_column(self, tenant_id: str, entity_id: str, pointer: str) -> tuple[str, str]:
        self._check_tenant(tenant_id)
        tbl = self.ensure_entity_table(tenant_id, entity_id)
        col = _safe_col_name(pointer)
        existing = {
            row["name"]
            for row in self.conn.execute(f'PRAGMA table_info("{tbl}")').fetchall()
        }
        if col not in existing:
            with self.conn:
                self.conn.execute(f'ALTER TABLE "{tbl}" ADD COLUMN "{col}" TEXT')
        return tbl, col

    def write_field_data(self, tenant_id: str, entity_id: str, pointer: str, value: Any) -> Any:
        self._check_tenant(tenant_id)
        tbl, col = self.ensure_field_column(tenant_id, entity_id, pointer)
        encoded = json.dumps(value)
        with self.conn:
            self.conn.execute(
                f'INSERT INTO "{tbl}" (row_id, "{col}") VALUES (?, ?) ON CONFLICT(row_id) DO UPDATE SET "{col}" = excluded."{col}"',
                ("default_row", encoded),
            )
        return self.read_field_data(tenant_id, entity_id, pointer)

    def read_field_data(self, tenant_id: str, entity_id: str, pointer: str) -> Any:
        self._check_tenant(tenant_id)
        tbl = _safe_table_name(tenant_id, entity_id)
        col = _safe_col_name(pointer)
        table_exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (tbl,),
        ).fetchone()
        if table_exists is None:
            return None
        cols = {row["name"] for row in self.conn.execute(f'PRAGMA table_info("{tbl}")').fetchall()}
        if col not in cols:
            return None
        row = self.conn.execute(f'SELECT "{col}" FROM "{tbl}" WHERE row_id = ?', ("default_row",)).fetchone()
        if row is None or row[col] is None:
            return None
        return json.loads(row[col])
