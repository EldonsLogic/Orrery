"""EventStore interface and MemoryStore.

Append-only. The store assigns a strictly increasing per-tenant sequence starting at 1 and
re-stamps recorded_at. There is no update or delete. Everything handed out is a deep copy.
"""
from __future__ import annotations

import copy
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable

from .build import iso_z, utc_now
from .errors import EventError
from .registry import Registry, default_registry
from .validate import validate_event

MAX_READ_LIMIT = 1000
_STAMPED = ("sequence", "recorded_at")


def find_gaps(sequences: list[int], start: int = 1) -> list[tuple[int, int]]:
    """Missing inclusive ranges in a sorted list of sequences that should begin at `start`."""
    gaps, expect = [], start
    for s in sequences:
        if s > expect:
            gaps.append((expect, s - 1))
        expect = s + 1
    return gaps


class EventStore(ABC):
    @abstractmethod
    def append(self, event: dict) -> dict:
        """Validate and store; return the stored event. Idempotent on event_id."""

    @abstractmethod
    def read(self, tenant_id: str, after_sequence: int = 0, limit: int = 100) -> list[dict]:
        """Events of one tenant with sequence > after_sequence, ascending."""

    @abstractmethod
    def get(self, tenant_id: str, event_id: str) -> dict | None:
        ...

    @abstractmethod
    def gaps(self, tenant_id: str) -> list[tuple[int, int]]:
        """Missing sequence ranges. Any gap is an alert."""


class MemoryStore(EventStore):
    def __init__(self, registry: Registry | None = None, clock: Callable[[], datetime] = utc_now):
        self._reg = registry or default_registry()
        self._clock = clock
        self._lock = threading.Lock()
        self._by_tenant: dict[str, dict[int, dict]] = {}
        self._ids: dict[str, str] = {}  # event_id -> tenant_id (global uniqueness)

    @staticmethod
    def _content(ev: dict) -> dict:
        return {k: v for k, v in ev.items() if k not in _STAMPED}

    def append(self, event: dict) -> dict:
        with self._lock:
            return self._append(event)

    def _append(self, event: dict) -> dict:
        if not isinstance(event, dict):
            raise EventError("EVS-ENV-002", "event is not an object")
        eid, tenant = event.get("event_id"), event.get("tenant_id")
        if isinstance(eid, str) and eid in self._ids:
            if self._ids[eid] != tenant:
                raise EventError("EVS-DUP-001", "event_id already used")  # no hint which tenant
            existing = self._by_tenant[tenant][self._seq_of(tenant, eid)]
            if self._content(existing) != self._content(event):
                raise EventError("EVS-DUP-002")
            return copy.deepcopy(existing)
        res = validate_event(event, self._reg, stamped=False)
        if not res.ok:
            raise EventError(res.errors[0].code, f"{res.errors[0].path}: {res.errors[0].message}")
        cause = event.get("causation_id")
        rows = self._by_tenant.setdefault(tenant, {})
        if cause is not None and not any(e["event_id"] == cause for e in rows.values()):
            raise EventError("EVS-CAUSE-001", "causation_id must name an existing event of this tenant")
        stored = copy.deepcopy(event)
        stored["sequence"] = max(rows, default=0) + 1
        stored["recorded_at"] = iso_z(self._clock())
        rows[stored["sequence"]] = stored
        self._ids[eid] = tenant
        return copy.deepcopy(stored)

    def _seq_of(self, tenant: str, eid: str) -> int:
        return next(s for s, e in self._by_tenant[tenant].items() if e["event_id"] == eid)

    def read(self, tenant_id: str, after_sequence: int = 0, limit: int = 100) -> list[dict]:
        if not isinstance(tenant_id, str) or isinstance(after_sequence, bool) or not isinstance(after_sequence, int) \
                or after_sequence < 0 or isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise EventError("EVS-READ-001", "tenant_id str, after_sequence >= 0, limit >= 1")
        limit = min(limit, MAX_READ_LIMIT)
        with self._lock:
            rows = self._by_tenant.get(tenant_id, {})
            seqs = sorted(s for s in rows if s > after_sequence)[:limit]
            return [copy.deepcopy(rows[s]) for s in seqs]

    def get(self, tenant_id: str, event_id: str) -> dict | None:
        with self._lock:
            for e in self._by_tenant.get(tenant_id, {}).values():
                if e["event_id"] == event_id:
                    return copy.deepcopy(e)
        return None

    def gaps(self, tenant_id: str) -> list[tuple[int, int]]:
        with self._lock:
            return find_gaps(sorted(self._by_tenant.get(tenant_id, {})))

    def last_sequence(self, tenant_id: str) -> int:
        with self._lock:
            return max(self._by_tenant.get(tenant_id, {}), default=0)
