"""HTTP layer: standard library only (ThreadingHTTPServer). Loopback only unless explicitly allowed, strict JSON, a 1 MB
body limit, fixed security headers, and every error as {"ok": false, "error": {"code", "path"}} without stack traces."""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from . import _paths as P
from .engine import Engine, load_engine
from .invoice import invoice_view
from .session import Session, StudioError

LOOPBACK = ("127.0.0.1", "::1", "localhost")
DEFAULT_PORT = 8765
MAX_BODY = 1_048_576
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
SECURITY_HEADERS = {"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/qr.js": ("qr.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
TOKEN_CSS = {"/tokens/tokens.css": "tokens.css", "/tokens/tokens.proposed.css": "tokens.proposed.css"}
ENGINE_NAME = re.compile("frap" + "pe|erp" + "next", re.I)  # ADR-0016: never in a response
ENTITY_LABELS = re.compile(r"/api/blueprint/entities/([^/]{1,64})/labels")


class StudioConfigError(ValueError):
    """The server was asked to do something unsafe (non-loopback bind without the explicit flag)."""


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate key")
            out[k] = v
        return out

    def constant(_name):
        raise ValueError("non-finite number")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, session: Session, quiet: bool = True):
        if ":" in address[0]:
            import socket
            self.address_family = socket.AF_INET6
        self.session, self.quiet = session, quiet
        super().__init__(address, Handler)
        self.allowed_hosts = set(LOOPBACK) | {address[0]}


def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, allow_non_loopback: bool = False,
                engine: Optional[Engine] = None, quiet: bool = True) -> StudioServer:
    if host not in LOOPBACK and not allow_non_loopback:
        raise StudioConfigError(f"refusing to bind {host}: loopback only unless --allow-non-loopback is passed")
    return StudioServer((host, port), Session(engine or load_engine()), quiet)


class Handler(BaseHTTPRequestHandler):
    server_version = "studio"
    sys_version = ""
    timeout = 15
    server: StudioServer

    def log_message(self, fmt, *args):  # no bodies, no headers
        if not self.server.quiet:
            sys.stderr.write("studio: %s %s\n" % (self.command, urlsplit(self.path).path))

    def version_string(self):
        return "studio"

    # ------------------------------------------------------------------ responses
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if ENGINE_NAME.search(text):  # fail closed: the engine is invisible
            status, text = 500, json.dumps({"ok": False, "error": {"code": "STUDIO-ENGINE-NAME", "path": "/"}})
        self._send(status, text.encode("utf-8"), "application/json; charset=utf-8")

    # ------------------------------------------------------------------ methods
    def do_GET(self):
        self._dispatch("GET")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def _not_allowed(self):
        self._json(405, {"ok": False, "error": {"code": "STUDIO-METHOD", "path": "/"}})

    do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_TRACE = _not_allowed

    # ------------------------------------------------------------------ dispatch
    def _check_request(self, method: str) -> None:
        host = (self.headers.get("Host") or "").strip()
        name = host[1:host.index("]")] if host.startswith("[") and "]" in host else host.rsplit(":", 1)[0]
        if name not in self.server.allowed_hosts:
            raise StudioError(421, "STUDIO-HOST", "/headers/host")
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc != host:
            raise StudioError(403, "STUDIO-ORIGIN", "/headers/origin")
        if method in ("PUT", "POST"):
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                raise StudioError(415, "STUDIO-CONTENT-TYPE", "/headers/content-type")
            if self.headers.get("Transfer-Encoding"):
                raise StudioError(411, "STUDIO-LENGTH-REQUIRED", "/headers/transfer-encoding")

    def _body(self) -> dict:
        raw_len = self.headers.get("Content-Length")
        if raw_len is None or raw_len.strip() == "":
            return {}
        if not raw_len.strip().isdigit():
            raise StudioError(400, "STUDIO-LENGTH-INVALID", "/headers/content-length")
        length = int(raw_len)
        if length > MAX_BODY:
            self.close_connection = True
            left = min(length, 4 * MAX_BODY)  # drain a bounded amount so the client can read the refusal
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            raise StudioError(413, "STUDIO-BODY-TOO-LARGE", "/", max=MAX_BODY)
        if length == 0:
            return {}
        try:
            value = strict_json(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise StudioError(400, "STUDIO-JSON-INVALID", "/") from None
        if not isinstance(value, dict):
            raise StudioError(400, "STUDIO-JSON-NOT-OBJECT", "/")
        return value

    def _route(self, method: str, path: str, query: str) -> Optional[Callable[[], dict]]:
        s = self.server.session
        get = {"/api/state": s.state, "/api/export": s.export_view, "/api/invoice": lambda: self._invoice(query)}
        put = {"/api/blueprint/company": lambda: s.set_company(self._body()),
               "/api/blueprint/components": lambda: s.set_component(self._body()),
               "/api/blueprint/branding": lambda: s.set_branding(self._body())}
        post = {"/api/compile": lambda: self._no_body(s.compile), "/api/apply": lambda: s.apply(self._body()),
                "/api/rollback": lambda: self._no_body(s.rollback), "/api/theme": lambda: self._no_body(s.theme),
                "/api/reset": lambda: self._no_body(s.reset)}
        m = ENTITY_LABELS.fullmatch(path)
        if m:
            put[path] = lambda: s.set_entity_labels(unquote(m.group(1)), self._body())
        table = {"GET": get, "PUT": put, "POST": post}
        if path in table[method]:
            return table[method][path]
        if any(path in t for t in table.values()):
            raise StudioError(405, "STUDIO-METHOD", "/")
        return None

    def _no_body(self, fn: Callable[[], dict]) -> dict:
        body = self._body()
        if body:
            raise StudioError(400, "STUDIO-FIELD-UNKNOWN", "/" + sorted(body)[0])
        return fn()

    @staticmethod
    def _invoice(query: str) -> dict:
        try:
            q = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query), max_num_fields=8)
        except ValueError:
            raise StudioError(400, "STUDIO-QUERY-INVALID", "/") from None
        for k, v in q.items():
            if k not in ("market", "lang", "invoice"):
                raise StudioError(400, "STUDIO-QUERY-UNKNOWN", "/" + k[:32])
            if len(v) != 1:
                raise StudioError(400, "STUDIO-QUERY-REPEATED", "/" + k)
        return invoice_view(q.get("market", ["ksa"])[0], q.get("lang", ["en"])[0], q.get("invoice", [None])[0])

    def _dispatch(self, method: str) -> None:
        try:
            self._check_request(method)
            url = urlsplit(self.path)
            if method == "GET" and url.path in STATIC:
                name, ctype = STATIC[url.path]
                return self._send(200, (P.STATIC_DIR / name).read_bytes(), ctype)
            if method == "GET" and url.path in TOKEN_CSS:
                return self._send(200, (P.TOKENS_DIR / TOKEN_CSS[url.path]).read_bytes(), "text/css; charset=utf-8")
            handler = self._route(method, url.path, url.query)
            if handler is None:
                raise StudioError(404, "STUDIO-ROUTE", "/")
            result = handler()
            self._json(200 if result.get("ok", True) else 409, result)
        except StudioError as exc:
            self._json(exc.status, exc.body())
        except Exception as exc:  # noqa: BLE001  (fail closed, no stack trace leaves the process)
            if not self.server.quiet:
                sys.stderr.write("studio: internal error (%s)\n" % type(exc).__name__)
            self._json(500, {"ok": False, "error": {"code": "STUDIO-INTERNAL", "path": "/"}})
