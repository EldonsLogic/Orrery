"""Request handling for the agent stream endpoint: auth, run loop, allow-listing, errors, audit.

`handle_request` is framework-free: it returns a `Response` whose `body` is an iterator of SSE bytes."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from . import events as ev
from .audit import Auditor
from .errors import AuthFailure, DomainFailure, InputRejected, to_error
from .ports import AgentRuntime, ApprovalReader, Principal, RuntimeContext, RuntimeUsage, TokenVerifier
from .request import RunRequest, parse_run_input

log = logging.getLogger("agui")
SSE_HEADERS = (("content-type", "text/event-stream"), ("cache-control", "no-cache, no-transform"),
               ("x-accel-buffering", "no"))
MAX_EVENTS_PER_RUN = 5000


class ThreadRegistry:
    """Thread ownership and server-held state. A thread id belongs to one (tenant, user) for good."""

    def __init__(self):
        self._owner: dict = {}
        self._state: dict = {}

    def claim(self, p: Principal, thread_id: str) -> dict:
        owner = self._owner.setdefault(thread_id, (p.tenant_id, p.subject))
        if owner != (p.tenant_id, p.subject):
            raise AuthFailure(403)
        return self._state.setdefault(thread_id, {})


@dataclass
class Dependencies:
    verifier: TokenVerifier
    runtime: AgentRuntime
    approvals: ApprovalReader
    auditor: Auditor
    resolve_tenant: Callable[[str], Optional[str]]  # gateway host -> tenant id; never from body or URL
    threads: ThreadRegistry = field(default_factory=ThreadRegistry)


@dataclass
class Response:
    status: int
    headers: tuple
    body: Iterator[bytes]


def _json_error(exc, locale) -> Response:
    e = to_error(exc, locale)
    import json
    payload = json.dumps({"error": {"code": e["code"], "message_key": e["message_key"]}}).encode()
    return Response(getattr(exc, "status", 500), (("content-type", "application/json"),), iter([payload]))


def _locale(headers: dict) -> str:
    return "ar" if str(headers.get("accept-language", "")).strip().lower().startswith("ar") else "en"


def _bearer(headers: dict) -> str:
    h = headers.get("authorization", "")
    if not isinstance(h, str) or not h[:7].lower() == "bearer " or not h[7:].strip():
        raise AuthFailure(401)
    return h[7:].strip()


def authenticate(deps: Dependencies, headers: dict, host: str) -> Principal:
    """Fail closed. The tenant is resolved from the host by the gateway and must match the token's tenant."""
    tenant = deps.resolve_tenant(host or "") if host else None
    if not tenant:
        raise AuthFailure(401)
    try:
        token = _bearer(headers)
        p = deps.verifier.verify(token, tenant)
    except AuthFailure:
        deps.auditor.denied(tenant, "no_token")
        raise
    except Exception:
        deps.auditor.denied(tenant, "invalid_session")
        raise AuthFailure(401)
    if not isinstance(p, Principal) or p.tenant_id != tenant:
        deps.auditor.denied(tenant, "tenant_mismatch")
        raise AuthFailure(401)
    return p


def handle_request(deps: Dependencies, *, method: str, headers: dict, host: str, body: bytes) -> Response:
    headers = {str(k).lower(): v for k, v in (headers or {}).items()}
    locale = _locale(headers)
    if method.upper() != "POST":
        return Response(405, (("allow", "POST"),), iter([b""]))
    try:
        principal = authenticate(deps, headers, host)
        req = parse_run_input(body)
        state = deps.threads.claim(principal, req.thread_id)
    except (AuthFailure, InputRejected) as exc:
        return _json_error(exc, locale)
    except Exception as exc:  # fail closed
        return _json_error(exc, locale)
    return Response(200, SSE_HEADERS, _stream(deps, principal, req, dict(state), locale, headers))


def _error_frame(exc, locale, p, run_id, deps) -> bytes:
    e = to_error(exc, locale)
    deps.auditor.run_event(p, run_id, "failed", e["code"])
    return ev.sse_frame(ev.run_error(e["message"], e["code"]))


def _recheck(deps, headers, host_tenant_principal: Principal) -> None:
    """The stream ends when the token or session version stops being valid (ADR-0044 item 10)."""
    try:
        deps.verifier.verify(_bearer(headers), host_tenant_principal.tenant_id)
    except Exception:
        raise AuthFailure(401)


def _stream(deps, p: Principal, req: RunRequest, server_state: dict, locale: str, headers: dict):
    run_id = req.run_id
    deps.auditor.run_event(p, run_id, "started")
    yield ev.sse_frame(ev.run_started(req.thread_id, run_id))
    open_msgs, open_calls, count = set(), set(), 0
    try:
        for aid in req.resume_ids:  # display only: report the recorded state, change nothing
            a = deps.approvals.get(p, aid)
            if a is not None:
                f = ev.sanitize(ev.custom("approval.status", {"approvalId": a.id, "status": a.status}))
                if f:
                    yield ev.sse_frame(f)
        ctx = RuntimeContext(principal=p, thread_id=req.thread_id, run_id=run_id, user_text=req.user_text,
                             server_state=server_state, locale=locale)
        source = deps.runtime.run(ctx) if req.user_text else ()
        for item in source:
            count += 1
            if count > MAX_EVENTS_PER_RUN:
                raise DomainFailure("limit")  # unmapped -> generic internal error
            _recheck(deps, headers, p)
            if isinstance(item, RuntimeUsage):
                deps.auditor.usage(p, run_id, item)
                continue
            out = ev.sanitize(item)
            if out is None or not _ordered(out, open_msgs, open_calls):
                log.warning("agui dropped event type=%s", item.get("type") if isinstance(item, dict) else None)
                continue
            if out["type"] in ("RUN_STARTED", "RUN_FINISHED", "RUN_ERROR"):
                continue  # the endpoint owns the run envelope
            yield ev.sse_frame(out)
        interrupts = [ev.interrupt(a.id, message=a.summary or None) for a in deps.approvals.pending(p)]
    except GeneratorExit:
        raise
    except Exception as exc:
        yield _error_frame(exc, locale, p, run_id, deps)
        return
    deps.auditor.run_event(p, run_id, "completed")
    yield ev.sse_frame(ev.run_finished(req.thread_id, run_id, interrupts))


def _ordered(out: dict, msgs: set, calls: set) -> bool:
    t = out["type"]
    if t == "TEXT_MESSAGE_START":
        msgs.add(out["messageId"])
    elif t in ("TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"):
        if out["messageId"] not in msgs:
            return False
        if t == "TEXT_MESSAGE_END":
            msgs.discard(out["messageId"])
    elif t == "TOOL_CALL_START":
        calls.add(out["toolCallId"])
    elif t in ("TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"):
        if out["toolCallId"] not in calls:
            return False
    return True
