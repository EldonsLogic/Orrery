"""Engine-identifying markers (ADR-0016). Internal code may name the engine; responses never may.

Two detectors with different jobs (never mix them up; the first one false-positives on tenant data):
- `contains_engine_marker`: bare words. Only for channels the engine controls or that are ours:
  response header values, our own schema keys. NEVER for tenant-authored values ("Caramel Frappe",
  "Front desk" are ordinary business data).
- `contains_engine_structure`: engine routes, module paths and stack-trace fingerprints. Inbound paths only.
- `contains_engine_trace`: engine links (a value that is a route, or a route with a path) and trace
  fingerprints. Last-resort check on projected tenant values; a bare "/app" inside a sentence passes. Bare words never match in either.
All lists are UNVERIFIED until the QA-016 staging crawl.
"""
from __future__ import annotations

import html
import re
from urllib.parse import unquote

ENGINE_MARKER_RE = re.compile(
    r"frappe|erpnext|\bdesk\b|/api/method|/api/resource|/assets/|/app/|/printview|socket\.io|werkzeug|pymysql|"
    r"jinja2|wkhtmltopdf|x-page-name|csrf_token|_server_messages|exc_type|traceback \(most recent call",
    re.IGNORECASE,
)

# Engine document field names: never valid as one of our response keys (the projection renames them).
ENGINE_FIELD_NAMES = frozenset({
    "doctype", "docstatus", "naming_series", "__onload", "__islocal", "__unsaved", "parenttype", "parentfield",
    "modified_by", "exc", "exc_type", "_server_messages",
})

_MODULES = (
    r"(?:frappe|erpnext)\.(?:exceptions|client|model|utils|desk|core|handler|app|auth|database|permissions|"
    r"sessions|www|api|boot|realtime|email|accounts|stock|selling|buying|controllers|setup)\b"
)
_ROUTES = (
    # engine routes, only when they start a path (not "example.com/app/x" inside tenant text)
    r"(?<![A-Za-z0-9._:-])/(?:app|desk|printview|api/(?:method|resource)|assets/(?:frappe|erpnext)|socket\.io|"
    r"private/files)(?![A-Za-z0-9_])"
)
_TRACES = (
    # dotted module paths and stack-trace fingerprints
    rf"\b{_MODULES}"
    r"|\b(?:werkzeug|pymysql|jinja2|MySQLdb)\.[a-z_]+"
    r"|apps/(?:frappe|erpnext)\b|traceback \(most recent call|\b_server_messages\b|\bexc_type\b"
)
# Inbound paths: routes and traces (plus site-packages, never a valid path segment of ours).
ENGINE_STRUCTURE_RE = re.compile(_ROUTES + "|" + _TRACES + r"|site-packages", re.IGNORECASE)
# Projected tenant values (re-review N1): a bare "/app" or "/desk" inside a sentence, or "site-packages", is
# ordinary tenant text and must not fail the whole response. Engine links still fail: a value that IS an
# engine route, or a route followed by a path or query ("/app/customer", "/printview?doctype=x").
_ROUTE_NAMES = r"(?:app|desk|printview|api/(?:method|resource)|assets/(?:frappe|erpnext)|socket\.io|private/files)"
ENGINE_VALUE_RE = re.compile(
    r"^\s*/" + _ROUTE_NAMES + r"(?![A-Za-z0-9_])"
    + r"|(?<![A-Za-z0-9._:-])/" + _ROUTE_NAMES + r"[/?#]\S"
    + "|" + _TRACES,
    re.IGNORECASE,
)
# Engine keys a route schema may never read from (re-review L1): engine message, exception and onload channels.
FORBIDDEN_SOURCES = frozenset({"_server_messages", "exc", "exc_type", "_exc_source", "__onload", "_debug_messages",
                               "traceback", "message_log"})


def contains_engine_marker(data: bytes | str) -> bool:
    """Bare-word check. Engine-controlled or our own channels only (headers, schema keys)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    return ENGINE_MARKER_RE.search(data) is not None


def _variants(text: str) -> set:
    seen = {text, html.unescape(text), unquote(text)}
    seen.add(html.unescape(unquote(text)))
    return seen


def contains_engine_structure(text: str) -> bool:
    """Engine routes, module paths and trace fingerprints, also behind one level of HTML/percent encoding.
    For inbound paths. Never for tenant values (use contains_engine_trace)."""
    return any(ENGINE_STRUCTURE_RE.search(v) for v in _variants(text))


def contains_engine_trace(text: str) -> bool:
    """Engine links and stack-trace fingerprints. Last-resort check on projected tenant values."""
    return any(ENGINE_VALUE_RE.search(v) for v in _variants(text))
