"""API edge core (PLT-024, ADR-0016): the only customer-facing surface in front of the engine.

Deny by default: a request is routed only if its normalised path is under /v1/ and matches a route
registered by us. Every response passes through the same filter: headers allow-listed, cookies
renamed, engine errors mapped to our error model, success bodies checked for engine markers
(a hit is replaced by internal_error; the original is never sent).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ..ulid import UlidGenerator
from .errors import ErrorResult, error_body, is_engine_error, map_engine_error
from .headers import (
    Headers, filter_response_headers, request_headers_for_engine, rewrite_set_cookies, with_security_headers,
)
from .markers import contains_engine_marker
from .paths import ALLOWED_METHODS, is_own_path, normalise_path


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    path: str  # raw request path without query string
    headers: Headers
    body: bytes = b""


@dataclass(frozen=True)
class UpstreamRequest:
    """What a route handler receives: our own path and engine-safe headers only."""

    method: str
    path: str
    headers: Headers
    body: bytes


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    headers: Headers
    body: bytes = b""


@dataclass(frozen=True)
class GatewayResponse:
    status: int
    headers: Headers
    body: bytes
    audit_id: str


Handler = Callable[[UpstreamRequest], UpstreamResponse]
AuditSink = Callable[[dict], None]


class Gateway:
    def __init__(self, routes: Mapping[str, Handler], *, audit_sink: AuditSink | None = None,
                 ulid: UlidGenerator | None = None):
        self._routes: dict[str, Handler] = {}
        for prefix, handler in routes.items():
            if normalise_path(prefix) != prefix or not is_own_path(prefix):
                raise ValueError(f"route {prefix!r} must be a normalised path under /v1/")
            self._routes[prefix] = handler
        self._audit_sink = audit_sink
        self._ulid = ulid or UlidGenerator()

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        audit_id = f"aud_{self._ulid.generate()}"
        try:
            status, headers, body, reason = self._dispatch(request, audit_id)
        except Exception:  # fail closed; never leak exception text
            return self._error(audit_id, "internal_error", "handler_exception", request)
        return self._finish(request, audit_id, status, headers, body, reason)

    def _dispatch(self, request: GatewayRequest, audit_id: str):
        path = normalise_path(request.path)
        method = request.method.upper() if isinstance(request.method, str) else ""
        handler = self._match(path)
        if method not in ALLOWED_METHODS or handler is None:
            return self._error_parts(audit_id, "not_found", "path_denied")
        upstream = handler(UpstreamRequest(method, path, request_headers_for_engine(request.headers), request.body))
        return self._filter(upstream, audit_id)

    def _match(self, path: str | None) -> Handler | None:
        if not is_own_path(path):
            return None
        best = max((p for p in self._routes if path == p or path.startswith(p + "/")), key=len, default=None)
        return self._routes[best] if best else None

    def _filter(self, up: UpstreamResponse, audit_id: str):
        if not isinstance(up.status, int) or not 200 <= up.status <= 599 or not isinstance(up.body, bytes):
            return self._error_parts(audit_id, "internal_error", "bad_upstream_response")
        if any(n.lower() == "content-encoding" and v.strip().lower() != "identity" for n, v in up.headers):
            return self._error_parts(audit_id, "internal_error", "unscannable_encoding")  # cannot be checked
        if up.status >= 300 or is_engine_error(up.status, up.body):
            # 3xx: engine redirects (login, desk) are never followed or exposed.
            status = up.status if up.status >= 400 else 500
            result = map_engine_error(status, up.headers, up.body, audit_id)
            return self._error_parts(audit_id, None, "engine_error", result=result, retry_headers=up.headers)
        if contains_engine_marker(up.body):
            return self._error_parts(audit_id, "internal_error", "engine_marker_in_body")
        headers = filter_response_headers(up.headers) + rewrite_set_cookies(up.headers)
        return up.status, with_security_headers(headers), up.body, "ok"

    def _error_parts(self, audit_id, code, reason, *, result: ErrorResult | None = None, retry_headers: Headers = ()):
        result = result or error_body(code, audit_id)
        headers: Headers = [("Content-Type", "application/json")]
        if result.http_status == 429:
            headers += [(n, v) for n, v in filter_response_headers(list(retry_headers)) if n.lower() == "retry-after"]
        return result.http_status, with_security_headers(headers), result.body, reason

    def _error(self, audit_id, code, reason, request):
        status, headers, body, reason = self._error_parts(audit_id, code, reason)
        return self._finish(request, audit_id, status, headers, body, reason)

    def _finish(self, request, audit_id, status, headers, body, reason) -> GatewayResponse:
        if self._audit_sink is not None:
            try:
                self._audit_sink({"audit_id": audit_id, "method": str(request.method)[:16],
                                  "path": str(request.path)[:256], "status": status, "reason": reason})
            except Exception:  # audit is required: fail closed rather than answer unlogged
                failed = error_body("internal_error", audit_id)
                return GatewayResponse(failed.http_status,
                                       with_security_headers([("Content-Type", "application/json")]),
                                       failed.body, audit_id)
        headers = [(n, v) for n, v in headers if n.lower() != "content-length"]
        headers.append(("Content-Length", str(len(body))))
        return GatewayResponse(status, headers, body, audit_id)
