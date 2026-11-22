"""SEC-004 harness only: serve the dev bench without the headless request hook (ERP-020).

The change_engine app registers `change_engine.api.route_guard.enforce_internal_only` as a
`before_request` hook on every site it is installed on, and that hook answers 404 to every
route outside a small internal allowlist (no `/api/method/login`, no session cookies, no
`/api/resource/ToDo`, no file or backup routes). The SEC-004 suite certifies the engine's own
tenant isolation (sessions, API tokens, files, backups, jobs, cache), which it can only attack
through those routes; with the hook on, every denial check would pass on a blanket 404 and every
positive control would fail. The combined run with the hook on is SEC-021.

It also serves /files and /assets from disk the way `bench serve` does (a production proxy
does that; bare gunicorn does not).

This module is mounted only by docker-compose.isolation.yml. It does not change the hook, the
route allowlist or any production image. It refuses to start unless the compose file set
SEC004_RAW_ENGINE=1 and the project name contains "sec004".
"""

import os

import frappe
from werkzeug.exceptions import NotFound

HOOK = "change_engine.api.route_guard.enforce_internal_only"

if os.environ.get("SEC004_RAW_ENGINE") != "1" or "sec004" not in os.environ.get("COMPOSE_PROJECT_NAME", ""):
    raise SystemExit("raw_engine_wsgi is for the SEC-004 throwaway bench only")

_get_hooks = frappe.get_hooks


def get_hooks(*args, **kwargs):
    """Pass every call through unchanged (frappe uses its own default sentinel) except the guard."""
    result = _get_hooks(*args, **kwargs)
    hook = args[0] if args else kwargs.get("hook")
    if hook == "before_request":
        return [h for h in result if h != HOOK]
    return result


frappe.get_hooks = get_hooks

from frappe.app import application_with_statics  # noqa: E402  imported after the patch on purpose

# A production proxy serves /files and /assets from disk; frappe's own `bench serve` does it with
# this wrapper. Without it a public-file URL is always 404 and the public-file controls could not
# tell a cross-tenant denial from "not served at all".
_with_statics = application_with_statics()


def application(environ, start_response):
    """The statics wrapper raises NotFound for a missing file; answer 404 instead of letting it become 500."""
    try:
        return _with_statics(environ, start_response)
    except NotFound as exc:
        return exc(environ, start_response)


__all__ = ["application"]
