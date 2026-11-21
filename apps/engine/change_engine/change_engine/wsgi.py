"""Headless WSGI entry point. Validate dispatch inputs before engine request initialization."""

from io import BytesIO
import json
import os
import re
from urllib.parse import parse_qsl

from werkzeug.wrappers import Response

from change_engine.api.route_guard import PREVIOUS_TOKEN_ENV, TOKEN_ENV, decide, is_rpc_param

MAX_BODY_BYTES = 1024 * 1024
_inner = None


def _not_found(start_response):
    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", "9")])
    return [b"Not Found"]


def _rpc_in_form(encoded):
    """Use UTF-8 form decoding on both query strings and URL-encoded request bodies."""
    pairs = parse_qsl(encoded, keep_blank_values=True, max_num_fields=1024, errors="strict")
    return any(is_rpc_param(key) for key, _ in pairs)


def _screen_body(env):
    """Bound and validate the exact bytes the engine will see, including dechunked WSGI input."""
    raw_length = env.get("CONTENT_LENGTH", "")
    transfer = env.get("HTTP_TRANSFER_ENCODING")
    terminated = env.get("wsgi.input_terminated") is True
    if transfer is not None and (transfer.lower() != "chunked" or raw_length or not terminated):
        return False
    if raw_length and not re.fullmatch(r"[0-9]{1,10}", raw_length):
        return False
    length = int(raw_length or 0)
    post = env["REQUEST_METHOD"] == "POST"
    if length > MAX_BODY_BYTES or (not post and (length or transfer)):
        return False
    # A terminated stream may contain bytes even when no length was supplied.
    limit = MAX_BODY_BYTES + 1 if post else 1
    body = env["wsgi.input"].read(limit if terminated else length)
    if len(body) > MAX_BODY_BYTES or (raw_length and len(body) != length) or (body and not post):
        return False
    if body:
        mime = env.get("CONTENT_TYPE", "").partition(";")[0].strip().lower()
        data = body.decode("utf-8")
        if mime == "application/json" or (mime.startswith("application/") and mime.endswith("+json")):
            fields = json.loads(data)
            if not isinstance(fields, (dict, list)) or (isinstance(fields, dict) and any(map(is_rpc_param, fields))):
                return False
        elif mime != "application/x-www-form-urlencoded" or _rpc_in_form(data):
            return False
    env["wsgi.input"] = BytesIO(body)
    env["CONTENT_LENGTH"] = str(len(body))
    env.pop("HTTP_TRANSFER_ENCODING", None)
    return True


def guard(app):
    """Authenticate before buffering. A bare probe exposes only site availability."""
    def guarded(env, start_response):
        try:
            decision = decide(env.get("REQUEST_METHOD"), env.get("PATH_INFO"), env.get("HTTP_X_INTERNAL_TOKEN"),
                              os.environ.get(TOKEN_ENV), previous_token=os.environ.get(PREVIOUS_TOKEN_ENV))
            query = env.get("QUERY_STRING", "")
            if not decision.allowed or "HTTP_X_FRAPPE_SITE_NAME" in env or _rpc_in_form(query):
                return _not_found(start_response)
            probe = decision.reason == "probe"
            if probe and (query or "HTTP_COOKIE" in env or "HTTP_AUTHORIZATION" in env):
                return _not_found(start_response)
            if not _screen_body(env):
                return _not_found(start_response)
            if probe:
                # Never pass site error pages, cookies or debug output to an anonymous caller.
                with Response.from_app(app, env) as response:
                    if response.status_code != 200:
                        return _not_found(start_response)
                return Response(b'{"message":"pong"}', mimetype="application/json")(env, start_response)
        except Exception:
            return _not_found(start_response)
        return app(env, start_response)
    return guarded


def application(environ, start_response):
    """Import the pinned engine lazily and serve it only through the guard."""
    global _inner
    if _inner is None:
        try:
            from frappe.app import application as engine_application
        except Exception:  # Any import-time failure must answer like every other denial, never a bare 500.
            return _not_found(start_response)
        _inner = guard(engine_application)
    return _inner(environ, start_response)
