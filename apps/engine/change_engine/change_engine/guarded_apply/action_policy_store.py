"""Durable, append-only admission and audit journal for guarded business actions."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime
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
                            audit = replace(audit, decision="deny", reason="expired", break_glass=False)
                    except Exception:
                        audit = replace(audit, decision="deny", reason="clock_unavailable", break_glass=False)
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
                            audit = replace(audit, decision="deny", reason="replay", break_glass=False)
                            break
                    db.execute("RELEASE claims")
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
