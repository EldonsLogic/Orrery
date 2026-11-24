"""Intent router port (OPR-002 fills it). The default says `ask`. The router only picks a mode; it grants nothing:
the Tool API still checks every call against the caller's roles (ADR-0004).

The port may return a bare mode string (legacy) or a `RouteResult` that also carries the confirmation binding (action
id, args hash, risk) the router established against the chat's pending (Q-265). `safe_route` always returns a
`RouteResult` and falls back to `ask` on any fault or malformed result."""
from __future__ import annotations

import logging
from typing import Protocol, Union

from .models import DEFAULT_MODE, MODES, PRIVILEGED, RISKS, RouteRequest, RouteResult

log = logging.getLogger("chat")
_RESOLVES = (None, "confirmed", "declined", "expired")


class RouterPort(Protocol):
    def route(self, request: RouteRequest) -> Union[str, RouteResult]:
        """Return one of discover, ask, act, change, or a RouteResult with the confirmation binding."""


class DefaultRouter:
    def route(self, request: RouteRequest) -> str:
        return DEFAULT_MODE


def _valid(r: RouteResult) -> bool:
    aid, ah = r.confirms_action_id, r.confirms_args_hash
    if r.mode not in MODES or r.risk_hint not in RISKS or r.resolves_pending not in _RESOLVES:
        return False
    if (aid is None) != (ah is None) or not all(x is None or (isinstance(x, str) and x) for x in (aid, ah)):
        return False
    if aid is not None and (r.mode not in PRIVILEGED or r.resolves_pending != "confirmed"):
        return False  # a binding without a privileged confirmed turn is meaningless: refuse the whole result
    if r.resolves_pending == "confirmed" and aid is None:
        return False
    return type(r.requires_confirmation) is bool


def safe_route(router: RouterPort, request: RouteRequest) -> RouteResult:
    """A router fault, an unknown mode or a malformed binding falls back to `ask` with no binding."""
    fallback = RouteResult(DEFAULT_MODE)
    try:
        out = router.route(request)
    except Exception as exc:
        log.error("router failure type=%s", type(exc).__name__)
        return fallback
    if isinstance(out, str):
        return RouteResult(out) if out in MODES else fallback
    return out if isinstance(out, RouteResult) and _valid(out) else fallback


class IntentRouterAdapter:
    """Binds the OPR-002 `IntentRouter` to the chat's port: the chat's pending and clock go in, and the decision's
    mode, risk and confirmation binding come out. `blueprint_live` and `entity_names(tenant_id)` are trusted host
    facts (never message text)."""

    def __init__(self, intent_router, *, blueprint_live=True, entity_names=lambda tenant_id: ()):
        self._r, self._live, self._names = intent_router, blueprint_live, entity_names

    def route(self, request: RouteRequest) -> RouteResult:
        from router.models import Pending, RouteContext  # the OPR-002 package, not this module

        pending = None
        pb = request.pending
        if pb is not None:
            try:
                pending = Pending(pb.mode, pb.action_id, pb.args_hash, pb.risk, pb.expires_at)
            except ValueError:
                pending = None
        live = self._live() if callable(self._live) else bool(self._live)
        ctx = RouteContext(live, tuple(self._names(request.tenant_id)), pending, request.locale, request.now)
        d = self._r.route(request.text, ctx)
        reasons = set(d.reasons)
        resolves = None
        if "pending_expired" in reasons:
            resolves = "expired"
        elif "confirmation_of_pending" in reasons:
            resolves = "confirmed" if d.confirms_action_id else "declined"
        return RouteResult(d.mode, d.risk_hint, d.requires_confirmation, d.confirms_action_id, d.confirms_args_hash,
                           resolves, d)
