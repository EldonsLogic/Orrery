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
        """Compare-and-delete: True only if `p` (by digest) is still the active proposal of its session and unused.
        A proposal superseded while its confirm was in flight is refused."""
        with self._lock:
            k = self._key(p.tenant_id, p.user_id, p.session_id)
            cur = self._active.get(k)
            if p.digest in self._used or cur is None or cur.digest != p.digest:
                return False
            del self._active[k]
            self._used.add(p.digest)
            return True

    def used(self, digest: str) -> bool:
        with self._lock:
            return digest in self._used

    def drop(self, tenant_id: str, user_id: str, session_id: str) -> None:
        with self._lock:
            self._active.pop(self._key(tenant_id, user_id, session_id), None)
