"""SQLite-backed durable state and non-destructive tenant data store for ChangeEngineAdapter."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from typing import Any


def _safe_table_name(tenant_id: str, entity_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\x00{entity_id}".encode("utf-8")).hexdigest()[:24]
    return f"tstore_{digest}"


def _safe_col_name(pointer: str) -> str:
    digest = hashlib.sha256(pointer.encode("utf-8")).hexdigest()[:24]
    return f"col_{digest}"


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

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._sites_cache: dict[str, SiteRecord] = {}
        self.dropped_data: list[str] = []
        self._init_schema()
        self._load_sites()

    def _load_sites(self) -> None:
        rows = self.conn.execute(
            """
            SELECT tenant_id, state, site_class, engine_target_json, blueprint_id,
                   country_pack, applied_json, applied_ids_json, history_json,
                   lock_id, sync_version, config_json, retained_json
            FROM adapter_sites
            """
        ).fetchall()
        for row in rows:
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
            self._sites_cache[row["tenant_id"]] = site

    def _init_schema(self) -> None:
        with self.conn:
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
        self._sites_cache.clear()
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
    def get_site(self, tenant_id: str) -> SiteRecord | None:
        return self._sites_cache.get(tenant_id)

    def hydrate_site(self, site: SiteRecord) -> SiteRecord:
        self._sites_cache[site.tenant_id] = site
        self.save_site(site)
        return site

    def create_site(self, tenant_id: str, params: dict[str, Any]) -> SiteRecord:
        site = SiteRecord(tenant_id, params)
        self._sites_cache[tenant_id] = site
        self.save_site(site)
        return site

    def save_site(self, site: SiteRecord) -> None:
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
                    sync_version = excluded.sync_version,
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

    # ------------------------------------------------------------------ idempotency
    def idem_get(self, tenant_id: str, operation: str, key: str) -> tuple[str, dict[str, Any]] | None:
        row = self.conn.execute(
            "SELECT input_hash, outcome_json FROM adapter_idempotency WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?",
            (tenant_id, operation, key),
        ).fetchone()
        if row is None:
            return None
        return row["input_hash"], json.loads(row["outcome_json"])

    def idem_put(self, tenant_id: str, operation: str, key: str, input_hash: str, outcome: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO adapter_idempotency (tenant_id, operation, idempotency_key, input_hash, outcome_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, operation, idempotency_key) DO UPDATE SET
                    input_hash = excluded.input_hash,
                    outcome_json = excluded.outcome_json
                """,
                (tenant_id, operation, key, input_hash, json.dumps(outcome)),
            )

    # ------------------------------------------------------------------ tokens and evidence
    def save_token(self, tenant_id: str, token: str, issued_at: int) -> None:
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
        row = self.conn.execute(
            "SELECT issued_at FROM adapter_plan_tokens WHERE tenant_id = ? AND token = ?",
            (tenant_id, token),
        ).fetchone()
        return int(row["issued_at"]) if row is not None else None

    def save_evidence(self, tenant_id: str, evidence_ref: str, statements: list[str]) -> None:
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
        row = self.conn.execute(
            "SELECT statements_json FROM adapter_plan_evidence WHERE tenant_id = ? AND evidence_ref = ?",
            (tenant_id, evidence_ref),
        ).fetchone()
        if row is None:
            raise KeyError(evidence_ref)
        return list(json.loads(row["statements_json"]))

    # ------------------------------------------------------------------ prepare & journal
    def save_prepare_intent(self, operation_id: str, tenant_id: str, artifact_id: str, payload: dict[str, Any]) -> None:
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
        with self.conn:
            self.conn.execute(
                "INSERT INTO adapter_execution_journal (tenant_id, artifact_id, step_seq, phase) VALUES (?, ?, ?, ?)",
                (tenant_id, artifact_id, seq, phase),
            )

    def execution_journal(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT artifact_id, step_seq, phase FROM adapter_execution_journal ORDER BY seq_id ASC"
        ).fetchall()
        return [{"artifactId": r["artifact_id"], "seq": int(r["step_seq"]), "phase": r["phase"]} for r in rows]

    # ------------------------------------------------------------------ audit & events
    def insert_audit(self, record: dict[str, Any]) -> None:
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
        rows = self.conn.execute(
            "SELECT audit_id, operation, request_id, correlation_id, tenant_id, service, on_behalf_of_json, input_hash, artifact_id, result FROM adapter_audit_log ORDER BY seq_id ASC"
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

    def append_event(self, event_id: str, event_type: str, data: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO adapter_events (event_id, event_type, data_json) VALUES (?, ?, ?)",
                (event_id, event_type, json.dumps(data)),
            )

    def events(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT event_id, event_type, data_json FROM adapter_events ORDER BY seq_id ASC").fetchall()
        return [{"eventId": r["event_id"], "type": r["event_type"], "data": json.loads(r["data_json"])} for r in rows]

    # ------------------------------------------------------------------ members (shadow users)
    def get_members(self, tenant_id: str) -> dict[str, dict[str, Any]]:
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
        tbl = _safe_table_name(tenant_id, entity_id)
        with self.conn:
            self.conn.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" (row_id TEXT PRIMARY KEY)')
        return tbl

    def ensure_field_column(self, tenant_id: str, entity_id: str, pointer: str) -> tuple[str, str]:
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
        tbl, col = self.ensure_field_column(tenant_id, entity_id, pointer)
        encoded = json.dumps(value)
        with self.conn:
            self.conn.execute(
                f'INSERT INTO "{tbl}" (row_id, "{col}") VALUES (?, ?) ON CONFLICT(row_id) DO UPDATE SET "{col}" = excluded."{col}"',
                ("default_row", encoded),
            )
        return self.read_field_data(tenant_id, entity_id, pointer)

    def read_field_data(self, tenant_id: str, entity_id: str, pointer: str) -> Any:
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
