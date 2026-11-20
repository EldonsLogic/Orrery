"""Storage port and in-memory reference store. Every call carries tenant and user; an entry of another tenant or
user is indistinguishable from a missing one. The store also re-checks the owner on every read (defence in depth)."""
from __future__ import annotations

import threading
from typing import Protocol

from .models import MemoryEntry, Scope


class MemoryStore(Protocol):
    def put(self, entry: MemoryEntry) -> None: ...
    def get(self, scope: Scope, entry_id: str): ...
    def list(self, scope: Scope) -> list: ...
    def count_tenant(self, tenant_id: str, now: float) -> int: ...
    def delete_expired(self, tenant_id: str, now: float) -> int: ...
    def replace(self, entry: MemoryEntry) -> None: ...
    def delete(self, scope: Scope, entry_id: str) -> bool: ...
    def delete_scope(self, scope: Scope) -> int: ...
    def delete_tenant(self, tenant_id: str) -> int: ...


class InMemoryStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._rows: dict = {}   # (tenant, user) -> {entry_id: MemoryEntry}

    def put(self, entry):
        with self._lock:
            self._rows.setdefault((entry.tenant_id, entry.user_id), {})[entry.entry_id] = entry

    replace = put

    def get(self, scope, entry_id):
        with self._lock:
            e = self._rows.get((scope.tenant_id, scope.user_id), {}).get(entry_id)
        return e if e and (e.tenant_id, e.user_id) == (scope.tenant_id, scope.user_id) else None

    def list(self, scope):
        with self._lock:
            rows = list(self._rows.get((scope.tenant_id, scope.user_id), {}).values())
        return [e for e in rows if (e.tenant_id, e.user_id) == (scope.tenant_id, scope.user_id)]

    def count_tenant(self, tenant_id, now):
        """Live (unexpired) rows only: expired data never counts against a cap."""
        with self._lock:
            return sum(1 for (t, _), v in self._rows.items() if t == tenant_id
                       for e in v.values() if e.expires_at > now)

    def delete_expired(self, tenant_id, now):
        """Hard-delete expired rows of one tenant (retention is real deletion, not a read filter)."""
        n = 0
        with self._lock:
            for (t, _), v in self._rows.items():
                if t == tenant_id:
                    for k in [k for k, e in v.items() if e.expires_at <= now]:
                        del v[k]
                        n += 1
        return n

    def delete(self, scope, entry_id):
        with self._lock:
            return self._rows.get((scope.tenant_id, scope.user_id), {}).pop(entry_id, None) is not None

    def delete_scope(self, scope):
        with self._lock:
            return len(self._rows.pop((scope.tenant_id, scope.user_id), {}))

    def delete_tenant(self, tenant_id):
        with self._lock:
            keys = [k for k in self._rows if k[0] == tenant_id]
            return sum(len(self._rows.pop(k)) for k in keys)
