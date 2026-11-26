"""API edge tests (PLT-024, ADR-0016): no response may reveal the engine."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gateway.edge import (  # noqa: E402
    ERROR_CODES, Field, Gateway, GatewayRequest, Route, SESSION_COOKIE, UpstreamResponse, contains_engine_marker,
    contains_engine_structure, normalise_path,
)

FORBIDDEN = ("frappe", "erpnext", "desk", "traceback", "/api/method", "/api/resource")
ENGINE_PATHS = [
    "/app", "/app/sales-invoice", "/desk", "/desk/", "/api/method/login", "/api/resource/Customer",
    "/assets/frappe/js/frappe.min.js", "/files/secret.pdf", "/private/files/x.pdf", "/socket.io/",
    "/login", "/", "/index.html", "/robots.txt", "/v1", "/v1/", "/V1/ping", "/v10/ping",
    "/v1/../app", "/v1/%2e%2e/app", "/v1/%252e%252e/app", "/v1/ping/../../desk", "/v1//ping",
    "/v1/ping;x=1", "/v1\\ping", "/v1/ping%00", "/v1/%ff", "/v1/unrouted", "/api/v1/ping", "//v1/ping",
    "/v1/ping%2fx", "/v1/ping%2Fx", "/v1/ping%5cx", "/v1/ping%5Cx", "/v1/ping/frappe.client.get_list", "/v1/ping/a",
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
    ("304 not modified", UpstreamResponse(304, [("ETag", '"engine"'), ("Server", "gunicorn")], b"")),
    ("405 method", UpstreamResponse(405, [("Allow", "GET")], b"Method Not Allowed")),
    ("413 too large", UpstreamResponse(413, [], b"")),
    ("422 unprocessable", UpstreamResponse(422, [], b'{"exc_type":"ValidationError"}')),
    ("418 teapot", UpstreamResponse(418, [], b"")),
    ("200 live engine sid", ok_json({"ok": True}, [("Set-Cookie", "sid=abcDEF123; Path=/; HttpOnly")])),
    ("200 sid behind comma", ok_json({"ok": True}, [("Set-Cookie", "system_user=yes; Path=/, sid=evil; Path=/")])),
    ("engine cookies on error", UpstreamResponse(401, [("Set-Cookie", "sid=Guest; Path=/"), ("Set-Cookie", "system_user=no")], b"{}")),
]


SCHEMA = {"items": [int], "ok": bool, "data": str, "name": str, "status": Field(int, source="docstatus")}


def make_gateway(handler, **route_args):
    events: list[dict] = []
    route_args.setdefault("schema", SCHEMA)
    return Gateway({"/v1/ping": Route(handler, **route_args)}, audit_sink=events.append), events


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
        self.assertEqual({e["reason"] for e in events if e["phase"] == "outcome"}, {"path_denied"})

    def test_own_paths_are_routed_with_declared_params_and_engine_safe_request(self):
        seen = []
        gw, _ = make_gateway(lambda r: seen.append(r) or ok_json({"ok": True}), max_params=1)
        resp = gw.handle(request("/v1/ping/sub-1/", "post", [
            ("Authorization", "Bearer x"), ("X-Role", "admin"), ("X-Frappe-CSRF-Token", "t"), ("Accept", "application/json"),
            ("If-None-Match", '"e"'), ("Cookie", "sid=attacker; other=1")]))
        self.assertEqual(resp.status, 200)
        up = seen[0]
        self.assertEqual((up.method, up.path), ("POST", "/v1/ping/sub-1"))
        self.assertEqual(up.headers, [("Accept", "application/json")])  # no cookie, no conditional header

    def test_route_params_are_limited_to_declared_count_and_identifier_alphabet(self):
        gw, _ = make_gateway(lambda r: ok_json({"ok": True}), max_params=1)
        self.assertEqual(gw.handle(request("/v1/ping")).status, 200)
        self.assertEqual(gw.handle(request("/v1/ping/a-1_b")).status, 200)
        for path in ("/v1/ping/a/b", "/v1/ping/frappe.client.get_list", "/v1/ping/a.b", "/v1/ping/a%2fb"):
            with self.subTest(path=path):
                self.assertEqual(gw.handle(request(path)).status, 404)

    def test_registering_a_non_own_route_or_bare_handler_fails(self):
        route = Route(lambda r: None, schema=SCHEMA)
        for bad in ("/app", "/v1", "/v1/", "/v1/../app", "v1/x"):
            with self.assertRaises(ValueError):
                Gateway({bad: route}, audit_sink=lambda e: None)
        with self.assertRaises(TypeError):
            Gateway({"/v1/ping": lambda r: None}, audit_sink=lambda e: None)

    def test_audit_sink_is_required(self):
        with self.assertRaises(TypeError):
            Gateway({"/v1/ping": Route(lambda r: None, schema=SCHEMA)})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            Gateway({"/v1/ping": Route(lambda r: None, schema=SCHEMA)}, audit_sink=None)  # type: ignore[arg-type]

    def test_normalise_path(self):
        self.assertEqual(normalise_path("/v1/a%2Db"), "/v1/a-b")
        self.assertIsNone(normalise_path("/v1/%2e%2e/x"))
        self.assertIsNone(normalise_path("/v1/%252e"))
        self.assertIsNone(normalise_path("/v1/a%2fb"))
        self.assertIsNone(normalise_path("/v1/a%2Fb"))
        self.assertIsNone(normalise_path("/v1/a%5cb"))
        self.assertIsNone(normalise_path("v1/x"))

    def test_modules_import_without_syntax_warnings(self):
        import warnings
        pkg = Path(__file__).resolve().parents[1] / "edge"
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # an invalid escape such as "\\;" is a SyntaxWarning
            for src in pkg.glob("*.py"):
                compile(src.read_text(encoding="utf-8"), str(src), "exec")


class SchemaTests(unittest.TestCase):
    def test_schema_with_engine_field_names_is_rejected_at_registration(self):
        for bad in ({"doctype": str}, {"docstatus": int}, {"naming_series": str}, {"__onload": dict}, {"_comments": str},
                    {"frappe_name": str}, {"Name": str}, {"a": {"doctype": str}}, {"a": [{"exc_type": str}]}, {}, [], str.upper):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Route(lambda r: None, schema=bad)

    def test_route_needs_exactly_one_of_schema_or_own_content_type(self):
        for kwargs in ({}, {"schema": SCHEMA, "own_content_type": "application/pdf"}, {"own_content_type": "text/html"},
                       {"own_content_type": "application/json"}, {"schema": SCHEMA, "filename": "../x.pdf"},
                       {"schema": SCHEMA, "filename": 'a"b.pdf'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Route(lambda r: None, **kwargs)

    def test_raw_engine_document_is_projected_to_our_fields_only(self):
        raw = {"data": {"name": "ACC-SINV-2026-00001", "doctype": "Sales Invoice", "docstatus": 1, "owner": "Administrator",
                        "naming_series": "ACC-SINV-.YYYY.-", "__onload": {"x": 1}, "grand_total": 115.5, "_comments": "[]"}}
        schema = {"data": {"number": Field(str, source="name"), "state": Field(int, source="docstatus"), "total": Field(float, source="grand_total")}}
        gw, _ = make_gateway(lambda r: ok_json(raw), schema=schema)
        resp = gw.handle(request())
        self.assertEqual(json.loads(resp.body), {"data": {"number": "ACC-SINV-2026-00001", "state": 1, "total": 115.5}})
        text = blob(resp)
        for word in ("doctype", "docstatus", "naming_series", "__onload", "administrator", "sales invoice", "_comments"):
            self.assertNotIn(word, text)

    def test_type_mismatch_and_non_finite_numbers_fail_closed(self):
        for body in ({"ok": "yes"}, {"items": "x"}, {"items": [True]}, {"items": [1.5]}, {"data": 5}, {"name": {"a": 1}}):
            with self.subTest(body=body):
                gw, _ = make_gateway(lambda r, body=body: ok_json(body))
                resp = gw.handle(request())
                self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))
        gw, _ = make_gateway(lambda r: UpstreamResponse(200, [("Content-Type", "application/json")], b'{"items":[NaN]}'))
        self.assertEqual(gw.handle(request()).status, 500)


class EscapeTests(unittest.TestCase):
    """Hostile 200 bodies that a substring scan misses. All must be refused or projected clean."""

    def check_refused(self, up, **route_args):
        gw, events = make_gateway(lambda r: up, **route_args)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"), resp.body)
        self.assertFalse([m for m in FORBIDDEN if m in blob(resp)])
        return events

    def test_undecodable_or_undeclared_bodies_are_refused(self):
        marker = '{"data":"x","note":"frappe.client.get_list"}'
        cases = {
            "utf-16": ("application/json", marker.encode("utf-16")),
            "utf-16le no bom": ("application/json", marker.encode("utf-16-le")),
            "utf-32": ("application/json", marker.encode("utf-32")),
            "gzip without header": ("application/json", gzip.compress(marker.encode())),
            "gzip labelled by type": ("application/gzip", gzip.compress(marker.encode())),
            "pdf with producer": ("application/pdf", b"%PDF-1.4\n/Producer (wkhtmltopdf 0.12.6)\n"),
            "html page": ("text/html", b"<html>Powered by ERPNext</html>"),
            "no content type": ("", marker.encode()),
            "latin-1 declared": ("application/json; charset=iso-8859-1", marker.encode()),
            "bom prefixed": ("application/json", b"\xef\xbb\xbf" + marker.encode()),
            "empty 200": ("application/json", b""),
        }
        for label, (ctype, body) in cases.items():
            with self.subTest(label):
                headers = [("Content-Type", ctype)] if ctype else []
                self.check_refused(UpstreamResponse(200, headers, body))

    def test_transfer_encoding_and_content_encoding_are_refused(self):
        for name, value in (("Transfer-Encoding", "gzip"), ("Content-Encoding", "br"), ("Content-Encoding", "gzip")):
            with self.subTest(name=name, value=value):
                self.check_refused(UpstreamResponse(200, [("Content-Type", "application/json"), (name, value)], b'{"ok":true}'))

    def test_escaped_engine_structure_in_allowed_values_is_refused(self):
        values = ["/app/sales-invoice/ACC-SINV-0001", "/printview?doctype=x", "see /api/method/frappe.client.get_list",
                  "frappe.exceptions.ValidationError: x", "werkzeug.exceptions.NotFound", "pymysql.err.OperationalError",
                  "jinja2.exceptions.UndefinedError", "Traceback (most recent call last):", "&#47;app&#47;customer",
                  "%2Fapp%2Fcustomer", "&#102;rappe.client.get_list", "/assets/frappe/js/x.js", "apps/frappe/frappe/x.py",
                  "/desk"]
        for value in values:
            with self.subTest(value=value):
                self.check_refused(ok_json({"data": value}))
        # JSON-escaped key and value: decoded before projection, so the escape changes nothing
        raw = b'{"fr\\u0061ppe":1,"data":"\\u002fapp\\u002fcustomer"}'
        self.check_refused(UpstreamResponse(200, [("Content-Type", "application/json")], raw))

    def test_engine_only_keys_and_unlisted_values_never_appear(self):
        raw = {"ok": True, "owner": "frappe", "doctype": "Customer", "url": "/app/customer", "print": "/printview?doctype=x",
               "ZnJhcHBl": "base64", "_server_messages": "[]"}
        gw, _ = make_gateway(lambda r: ok_json(raw))
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)), (200, {"ok": True}))
        self.assertFalse([m for m in FORBIDDEN if m in blob(resp)])

    def test_own_content_type_route_passes_only_the_declared_type(self):
        pdf = UpstreamResponse(200, [("Content-Type", "application/pdf; charset=binary"), ("Content-Disposition", 'attachment; filename="Sales Invoice-ACC-SINV-2026-00001.pdf"'),
                                     ("Server", "gunicorn")], b"%PDF-1.7 our renderer")
        gw, _ = make_gateway(lambda r: pdf, schema=None, own_content_type="application/pdf", filename="invoice.pdf")
        resp = gw.handle(request())
        self.assertEqual((resp.status, resp.body), (200, b"%PDF-1.7 our renderer"))
        headers = dict(resp.headers)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="invoice.pdf"')
        self.assertNotIn("sales invoice", blob(resp).lower())
        # a different upstream type on a declared route is refused, as is a JSON route answering with a PDF
        self.check_refused(UpstreamResponse(200, [("Content-Type", "text/html")], b"<html>Frappe</html>"),
                           schema=None, own_content_type="application/pdf")
        self.check_refused(UpstreamResponse(200, [("Content-Type", "application/pdf")], b"%PDF /Producer (wkhtmltopdf)"))


class FalsePositiveTests(unittest.TestCase):
    """Tenant-authored values that merely contain engine words must pass (they are ordinary business data)."""

    VALUES = ["Caramel Frappe", "Front desk", "Help Desk", "frappe latte", "Frappe", "ERPNext consultant fee", "Desk & chair set",
              "Standing desk 140cm", "desktop", "Visit https://example.com/app/login", "/assets/ledger", "Frappé grec",
              "user@frappe.io", "files: /files/report.pdf", "قهوة فرابيه", "Application form /apple"]

    def test_tenant_values_with_engine_words_pass(self):
        for value in self.VALUES:
            with self.subTest(value=value):
                gw, _ = make_gateway(lambda r, value=value: ok_json({"items": [1], "name": value, "data": value}))
                resp = gw.handle(request())
                self.assertEqual(resp.status, 200, value)
                self.assertEqual(json.loads(resp.body)["name"], value)

    def test_list_of_records_with_engine_words_is_served(self):
        schema = {"items": [{"item_name": str}]}
        body = {"items": [{"item_name": "Caramel Frappe"}, {"item_name": "Front desk"}]}
        gw, _ = make_gateway(lambda r: ok_json(body), schema=schema)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)), (200, body))

    def test_route_like_tenant_values_do_not_fail_the_list(self):
        """Re-review N1: one record mentioning /app, /desk or site-packages must not 500 the whole list."""
        schema = {"items": [{"item_name": str}]}
        names = ["See /app for details", "مكتب/desk", "قسم /app", "Notes: /printview layout", "pip site-packages folder",
                 "Front desk"]
        body = {"items": [{"item_name": n} for n in names]}
        gw, _ = make_gateway(lambda r: ok_json(body), schema=schema)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)), (200, body))

    def test_trace_fingerprints_in_values_still_fail_closed(self):
        schema = {"items": [{"item_name": str}]}
        for leak in ("Traceback (most recent call last):", "frappe.exceptions.ValidationError", "pymysql.err.OperationalError",
                     "werkzeug.exceptions.NotFound", "File apps/frappe/frappe/app.py"):
            with self.subTest(leak=leak):
                gw, _ = make_gateway(lambda r, leak=leak: ok_json({"items": [{"item_name": leak}]}), schema=schema)
                self.assertEqual(gw.handle(request()).status, 500)

    def test_engine_message_channels_cannot_be_a_field_source(self):
        """Re-review L1: a schema may not wire _server_messages or exception keys into a response."""
        for src in ("_server_messages", "exc", "exc_type", "__onload", "_debug_messages"):
            with self.subTest(src=src), self.assertRaises(ValueError):
                Route(lambda r: None, schema={"note": Field(str, source=src)})

    def test_detectors(self):
        for text in ("Frappe", "ERPNext", "go to Desk now", "/api/method/x", "X-Page-Name", "Traceback (most recent call last)",
                     "/app/customer", "werkzeug"):
            self.assertTrue(contains_engine_marker(text), text)  # bare words: engine-controlled channels only
        for text in ("desktop", "Orrery", "Seshna", "describe", '{"excluded": 1}'):
            self.assertFalse(contains_engine_marker(text), text)
        for text in ("Caramel Frappe", "Front desk", "frappe latte", "desktop", "example.com/app/x", "/apple"):
            self.assertFalse(contains_engine_structure(text), text)
        for text in ("frappe.client.get_list", "/app/customer", "/printview", "/api/method/login", "werkzeug.exceptions.X"):
            self.assertTrue(contains_engine_structure(text), text)


class ResponseFilterTests(unittest.TestCase):
    def test_table_of_engine_responses_leaks_nothing(self):
        for label, up in ENGINE_RESPONSES:
            with self.subTest(label):
                gw, events = make_gateway(lambda r, up=up: up)
                resp = gw.handle(request())
                text = blob(resp)
                self.assertFalse([m for m in FORBIDDEN if m in text], text)
                for leak in ("set-cookie", "server:", "x-frappe", "x-page-name", "location:", "etag", "allow:", "sid="):
                    self.assertNotIn(leak, text)
                payload = json.loads(resp.body)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(set(payload["error"]), {"code", "message_key", "retryable", "details"})
                self.assertEqual(payload["audit_id"], resp.audit_id)
                self.assertTrue(resp.audit_id.startswith("aud_"))
                self.assertIn(payload["error"]["code"], ERROR_CODES)
                self.assertEqual(events[-1]["audit_id"], resp.audit_id)

    def test_error_mapping(self):
        expect = {"403 permission": (403, "permission_denied", False), "404 html desk": (404, "not_found", False),
                  "401 login redirect": (502, "engine_error", False), "417 validation": (400, "invalid_arguments", True),
                  "500 sql": (502, "engine_error", False), "503 plain": (503, "engine_error", True),
                  "409 stale": (409, "conflict", True), "429": (429, "rate_limited", True),
                  "200 error envelope": (400, "invalid_arguments", True), "200 leaks marker": (500, "internal_error", False),
                  "200 gzip": (500, "internal_error", False), "bad status": (500, "internal_error", False),
                  "304 not modified": (502, "engine_error", False), "405 method": (400, "invalid_arguments", True),
                  "413 too large": (400, "invalid_arguments", True), "422 unprocessable": (400, "invalid_arguments", True),
                  "418 teapot": (502, "engine_error", False), "200 live engine sid": (500, "internal_error", False),
                  "200 sid behind comma": (500, "internal_error", False),
                  "engine cookies on error": (403, "permission_denied", False)}
        self.assertEqual({label for label, _ in ENGINE_RESPONSES}, set(expect))
        for label, up in ENGINE_RESPONSES:
            with self.subTest(label):
                gw, _ = make_gateway(lambda r, up=up: up)
                resp = gw.handle(request())
                err = json.loads(resp.body)["error"]
                self.assertEqual((resp.status, err["code"], err["retryable"]), expect[label])

    def test_rate_limit_emits_only_our_bounded_retry_after(self):
        for engine_value, ours in (("999999", 3600), ("30", 30), ("Wed, 21 Oct 2015 07:28:00 GMT", 1), ("soon", 1)):
            with self.subTest(engine_value):
                gw, _ = make_gateway(lambda r, v=engine_value: UpstreamResponse(429, [("Retry-After", v)], b"{}"))
                resp = gw.handle(request())
                self.assertEqual(json.loads(resp.body)["error"]["details"], {"retry_after_s": ours})
                self.assertEqual([v for n, v in resp.headers if n == "Retry-After"], [str(ours)])

    def test_engine_write_with_server_messages_is_a_success_not_an_error(self):
        # msgprint text rides on successful engine writes; the committed write must not be reported as a 502.
        for body in ({"ok": True, "_server_messages": "[]"},
                     {"ok": True, "_server_messages": '["{\\"message\\": \\"Saved\\"}"]'}):
            with self.subTest(body=body):
                gw, events = make_gateway(lambda r, body=body: ok_json(body, status=201))
                resp = gw.handle(request(method="POST"))
                self.assertEqual((resp.status, json.loads(resp.body)), (201, {"ok": True}))  # messages dropped, not forwarded
                self.assertNotIn("_server_messages", blob(resp))
                self.assertEqual([e["reason"] for e in events if e["phase"] == "outcome"], ["ok"])

    def test_error_inside_a_200_is_still_an_error(self):
        for body in ({"exc": "x"}, {"exc_type": "ValidationError"}):
            gw, _ = make_gateway(lambda r, body=body: ok_json(body))
            self.assertNotEqual(gw.handle(request()).status, 200)

    def test_success_headers_are_ours_and_engine_ones_are_dropped(self):
        up = ok_json({"items": [1, 2]}, [
            ("Server", "gunicorn"), ("X-Frappe-Request-Id", "1"), ("ETag", '"engine-v1"'), ("Cache-Control", "public, max-age=31536000"),
            ("Expires", "Wed, 01 Jan 2031 00:00:00 GMT"), ("Last-Modified", "Wed, 01 Jan 2020 00:00:00 GMT"),
            ("Content-Language", "ar"), ("Vary", "Accept-Language"),
            ("Content-Disposition", 'attachment; filename="Sales Invoice-ACC-SINV-2026-00001.pdf"'),
            ("Set-Cookie", "system_user=yes; Path=/"), ("Set-Cookie", "full_name=Jane; Path=/"),
            ("Set-Cookie", "user_id=a@b.test; Path=/"), ("Set-Cookie", "user_image=; Path=/"), ("Set-Cookie", "sid=Guest; Path=/")])
        gw, _ = make_gateway(lambda r: up)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)), (200, {"items": [1, 2]}))
        headers = dict(resp.headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual([v for n, v in resp.headers if n == "Cache-Control"], ["no-store"])
        self.assertNotEqual(headers["ETag"], '"engine-v1"')
        self.assertEqual({n.lower() for n in headers}, {"content-type", "content-language", "vary", "etag", "x-content-type-options",
                                                       "referrer-policy", "cache-control", "content-length"})
        self.assertEqual(headers["Content-Length"], str(len(resp.body)))

    def test_conditional_get_is_answered_from_our_etag(self):
        gw, _ = make_gateway(lambda r: ok_json({"ok": True}))
        first = gw.handle(request())
        etag = dict(first.headers)["ETag"]
        again = gw.handle(request(headers=[("If-None-Match", etag)]))
        self.assertEqual((again.status, again.body), (304, b""))
        self.assertEqual(dict(again.headers)["ETag"], etag)
        self.assertEqual(gw.handle(request(headers=[("If-None-Match", '"other"')])).status, 200)
        self.assertEqual(gw.handle(request(method="POST", headers=[("If-None-Match", etag)])).status, 200)

    def test_allowed_header_with_engine_marker_is_dropped(self):
        up = ok_json({"ok": 1}, [("Vary", "X-Frappe-Site-Name"), ("Content-Language", "frappe")])
        gw, _ = make_gateway(lambda r: up)
        self.assertNotIn("frappe", blob(gw.handle(request())))

    def test_handler_exception_text_never_leaks(self):
        def boom(r):
            raise RuntimeError("frappe.exceptions.ValidationError at /app/secret")
        gw, events = make_gateway(boom)
        resp = gw.handle(request())
        self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))
        self.assertNotIn("frappe", blob(resp))
        self.assertEqual(events[-1]["reason"], "handler_exception")


class SessionTests(unittest.TestCase):
    def test_engine_sid_is_never_exposed_as_our_session(self):
        for cookie in ("sid=abcDEF123; Max-Age=3600; Path=/; HttpOnly", "SID=abc", "sid=abc; Expires=Fri, 01 Jan 2100 00:00:00 GMT"):
            with self.subTest(cookie):
                gw, _ = make_gateway(lambda r, c=cookie: ok_json({"ok": True}, [("Set-Cookie", c)]))
                resp = gw.handle(request())
                self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))
                self.assertNotIn("abc", blob(resp))
                self.assertNotIn("set-cookie", blob(resp))

    def test_engine_logout_and_guest_cookies(self):
        gw, _ = make_gateway(lambda r: ok_json({"ok": True}, [("Set-Cookie", "sid=Guest; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/")]))
        resp = gw.handle(request())
        self.assertEqual(resp.status, 200)
        self.assertEqual([v for n, v in resp.headers if n == "Set-Cookie"],
                         [f"{SESSION_COOKIE}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax"])
        gw, _ = make_gateway(lambda r: ok_json({"ok": True}, [("Set-Cookie", "sid=abc; Max-Age=0; Path=/")]))
        self.assertEqual([v for n, v in gw.handle(request()).headers if n == "Set-Cookie"][0].split(";")[0], f"{SESSION_COOKIE}=")
        gw, _ = make_gateway(lambda r: ok_json({"ok": True}, [("Set-Cookie", "sid=Guest; Path=/"), ("Set-Cookie", "sid=; Path=/")]))
        self.assertNotIn("set-cookie", blob(gw.handle(request())))

    def test_inbound_session_cookie_is_rejected_and_cleared_without_reaching_the_engine(self):
        seen = []
        gw, events = make_gateway(lambda r: seen.append(r) or ok_json({"ok": True}))
        for cookie in (f"{SESSION_COOKIE}=abc123", f"{SESSION_COOKIE}=a; {SESSION_COOKIE}=b", f"{SESSION_COOKIE}=",
                       f"other=1; {SESSION_COOKIE}=abc"):
            with self.subTest(cookie):
                resp = gw.handle(request(headers=[("Cookie", cookie)]))
                self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (403, "permission_denied"))
                self.assertEqual([v for n, v in resp.headers if n == "Set-Cookie"],
                                 [f"{SESSION_COOKIE}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax"])
        two_headers = gw.handle(request(headers=[("Cookie", f"{SESSION_COOKIE}=a"), ("Cookie", f"{SESSION_COOKIE}=")]))
        self.assertEqual(two_headers.status, 403)
        self.assertEqual(seen, [])
        self.assertEqual({e["reason"] for e in events}, {"session_unsupported"})

    def test_other_cookies_are_ignored_and_never_forwarded(self):
        seen = []
        gw, _ = make_gateway(lambda r: seen.append(r) or ok_json({"ok": True}))
        self.assertEqual(gw.handle(request(headers=[("Cookie", "sid=attacker; system_user=yes")])).status, 200)
        self.assertEqual(seen[0].headers, [])


class AuditTests(unittest.TestCase):
    def test_success_and_failure_are_both_audited_with_intent_before_a_write(self):
        order = []
        events: list[dict] = []
        def handler(r):
            order.append("handler")
            return ok_json({"ok": True})
        gw = Gateway({"/v1/ping": Route(handler, schema=SCHEMA)}, audit_sink=lambda e: (order.append(e["phase"]), events.append(e)))
        post = gw.handle(request(method="POST"))
        self.assertEqual(order, ["intent", "handler", "outcome"])
        self.assertEqual([(e["phase"], e.get("status"), e.get("reason")) for e in events], [("intent", None, None), ("outcome", 200, "ok")])
        self.assertTrue(all(e["audit_id"] == post.audit_id for e in events))
        events.clear()
        gw.handle(request(method="GET"))
        gw.handle(request("/v1/nope"))
        self.assertEqual([(e["phase"], e["status"], e["reason"]) for e in events], [("outcome", 200, "ok"), ("outcome", 404, "path_denied")])

    def test_sink_down_before_a_write_means_the_handler_never_runs(self):
        ran = []
        def sink(event):
            raise OSError("disk full")
        gw = Gateway({"/v1/ping": Route(lambda r: ran.append(1) or ok_json({"ok": 1}), schema=SCHEMA)}, audit_sink=sink)
        for method in ("POST", "DELETE"):
            resp = gw.handle(request(method=method))
            self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (503, "audit_unavailable"))
        self.assertEqual(ran, [])
        self.assertEqual(gw._inflight_mutations, 0)

    def test_sink_failure_is_an_error_for_reads_and_denials(self):
        def sink(event):
            raise OSError("disk full")
        gw = Gateway({"/v1/ping": Route(lambda r: ok_json({"ok": 1}), schema=SCHEMA)}, audit_sink=sink)
        for path in ("/v1/ping", "/v1/nope"):
            resp = gw.handle(request(path))
            self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))

    def test_outcome_write_failure_after_a_committed_write_reports_the_real_result_and_queues_the_record(self):
        calls = []
        def sink(event):
            calls.append(event["phase"])
            if event["phase"] == "outcome":
                raise OSError("sink died after the effect")
        gw = Gateway({"/v1/ping": Route(lambda r: ok_json({"ok": True}, status=201), schema=SCHEMA)}, audit_sink=sink)
        resp = gw.handle(request(method="POST"))
        self.assertEqual((resp.status, json.loads(resp.body)), (201, {"ok": True}))  # not a 500: no duplicate retry
        queued = gw.drain_unlogged()
        self.assertEqual([(q["audit_id"], q["status"], q["reason"]) for q in queued], [(resp.audit_id, 201, "ok")])
        self.assertEqual(gw.drain_unlogged(), [])


class ReviewRegressionTests(unittest.TestCase):
    """Eldon's review: audit pressure, malformed input and response-header safety."""

    def test_outcome_backlog_refuses_mutations_before_deque_overflow(self):
        intents, ran = [], []
        def sink(event):
            if event["phase"] == "outcome":
                raise OSError("outcome sink unavailable")
            intents.append(event)
        gw = Gateway({"/v1/ping": Route(lambda r: ran.append(r) or ok_json({"ok": True}), schema=SCHEMA)}, audit_sink=sink)
        accepted = []
        for _ in range(1100):
            resp = gw.handle(request(method="POST"))
            if resp.status == 200:
                accepted.append(resp.audit_id)
            else:
                self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (503, "audit_unavailable"))
        self.assertEqual(len(accepted), 900)
        self.assertEqual(len(ran), len(accepted))
        self.assertEqual(len(intents), len(accepted))
        self.assertEqual([r["audit_id"] for r in gw.drain_unlogged()], accepted)
        self.assertEqual(gw.audit_drop_count, 0)
        self.assertEqual(gw.handle(request(method="POST")).status, 200)

    def test_inflight_mutation_reserves_backlog_capacity(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        entered, release = Event(), Event()
        def handler(r):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test did not release handler")
            return ok_json({"ok": True})
        def sink(event):
            if event["phase"] == "outcome":
                raise OSError("outcome sink unavailable")
        gw = Gateway({"/v1/ping": Route(handler, schema=SCHEMA)}, audit_sink=sink)
        gw._unlogged.extend({"sequence": i} for i in range(899))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(gw.handle, request(method="POST"))
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(gw.handle(request(method="POST")).status, 503)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=5).status, 200)
        self.assertEqual(len(gw.drain_unlogged()), 900)
        self.assertEqual(gw.audit_drop_count, 0)

    def test_malformed_headers_fail_closed_without_handler_call(self):
        ran = []
        gw, events = make_gateway(lambda r: ran.append(r) or ok_json({"ok": True}))
        for headers in (None, 123, "Cookie", [("Cookie",)], [(1, "x")], [("Cookie", None)], ["ab"]):
            with self.subTest(headers=headers):
                resp = gw.handle(GatewayRequest("POST", "/v1/ping", headers))
                self.assertEqual((resp.status, json.loads(resp.body)["error"]["code"]), (500, "internal_error"))
        self.assertEqual(ran, [])
        self.assertTrue(all(e["phase"] == "outcome" for e in events))

    def test_audit_records_both_caller_and_normalised_path(self):
        gw, events = make_gateway(lambda r: ok_json({"ok": True}))
        for raw, normal, flag in (("/v1/p%69ng/", "/v1/ping", "changed"),
                                  ("/v1/ping", "/v1/ping", "unchanged"),
                                  ("/v1/../app", None, "rejected"), ("/" + "x" * 2100, None, "rejected")):
            gw.handle(request(raw))
            self.assertEqual((events[-1]["path"], events[-1]["normalised_path"], events[-1]["path_normalisation"]),
                             (raw[:256], normal, flag))

    def test_registration_rejects_header_injection_and_invalid_parameters(self):
        for filename in ("a\n", "invoice.pdf\r\nX-Test: yes"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                Route(lambda r: None, schema=SCHEMA, filename=filename)
        for ctype in ("application/pdf\r\nX-Test: yes", "application/pdf; charset=binary\n",
                      "application/pdf; garbage", 'application/pdf; name="unterminated'):
            with self.subTest(ctype=ctype), self.assertRaises(ValueError):
                Route(lambda r: None, own_content_type=ctype)
        Route(lambda r: None, own_content_type="application/pdf; charset=binary")

    def test_empty_204_has_no_content_type(self):
        gw, _ = make_gateway(lambda r: UpstreamResponse(204, [], b""))
        resp = gw.handle(request())
        self.assertEqual((resp.status, resp.body), (204, b""))
        self.assertNotIn("content-type", {n.lower() for n, _ in resp.headers})


if __name__ == "__main__":
    unittest.main()
