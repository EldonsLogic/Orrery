"""MariaDB-backed adapter state living beside the tenant data (ERP-026, ADR-0041).

One schema per tenant database; every table keeps its tenant_id column anyway so a misrouted
connection cannot read another tenant's rows. Shares the read paths of SQLiteAdapterStore through
a small connection shim and overrides the schema and every upsert with MariaDB SQL.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from change_engine.adapter.storage import (
    IdempotencyConflict,
    SQLiteAdapterStore,
    SiteRecord,
    _safe_col_name,
    _safe_table_name,
)

_T = "VARCHAR(128) NOT NULL"  # tenantId is up to 65 characters (common.schema.json); headroom for the platform id
_SCHEMA = [
    f"CREATE TABLE IF NOT EXISTS adapter_sites (tenant_id {_T}, state VARCHAR(32) NOT NULL, site_class VARCHAR(32) NOT NULL,"
    " engine_target_json LONGTEXT NOT NULL, blueprint_id VARCHAR(128) NOT NULL, country_pack VARCHAR(64) NOT NULL,"
    " applied_json LONGTEXT, applied_ids_json LONGTEXT NOT NULL, history_json LONGTEXT NOT NULL, lock_id VARCHAR(128),"
    " sync_version BIGINT NOT NULL, config_json LONGTEXT NOT NULL, retained_json LONGTEXT NOT NULL, PRIMARY KEY (tenant_id))",
    f"CREATE TABLE IF NOT EXISTS adapter_idempotency (tenant_id {_T}, operation VARCHAR(32) NOT NULL,"
    " idempotency_key VARCHAR(255) NOT NULL, input_hash VARCHAR(80) NOT NULL, outcome_json LONGTEXT NOT NULL,"
    " status VARCHAR(16) NOT NULL DEFAULT 'done', operation_id VARCHAR(128), lease_expires_at BIGINT, meta_json LONGTEXT,"
    " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (tenant_id, operation, idempotency_key),"
    " KEY ix_idem_lease (status, lease_expires_at), KEY ix_idem_created (created_at))",
    f"CREATE TABLE IF NOT EXISTS adapter_plan_tokens (tenant_id {_T}, token VARCHAR(128) NOT NULL,"
    " issued_at BIGINT NOT NULL, PRIMARY KEY (tenant_id, token))",
    f"CREATE TABLE IF NOT EXISTS adapter_plan_evidence (tenant_id {_T}, evidence_ref VARCHAR(128) NOT NULL,"
    " statements_json LONGTEXT NOT NULL, PRIMARY KEY (tenant_id, evidence_ref))",
    f"CREATE TABLE IF NOT EXISTS adapter_prepare_intents (operation_id VARCHAR(128) NOT NULL, tenant_id {_T},"
    " artifact_id VARCHAR(128) NOT NULL, payload_json LONGTEXT NOT NULL, status VARCHAR(32) NOT NULL, PRIMARY KEY (operation_id))",
    f"CREATE TABLE IF NOT EXISTS adapter_execution_journal (seq_id BIGINT NOT NULL AUTO_INCREMENT, tenant_id {_T},"
    " artifact_id VARCHAR(128) NOT NULL, step_seq INT NOT NULL, phase VARCHAR(32) NOT NULL, PRIMARY KEY (seq_id))",
    "CREATE TABLE IF NOT EXISTS adapter_audit_log (seq_id BIGINT NOT NULL AUTO_INCREMENT, audit_id VARCHAR(64) NOT NULL,"
    " operation VARCHAR(32) NOT NULL, request_id VARCHAR(128), correlation_id VARCHAR(128), tenant_id VARCHAR(128),"
    " service VARCHAR(64), on_behalf_of_json LONGTEXT, input_hash VARCHAR(80), artifact_id VARCHAR(128), result VARCHAR(64),"
    " PRIMARY KEY (seq_id), UNIQUE KEY uq_audit_id (audit_id))",
    "CREATE TABLE IF NOT EXISTS adapter_events (seq_id BIGINT NOT NULL AUTO_INCREMENT, tenant_id VARCHAR(128),"
    " event_id VARCHAR(128) NOT NULL, event_type VARCHAR(64) NOT NULL, data_json LONGTEXT NOT NULL, PRIMARY KEY (seq_id),"
    " KEY ix_events_tenant (tenant_id, seq_id))",
    f"CREATE TABLE IF NOT EXISTS adapter_members (tenant_id {_T}, member_ref VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL,"
    " role_ids_json LONGTEXT NOT NULL, display_name VARCHAR(255), can_authenticate TINYINT NOT NULL DEFAULT 0,"
    " email_sent TINYINT NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id, member_ref))",
]
_STATE_TABLES = ("adapter_sites", "adapter_idempotency", "adapter_plan_tokens", "adapter_plan_evidence",
                 "adapter_prepare_intents", "adapter_execution_journal", "adapter_audit_log", "adapter_events", "adapter_members")


class _Conn:
    """sqlite3-shaped shim over a DB-API connection: `?` params, dict rows, commit or rollback on `with`.

    Nested `with` blocks are SAVEPOINTs, so an inner failure the caller catches undoes only the inner work.
    One connection serves one thread at a time (re-entrant lock held for the whole outer transaction)."""

    def __init__(self, raw: Any) -> None:
        self.raw = raw
        self.depth = 0
        self._lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        import pymysql.cursors  # driver comes from the bench; imported lazily so the SQLite path needs none

        with self._lock:
            cur = self.raw.cursor(pymysql.cursors.DictCursor)
            cur.execute(sql.replace("?", "%s"), params or None)
            if self.depth == 0:  # a standalone read must not hold a transaction (and its metadata lock) open
                self.raw.commit()
            return cur

    def __enter__(self) -> "_Conn":
        self._lock.acquire()
        try:
            if self.depth > 0:
                self.raw.cursor().execute(f"SAVEPOINT sp{self.depth}")
        except BaseException:
            self._lock.release()
            raise
        self.depth += 1
        return self

    def __exit__(self, exc_type: Any, *_: Any) -> None:
        try:
            self.depth -= 1
            if self.depth == 0:
                self.raw.rollback() if exc_type is not None else self.raw.commit()
            else:
                cur = self.raw.cursor()
                if exc_type is not None:
                    cur.execute(f"ROLLBACK TO SAVEPOINT sp{self.depth}")
                cur.execute(f"RELEASE SAVEPOINT sp{self.depth}")
        finally:
            self._lock.release()

    def close(self) -> None:
        self.raw.close()


class MariaDBAdapterStore(SQLiteAdapterStore):
    """Adapter state in the tenant database. Pass the tenant DB connection (pymysql DictCursor, autocommit off).

    Pass tenant_id to bind the store to that tenant: every other tenant is refused and events, audit and journal reads
    return only that tenant's rows, so a misrouted connection cannot read or write across tenants (ADR-0041)."""

    volatile = False
    production_grade = True
    _FOR_UPDATE = " FOR UPDATE"

    def __init__(self, connection: Any, tenant_id: str | None = None) -> None:
        self.bound_tenant = tenant_id
        get_autocommit = getattr(connection, "get_autocommit", None)
        if callable(get_autocommit) and get_autocommit():
            raise ValueError("MariaDBAdapterStore needs a connection with autocommit off: the store owns its transactions")
        self.conn = _Conn(connection)
        self.clock = time.time
        self.dropped_data: list[str] = []
        self._init_schema()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group several store calls, or the caller's own effect on the same connection, into one commit.

        DDL (CREATE or ALTER TABLE) commits implicitly in MariaDB and is refused inside a transaction."""
        with self.conn:
            yield

    def _no_ddl_in_transaction(self) -> None:
        if self.conn.depth > 0:
            raise RuntimeError("DDL commits implicitly in MariaDB: not allowed inside store.transaction()")

    def _init_schema(self) -> None:
        for ddl in _SCHEMA:
            self.conn.execute(ddl + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")

    def _insert_reservation(self, row: tuple) -> bool:
        import pymysql

        try:
            self.conn.execute(
                "INSERT INTO adapter_idempotency (tenant_id, operation, idempotency_key, input_hash, outcome_json, status, "
                "operation_id, lease_expires_at, meta_json) VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, ?)",
                row,
            )
            return True
        except pymysql.err.IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:  # the key already exists: another caller holds or finished it
                return False
            raise

    def idem_put(self, tenant_id: str, operation: str, key: str, input_hash: str, outcome: dict[str, Any]) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            self.conn.execute(
                "INSERT INTO adapter_idempotency (tenant_id, operation, idempotency_key, input_hash, outcome_json) VALUES (?, ?, ?, ?, ?) "
                "ON DUPLICATE KEY UPDATE outcome_json = IF(input_hash = VALUES(input_hash), VALUES(outcome_json), outcome_json), "
                "status = IF(input_hash = VALUES(input_hash), 'done', status)",
                (tenant_id, operation, key, input_hash, json.dumps(outcome)),
            )
            row = self.conn.execute(
                "SELECT input_hash FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?",
                (tenant_id, operation, key),
            ).fetchone()
            if row["input_hash"] != input_hash:
                raise IdempotencyConflict(f"{operation}/{key} is bound to a different input")

    def _upsert(self, table: str, row: dict[str, Any], keys: tuple[str, ...], keep: tuple[str, ...] = ()) -> None:
        cols = ", ".join(f"`{c}`" for c in row)
        update = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in row if c not in keys and c not in keep)
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({', '.join('?' * len(row))}) ON DUPLICATE KEY UPDATE {update}"
        with self.conn:
            self.conn.execute(sql, tuple(row.values()))

    def reset(self) -> None:
        self.dropped_data.clear()
        rows = self.conn.execute(
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'tstore\\_%'"
        ).fetchall()
        with self.conn:
            for row in rows:
                self.conn.execute(f"DROP TABLE IF EXISTS `{row['name']}`")
            for tbl in _STATE_TABLES:
                self.conn.execute(f"DELETE FROM `{tbl}`")

    def save_site(self, site: SiteRecord) -> None:
        self._check_tenant(site.tenant_id)
        self._upsert("adapter_sites", {
            "tenant_id": site.tenant_id, "state": site.state, "site_class": site.site_class,
            "engine_target_json": json.dumps(site.engine_target), "blueprint_id": site.blueprint_id,
            "country_pack": site.country_pack,
            "applied_json": json.dumps(site.applied) if site.applied is not None else None,
            "applied_ids_json": json.dumps(sorted(site.applied_ids)), "history_json": json.dumps(site.history),
            "lock_id": site.lock, "sync_version": site.sync_version, "config_json": json.dumps(site.config),
            "retained_json": json.dumps(site.retained),
        }, ("tenant_id",), keep=("sync_version",))  # sync_version moves only through set_sync_version

    def save_token(self, tenant_id: str, token: str, issued_at: int) -> None:
        self._check_tenant(tenant_id)
        self._upsert("adapter_plan_tokens", {"tenant_id": tenant_id, "token": token, "issued_at": issued_at}, ("tenant_id", "token"))

    def save_evidence(self, tenant_id: str, evidence_ref: str, statements: list[str]) -> None:
        self._check_tenant(tenant_id)
        self._upsert("adapter_plan_evidence", {"tenant_id": tenant_id, "evidence_ref": evidence_ref,
                                               "statements_json": json.dumps(statements)}, ("tenant_id", "evidence_ref"))

    def save_prepare_intent(self, operation_id: str, tenant_id: str, artifact_id: str, payload: dict[str, Any]) -> None:
        self._check_tenant(tenant_id)
        self._upsert("adapter_prepare_intents", {"operation_id": operation_id, "tenant_id": tenant_id, "artifact_id": artifact_id,
                                                 "payload_json": json.dumps(payload), "status": "PREPARED"}, ("operation_id",))

    def replace_members(self, tenant_id: str, members: dict[str, dict[str, Any]]) -> None:
        self._check_tenant(tenant_id)
        with self.conn:
            for ref, rec in members.items():
                self._upsert("adapter_members", {
                    "tenant_id": tenant_id, "member_ref": ref, "status": rec["status"],
                    "role_ids_json": json.dumps(rec["roleIds"]), "display_name": rec.get("displayName"),
                    "can_authenticate": 0, "email_sent": 0,
                }, ("tenant_id", "member_ref"))

    # ------------------------------------------------ additive tenant field data (same shape as the SQLite store)
    def ensure_entity_table(self, tenant_id: str, entity_id: str) -> str:
        self._check_tenant(tenant_id)
        self._no_ddl_in_transaction()
        tbl = _safe_table_name(tenant_id, entity_id)
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS `{tbl}` (row_id VARCHAR(64) NOT NULL, PRIMARY KEY (row_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        return tbl

    def ensure_field_column(self, tenant_id: str, entity_id: str, pointer: str) -> tuple[str, str]:
        self._check_tenant(tenant_id)
        tbl, col = self.ensure_entity_table(tenant_id, entity_id), _safe_col_name(pointer)
        self.conn.execute(f"ALTER TABLE `{tbl}` ADD COLUMN IF NOT EXISTS `{col}` LONGTEXT")
        return tbl, col

    def write_field_data(self, tenant_id: str, entity_id: str, pointer: str, value: Any) -> Any:
        self._check_tenant(tenant_id)
        tbl, col = self.ensure_field_column(tenant_id, entity_id, pointer)
        self._upsert(tbl, {"row_id": "default_row", col: json.dumps(value, ensure_ascii=False)}, ("row_id",))
        return self.read_field_data(tenant_id, entity_id, pointer)

    def read_field_data(self, tenant_id: str, entity_id: str, pointer: str) -> Any:
        self._check_tenant(tenant_id)
        tbl, col = _safe_table_name(tenant_id, entity_id), _safe_col_name(pointer)
        found = self.conn.execute(
            "SELECT 1 AS ok FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
            (tbl, col),
        ).fetchone()
        if found is None:
            return None
        row = self.conn.execute(f"SELECT `{col}` AS v FROM `{tbl}` WHERE row_id = ?", ("default_row",)).fetchone()
        return None if row is None or row["v"] is None else json.loads(row["v"])
