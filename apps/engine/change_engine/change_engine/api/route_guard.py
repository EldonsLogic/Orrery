"""Shared allowlist for the internal engine WSGI application and request hook (ERP-020)."""

import hmac
import os
import re
from typing import NamedTuple

from werkzeug.exceptions import NotFound
from werkzeug.wrappers import Response

try:
    import frappe
except ImportError:  # The policy tests run outside the bench.
    frappe = None

TOKEN_HEADER = "X-Internal-Token"
TOKEN_ENV = "ENGINE_INTERNAL_TOKEN"
PREVIOUS_TOKEN_ENV = "ENGINE_INTERNAL_TOKEN_PREVIOUS"
MIN_TOKEN_LENGTH = 32
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}")

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

# Only top-level business records used by the adapter. A mapping change requires review
# before it can expose another type. Writes use the guarded adapter methods.
RESOURCE_ALLOWLIST = {name: ("GET",) for name in ("Customer", "Item", "Sales Order", "Delivery Note", "Sales Invoice")}
_RESOURCE = re.compile(r"/api/resource/([^/]+)(?:/[A-Za-z0-9](?:[A-Za-z0-9 _.:\-]*[A-Za-z0-9_:\-])?)?")
_ADAPTER_METHOD_PATHS = frozenset(METHOD_PREFIX + name for name in ADAPTER_METHODS)


class Decision(NamedTuple):
    allowed: bool
    reason: str  # Safe to log without recording paths, parameters or credentials.


def valid_token(value):
    """Accept a single bounded URL-safe token. Operators generate it from secure random bytes."""
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def validate_internal_tokens():
    """Reject unusable deployment credentials before opening the HTTP listener.

    The current token is mandatory. The optional previous token supports a bounded
    operational rotation window; remove it once callers use the current credential.
    Error messages deliberately exclude credential values.
    """
    if not valid_token(os.environ.get(TOKEN_ENV)):
        raise ValueError("A valid current internal token is required")
    previous = os.environ.get(PREVIOUS_TOKEN_ENV)
    if previous and not valid_token(previous):
        raise ValueError("The configured previous internal token is invalid")


def is_rpc_param(key):
    """Match dispatch keys by presence, including empty values."""
    return isinstance(key, str) and key.strip().lower() in {"cmd", "run_method"}


def decide(method, path, presented_token, expected_token, has_rpc_param=False, previous_token=None):
    """Authorize a route before reading its body. A previous token requires a valid current token."""
    if has_rpc_param:
        return Decision(False, "rpc")
    if path == PING_PATH and method == "GET":
        return Decision(True, "probe")
    if not isinstance(path, str) or ".." in path:
        return Decision(False, "route")
    if path in _ADAPTER_METHOD_PATHS:
        methods = ("POST",)
    else:
        resource = _RESOURCE.fullmatch(path)
        methods = RESOURCE_ALLOWLIST.get(resource[1], ()) if resource else ()
    if method not in methods:
        return Decision(False, "route")
    if not valid_token(expected_token) or not valid_token(presented_token):
        return Decision(False, "token")
    matches = hmac.compare_digest(expected_token, presented_token)
    if valid_token(previous_token):
        matches |= hmac.compare_digest(previous_token, presented_token)
    return Decision(matches, "internal" if matches else "token")


def enforce_internal_only():
    """Recheck the parsed query and dispatch arguments before engine API handling."""
    reason = "error"
    try:
        request = frappe.local.request
        decision = decide(
            request.method, request.path, request.headers.get(TOKEN_HEADER), os.environ.get(TOKEN_ENV),
            has_rpc_param=any(is_rpc_param(k) for data in (request.args, frappe.form_dict) for k in data),
            previous_token=os.environ.get(PREVIOUS_TOKEN_ENV),
        )
        if decision.allowed and "X-Frappe-Site-Name" not in request.headers:
            return
        reason = "site_header" if decision.allowed else decision.reason
    except Exception:
        pass
    try:
        frappe.logger("route_guard").warning("blocked request: %s", reason)
    except Exception:
        pass
    raise NotFound(response=Response("Not Found", status=404, mimetype="text/plain"))


if __name__ == "__main__":
    validate_internal_tokens()
