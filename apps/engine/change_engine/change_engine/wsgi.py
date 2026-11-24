"""WSGI entry point for the headless engine (ERP-020, ADR-0016).

`gunicorn change_engine.wsgi:application` serves the engine with the route allowlist applied
before the engine sees the request. This matters: the engine's login manager processes
`/api/method/login` while it builds the request, before any `before_request` hook runs, so
the hook in `api/route_guard.py` alone cannot stop a login attempt or hide its error shape.
Here a blocked request gets a plain 404 and never reaches the engine at all.

The internal token comes from the ENGINE_INTERNAL_TOKEN environment variable only (site
config is not loaded yet at this point). The `cmd` parameter is checked in the query string
here; in form or JSON bodies it is checked by the hook, which stays registered as a second
layer. Fails closed on any error.
"""

import os
from urllib.parse import parse_qsl

from change_engine.api.route_guard import TOKEN_ENV, TOKEN_HEADER, decide

_NOT_FOUND = b"Not Found"
_inner = None


def _not_found(start_response):
    start_response(
        "404 Not Found",
        [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(_NOT_FOUND)))],
    )
    return [_NOT_FOUND]


def guard(app):
    """Wrap a WSGI app so only allowlisted requests reach it."""

    def guarded(environ, start_response):
        try:
            query = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
            decision = decide(
                environ.get("REQUEST_METHOD"),
                environ.get("PATH_INFO"),
                environ.get("HTTP_" + TOKEN_HEADER.upper().replace("-", "_")),
                os.environ.get(TOKEN_ENV),
                has_cmd=any(key == "cmd" for key, _ in query),
            )
            allowed = decision.allowed
        except Exception:
            allowed = False
        if not allowed:
            return _not_found(start_response)
        return app(environ, start_response)

    return guarded


def application(environ, start_response):
    """The guarded engine application (imports the engine on first use)."""
    global _inner
    if _inner is None:
        from frappe.app import application as engine_application

        _inner = guard(engine_application)
    return _inner(environ, start_response)
