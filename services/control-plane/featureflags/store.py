"""Flag store port and an in-memory implementation for tests. A real store must
make `commit` one atomic compare-and-set that writes state and audit together."""

import hashlib
import json
import threading
from collections import deque

from .errors import FlagError
from .model import AuditRecord, FlagState, KillState

GENESIS = "0" * 64
MAX_DENIALS = 1000


class InMemoryFlagStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._flags: dict = {}
        self._kill = KillState()
        self._version = 0
        self._audit: list = []
        self._denials: deque = deque(maxlen=MAX_DENIALS)
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

    def commit(self, expected_version, *, flag_key=None, flag_state=None, kill=None, entry) -> AuditRecord:
        """Apply the new state and append the audit record, or do neither."""
        with self._lock:
            self._check()
            if expected_version != self._version:
                raise FlagError("FLG-040")
            prev = self._audit[-1].hash if self._audit else GENESIS
            body = dict(entry, seq=len(self._audit) + 1, prev_hash=prev)
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            record = AuditRecord(hash=digest, **body)
            if flag_state is not None:
                self._flags[flag_key] = flag_state
            if kill is not None:
                self._kill = kill
            self._audit.append(record)
            self._version += 1
            return record

    def audit(self) -> list:
        return list(self._audit)

    def audit_for_tenant(self, tenant_id) -> list:
        """A tenant sees only changes scoped to it, never other tenants' records."""
        return [r for r in self._audit if r.tenant_id == tenant_id]

    def verify_chain(self) -> bool:
        prev = GENESIS
        for r in self._audit:
            body = {k: getattr(r, k) for k in r.__dataclass_fields__ if k != "hash"}
            if r.prev_hash != prev or hashlib.sha256(
                    json.dumps(body, sort_keys=True).encode()).hexdigest() != r.hash:
                return False
            prev = r.hash
        return True

    def note_denial(self, entry: dict) -> None:
        self._denials.append(entry)

    def denials(self) -> list:
        return list(self._denials)
