"""Our error model (contracts/tool-api.md section 7) and engine-error mapping (ADR-0016).

The mapping reads only the HTTP status, the engine exception type (matched against a fixed table) and
Retry-After. No engine message, trace, SQL or field text is ever copied into the result.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

# code -> (http status we return, retryable)
ERROR_CODES: dict[str, tuple[int, bool]] = {
    "invalid_arguments": (400, True),
    "permission_denied": (403, False),
    "not_found": (404, False),
    "conflict": (409, True),
    "rate_limited": (429, True),
    "engine_error": (502, False),
    "internal_error": (500, False),
}

# Fixed table of engine exception types we recognise. Anything else falls back to the HTTP status.
_EXC_TYPE_CODES = {
    "PermissionError": "permission_denied",
    "AuthenticationError": "permission_denied",
    "DoesNotExistError": "not_found",
    "TimestampMismatchError": "conflict",
    "RateLimitExceededError": "rate_limited",
}
_STATUS_CODES = {
    400: "invalid_arguments", 401: "permission_denied", 403: "permission_denied", 404: "not_found",
    409: "conflict", 429: "rate_limited",
}
MAX_RETRY_AFTER_S = 3600
_ENGINE_ERROR_KEYS = {"exc", "exc_type", "_server_messages", "_error_message"}


@dataclass(frozen=True)
class ErrorResult:
    http_status: int
    body: bytes  # JSON, our error model


def error_body(code: str, audit_id: str, details: dict | None = None, *, unavailable: bool = False) -> ErrorResult:
    http_status, retryable = ERROR_CODES[code]
    if unavailable:  # engine temporarily down: tell the caller it may retry
        http_status, retryable = 503, True
    payload = {
        "status": "error",
        "error": {"code": code, "message_key": f"errors.{code}", "retryable": retryable, "details": details or {}},
        "audit_id": audit_id,
    }
    return ErrorResult(http_status, json.dumps(payload, separators=(",", ":")).encode())


def _exc_type(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return None
    value = data.get("exc_type") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _retry_after_s(headers: list[tuple[str, str]]) -> int | None:
    for name, value in headers:
        if name.lower() == "retry-after" and value.strip().isdigit():
            return min(int(value.strip()), MAX_RETRY_AFTER_S)
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
    """Engine failures: any 4xx/5xx, or a body carrying engine exception fields."""
    if status >= 400:
        return True
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return False
    return isinstance(data, dict) and bool(data.keys() & _ENGINE_ERROR_KEYS)
