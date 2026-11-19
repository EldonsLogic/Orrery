"""Injected ports. Real implementations: the metered gateway (PLT-009), the Tool API gateway, a database
trace store. Tests inject scripted fakes. Nothing here makes a model call or touches the network."""
from __future__ import annotations

import threading
from typing import Callable, Optional, Protocol

from .models import ModelReply, ModelRequest, Span, ToolRequest, ToolResponse


class BudgetStop(Exception):
    """A model port raises this when the gateway precheck refuses a call. `kind` is a short budget kind."""

    def __init__(self, kind: str = "cost"):
        super().__init__(kind)
        self.kind = kind


class ModelPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelReply:
        """One model call. Raise `BudgetStop` when over budget. Any other exception fails the run closed."""


class ToolPort(Protocol):
    def call(self, request: ToolRequest) -> ToolResponse:
        """Execute through the Tool API gateway (roles, scope, approvals, idempotency, audit all live there)."""


class TraceStore(Protocol):
    def append(self, span: Span) -> None: ...

    def spans(self, tenant_id: str, run_id: str) -> list: ...


class EventSink(Protocol):
    def emit(self, tenant_id: str, subject: str, type: str, data: dict, trace: Optional[dict]) -> None:
        """Write one event-stream event (contract 4). Must not raise into the loop."""


class Ids(Protocol):
    def new_id(self, prefix: str) -> str: ...

    def new_ulid(self) -> str: ...


Clock = Callable[[], float]  # seconds, monotonic


class CancelToken:
    """Set from another thread (the stream endpoint on disconnect). The loop checks it between steps."""

    def __init__(self):
        self._ev = threading.Event()

    def cancel(self) -> None:
        self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()
