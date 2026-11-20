"""Flag store port and an in-memory implementation for tests. A real store must
make `commit` one atomic compare-and-set that writes state and audit together."""

import hashlib
import hmac
import json
import threading
from collections import deque

from .errors import FlagError
from .model import AuditRecord, FlagState, KillState, Proposal, TenantAuditView, valid_id

GENESIS = "0" * 64
MAX_DENIALS = 1000
MAX_PROPOSALS = 100
_BODY = [f for f in AuditRecord.__dataclass_fields__ if f != "seal"]


class AuditSealer:
    """Keyed MAC over each audit record. A key is required (fail closed without
    one); the key id is stored in every record so keys can rotate. Key custody
    belongs to the platform audit store / KMS (Q-454)."""

    def __init__(self, keys: dict, current: str):
        if (not isinstance(keys, dict) or current not in keys
                or not all(isinstance(k, str) and k and isinstance(v, (bytes, bytearray))
                           and len(v) >= 32 for k, v in keys.items())):
            raise FlagError("FLG-050")
        self._keys = {k: bytes(v) for k, v in keys.items()}
        self.current = current

    def seal(self, key_id, body: dict) -> str:
        key = self._keys.get(key_id)
        if key is None:
            raise FlagError("FLG-050")
        return hmac.new(key, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()


class InMemoryAnchor:
    """Length and head seal of the audit log, kept apart from the log so that
    truncation or a rewrite shows. In production this lives in the platform audit
    store, not next to the flag store."""

    def __init__(self):
        self.length, self.head = 0, GENESIS

    def set(self, length, head):
        self.length, self.head = length, head


class InMemoryFlagStore:
    def __init__(self, sealer, anchor=None):
        if not isinstance(sealer, AuditSealer):
            raise FlagError("FLG-050")
        self._sealer = sealer
        self._anchor = anchor if anchor is not None else InMemoryAnchor()
        self._lock = threading.Lock()
        self._flags: dict = {}
        self._kill = KillState()
        self._version = 0
        self._audit: list = []
        self._denials: deque = deque(maxlen=MAX_DENIALS)
        self._proposals: dict = {}
        self._stepups: dict = {}
        self.fail = False  # tests: simulate an outage

    def _check(self):
        if self.fail:
            raise FlagError("FLG-050")

    def version(self) -> int:
        self._check()
        return self._version

    def get_flag(self, key) -> FlagState:
        self._check()
        return self._flags.get(key, FlagState())

    def kill_state(self) -> KillState:
        self._check()
        return self._kill

    # --- audit ---------------------------------------------------------
    def _verified(self):
        prev = GENESIS
        for i, r in enumerate(self._audit):
            body = {f: getattr(r, f) for f in _BODY}
            if (not isinstance(r, AuditRecord) or r.seq != i + 1 or r.prev_seal != prev
                    or not hmac.compare_digest(r.seal, self._sealer.seal(r.key_id, body))):
                raise FlagError("FLG-050")
            prev = r.seal
        if self._anchor.length != len(self._audit) or self._anchor.head != prev:
            raise FlagError("FLG-050")

    def commit(self, expected_version, *, flag_key=None, flag_state=None, kill=None, entry) -> AuditRecord:
        """Apply the new state and append the audit record, or do neither."""
        with self._lock:
            self._check()
            if expected_version != self._version:
                raise FlagError("FLG-040")
            prev = self._audit[-1].seal if self._audit else GENESIS
            if self._anchor.length != len(self._audit) or self._anchor.head != prev:
                raise FlagError("FLG-050")  # log and anchor disagree: refuse to extend
            at = max(entry["at"], self._audit[-1].at if self._audit else 0)  # never goes back
            body = dict(entry, at=at, seq=len(self._audit) + 1, prev_seal=prev,
                        key_id=self._sealer.current)
            body.setdefault("approved_by", None)
            seal = self._sealer.seal(self._sealer.current, body)
            record = AuditRecord(seal=seal, **body)
            if flag_state is not None:
                self._flags[flag_key] = flag_state
            if kill is not None:
                self._kill = kill
            self._audit.append(record)
            self._anchor.set(len(self._audit), seal)
            self._version += 1
            return record

    def audit(self) -> list:
        """Whole log for staff. Verifies the chain and anchor first; fails closed."""
        with self._lock:
            self._verified()
            return list(self._audit)

    def audit_for_tenant(self, tenant_id) -> list:
        """A tenant sees only changes scoped to it, redacted; never platform-wide
        records, staff ids or free-text reasons."""
        if not valid_id(tenant_id):
            raise FlagError("FLG-003")
        with self._lock:
            self._verified()
            return [TenantAuditView(r.seq, r.at, r.action, r.flag_key, r.old, r.new)
                    for r in self._audit if r.tenant_id == tenant_id]

    def verify_chain(self) -> bool:
        try:
            with self._lock:
                self._verified()
            return True
        except FlagError:
            return False

    # --- denials, proposals, step-ups ---------------------------------
    def note_denial(self, entry: dict) -> None:
        self._denials.append(entry)

    def denials(self) -> list:
        return list(self._denials)

    def put_proposal(self, p: Proposal, now: int) -> None:
        with self._lock:
            self._check()
            self._proposals = {k: v for k, v in self._proposals.items() if v.expires_at > now}
            if len(self._proposals) >= MAX_PROPOSALS:
                raise FlagError("FLG-003")
            self._proposals[p.proposal_id] = p

    def take_proposal(self, proposal_id, now: int, not_by=None):
        """Single use: the proposal is removed whether or not the caller then
        succeeds, so an approval can never be replayed."""
        with self._lock:
            self._check()
            p = self._proposals.get(proposal_id) if isinstance(proposal_id, str) else None
            if p is None or p.proposer == not_by:
                return None  # the proposer cannot burn their own proposal either
            del self._proposals[proposal_id]
            return p if p.expires_at > now else None

    def consume_step_up(self, subject, auth_time, now, ttl) -> bool:
        """A step-up (subject and sign-in time) pays for one change only."""
        with self._lock:
            self._check()
            self._stepups = {k: e for k, e in self._stepups.items() if e > now}
            if (subject, auth_time) in self._stepups:
                return False
            self._stepups[(subject, auth_time)] = now + ttl
            return True
