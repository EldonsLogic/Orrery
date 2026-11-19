"""Our error model (contracts/tool-api.md section 7) and engine-error mapping (ADR-0016).

The mapping reads only the HTTP status, the engine exception type (matched against a fixed table) and
Retry-After. No engine message, trace, SQL or field text is ever copied into the result.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# code -> (http status we return, retryable)
ERROR_CODES: dict[str, tuple[int, bool]] = {
    "invalid_arguments": (400, True),
    "permission_denied": (403, False),
    "not_found": (404, False),
    "conflict": (409, True),
    "rate_limited": (429, True),
    "engine_error": (502, False),
    "internal_error": (500, False),
    "audit_unavailable": (503, True),  # local edge availability error; contract follow-up in Q-300
}

# Fixed table of engine exception types we recognise. Anything else falls back to the HTTP status.
# UNVERIFIED (from knowledge of the engine, not a live run): confirm in QA-016; OPR-018 refines it.
_EXC_TYPE_CODES = {
    "PermissionError": "permission_denied",
    "AuthenticationError": "permission_denied",
    "DoesNotExistError": "not_found",
    "TimestampMismatchError": "conflict",
    "DuplicateEntryError": "conflict",
    "RateLimitExceededError": "rate_limited",
    "ValidationError": "invalid_arguments",
    "MandatoryError": "invalid_arguments",
    "LinkValidationError": "invalid_arguments",
    "InvalidNameError": "invalid_arguments",
}
# 405, 413, 417 (the engine's ValidationError status, UNVERIFIED) and 422 are caller errors, not engine faults.
_STATUS_CODES = {
    400: "invalid_arguments", 401: "permission_denied", 403: "permission_denied", 404: "not_found",
    405: "invalid_arguments", 409: "conflict", 413: "invalid_arguments", 417: "invalid_arguments",
    422: "invalid_arguments", 429: "rate_limited",
}
MAX_RETRY_AFTER_S = 3600
# On a 2xx these mean the engine failed inside a 200. `_server_messages` (msgprint) is NOT here: the engine
# attaches it to successful writes too, and misreporting a committed write as a failure causes duplicates.
_ENGINE_ERROR_KEYS = {"exc", "exc_type"}


@dataclass(frozen=True)
class ErrorResult:
    http_status: int
    body: bytes  # JSON, our error model
    retry_after_s: int | None = None  # our own Retry-After value (429 only)


def error_body(code: str, audit_id: str, details: dict | None = None, *, unavailable: bool = False) -> ErrorResult:
    http_status, retryable = ERROR_CODES[code]
    if unavailable:  # engine temporarily down: tell the caller it may retry
        http_status, retryable = 503, True
    payload = {
        "status": "error",
        "error": {"code": code, "message_key": f"errors.{code}", "retryable": retryable, "details": details or {}},
        "audit_id": audit_id,
    }
    retry_after = (details or {}).get("retry_after_s") if code == "rate_limited" else None
    return ErrorResult(http_status, json.dumps(payload, separators=(",", ":")).encode(), retry_after)


def _exc_type(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return None
    value = data.get("exc_type") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _retry_after_s(headers: list[tuple[str, str]]) -> int | None:
    """Seconds from a delta or an HTTP-date Retry-After, bounded. We emit only our own number."""
    for name, value in headers:
        if name.lower() != "retry-after":
            continue
        value = value.strip()
        if value.isdigit():
            return min(int(value), MAX_RETRY_AFTER_S)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, min(int((when - datetime.now(timezone.utc)).total_seconds()), MAX_RETRY_AFTER_S))
    return None


def map_engine_error(status: int, headers: list[tuple[str, str]], body: bytes, audit_id: str) -> ErrorResult:
    """Turn an engine failure response into our error model. Never returns engine text."""
    code = _EXC_TYPE_CODES.get(_exc_type(body) or "") or _STATUS_CODES.get(status)
    if code is None:
        code = "engine_error"
    details: dict = {}
    if code == "rate_limited":
        details["retry_after_s"] = _retry_after_s(headers) or 1
    unavailable = code == "engine_error" and status in (502, 503, 504)
    return error_body(code, audit_id, details, unavailable=unavailable)


def is_engine_error(status: int, body: bytes) -> bool:
    """Engine failures: any 4xx/5xx, or a 2xx body carrying `exc` or `exc_type` (an error inside a 200)."""
    if status >= 400:
        return True
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return False
    return isinstance(data, dict) and bool(data.keys() & _ENGINE_ERROR_KEYS)
