"""Engine headless route guard (ERP-020, ADR-0016).

The engine runs behind our gateway on an internal network and is never a customer-facing
web server. This guard is the engine-side half of that rule: it is registered as a
`before_request` hook and denies every HTTP request unless it matches an explicit
allowlist. Desk (/app, /desk), /login, the default website routes, static and file routes,
the legacy `cmd` RPC and every `/api/method/*` or `/api/resource/*` call that is not on the
allowlist all get the same plain 404, which says nothing about the engine.

Two tiers:
- Probe tier (no secret): `GET|HEAD /api/method/ping` only, for liveness checks.
- Internal tier: the adapter's methods and the generic record API, only for a caller that
  presents the shared internal token (header `X-Internal-Token`). The token is set by the
  gateway or adapter, never by a customer; the gateway must strip any client-supplied copy
  (PLT-024). Frappe's own authentication and permissions still apply on top.

Fails closed: no token configured, a short token, a wrong token, an unknown method, an odd
path or any error inside the guard means deny. This is defence in depth: the primary control
is that the engine port is reachable only from the internal network (infra/engine).

No LLM, UI or branding code. Never logs the token.
"""

import hmac
import os
import re
from typing import NamedTuple, Optional

try:
    import frappe
except ImportError:  # standalone unit tests
    frappe = None

try:
    from werkzeug.exceptions import NotFound
except ImportError:  # standalone unit tests, werkzeug ships with Frappe
    class NotFound(Exception):
        """Stand-in for werkzeug's 404 when running outside Frappe."""

TOKEN_HEADER = "X-Internal-Token"
TOKEN_ENV = "ENGINE_INTERNAL_TOKEN"
TOKEN_CONF_KEY = "internal_api_token"
MIN_TOKEN_LENGTH = 32

METHOD_PREFIX = "/api/method/change_engine.api.endpoints."

# Whitelisted adapter endpoints in api/endpoints.py. A test fails if this list and the
# `frappe.whitelist()` assignments in that file drift apart.
ADAPTER_METHODS = (
    "propose_configuration_change",
    "apply_configuration_change",
    "apply_property_setter_change",
    "apply_workflow_change",
    "apply_report_change",
    "revert_configuration_change",
    "get_runtime_policies",
    "register_runtime_policy",
    "unregister_runtime_policy",
    "get_policy_audit_trail",
    "get_policy_revisions",
    "evaluate_document_policies",
)

PING_PATH = "/api/method/ping"

# Record names and doctypes: strict charset, no path tricks. Request paths arrive decoded.
_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9 _\-.:]*"
_RESOURCE_COLLECTION = re.compile(r"/api/resource/(%s)" % _SEGMENT)
_RESOURCE_DOCUMENT = re.compile(r"/api/resource/(%s)/(%s)" % (_SEGMENT, _SEGMENT))
_ADAPTER_METHOD_PATHS = frozenset(METHOD_PREFIX + name for name in ADAPTER_METHODS)


class Decision(NamedTuple):
    allowed: bool
    reason: str  # short machine reason, safe to log, never contains a secret


def _deny(reason: str) -> Decision:
    return Decision(False, reason)


def _valid_token(value) -> bool:
    return isinstance(value, str) and len(value) >= MIN_TOKEN_LENGTH and value.isascii()


def _has_path_tricks(path: str) -> bool:
    return ".." in path or "//" in path or any(ord(c) < 33 and c != " " or ord(c) == 127 for c in path)


def decide(method, path, presented_token, expected_token, has_cmd: bool = False) -> Decision:
    """Pure allow/deny decision for one request. Deny unless allowlisted."""
    if has_cmd:
        return _deny("legacy_rpc")
    if not isinstance(method, str) or method not in ("GET", "HEAD", "POST", "PUT", "DELETE"):
        return _deny("method")
    if not isinstance(path, str) or not path.startswith("/api/") or _has_path_tricks(path):
        return _deny("route")

    if path == PING_PATH:
        return Decision(True, "probe") if method in ("GET", "HEAD") else _deny("method")

    if path in _ADAPTER_METHOD_PATHS:
        internal_methods = ("POST",)
    elif _RESOURCE_DOCUMENT.fullmatch(path):
        internal_methods = ("GET", "PUT", "DELETE")  # Frappe REST: read, update, delete one record
    elif _RESOURCE_COLLECTION.fullmatch(path):
        internal_methods = ("GET", "POST")  # list, create
    else:
        return _deny("route")
    if method not in internal_methods:
        return _deny("method")

    if not _valid_token(expected_token):
        return _deny("internal_disabled")
    if not _valid_token(presented_token) or not hmac.compare_digest(
        presented_token.encode("ascii"), expected_token.encode("ascii")
    ):
        return _deny("token")
    return Decision(True, "internal")


def _expected_token() -> Optional[str]:
    conf = getattr(frappe.local, "conf", None)
    token = conf.get(TOKEN_CONF_KEY) if conf else None
    return token or os.environ.get(TOKEN_ENV)


def enforce_internal_only() -> None:
    """Frappe `before_request` hook. Raises a plain 404 unless the request is allowlisted."""
    reason = "error"
    try:
        request = frappe.local.request
        form = getattr(frappe, "form_dict", None) or {}
        decision = decide(
            request.method,
            request.path,
            request.headers.get(TOKEN_HEADER),
            _expected_token(),
            has_cmd=bool(form.get("cmd")),
        )
        if decision.allowed:
            return
        reason = decision.reason
    except Exception:
        reason = "error"
    try:
        frappe.logger("route_guard").warning("blocked request: %s", reason)
    except Exception:
        pass
    raise NotFound()
