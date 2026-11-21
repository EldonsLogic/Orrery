"""ERP-029 deterministic reconciliation of admitted business-action outcomes.

Every request the ERP-023 enforcer admitted ends as applied, failed or unknown. A
recorded applied or failed outcome is final. A recorded unknown outcome, or a missing
one (crash or outcome-write failure), is resolved only by an exact engine read-back
by the admitted idempotency key; nothing here retries an effect or releases a claim.
Each transition is appended to a keyed hash chain and every error fails closed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hmac
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Callable

from .action_policy_enforcer import canonical_json
from .action_policy_store import ActionAudit, ActionPolicyStore, valid_instant

_TERMINAL = ("applied", "failed")
_REASONS = frozenset({
    "recorded", "readback", "readback_pending", "readback_invalid", "readback_mismatch",
    "reader_error", "admission_unbound", "stuck",
})


@dataclass(frozen=True)
class EngineReadback:
    """What the engine holds for one idempotency key, echoing the exact key it read.

    `applied`: a durable effect exists and carries the bound request and payload hash.
    `not_applied`: no effect exists and the engine guarantees none can commit later.
    `pending`: anything else; the outcome stays unknown.
    """

    tenant_id: str
    submitter_id: str
    idempotency_key: str
    state: str
    request_id: str | None = None
    payload_hash: str | None = None


@dataclass(frozen=True)
class ReconciledOutcome:
    tenant_id: str
    request_id: str
    state: str
    reason: str
    stuck: bool


class ReconciliationRefused(Exception):
    """The run stopped before writing anything it could not prove."""


def _identifier(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 256 and bool(value.strip())


class ActionOutcomeReconciler:
    """Reconcile one tenant's admitted actions against an injected, read-only engine view."""

    def __init__(
        self, path: str | Path, *, tenant_id: str,
        read_engine_state: Callable[[str, str, str], EngineReadback],
        journal_key: bytes, clock: Callable[[], datetime], stuck_after: timedelta,
    ):
        if not _identifier(tenant_id):
            raise ValueError("Reconciliation requires a bound tenant")
        if type(journal_key) is not bytes or len(journal_key) < 32:
            raise ValueError("Reconciliation requires a journal key of at least 32 bytes")
        if type(stuck_after) is not timedelta or stuck_after <= timedelta(0):
            raise ValueError("Reconciliation requires a positive stuck threshold")
        if not callable(read_engine_state) or not callable(clock):
            raise ValueError("Reconciliation requires an engine reader and a clock")
        self._store = ActionPolicyStore(path)  # Refuses non-durable storage.
        self._uri = Path(path).resolve().as_uri() + "?mode=rw"
        self._tenant = tenant_id
        self._read = read_engine_state
        self._key = journal_key
        self._clock = clock
        self._stuck_after = stuck_after
        with sqlite3.connect(self._uri, uri=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS action_outcome_reconciliation (
                    sequence INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('applied', 'failed', 'unknown')),
                    reason TEXT NOT NULL, timestamp TEXT NOT NULL, mac TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS action_outcome_reconciliation_terminal
                ON action_outcome_reconciliation (tenant_id, request_id)
                WHERE state IN ('applied', 'failed');
                CREATE TRIGGER IF NOT EXISTS action_outcome_reconciliation_no_update
                BEFORE UPDATE ON action_outcome_reconciliation
                BEGIN SELECT RAISE(ABORT, 'Append-only reconciliation'); END;
                CREATE TRIGGER IF NOT EXISTS action_outcome_reconciliation_no_delete
                BEFORE DELETE ON action_outcome_reconciliation
                BEGIN SELECT RAISE(ABORT, 'Append-only reconciliation'); END;
                CREATE TRIGGER IF NOT EXISTS action_outcome_reconciliation_no_replace
                BEFORE INSERT ON action_outcome_reconciliation
                WHEN EXISTS (SELECT 1 FROM action_outcome_reconciliation WHERE sequence = NEW.sequence)
                BEGIN SELECT RAISE(ABORT, 'Append-only reconciliation'); END;
            """)
        db.close()
        self._reset()

    def reconcile(self, request_ids: tuple[str, ...] | None = None) -> tuple[ReconciledOutcome, ...]:
        """Reconcile this tenant's admissions, or the named ones, in admission order."""
        try:
            now = self._clock()
        except Exception:
            now = None
        if not valid_instant(now):
            raise ReconciliationRefused("clock_unavailable")
        admissions = self._admissions()
        if request_ids is None:
            selected = list(admissions)
        else:
            if type(request_ids) is not tuple or not all(type(rid) is str and rid in admissions for rid in request_ids):
                raise ReconciliationRefused("unknown_request")
            selected = list(dict.fromkeys(request_ids))
        db = sqlite3.connect(self._uri, uri=True)
        try:
            self._reset()
            self._verify(db)
        finally:
            db.close()
        return tuple(self._reconcile_one(admissions[rid], now) for rid in selected)

    # ------------------------------------------------------------------ internals
    def _admissions(self) -> dict[str, ActionAudit]:
        found: dict[str, ActionAudit] = {}
        for audit in self._store.audit_log():
            if audit.tenant_id != self._tenant or audit.decision == "deny":
                continue
            if audit.request_id in found or not _identifier(audit.request_id):
                raise ReconciliationRefused("audit_inconsistent")
            found[audit.request_id] = audit
        return found

    def _reconcile_one(self, audit: ActionAudit, now: datetime) -> ReconciledOutcome:
        latest = self._latest.get(audit.request_id)
        if latest is not None and latest[0] in _TERMINAL:
            return self._terminal(audit.request_id, latest)
        outcome = self._store.outcome_for(self._tenant, audit.request_id)
        if outcome is not None and outcome.status in _TERMINAL:
            state, reason = outcome.status, "recorded"
        else:
            state, reason = self._read_back(audit)
        if state == "unknown" and now - audit.timestamp >= self._stuck_after:
            reason = "stuck"  # Human floor: escalate, never retry or release the claim.
        return self._append(audit.request_id, state, reason, now)

    def _terminal(self, request_id: str, latest: tuple[str, str]) -> ReconciledOutcome:
        outcome = self._store.outcome_for(self._tenant, request_id)
        if outcome is not None and outcome.status in _TERMINAL and outcome.status != latest[0]:
            raise ReconciliationRefused("outcome_conflict")
        return ReconciledOutcome(self._tenant, request_id, latest[0], latest[1], False)

    def _read_back(self, audit: ActionAudit) -> tuple[str, str]:
        binding = self._store.admission_key(self._tenant, audit.request_id)
        if binding is None or audit.submitter is None or binding[0] != audit.submitter.id:
            return "unknown", "admission_unbound"
        submitter_id, key = binding
        try:
            readback = self._read(self._tenant, submitter_id, key)
        except Exception:
            return "unknown", "reader_error"
        if type(readback) is not EngineReadback:
            return "unknown", "readback_invalid"
        if (readback.tenant_id, readback.submitter_id, readback.idempotency_key) != (self._tenant, submitter_id, key):
            return "unknown", "readback_mismatch"
        if readback.state == "applied":
            bound = (type(readback.request_id) is str and readback.request_id == audit.request_id
                     and type(readback.payload_hash) is str and type(audit.payload_hash) is str
                     and hmac.compare_digest(readback.payload_hash.encode(), audit.payload_hash.encode()))
            return ("applied", "readback") if bound else ("unknown", "readback_mismatch")
        if readback.state == "not_applied":
            clean = readback.request_id is None and readback.payload_hash is None
            return ("failed", "readback") if clean else ("unknown", "readback_mismatch")
        if readback.state == "pending":
            return "unknown", "readback_pending"
        return "unknown", "readback_invalid"

    def _append(self, request_id: str, state: str, reason: str, now: datetime) -> ReconciledOutcome:
        db = sqlite3.connect(self._uri, uri=True)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                self._verify(db)  # Entries a concurrent run appended since the last check.
                latest = self._latest.get(request_id)
                if latest is not None and latest[0] in _TERMINAL:
                    return self._terminal(request_id, latest)
                stuck = reason == "stuck"
                if latest is None or state in _TERMINAL or (stuck and latest[1] != "stuck"):
                    sequence = self._sequence + 1
                    fields = (self._tenant, request_id, state, reason, now.isoformat())
                    mac = self._mac(sequence, fields)
                    db.execute("INSERT INTO action_outcome_reconciliation VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (sequence, *fields, mac))
                    self._sequence, self._prev = sequence, mac
                    self._latest[request_id] = (state, reason)
                elif latest[1] == "stuck":
                    stuck = True
            return ReconciledOutcome(self._tenant, request_id, state, reason, stuck)
        finally:
            db.close()

    def _reset(self) -> None:
        self._sequence, self._prev = 0, ""
        self._latest: dict[str, tuple[str, str]] = {}

    def _mac(self, sequence: int, fields: tuple[str, ...]) -> str:
        tenant_id, request_id, state, reason, timestamp = fields
        body = canonical_json({
            "prev": self._prev, "sequence": sequence, "tenant_id": tenant_id, "request_id": request_id,
            "state": state, "reason": reason, "timestamp": timestamp,
        })
        return hmac.new(self._key, body, sha256).hexdigest()

    def _verify(self, db: sqlite3.Connection) -> None:
        """Check the chain across every tenant's entries; act only on this tenant's."""
        rows = db.execute(
            "SELECT sequence, tenant_id, request_id, state, reason, timestamp, mac "
            "FROM action_outcome_reconciliation WHERE sequence > ? ORDER BY sequence", (self._sequence,),
        ).fetchall()
        for sequence, tenant_id, request_id, state, reason, timestamp, mac in rows:
            fields = (tenant_id, request_id, state, reason, timestamp)
            if (sequence != self._sequence + 1 or not all(type(v) is str for v in (*fields, mac))
                    or reason not in _REASONS
                    or not hmac.compare_digest(mac.encode(), self._mac(sequence, fields).encode())):
                raise ReconciliationRefused("journal_tampered")
            self._sequence, self._prev = sequence, mac
            if tenant_id == self._tenant:
                self._latest[request_id] = (state, reason)
