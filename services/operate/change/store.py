"""In-memory proposal store: one active proposal per tenant, user and session. A new one supersedes the old one."""
from __future__ import annotations

import threading
from typing import Optional

from .models import Proposal


class InMemoryProposalStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._active: dict = {}
        self._used: set = set()

    @staticmethod
    def _key(tenant_id, user_id, session_id):
        return (tenant_id, user_id, session_id)

    def put(self, p: Proposal) -> None:
        with self._lock:
            self._active[self._key(p.tenant_id, p.user_id, p.session_id)] = p

    def active(self, tenant_id: str, user_id: str, session_id: str) -> Optional[Proposal]:
        with self._lock:
            return self._active.get(self._key(tenant_id, user_id, session_id))

    def consume(self, p: Proposal) -> bool:
        with self._lock:
            if p.digest in self._used:
                return False
            self._used.add(p.digest)
            k = self._key(p.tenant_id, p.user_id, p.session_id)
            if self._active.get(k) is p or (self._active.get(k) and self._active[k].digest == p.digest):
                del self._active[k]
            return True

    def used(self, digest: str) -> bool:
        with self._lock:
            return digest in self._used

    def drop(self, tenant_id: str, user_id: str, session_id: str) -> None:
        with self._lock:
            self._active.pop(self._key(tenant_id, user_id, session_id), None)
