"""Header and cookie filtering (ADR-0016). Allow-list only: anything not named here is dropped."""
from __future__ import annotations

import re

from .markers import contains_engine_marker

Headers = list[tuple[str, str]]

# Response headers that may reach the customer. Everything else (Server, X-Frappe-*, X-Page-Name,
# X-Powered-By, Via, Link, Location, ...) is dropped. Content-Length is recomputed by the gateway.
RESPONSE_ALLOW = frozenset({
    "content-type", "cache-control", "etag", "expires", "last-modified", "content-language",
    "content-disposition", "retry-after", "vary",
})
# Request headers forwarded to the engine. Identity never comes from the caller: no Authorization,
# X-Forwarded-*, role or tenant headers are forwarded.
REQUEST_ALLOW = frozenset({
    "accept", "accept-language", "content-type", "if-none-match", "if-modified-since", "idempotency-key",
})

SESSION_COOKIE = "__Host-session"  # ours; the engine's `sid` is mapped to and from it
ENGINE_SESSION_COOKIE = "sid"
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._~%=+/-]*$")

SECURITY_HEADERS: Headers = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
]


def filter_response_headers(headers: Headers) -> Headers:
    """Keep allow-listed headers whose value carries no engine marker."""
    out: Headers = []
    for name, value in headers:
        lname = name.lower()
        if lname in RESPONSE_ALLOW and not contains_engine_marker(value) and "\r" not in value and "\n" not in value:
            out.append((name, value))
    return out


def with_security_headers(headers: Headers) -> Headers:
    present = {n.lower() for n, _ in headers}
    return headers + [(n, v) for n, v in SECURITY_HEADERS if n.lower() not in present]


def rewrite_set_cookies(headers: Headers) -> Headers:
    """Map the engine session cookie to ours with hardened attributes; drop every other engine cookie.

    Dropped by design: system_user, full_name, user_id, user_image and anything unknown.
    """
    out: Headers = []
    for name, value in headers:
        if name.lower() != "set-cookie":
            continue
        parts = [p.strip() for p in value.split(";")]
        cname, _, cvalue = parts[0].partition("=")
        if cname.strip() != ENGINE_SESSION_COOKIE or not _SAFE_VALUE_RE.match(cvalue):
            continue
        cookie = f"{SESSION_COOKIE}={cvalue}"
        for attr in parts[1:]:
            key, _, val = attr.partition("=")
            if key.strip().lower() == "max-age" and val.strip().lstrip("-").isdigit():
                cookie += f"; Max-Age={val.strip()}"
        out.append(("Set-Cookie", cookie + "; Path=/; Secure; HttpOnly; SameSite=Lax"))
    return out


def request_headers_for_engine(headers: Headers) -> Headers:
    """Forward allow-listed headers, and translate our session cookie to the engine's. Fail closed."""
    out: Headers = [(n, v) for n, v in headers if n.lower() in REQUEST_ALLOW and "\r" not in v and "\n" not in v]
    for name, value in headers:
        if name.lower() != "cookie":
            continue
        for pair in value.split(";"):
            cname, _, cvalue = pair.strip().partition("=")
            if cname == SESSION_COOKIE and _SAFE_VALUE_RE.match(cvalue):
                out.append(("Cookie", f"{ENGINE_SESSION_COOKIE}={cvalue}"))
    return out
