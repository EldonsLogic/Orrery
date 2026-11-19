"""Error firewall (ADR-0036, ADR-0044 item 6). Tool and model failures become a small closed set of codes.

A tool error keeps its code only when it is a Tool API class code or an ADR-0036 catalog id; anything else becomes
`internal_error`. Free-text fields (`details`, messages, exception text) are dropped: they may name the engine."""
from __future__ import annotations

import logging
import uuid

from toolapi.errors import build_error, load_catalog

log = logging.getLogger("agent_runtime")
# contracts/tool-api.md section 7. `approval_required` is a status here, not a failure.
TOOL_API_CODES = frozenset({"invalid_arguments", "unknown_tool", "permission_denied", "approval_required",
                            "guard_failed", "not_found", "conflict", "idempotency_conflict", "rate_limited",
                            "budget_exceeded", "engine_error", "internal_error"})
RETRYABLE = frozenset({"invalid_arguments", "conflict", "rate_limited"})
RUN_CODES = frozenset({"budget_exceeded", "permission_denied", "invalid_arguments", "internal_error", "cancelled",
                       "needs_approval", "propose_unavailable"})
_CATALOG = None


def _catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_catalog()
    return _CATALOG


def map_tool_error(error) -> dict:
    """Return {"code", "message_key", "retryable", "params"?} safe for the model and the trace."""
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and code in TOOL_API_CODES:
        return {"code": code, "message_key": f"errors.{code}", "retryable": code in RETRYABLE}
    if isinstance(code, str):
        built = build_error(code, error.get("params") if isinstance(error, dict) else None, _catalog(),
                            uuid.uuid4().hex)
        dom = built.get("domain")
        if dom:  # catalog id with valid typed params
            return {"code": dom["code"], "message_key": f"errors.domain.{dom['code']}",
                    "retryable": bool(built.get("retryable")), "params": dom.get("params", {})}
    return {"code": "internal_error", "message_key": "errors.internal_error", "retryable": False}


def firewall_exception(exc: BaseException) -> dict:
    """An exception from a port: log the type and a correlation id, return only `internal_error`."""
    cid = uuid.uuid4().hex
    log.error("agent runtime port failure correlation_id=%s type=%s", cid, type(exc).__name__)
    return {"code": "internal_error", "message_key": "errors.internal_error", "retryable": False,
            "correlation_id": cid}
