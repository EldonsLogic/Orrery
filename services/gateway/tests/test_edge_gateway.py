"""API edge tests (PLT-024, ADR-0016): no response may reveal the engine."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gateway.edge import (  # noqa: E402
    ERROR_CODES, Gateway, GatewayRequest, SESSION_COOKIE, UpstreamResponse, contains_engine_marker,
    normalise_path,
)

FORBIDDEN = ("frappe", "erpnext", "desk", "traceback", "/api/method", "/api/resource")
ENGINE_PATHS = [
    "/app", "/app/sales-invoice", "/desk", "/desk/", "/api/method/login", "/api/resource/Customer",
    "/assets/frappe/js/frappe.min.js", "/files/secret.pdf", "/private/files/x.pdf", "/socket.io/",
    "/login", "/", "/index.html", "/robots.txt", "/v1", "/v1/", "/V1/ping", "/v10/ping",
    "/v1/../app", "/v1/%2e%2e/app", "/v1/%252e%252e/app", "/v1/ping/../../desk", "/v1//ping",
    "/v1/ping;x=1", "/v1\\ping", "/v1/ping%00", "/v1/%ff", "/v1/unrouted", "/api/v1/ping", "//v1/ping",
]


def ok_json(body: dict, headers=None, status=200):
    return UpstreamResponse(status, [("Content-Type", "application/json")] + (headers or []), json.dumps(body).encode())


# (label, upstream response) rows: every one is a hostile or failing engine response.
ENGINE_RESPONSES = [
    ("403 permission", UpstreamResponse(403, [("Server", "gunicorn"), ("X-Frappe-Site-Name", "t1")],
        b'{"exc_type":"PermissionError","exc":"[\\"Traceback (most recent call last):\\\\n File apps/frappe/x.py\\"]",'
        b'"_server_messages":"[\\"No permission for Sales Invoice\\"]"}')),
    ("404 html desk", UpstreamResponse(404, [("Content-Type", "text/html"), ("X-Page-Name", "404")],
        b"<html><title>Page Not Found - Frappe</title><a href='/desk'>Desk</a></html>")),
    ("401 login redirect", UpstreamResponse(302, [("Location", "/login?redirect-to=/app")], b"")),
    ("417 validation", UpstreamResponse(417, [], b'{"exc_type":"ValidationError","_server_messages":"[\\"Customer is mandatory\\"]"}')),
    ("500 sql", UpstreamResponse(500, [("Server", "nginx")],
        b'{"exc":"pymysql.err.OperationalError: (1054, \\"Unknown column tabSales Invoice.x\\")","exc_type":"OperationalError"}')),
    ("503 plain", UpstreamResponse(503, [("Retry-After", "7"), ("X-Powered-By", "ERPNext")], b"Service Unavailable")),
    ("409 stale", UpstreamResponse(409, [], b'{"exc_type":"TimestampMismatchError"}')),
    ("429", UpstreamResponse(429, [("Retry-After", "30"), ("Server", "frappe")], b'{"exc_type":"RateLimitExceededError"}')),
    ("200 error envelope", ok_json({"exc_type": "ValidationError", "exc": "Traceback x"})),
    ("200 leaks marker", ok_json({"data": "see /app/customer for erpnext"})),
    ("200 gzip", UpstreamResponse(200, [("Content-Encoding", "gzip")], b"\x1f\x8b\x08")),
    ("bad status", UpstreamResponse(99, [], b"")),
    ("engine cookies on error", UpstreamResponse(401, [("Set-Cookie", "sid=Guest; Path=/"), ("Set-Cookie", "system_user=no")], b"{}")),
]


def make_gateway(handler):
    events: list[dict] = []
    return Gateway({"/v1/ping": handler}, audit_sink=events.append), events


def request(path="/v1/ping", method="GET", headers=None, body=b""):
    return GatewayRequest(method, path, headers or [], body)


def blob(resp) -> str:
    return (resp.body.decode("utf-8", "replace") + "\n" + "\n".join(f"{n}: {v}" for n, v in resp.headers)).lower()


class PathPolicyTests(unittest.TestCase):
    def test_every_engine_or_unrouted_path_is_our_404_with_no_engine_body(self):
        called = []
        gw, events = make_gateway(lambda r: called.append(r) or ok_json({"ok": True}))
        bodies = set()
        for path in ENGINE_PATHS:
            for method in ("GET", "POST", "TRACE", "CONNECT"):
                with self.subTest(path=path, method=method):
                    resp = gw.handle(request(path, method))
                    err = json.loads(resp.body)["error"]
                    self.assertEqual((resp.status, err["code"], err["message_key"]), (404, "not_found", "errors.not_found"))
                    self.assertFalse(any(m in blob(resp) for m in FORBIDDEN))
                    bodies.add(resp.body.replace(resp.audit_id.encode(), b"<id>"))
        self.assertEqual(called, [])  # nothing reached the engine
        self.assertEqual(len(bodies), 1)  # identical for every denial: no oracle
        self.assertEqual({e["reason"] for e in events}, {"path_denied"})

    def test_own_paths_are_routed_with_prefix_match_and_engine_safe_request(self):
        seen = []
        gw, _ = make_gateway(lambda r: seen.append(r) or ok_json({"ok": True}))
        resp = gw.handle(request("/v1/ping/sub-1/", "post", [
            ("Authorization", "Bearer x"), ("X-Role", "admin"), ("X-Frappe-CSRF-Token", "t"), ("Accept", "application/json"),
            ("Cookie", f"{SESSION_COOKIE}=abc123; sid=attacker; other=1")]))
        self.assertEqual(resp.status, 200)
        up = seen[0]
        self.assertEqual((up.method, up.path), ("POST", "/v1/ping/sub-1"))
        self.assertEqual(sorted(up.headers), [("Accept", "application/json"), ("Cookie", "sid=abc123")])

    def test_registering_a_non_own_route_fails(self):
        for bad in ("/app", "/v1", "/v1/", "/v1/../app", "v1/x"):
            with self.assertRaises(ValueError):
                Gateway({bad: lambda r: None})

    def test_normalise_path(self):
        self.assertEqual(normalise_path("/v1/a%2Db"), "/v1/a-b")
        self.assertIsNone(normalise_path("/v1/%2e%2e/x"))
        self.assertIsNone(normalise_path("/v1/%252e"))
        self.assertIsNone(normalise_path("v1/x"))


class ResponseFilterTests(unittest.TestCase):
    def test_table_of_engine_responses_leaks_nothing(self):
        for label, up in ENGINE_RESPONSES:
            with self.subTest(label):
                gw, events = make_gateway(lambda r, up=up: up)
                resp = gw.handle(request())
                text = blob(resp)
                self.assertFalse([m for m in FORBIDDEN if m in text], text)
                self.assertNotIn("set-cookie", text)
                self.assertNotIn("server:", text)
                self.assertNotIn("x-frappe", text)
                self.assertNotIn("x-page-name", text)
                self.assertNotIn("location:", text)
                payload = json.loads(resp.body)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(set(payload["error"]), {"code", "message_key", "retryable", "details"})
                self.assertEqual(payload["audit_id"], resp.audit_id)
                self.assertTrue(resp.audit_id.startswith("aud_"))
                self.assertIn(payload["error"]["code"], ERROR_CODES)
                self.assertEqual(events[0]["audit_id"], resp.audit_id)

    def test_error_mapping(self):
        expect = {"403 permission": (403, "permission_denied", False), "404 html desk": (404, "not_found", False),
                  "401 login redirect": (502, "engine_error", False), "417 validation": (502, "engine_error", False),
                  "500 sql": (502, "engine_error", False), "503 plain": (503, "engine_error", True),
                  "409 stale": (409, "conflict", True), "429": (429, "rate_limited", True),
                  "200 error envelope": (502, "engine_error", False), "200 leaks marker": (500, "internal_error", False),
                  "200 gzip": (500, "internal_error", False), "bad status": (500, "internal_error", False),
                  "engine cookies on error": (403, "permission_denied", False)}
        for label, up in ENGINE_RESPONSES:
            with self.subTest(label):
                gw, _ = make_gateway(lambda r, up=up: up)
                resp = gw.handle(request())
                err = json.loads(resp.body)["error"]
                self.assertEqual((resp.status, err["code"], err["retryable"]), expect[label])

    def test_rate_limit_keeps_only_bounded_retry_after(self):
        gw, _ = make_gateway(lambda r: UpstreamResponse(429, [("Retry-After", "999999")], b"{}"))
        resp = gw.handle(request())
        self.assertEqual(json.loads(resp.body)["error"]["details"], {"retry_after_s": 3600})
        self.assertIn(("Retry-After", "999999"), resp.headers)  # header is allow-listed but body value is bounded

    def test_success_passes_body_renames_session_cookie_and_drops_engine_cookies(self):
        up = ok_json({"items": [1, 2]}, [
            ("Server", "gunicorn"), ("X-Frappe-Request-Id", "1"), ("ETag", '"v1"'),
            ("Set-Cookie", "sid=abcDEF123; Expires=Wed, 01 Jan 2031 00:00:00 GMT; Max-Age=3600; Domain=x.test; Path=/app; HttpOnly"),
            ("Set-Cookie", "system_user=yes; Path=/"), ("Set-Cookie", "full_name=Jane; Path=/"),
            ("Set-Cookie", "user_id=a@b.test; Path=/"), ("Set-Cookie", "user_image=; Path=/"),
            ("Set-Cookie", "sid=ba\"d; Path=/")])
        gw, _ = make_gateway(lambda r: up)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)), (200, {"items": [1, 2]}))
        cookies = [v for n, v in resp.headers if n == "Set-Cookie"]
        self.assertEqual(cookies, [f"{SESSION_COOKIE}=abcDEF123; Max-Age=3600; Path=/; Secure; HttpOnly; SameSite=Lax"])
        names = {n.lower() for n, _ in resp.headers}
        self.assertEqual(names, {"content-type", "etag", "set-cookie", "x-content-type-options", "referrer-policy",
                                 "cache-control", "content-length"})
        self.assertEqual(dict(resp.headers)["Content-Length"], str(len(resp.body)))

    def test_allowed_header_with_engine_marker_is_dropped(self):
        up = ok_json({"ok": 1}, [("Content-Disposition", 'attachment; filename="frappe.pdf"')])
        gw, _ = make_gateway(lambda r: up)
        self.assertNotIn("frappe", blob(gw.handle(request())))

    def test_handler_exception_text_never_leaks(self):
        def boom(r):
            raise RuntimeError("frappe.exceptions.ValidationError at /app/secret")
        gw, events = make_gateway(boom)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))
        self.assertNotIn("frappe", blob(resp))
        self.assertEqual(events[0]["reason"], "handler_exception")

    def test_audit_sink_failure_fails_closed(self):
        def sink(event):
            raise OSError("disk full")
        gw = Gateway({"/v1/ping": lambda r: ok_json({"ok": 1})}, audit_sink=sink)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))

    def test_marker_detector(self):
        for text in ("Frappe", "ERPNext", "go to Desk now", "/api/method/x", "X-Page-Name", "Traceback (most recent call last)"):
            self.assertTrue(contains_engine_marker(text), text)
        for text in ("desktop", "Orrery", "describe", '{"excluded": 1}'):
            self.assertFalse(contains_engine_marker(text), text)

    def test_success_json_with_exc_like_word_is_not_treated_as_error(self):
        gw, _ = make_gateway(lambda r: ok_json({"excluded": True, "except": 1}))
        self.assertEqual(gw.handle(request()).status, 200)


if __name__ == "__main__":
    unittest.main()
