"""ERP-029 deterministic reconciliation of admitted business-action outcomes.

Every request the ERP-023 enforcer admitted ends as applied, failed or unknown. A
recorded applied or failed outcome is final. A recorded unknown outcome, or a missing
one (crash or outcome-write failure), is resolved only by an exact engine read-back
by the admitted idempotency key; nothing here retries an effect or releases a claim.
Each run appends its transitions to a keyed hash chain in one transaction, or refuses
and writes nothing; every error fails closed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hmac
from hashlib import sha256
from pathlib import Path
import sqlite3
import threading
from typing import Callable

from .action_policy_enforcer import canonical_json
from .action_policy_store import ActionAudit, ActionOutcome, ActionPolicyStore, valid_instant

_TERMINAL = ("applied", "failed")
_REASONS = frozenset({
    "recorded", "readback", "readback_pending", "readback_invalid", "readback_mismatch",
    "reader_error", "admission_unbound", "handler_in_flight",
})
_COLUMNS = ("sequence", "tenant_id", "request_id", "state", "reason", "stuck", "timestamp", "mac")
_SEQUENCE_CHECK = "CHECK (sequence > 0)"


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


@dataclass(frozen=True)
class _Entry:
    state: str
    reason: str
    stuck: bool
    timestamp: datetime


class ReconciliationRefused(Exception):
    """The run stopped before writing anything it could not prove."""

    def __init__(self, reason: str, request_ids: tuple[str, ...] = ()):
        super().__init__(reason)
        self.request_ids = request_ids


def _identifier(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 256 and bool(value.strip())


class ActionOutcomeReconciler:
    """Reconcile one tenant's admitted actions against an injected, read-only engine view."""

    def __init__(
        self, path: str | Path, *, tenant_id: str,
        read_engine_state: Callable[[str, str, str], EngineReadback],
        journal_key: bytes, clock: Callable[[], datetime], stuck_after: timedelta,
        handler_deadline: timedelta,
    ):
        if not _identifier(tenant_id):
            raise ValueError("Reconciliation requires a bound tenant")
        if type(journal_key) is not bytes or len(journal_key) < 32:
            raise ValueError("Reconciliation requires a journal key of at least 32 bytes")
        if type(stuck_after) is not timedelta or stuck_after <= timedelta(0):
            raise ValueError("Reconciliation requires a positive stuck threshold")
        if type(handler_deadline) is not timedelta or not timedelta(0) < handler_deadline < stuck_after:
            raise ValueError("Reconciliation requires a positive handler deadline below the stuck threshold")
        if not callable(read_engine_state) or not callable(clock):
            raise ValueError("Reconciliation requires an engine reader and a clock")
        self._store = ActionPolicyStore(path)  # Refuses non-durable storage.
        self._uri = Path(path).resolve().as_uri() + "?mode=rw"
        self._tenant = tenant_id
        self._read = read_engine_state
        self._key = journal_key
        self._clock = clock
        self._stuck_after = stuck_after
        self._handler_deadline = handler_deadline
        self._lock = threading.Lock()  # One run at a time per instance.
        with sqlite3.connect(self._uri, uri=True) as db:
            db.executescript(f"""
                CREATE TABLE IF NOT EXISTS action_outcome_reconciliation (
                    sequence INTEGER PRIMARY KEY {_SEQUENCE_CHECK},
                    tenant_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('applied', 'failed', 'unknown')),
                    reason TEXT NOT NULL,
                    stuck INTEGER NOT NULL CHECK (stuck IN (0, 1) AND (stuck = 0 OR state = 'unknown')),
                    timestamp TEXT NOT NULL, mac TEXT NOT NULL
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
            # No in-place migration: a journal with another layout (an earlier draft) is refused.
            columns = tuple(row[1] for row in db.execute("PRAGMA table_info(action_outcome_reconciliation)"))
            sql = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' "
                             "AND name = 'action_outcome_reconciliation'").fetchone()[0]
        db.close()
        if columns != _COLUMNS or _SEQUENCE_CHECK not in sql:
            raise ValueError("Reconciliation journal has an unexpected schema")
        self._reset()

    def reconcile(self, request_ids: tuple[str, ...] | None = None) -> tuple[ReconciledOutcome, ...]:
        """Reconcile this tenant's admissions, or the named ones, in admission order.

        All entries of a run commit together; a refusal writes nothing.
        """
        with self._lock:
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
                if type(request_ids) is not tuple or not all(
                        type(rid) is str and rid in admissions for rid in request_ids):
                    raise ReconciliationRefused("unknown_request")
                selected = list(dict.fromkeys(request_ids))
            db = sqlite3.connect(self._uri, uri=True)
            try:
                self._reset()
                self._verify(db)
            finally:
                db.close()
            self._check_run(admissions, now)  # Before any read-back or write.
            planned = {}
            for rid in selected:
                if not self._is_terminal(rid):
                    outcome = self._store.outcome_for(self._tenant, rid)
                    planned[rid] = self._decide(admissions[rid], outcome, now)
            return self._commit(admissions, selected, planned, now)

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

    def _is_terminal(self, request_id: str) -> bool:
        latest = self._latest.get(request_id)
        return latest is not None and latest.state in _TERMINAL

    def _check_run(self, admissions: dict[str, ActionAudit], now: datetime) -> None:
        """Refuse the whole run on a backwards clock or a contradicted final entry, any request."""
        if any(now < audit.timestamp for audit in admissions.values()) or any(
                now < entry.timestamp for entry in self._latest.values()):
            raise ReconciliationRefused("clock_unavailable")
        conflicts = []
        for rid, entry in self._latest.items():
            if entry.state in _TERMINAL:
                outcome = self._store.outcome_for(self._tenant, rid)
                if outcome is not None and outcome.status in _TERMINAL and outcome.status != entry.state:
                    conflicts.append(rid)
        if conflicts:
            raise ReconciliationRefused("outcome_conflict", tuple(conflicts))

    def _decide(self, audit: ActionAudit, outcome: ActionOutcome | None, now: datetime) -> tuple[str, str]:
        if outcome is not None and outcome.status in _TERMINAL:
            return outcome.status, "recorded"
        state, reason = self._read_back(audit)
        if state == "failed" and outcome is None and now - audit.timestamp < self._handler_deadline:
            return "unknown", "handler_in_flight"  # A slow handler may still record its outcome.
        return state, reason

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

    def _commit(
        self, admissions: dict[str, ActionAudit], selected: list[str],
        planned: dict[str, tuple[str, str]], now: datetime,
    ) -> tuple[ReconciledOutcome, ...]:
        db = sqlite3.connect(self._uri, uri=True)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                self._verify(db)  # Entries a concurrent run appended since the first check.
                self._check_run(admissions, now)
                results = []
                for rid in selected:
                    latest = self._latest.get(rid)
                    if latest is not None and latest.state in _TERMINAL:
                        results.append(ReconciledOutcome(self._tenant, rid, latest.state, latest.reason, False))
                        continue
                    state, reason = planned[rid]
                    outcome = self._store.outcome_for(self._tenant, rid)  # A recorded final outcome wins.
                    if outcome is not None and outcome.status in _TERMINAL:
                        state, reason = outcome.status, "recorded"
                    # Human floor: escalate once, never retry or release the claim.
                    stuck = state == "unknown" and now - admissions[rid].timestamp >= self._stuck_after
                    if latest is None or state in _TERMINAL or (stuck and not latest.stuck):
                        self._insert(db, rid, state, reason, stuck, now)
                    results.append(ReconciledOutcome(self._tenant, rid, state, reason, stuck))
            return tuple(results)
        except sqlite3.IntegrityError:
            raise ReconciliationRefused("journal_tampered") from None
        finally:
            db.close()

    def _insert(self, db: sqlite3.Connection, rid: str, state: str, reason: str, stuck: bool, now: datetime) -> None:
        sequence = self._sequence + 1
        fields = (self._tenant, rid, state, reason, int(stuck), now.isoformat())
        mac = self._mac(sequence, fields)
        db.execute("INSERT INTO action_outcome_reconciliation VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (sequence, *fields, mac))
        self._sequence, self._prev = sequence, mac
        self._latest[rid] = _Entry(state, reason, stuck, now)

    def _reset(self) -> None:
        self._sequence, self._prev = 0, ""
        self._latest: dict[str, _Entry] = {}

    def _mac(self, sequence: int, fields: tuple) -> str:
        tenant_id, request_id, state, reason, stuck, timestamp = fields
        body = canonical_json({
            "prev": self._prev, "sequence": sequence, "tenant_id": tenant_id, "request_id": request_id,
            "state": state, "reason": reason, "stuck": stuck, "timestamp": timestamp,
        })
        return hmac.new(self._key, body, sha256).hexdigest()

    def _verify(self, db: sqlite3.Connection) -> None:
        """Check the chain across every tenant's entries; act only on this tenant's.

        Rows after the last checked one are verified in order; then the table must hold
        exactly sequences 1..n, so a gap, a duplicate or a sequence <= 0 is refused.
        """
        rows = db.execute(
            "SELECT sequence, tenant_id, request_id, state, reason, stuck, timestamp, mac "
            "FROM action_outcome_reconciliation WHERE sequence > ? ORDER BY sequence", (self._sequence,),
        ).fetchall()
        for sequence, tenant_id, request_id, state, reason, stuck, timestamp, mac in rows:
            fields = (tenant_id, request_id, state, reason, stuck, timestamp)
            if (sequence != self._sequence + 1
                    or not all(type(v) is str for v in (tenant_id, request_id, state, reason, timestamp, mac))
                    or reason not in _REASONS or type(stuck) is not int or stuck not in (0, 1)
                    or not hmac.compare_digest(mac.encode(), self._mac(sequence, fields).encode())):
                raise ReconciliationRefused("journal_tampered")
            try:
                instant = datetime.fromisoformat(timestamp)
            except ValueError:
                instant = None
            if not valid_instant(instant):
                raise ReconciliationRefused("journal_tampered")
            self._sequence, self._prev = sequence, mac
            if tenant_id == self._tenant:
                self._latest[request_id] = _Entry(state, reason, bool(stuck), instant)
        count, low = db.execute(
            "SELECT COUNT(*), MIN(sequence) FROM action_outcome_reconciliation").fetchone()
        if count != self._sequence or (count and low != 1):
            raise ReconciliationRefused("journal_tampered")
