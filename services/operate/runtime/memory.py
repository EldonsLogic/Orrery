"""In-memory implementations and determinism helpers (injected ids and clock)."""
from __future__ import annotations

import copy
import logging
import threading

from .models import Span

log = logging.getLogger("agent_runtime")


class MemoryTraceStore:
    """Append-only, tenant-scoped. A read needs the tenant id; another tenant's run is simply not found."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_key: dict = {}

    def append(self, span: Span) -> None:
        with self._lock:
            self._by_key.setdefault((span.tenant_id, span.run_id), []).append(span)

    def spans(self, tenant_id: str, run_id: str) -> list:
        with self._lock:
            return copy.deepcopy(self._by_key.get((tenant_id, run_id), []))


class SequentialIds:
    """Deterministic ids: the same call order gives the same ids. ULIDs are valid Crockford strings."""

    def __init__(self, start: int = 0):
        self._n = start
        self._lock = threading.Lock()

    def _next(self) -> int:
        with self._lock:
            self._n += 1
            return self._n

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{self._next():05d}"

    def new_ulid(self) -> str:
        return f"{self._next():026d}"


class TickClock:
    """Fake monotonic clock: each read advances by `step` seconds (0 keeps time still); `advance` jumps."""

    def __init__(self, start: float = 0.0, step: float = 0.001):
        self.now, self.step = start, step

    def __call__(self) -> float:
        t = self.now
        self.now += self.step
        return t

    def advance(self, seconds: float) -> None:
        self.now += seconds


class StoreEventSink:
    """EventSink over an evstream store. A write fault is logged and swallowed: auditing never breaks a run."""

    def __init__(self, store, ids, clock_dt=None, service: str = "operate.runtime", build_event=None, context=None):
        from evstream import Context, build_event as _be  # lazy: path set by the host
        self._store, self._ids, self._service = store, ids, service
        self._Context, self._build = context or Context, build_event or _be
        self._clock_dt = clock_dt

    def emit(self, tenant_id, subject, type, data, trace) -> None:
        try:
            ctx = self._Context(tenant_id=tenant_id, actor_kind="user", actor_id=subject, service=self._service,
                            correlation_id=str(data.get("run_id", "")) or None)
            kw = {"event_id": self._ids.new_ulid()}
            if self._clock_dt:
                kw["clock"] = self._clock_dt
            self._store.append(self._build(ctx, type, data, trace=trace, **kw))
        except Exception:
            log.exception("runtime event write failed type=%s", type)
