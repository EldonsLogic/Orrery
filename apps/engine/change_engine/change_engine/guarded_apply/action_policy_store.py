"""Durable, append-only admission and audit journal for guarded business actions."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable


@dataclass(frozen=True)
class Principal:
    """Identity and current roles resolved by the trusted tenant authority."""

    id: str
    kind: str
    roles: frozenset[str]
    owner_id: str | None = None


@dataclass(frozen=True)
class ActionAudit:
    """One write-ahead authorization decision. Payloads and session credentials stay out."""

    tenant_id: str | None
    request_id: str | None
    action_id: str | None
    action_version: int | None
    table_version: str | None
    payload_hash: str | None
    drafter: Principal | None
    submitter: Principal | None
    approvers: tuple[Principal, ...]
    timestamp: datetime
    decision: str
    reason: str
    break_glass: bool = False
    # Q-41, Q-563: the sole owner approved their own request or their own agent's draft (review report input).
    self_approved: bool = False


@dataclass(frozen=True)
class ActionOutcome:
    """One observed effect outcome for an admitted tenant request."""

    tenant_id: str
    request_id: str
    status: str
    timestamp: datetime


def _serialize(value: object) -> list[str] | str:
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Invalid audit value")


def _principal(value: dict | None) -> Principal | None:
    return Principal(**{**value, "roles": frozenset(value["roles"])}) if value else None


def valid_instant(value: object) -> bool:
    """Only accept timezone-aware clock and expiry values."""
    return type(value) is datetime and value.utcoffset() is not None


class ActionPolicyStore:
    """Use one server-owned database path shared by the engine workers.

    A committed allow reserves the request, idempotency key and every approval.
    On a crash or uncertain effect, reservations survive and require reconciliation.
    """

    def __init__(self, path: str | Path):
        if not path or str(path) == ":memory:":
            raise ValueError("Action policy requires durable storage")
        self._uri = Path(path).resolve().as_uri() + "?mode=rw"
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS action_policy_claims (
                    tenant_id TEXT NOT NULL, kind TEXT NOT NULL, claim TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, kind, claim)
                );
                CREATE TABLE IF NOT EXISTS action_policy_audit (
                    sequence INTEGER PRIMARY KEY, record TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS action_policy_audit_no_update
                BEFORE UPDATE ON action_policy_audit
                BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_audit_no_delete
                BEFORE DELETE ON action_policy_audit
                BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_audit_no_replace
                BEFORE INSERT ON action_policy_audit
                WHEN EXISTS (SELECT 1 FROM action_policy_audit WHERE sequence = NEW.sequence)
                BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
                CREATE TABLE IF NOT EXISTS action_policy_outcomes (
                    tenant_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('applied', 'failed', 'unknown')),
                    timestamp TEXT NOT NULL, PRIMARY KEY (tenant_id, request_id)
                );
                CREATE TRIGGER IF NOT EXISTS action_policy_outcomes_no_update
                BEFORE UPDATE ON action_policy_outcomes
                BEGIN SELECT RAISE(ABORT, 'Append-only outcome'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_outcomes_no_delete
                BEFORE DELETE ON action_policy_outcomes
                BEGIN SELECT RAISE(ABORT, 'Append-only outcome'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_outcomes_no_replace
                BEFORE INSERT ON action_policy_outcomes
                WHEN EXISTS (SELECT 1 FROM action_policy_outcomes
                             WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id)
                BEGIN SELECT RAISE(ABORT, 'Append-only outcome'); END;
                -- ERP-029: binds each admitted request to its idempotency key for read-back.
                CREATE TABLE IF NOT EXISTS action_policy_admission_keys (
                    tenant_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    submitter_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, request_id),
                    UNIQUE (tenant_id, submitter_id, idempotency_key)
                );
                CREATE TRIGGER IF NOT EXISTS action_policy_admission_keys_no_update
                BEFORE UPDATE ON action_policy_admission_keys
                BEGIN SELECT RAISE(ABORT, 'Append-only admission key'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_admission_keys_no_delete
                BEFORE DELETE ON action_policy_admission_keys
                BEGIN SELECT RAISE(ABORT, 'Append-only admission key'); END;
                CREATE TRIGGER IF NOT EXISTS action_policy_admission_keys_no_replace
                BEFORE INSERT ON action_policy_admission_keys
                WHEN EXISTS (SELECT 1 FROM action_policy_admission_keys WHERE tenant_id = NEW.tenant_id
                             AND (request_id = NEW.request_id OR (submitter_id = NEW.submitter_id
                                  AND idempotency_key = NEW.idempotency_key)))
                BEGIN SELECT RAISE(ABORT, 'Append-only admission key'); END;
            """)
        db.close()

    def record(
        self, audit: ActionAudit, idempotency_key: str | None, approvals: tuple[str, ...],
        *, expires_at: datetime | None, clock: Callable[[], datetime],
    ) -> ActionAudit:
        """Commit the decision and its replay claims together, downgrading collisions to denials."""
        db = sqlite3.connect(self._uri, uri=True)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                if audit.decision != "deny":
                    # Check time again after waiting for a concurrent admission's write lock.
                    try:
                        now = clock()
                        if not valid_instant(now) or now < audit.timestamp:
                            raise ValueError("Untrusted clock")
                        audit = replace(audit, timestamp=now)
                        if expires_at is not None and now >= expires_at:
                            audit = replace(audit, decision="deny", reason="expired", break_glass=False,
                                            self_approved=False)
                    except Exception:
                        audit = replace(audit, decision="deny", reason="clock_unavailable", break_glass=False,
                                        self_approved=False)
                if audit.decision != "deny":
                    assert audit.submitter is not None
                    keys = [("request", audit.request_id), ("idempotency", json.dumps(
                        [audit.submitter.id, idempotency_key])),
                        *(("approval", approval) for approval in approvals)]
                    db.execute("SAVEPOINT claims")
                    for kind, key in keys:
                        inserted = db.execute(
                            "INSERT INTO action_policy_claims VALUES (?, ?, ?) "
                            "ON CONFLICT (tenant_id, kind, claim) DO NOTHING",
                            (audit.tenant_id, kind, key),
                        ).rowcount
                        if not inserted:
                            db.execute("ROLLBACK TO claims")
                            audit = replace(audit, decision="deny", reason="replay", break_glass=False,
                                            self_approved=False)
                            break
                    db.execute("RELEASE claims")
                if audit.decision != "deny":
                    db.execute(
                        "INSERT INTO action_policy_admission_keys VALUES (?, ?, ?, ?)",
                        (audit.tenant_id, audit.request_id, audit.submitter.id, idempotency_key),
                    )
                db.execute(
                    "INSERT INTO action_policy_audit (record) VALUES (?)",
                    (json.dumps(asdict(audit), default=_serialize),),
                )
            return audit
        finally:
            db.close()

    def audit_log(self) -> tuple[ActionAudit, ...]:
        """Read the immutable decision snapshots in append order for internal audit."""
        db = sqlite3.connect(self._uri, uri=True)
        try:
            records = []
            for (raw,) in db.execute("SELECT record FROM action_policy_audit ORDER BY sequence"):
                fields = json.loads(raw)
                fields["timestamp"] = datetime.fromisoformat(fields["timestamp"])
                fields["drafter"] = _principal(fields["drafter"])
                fields["submitter"] = _principal(fields["submitter"])
                fields["approvers"] = tuple(_principal(actor) for actor in fields["approvers"])
                records.append(ActionAudit(**fields))
            return tuple(records)
        finally:
            db.close()

    def admission_key(self, tenant_id: str, request_id: str) -> tuple[str, str] | None:
        """Return (submitter_id, idempotency_key) only while both admission claims exist."""
        db = sqlite3.connect(self._uri, uri=True)
        try:
            row = db.execute(
                "SELECT submitter_id, idempotency_key FROM action_policy_admission_keys "
                "WHERE tenant_id = ? AND request_id = ?", (tenant_id, request_id),
            ).fetchone()
            if row is None:
                return None
            claims = db.execute(
                "SELECT COUNT(*) FROM action_policy_claims WHERE tenant_id = ? AND "
                "((kind = 'request' AND claim = ?) OR (kind = 'idempotency' AND claim = ?))",
                (tenant_id, request_id, json.dumps(list(row))),
            ).fetchone()[0]
            return (row[0], row[1]) if claims == 2 else None
        finally:
            db.close()

    def record_outcome(self, tenant_id: str, request_id: str, status: str) -> None:
        """Append an outcome only for an admitted request, preserving all replay claims."""
        db = sqlite3.connect(self._uri, uri=True)
        try:
            with db:
                inserted = db.execute(
                    "INSERT INTO action_policy_outcomes (tenant_id, request_id, status, timestamp) "
                    "SELECT tenant_id, claim, ?, ? FROM action_policy_claims "
                    "WHERE tenant_id = ? AND kind = 'request' AND claim = ?",
                    (status, datetime.now(timezone.utc).isoformat(), tenant_id, request_id),
                ).rowcount
                if inserted != 1:
                    raise ValueError("Outcome requires a request claim")
        finally:
            db.close()

    def outcome_for(self, tenant_id: str, request_id: str) -> ActionOutcome | None:
        """Read the recorded outcome, if any, for a request in the given tenant."""
        db = sqlite3.connect(self._uri, uri=True)
        try:
            row = db.execute(
                "SELECT status, timestamp FROM action_policy_outcomes WHERE tenant_id = ? AND request_id = ?",
                (tenant_id, request_id),
            ).fetchone()
            return ActionOutcome(tenant_id, request_id, row[0], datetime.fromisoformat(row[1])) if row else None
        finally:
            db.close()
