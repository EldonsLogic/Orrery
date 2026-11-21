"""Session and history storage interface plus an in-memory fake. Every call carries tenant and user; a session is
visible only to the user who opened it (another tenant or user gets None: fail closed, no existence leak).

`RetentionHook` is the seam for OPR-012 (retention and purge): the service calls it, the default does nothing."""
from __future__ import annotations

import copy
import json
import threading
from dataclasses import asdict
from typing import Protocol

from .models import Entry, MessageRecord, Session


class RetentionHook(Protocol):
    def on_append(self, session: Session, entry: Entry) -> None: ...

    def on_close(self, session: Session) -> None: ...


class NoRetention:
    def on_append(self, session, entry) -> None:
        return None

    def on_close(self, session) -> None:
        return None


class ChatStore(Protocol):
    def create_session(self, session: Session) -> Session: ...

    def get_session(self, tenant_id: str, user_id: str, session_id: str): ...

    def latest_session(self, tenant_id: str, user_id: str): ...

    def save_session(self, session: Session) -> None: ...

    def append(self, session: Session, entry: Entry) -> Entry:
        """Assign the next `seq`, store, return the stored entry."""

    def entries(self, session: Session) -> list: ...

    def get_message(self, session: Session, message_id: str): ...

    def put_message(self, session: Session, record: MessageRecord) -> None: ...

    def begin_run(self, session: Session, run_id: str, now: float, ttl_s: float) -> bool:
        """Atomic: False when a live (younger than ttl) run is already active for the session."""

    def end_run(self, session: Session, run_id: str) -> None: ...


class MemoryChatStore:
    def __init__(self, max_entries: int = 400):
        self._lock = threading.RLock()
        self._max = max_entries
        self._sessions: dict = {}   # (tenant, session_id) -> Session
        self._entries: dict = {}    # (tenant, session_id) -> [Entry]
        self._messages: dict = {}   # (tenant, session_id) -> {message_id: MessageRecord}
        self._runs: dict = {}       # (tenant, session_id) -> (run_id, started)

    @staticmethod
    def _k(s: Session) -> tuple:
        return (s.tenant_id, s.session_id)

    def create_session(self, session):
        with self._lock:
            self._sessions[self._k(session)] = session
            return session

    def get_session(self, tenant_id, user_id, session_id):
        with self._lock:
            s = self._sessions.get((tenant_id, session_id))
            return s if s is not None and s.user_id == user_id else None

    def latest_session(self, tenant_id, user_id):
        with self._lock:
            mine = [s for s in self._sessions.values() if s.tenant_id == tenant_id and s.user_id == user_id]
            return max(mine, key=lambda s: (s.last_active, s.created_at), default=None)

    def save_session(self, session):
        with self._lock:
            if self.get_session(session.tenant_id, session.user_id, session.session_id) is not None:
                self._sessions[self._k(session)] = session

    def append(self, session, entry):
        with self._lock:
            rows = self._entries.setdefault(self._k(session), [])
            stored = Entry(**{**asdict(entry), "seq": (rows[-1].seq + 1) if rows else 1})
            rows.append(stored)
            del rows[:-self._max]
            return stored

    def entries(self, session):
        with self._lock:
            return list(self._entries.get(self._k(session), []))

    def get_message(self, session, message_id):
        with self._lock:
            return self._messages.get(self._k(session), {}).get(message_id)

    def put_message(self, session, record):
        with self._lock:
            self._messages.setdefault(self._k(session), {})[record.message_id] = record

    def begin_run(self, session, run_id, now, ttl_s):
        with self._lock:
            cur = self._runs.get(self._k(session))
            if cur is not None and now - cur[1] < ttl_s:
                return False
            self._runs[self._k(session)] = (run_id, now)
            return True

    def end_run(self, session, run_id):
        with self._lock:
            if self._runs.get(self._k(session), (None,))[0] == run_id:
                del self._runs[self._k(session)]

    # -- persistence stand-in: a real store is a database; this lets a test "restart" the service
    def dump(self) -> str:
        with self._lock:
            return json.dumps({
                "sessions": [asdict(s) for s in self._sessions.values()],
                "entries": [[list(k), [asdict(e) for e in v]] for k, v in self._entries.items()],
                "messages": [[list(k), [asdict(r) for r in v.values()]] for k, v in self._messages.items()],
                "runs": [[list(k), list(v)] for k, v in self._runs.items()]}, ensure_ascii=False)

    @classmethod
    def load(cls, blob: str) -> "MemoryChatStore":
        d, st = json.loads(blob), cls()
        for s in d["sessions"]:
            st._sessions[(s["tenant_id"], s["session_id"])] = Session(**s)
        for k, v in d["entries"]:
            st._entries[tuple(k)] = [Entry(**e) for e in v]
        for k, v in d["messages"]:
            st._messages[tuple(k)] = {r["message_id"]: MessageRecord(**r) for r in v}
        for k, v in d["runs"]:
            st._runs[tuple(k)] = tuple(v)
        return st

    def raw_snapshot(self) -> dict:  # test helper: what is at rest
        with self._lock:
            return copy.deepcopy({"entries": self._entries, "messages": self._messages})


class MemoryPendingStore:
    """One pending confirmation per tenant, user and session. Set only by the chat service after a preview was shown."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict = {}

    def set(self, tenant_id: str, user_id: str, session_id: str, pending) -> None:
        with self._lock:
            self._items[(tenant_id, user_id, session_id)] = pending

    def get(self, tenant_id: str, user_id: str, session_id: str):
        with self._lock:
            return self._items.get((tenant_id, user_id, session_id))

    def clear(self, tenant_id: str, user_id: str, session_id: str) -> None:
        with self._lock:
            self._items.pop((tenant_id, user_id, session_id), None)
