"""API edge core (PLT-024, ADR-0016): the only customer-facing surface in front of the engine.

Deny by default: a request is routed only if its normalised path is under /v1/ and matches a route
registered by us (exact path, plus at most `max_params` identifier segments). Engine output is never
passed through raw: a route declares an allow-listed schema (our field names) and the gateway builds the
response body from it; a non-JSON route must explicitly declare the sanitised content type its handler
produces. Engine errors are mapped to our error model, engine headers and cookies never reach the caller,
and every request is audited (an intent record before a mutating request, an outcome record after).
"""
from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass
from typing import Callable, Mapping

from ..ulid import UlidGenerator
from .errors import ErrorResult, error_body, is_engine_error, map_engine_error
from .headers import (
    CLEAR_SESSION_COOKIE, Headers, engine_session_directive, filter_response_headers, has_gateway_session_cookie,
    request_headers_for_engine, with_security_headers,
)
from .markers import contains_engine_structure
from .paths import ALLOWED_METHODS, is_own_path, normalise_path
from .projection import RenderError, media_type, project_json_body, validate_schema

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PARAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # no dots: an engine method name cannot be a path parameter
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}$")
_CONTENT_TYPE_RE = re.compile(r"^[a-z]+/[a-z0-9][a-z0-9.+-]*$")


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    path: str  # raw request path without query string
    headers: Headers
    body: bytes = b""


@dataclass(frozen=True)
class UpstreamRequest:
    """What a route handler receives: our own path and engine-safe headers only (never a cookie)."""

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


@dataclass(frozen=True)
class Route:
    """One registered route. Exactly one of `schema` or `own_content_type`.

    schema: allow-list projection of a JSON engine response (see projection.py).
    own_content_type: the handler's body is produced by OUR renderer (for example our PDF renderer), not
        the engine's; the gateway then passes the bytes through only when the upstream media type equals
        this declaration. Declaring it is a security-reviewed trust statement about the handler.
    filename: our own download name (Content-Disposition); the engine's is never used.
    max_params: how many identifier segments may follow the route path (0 = exact match only).
    """

    handler: Handler
    schema: object | None = None
    own_content_type: str | None = None
    filename: str | None = None
    max_params: int = 0

    def __post_init__(self):
        if not callable(self.handler) or (self.schema is None) == (self.own_content_type is None):
            raise ValueError("a route needs a handler and exactly one of schema or own_content_type")
        if self.schema is not None:
            validate_schema(self.schema)
        else:
            ctype = self.own_content_type
            if not isinstance(ctype, str) or not _CONTENT_TYPE_RE.match(ctype.split(";")[0].strip().lower()) or \
                    ctype.split(";")[0].strip().lower() in ("application/json", "text/html"):
                raise ValueError("own_content_type must be a concrete non-JSON, non-HTML media type")
        if self.filename is not None and not _FILENAME_RE.match(self.filename):
            raise ValueError("filename must be a plain safe name")
        if not isinstance(self.max_params, int) or not 0 <= self.max_params <= 4:
            raise ValueError("max_params must be 0..4")


def _etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def _client_has(headers: Headers, etag: str) -> bool:
    for name, value in headers:
        if name.lower() == "if-none-match":
            tags = [t.strip() for t in value.split(",")]
            return "*" in tags or etag in tags or ("W/" + etag) in tags
    return False


class Gateway:
    def __init__(self, routes: Mapping[str, Route], *, audit_sink: AuditSink, ulid: UlidGenerator | None = None):
        if not callable(audit_sink):
            raise TypeError("audit_sink is required: the gateway does not serve unaudited requests")
        self._routes: dict[str, Route] = {}
        for prefix, route in routes.items():
            if not isinstance(route, Route):
                raise TypeError(f"route {prefix!r} must be a Route (schema-declared), not a bare handler")
            if normalise_path(prefix) != prefix or not is_own_path(prefix):
                raise ValueError(f"route {prefix!r} must be a normalised path under /v1/")
            self._routes[prefix] = route
        self._audit_sink = audit_sink
        self._ulid = ulid or UlidGenerator()
        # Outcome records that could not be written after a committed effect; drain and retry them.
        self._unlogged: deque[dict] = deque(maxlen=1000)

    def drain_unlogged(self) -> list[dict]:
        records = list(self._unlogged)
        self._unlogged.clear()
        return records

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        audit_id = f"aud_{self._ulid.generate()}"
        method = request.method.upper() if isinstance(request.method, str) else ""
        path = normalise_path(request.path)
        route = self._match(path) if method in ALLOWED_METHODS else None
        if route is None:
            return self._complete(request, audit_id, self._error_parts(audit_id, "not_found", "path_denied"), False)
        if has_gateway_session_cookie(request.headers):
            # No session store yet (ADR-0007): nothing can validate this cookie. Fail closed and clear it.
            parts = self._error_parts(audit_id, "permission_denied", "session_unsupported", [("Set-Cookie", CLEAR_SESSION_COOKIE)])
            return self._complete(request, audit_id, parts, False)
        mutating = method in MUTATING_METHODS
        if mutating and not self._write(self._record(request, audit_id, "intent")):
            return self._unaudited(audit_id)  # the handler never runs without an audit trail
        try:
            upstream = route.handler(UpstreamRequest(method, path, request_headers_for_engine(request.headers), request.body))
            parts = self._filter(route, upstream, request, method, audit_id)
        except Exception:  # fail closed; never leak exception text
            parts = self._error_parts(audit_id, "internal_error", "handler_exception")
        return self._complete(request, audit_id, parts, mutating)

    def _match(self, path: str | None) -> Route | None:
        if not is_own_path(path) or contains_engine_structure(path):
            return None
        best: tuple[str, Route] | None = None
        for prefix, route in self._routes.items():
            if path == prefix:
                extra: list[str] = []
            elif path.startswith(prefix + "/"):
                extra = path[len(prefix) + 1:].split("/")
            else:
                continue
            if len(extra) > route.max_params or not all(_PARAM_RE.match(s) for s in extra):
                continue
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, route)
        return best[1] if best else None

    def _filter(self, route: Route, up: UpstreamResponse, request: GatewayRequest, method: str, audit_id: str):
        if not isinstance(up.status, int) or not 200 <= up.status <= 599 or not isinstance(up.body, bytes):
            return self._error_parts(audit_id, "internal_error", "bad_upstream_response")
        if any(n.lower() in ("content-encoding", "transfer-encoding") and v.strip().lower() not in ("", "identity")
               for n, v in up.headers):
            return self._error_parts(audit_id, "internal_error", "unscannable_encoding")  # cannot be checked
        if up.status >= 300 or is_engine_error(up.status, up.body):
            # 3xx: engine redirects (login, desk) are never followed or exposed. A 304 cannot be legitimate:
            # conditional headers are not forwarded (we answer them from our own ETag).
            status = up.status if up.status >= 400 else 500
            return self._error_parts(audit_id, None, "engine_error", result=map_engine_error(status, up.headers, up.body, audit_id))
        directive = engine_session_directive(up.headers)
        if directive == "issue":  # the engine sid is never our session (ADR-0007 will define one)
            return self._error_parts(audit_id, "internal_error", "engine_session_not_issuable")
        try:
            content_type, body = self._render(route, up)
        except RenderError as exc:
            return self._error_parts(audit_id, "internal_error", exc.reason)
        headers: Headers = [("Content-Type", content_type)] + filter_response_headers(up.headers)
        if route.filename:
            headers.append(("Content-Disposition", f'attachment; filename="{route.filename}"'))
        if directive == "clear":
            headers.append(("Set-Cookie", CLEAR_SESSION_COOKIE))
        if body and up.status == 200:
            etag = _etag(body)
            headers.append(("ETag", etag))
            if method in ("GET", "HEAD") and _client_has(request.headers, etag):
                return 304, with_security_headers([h for h in headers if h[0] != "Content-Type"]), b"", "not_modified"
        return up.status, with_security_headers(headers), body, "ok"

    @staticmethod
    def _render(route: Route, up: UpstreamResponse) -> tuple[str, bytes]:
        if up.status in (204, 205) and not up.body:
            return (route.own_content_type or "application/json"), b""
        if route.schema is not None:
            return "application/json", project_json_body(up.headers, up.body, route.schema)
        if media_type(up.headers)[0] != route.own_content_type.split(";")[0].strip().lower():
            raise RenderError("undeclared_content_type")
        return route.own_content_type, up.body

    def _error_parts(self, audit_id, code, reason, extra_headers: Headers = (), *, result: ErrorResult | None = None):
        result = result or error_body(code, audit_id)
        headers: Headers = [("Content-Type", "application/json")] + list(extra_headers)
        if result.http_status == 429 and result.retry_after_s is not None:
            headers.append(("Retry-After", str(result.retry_after_s)))  # our own value, never the engine's header
        return result.http_status, with_security_headers(headers), result.body, reason

    @staticmethod
    def _record(request: GatewayRequest, audit_id: str, phase: str, **extra) -> dict:
        return {"audit_id": audit_id, "phase": phase, "method": str(request.method)[:16],
                "path": str(request.path)[:256], **extra}

    def _write(self, record: dict) -> bool:
        try:
            self._audit_sink(record)
            return True
        except Exception:
            return False

    def _unaudited(self, audit_id: str) -> GatewayResponse:
        failed = error_body("internal_error", audit_id)
        headers = with_security_headers([("Content-Type", "application/json"), ("Content-Length", str(len(failed.body)))])
        return GatewayResponse(failed.http_status, headers, failed.body, audit_id)

    def _complete(self, request, audit_id, parts, effect_possible: bool) -> GatewayResponse:
        """Write the outcome record. Failure is an error, except after a committed mutating effect."""
        status, headers, body, reason = parts
        record = self._record(request, audit_id, "outcome", status=status, reason=reason)
        if not self._write(record):
            if not effect_possible:
                return self._unaudited(audit_id)
            # The write may have committed: report the real result (a 500 would invite a duplicate) and
            # keep the outcome record for retry. The intent record already exists.
            self._unlogged.append(record)
        headers = [(n, v) for n, v in headers if n.lower() != "content-length"]
        if status != 304:
            headers.append(("Content-Length", str(len(body))))
        return GatewayResponse(status, headers, body, audit_id)
