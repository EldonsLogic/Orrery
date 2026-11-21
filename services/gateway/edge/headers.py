"""Header and cookie handling (ADR-0016). Allow-list only: anything not named here is dropped.

Sessions: the gateway does not issue sessions yet (ADR-0007 decides how). Until then it fails closed:
the engine `sid` is never exposed as our session and no inbound cookie is ever forwarded to the engine.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .markers import contains_engine_marker

Headers = list[tuple[str, str]]

# Response headers that may reach the customer, after a marker check. Everything else (Server, X-Frappe-*,
# X-Page-Name, X-Powered-By, Via, Link, Location, Cache-Control, ETag, Expires, Last-Modified,
# Content-Disposition, Retry-After...) is dropped; we build Content-Type, ETag, Content-Disposition,
# Cache-Control and Retry-After ourselves. Content-Length is recomputed by the gateway.
RESPONSE_ALLOW = frozenset({"content-language", "vary"})
# Request headers forwarded to the engine. Identity never comes from the caller: no Authorization,
# Cookie, X-Forwarded-*, role or tenant headers. Conditional headers are answered by the gateway itself
# (our ETag), so they are not forwarded either.
REQUEST_ALLOW = frozenset({"accept", "accept-language", "content-type", "idempotency-key"})

SESSION_COOKIE = "__Host-session"  # ours; reserved for the ADR-0007 session store
CLEAR_SESSION_COOKIE = f"{SESSION_COOKIE}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax"
_ENGINE_SID_RE = re.compile(r"(?:^|[,;]\s*)sid=([^;,]*)", re.IGNORECASE)

SECURITY_HEADERS: Headers = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
]


def _clean(value: str) -> bool:
    return "\r" not in value and "\n" not in value


def filter_response_headers(headers: Headers) -> Headers:
    """Keep allow-listed headers whose value carries no engine marker (engine-controlled channel)."""
    return [(n, v) for n, v in headers if n.lower() in RESPONSE_ALLOW and _clean(v) and not contains_engine_marker(v)]


def with_security_headers(headers: Headers) -> Headers:
    """Ours always wins: Cache-Control is `no-store` on every response; any other value is replaced."""
    kept = [(n, v) for n, v in headers if n.lower() != "cache-control"]
    present = {n.lower() for n, _ in kept}
    return kept + [(n, v) for n, v in SECURITY_HEADERS if n.lower() not in present] + [("Cache-Control", "no-store")]


def _expired(attrs: list[str]) -> bool:
    for attr in attrs:
        key, _, val = attr.partition("=")
        key, val = key.strip().lower(), val.strip()
        if key == "max-age" and val.lstrip("-").isdigit() and int(val) <= 0:
            return True
        if key == "expires":
            try:
                when = parsedate_to_datetime(val)
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when <= datetime.now(timezone.utc):
                return True
    return False


def engine_session_directive(headers: Headers) -> str:
    """What the engine's Set-Cookie headers ask for: "none", "clear" (logout/expiry) or "issue".

    "issue" (a live, non-Guest `sid`) cannot be honoured: exposing the engine sid as our session would
    make the engine session the identity. The gateway refuses such a response. Guest and empty values are
    ignored; an expired `sid` (the engine's logout) becomes a clear of our own cookie. Nothing else from
    Set-Cookie ever reaches the customer (system_user, full_name, user_id, user_image, unknown).
    """
    clear = False
    for name, value in headers:
        if name.lower() != "set-cookie":
            continue
        first, *attrs = [p.strip() for p in value.split(";")]
        cname, _, cvalue = first.partition("=")
        if cname.strip().lower() == "sid":
            if _expired(attrs):
                clear = True
            elif cvalue.strip() not in ("", "Guest"):
                return "issue"
            continue
        for match in _ENGINE_SID_RE.finditer(value):  # sid smuggled behind another cookie or a comma join
            if match.group(1).strip() not in ("", "Guest"):
                return "issue"
    return "clear" if clear else "none"


def has_gateway_session_cookie(headers: Headers) -> bool:
    """True when the caller sent our session cookie at all (valid, empty or duplicated): no session store exists yet."""
    for name, value in headers:
        if name.lower() != "cookie":
            continue
        for pair in value.split(";"):
            if pair.strip().partition("=")[0].strip().lower() == SESSION_COOKIE.lower():
                return True
    return False


def request_headers_for_engine(headers: Headers) -> Headers:
    """Forward allow-listed headers only. Cookies are never forwarded. Fail closed."""
    return [(n, v) for n, v in headers if n.lower() in REQUEST_ALLOW and _clean(v)]
