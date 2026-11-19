"""Intent router port (OPR-002 fills it). The default says `ask`. The router only picks a mode; it grants nothing:
the Tool API still checks every call against the caller's roles (ADR-0004)."""
from __future__ import annotations

import logging
from typing import Protocol

from .models import DEFAULT_MODE, MODES, RouteRequest

log = logging.getLogger("chat")


class RouterPort(Protocol):
    def route(self, request: RouteRequest) -> str:
        """Return one of discover, ask, act, change."""


class DefaultRouter:
    def route(self, request: RouteRequest) -> str:
        return DEFAULT_MODE


def safe_route(router: RouterPort, request: RouteRequest) -> str:
    """A router fault or an unknown mode falls back to `ask`."""
    try:
        mode = router.route(request)
    except Exception as exc:
        log.error("router failure type=%s", type(exc).__name__)
        return DEFAULT_MODE
    return mode if mode in MODES else DEFAULT_MODE
