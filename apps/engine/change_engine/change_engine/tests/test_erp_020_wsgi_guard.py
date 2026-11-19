"""ERP-020: WSGI-level guard that runs before Frappe sees the request. Standalone.

Run from apps/engine/change_engine:
    PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_wsgi_guard
"""

import io
import json
import os
import sys
import types
import unittest
from unittest import mock

from change_engine import wsgi
from change_engine.api import route_guard as rg

TOKEN = "t" * 48
ADAPTER = rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]
JSON = "application/json"
FORM = "application/x-www-form-urlencoded"


def call(app, method, path, query="", headers=None, body=None, content_type=None, chunked=False):
    """Drive a WSGI app. `body` bytes become wsgi.input; `chunked` mimics gunicorn (no Content-Length)."""
    stream = io.BytesIO(body or b"")
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "wsgi.input": stream, "wsgi.input_terminated": True}
    if body is not None and not chunked:
        environ["CONTENT_LENGTH"] = str(len(body))
    if chunked:
        environ["HTTP_TRANSFER_ENCODING"] = "chunked"
    if content_type is not None:
        environ["CONTENT_TYPE"] = content_type
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    seen = {}

    def start_response(status, response_headers, exc_info=None):
        seen["status"] = status
        seen["headers"] = response_headers

    result = app(environ, start_response)
    out = b"".join(result)
    if hasattr(result, "close"):
        result.close()
    return seen["status"], seen["headers"], out, stream


class WsgiGuardTests(unittest.TestCase):
    def setUp(self):
        self.reached = []
        self.engine_status = "200 OK"
        self.engine_headers = [("Content-Type", "application/json")]

        def inner(environ, start_response):
            length = int(environ.get("CONTENT_LENGTH") or 0)
            body = environ["wsgi.input"].read(length) if length else b""
            self.reached.append({"path": environ["PATH_INFO"], "body": body, "environ": dict(environ)})
            start_response(self.engine_status, list(self.engine_headers))
            return [b"inner"]

        self.app = wsgi.guard(inner)
        patcher = mock.patch.dict(os.environ, {rg.TOKEN_ENV: TOKEN})
        patcher.start()
        self.addCleanup(patcher.stop)

    def internal(self, method, path, **kw):
        headers = {rg.TOKEN_HEADER: TOKEN, **kw.pop("headers", {})}
        return call(self.app, method, path, headers=headers, **kw)

    def assertPlain404(self, result):
        status, headers, body, _ = result
        self.assertTrue(status.startswith("404"), status)
        self.assertEqual(body, b"Not Found")
        self.assertEqual({k.lower() for k, _ in headers}, {"content-type", "content-length"})

    def assertNotReached(self):
        self.assertEqual(self.reached, [])

    # --- routes -----------------------------------------------------------------------------
    def test_blocked_paths_never_reach_the_engine(self):
        for method, path in (("GET", "/"), ("GET", "/app"), ("GET", "/login"), ("POST", "/api/method/login"),
                             ("GET", "/api/method/login"), ("GET", "/assets/x.js"), ("GET", "/files/a.png"),
                             ("POST", "/api/method/frappe.auth.get_logged_user"), ("GET", "")):
            with self.subTest(path=path):
                self.assertPlain404(self.internal(method, path))
        self.assertNotReached()

    def test_allowed_paths_reach_the_engine(self):
        self.assertTrue(call(self.app, "GET", "/api/method/ping")[0].startswith("200"))
        self.assertTrue(self.internal("GET", "/api/resource/Customer/CUST-1")[0].startswith("200"))
        self.assertEqual([r["path"] for r in self.reached], ["/api/method/ping", "/api/resource/Customer/CUST-1"])

    def test_internal_tier_needs_the_environment_token(self):
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: ""}):
            self.assertPlain404(self.internal("GET", "/api/resource/Customer/CUST-1"))
        self.assertNotReached()

    def test_malformed_environ_fails_closed(self):
        out = b"".join(self.app({}, lambda *a, **k: None))
        self.assertEqual(out, b"Not Found")
        self.assertNotReached()

    def test_unauthenticated_request_body_is_never_read(self):
        stream = io.BytesIO(b'{"cmd":"login"}')
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": ADAPTER, "QUERY_STRING": "", "wsgi.input": stream,
                   "CONTENT_LENGTH": "15", "CONTENT_TYPE": JSON}
        out = b"".join(self.app(environ, lambda *a, **k: None))
        self.assertEqual(out, b"Not Found")
        self.assertEqual(stream.tell(), 0)

    # --- H1: legacy RPC and controller RPC parameters, everywhere ---------------------------
    def test_cmd_and_run_method_in_query_string_are_blocked(self):
        for query in ("cmd=frappe.auth.get_logged_user", "a=1&cmd=x", "cmd=", "run_method=get_all_roles",
                      "%63md=login", "a=1&run_method=", "CMD=login", " cmd=login"):
            for method, path, headers in (("GET", "/api/method/ping", {}),
                                          ("GET", "/api/resource/Customer/C-1", {rg.TOKEN_HEADER: TOKEN}),
                                          ("POST", ADAPTER, {rg.TOKEN_HEADER: TOKEN})):
                with self.subTest(query=query, path=path):
                    self.assertPlain404(call(self.app, method, path, query=query, headers=headers))
        self.assertNotReached()

    def test_cmd_in_json_body_is_blocked_on_every_method(self):
        for body in (b'{"cmd":"login","usr":"Administrator","pwd":"x"}', b'{"cmd":"x"}', b'{"run_method":"m"}',
                     b'{"a":1,"cmd":""}', b'{bad', b'[1,'):
            for method, path, headers in (("GET", "/api/method/ping", {}), ("HEAD", "/api/method/ping", {}),
                                          ("POST", ADAPTER, {rg.TOKEN_HEADER: TOKEN}),
                                          ("GET", "/api/resource/Customer/C-1", {rg.TOKEN_HEADER: TOKEN})):
                with self.subTest(method=method, path=path, body=body):
                    self.assertPlain404(call(self.app, method, path, headers=headers, body=body,
                                             content_type=JSON))
        self.assertNotReached()

    def test_cmd_in_urlencoded_body_is_blocked(self):
        for body in (b"cmd=login&usr=Administrator&pwd=x", b"a=1&cmd=x", b"%63md=login", b"run_method=m",
                     b"cmd=", b"a=1&RUN_METHOD=x"):
            for method, path, headers in (("POST", ADAPTER, {rg.TOKEN_HEADER: TOKEN}),
                                          ("POST", "/api/method/ping", {}),
                                          ("GET", "/api/method/ping", {})):
                with self.subTest(method=method, path=path, body=body):
                    self.assertPlain404(call(self.app, method, path, headers=headers, body=body,
                                             content_type=FORM))
        self.assertNotReached()

    def test_multipart_bodies_are_refused_on_every_route(self):
        boundary = "XyZ"
        for body in (f'--{boundary}\r\nContent-Disposition: form-data; name="cmd"\r\n\r\nlogin\r\n--{boundary}--\r\n',
                     f'--{boundary}\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n--{boundary}--\r\n'):
            for method, path, headers in (("POST", ADAPTER, {rg.TOKEN_HEADER: TOKEN}),
                                          ("POST", "/api/method/ping", {}), ("GET", "/api/method/ping", {})):
                with self.subTest(method=method, path=path):
                    self.assertPlain404(call(self.app, method, path, headers=headers, body=body.encode(),
                                             content_type=f"multipart/form-data; boundary={boundary}"))
        self.assertNotReached()

    def test_content_type_is_matched_case_insensitively_and_json_suffix_counts(self):
        for content_type in ("Application/JSON; charset=utf-8", "application/vnd.x+json", "APPLICATION/JSON"):
            with self.subTest(content_type=content_type):
                self.assertPlain404(self.internal("POST", ADAPTER, body=b'{"cmd":"login"}',
                                                  content_type=content_type))
        self.assertNotReached()

    def test_unparseable_content_type_with_a_body_is_refused(self):
        for content_type in (None, "", "text/plain", "application/xml", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                self.assertPlain404(self.internal("POST", ADAPTER, body=b"cmd=login", content_type=content_type))
        self.assertNotReached()

    def test_chunked_body_is_inspected_too(self):
        self.assertPlain404(self.internal("POST", ADAPTER, body=b'{"cmd":"login"}', content_type=JSON,
                                          chunked=True))
        self.assertNotReached()

    def test_oversized_and_invalid_lengths_are_refused_without_reading_everything(self):
        big = b"a" * (wsgi.MAX_BODY_BYTES + 1)
        for kwargs in ({"body": big, "content_type": FORM}, {"body": big, "content_type": FORM, "chunked": True}):
            with self.subTest(chunked=kwargs.get("chunked", False)):
                result = self.internal("POST", ADAPTER, **kwargs)
                self.assertPlain404(result)
                self.assertLessEqual(result[3].tell(), wsgi.MAX_BODY_BYTES + 1)
        for length in ("-1", "abc", "1e3", " "):
            with self.subTest(length=length):
                environ = {"REQUEST_METHOD": "POST", "PATH_INFO": ADAPTER, "QUERY_STRING": "",
                           "HTTP_X_INTERNAL_TOKEN": TOKEN, "CONTENT_LENGTH": length, "CONTENT_TYPE": JSON,
                           "wsgi.input": io.BytesIO(b"{}")}
                self.assertEqual(b"".join(self.app(environ, lambda *a, **k: None)), b"Not Found")
        self.assertNotReached()

    def test_bodies_are_refused_on_every_non_post_request(self):
        for method, path, headers in (("GET", "/api/method/ping", {}), ("HEAD", "/api/method/ping", {}),
                                      ("GET", "/api/resource/Customer/C-1", {rg.TOKEN_HEADER: TOKEN}),
                                      ("GET", "/api/resource/Customer", {rg.TOKEN_HEADER: TOKEN})):
            for body, chunked in ((b"{}", False), (b"x", False), (b"{}", True)):
                with self.subTest(method=method, path=path, chunked=chunked):
                    self.assertPlain404(call(self.app, method, path, headers=headers, body=body,
                                             content_type=JSON, chunked=chunked))
        self.assertNotReached()

    def test_empty_body_with_zero_length_is_fine(self):
        result = call(self.app, "GET", "/api/method/ping", body=b"", content_type=JSON)
        self.assertTrue(result[0].startswith("200"))

    # --- allowed internal calls keep their body ---------------------------------------------
    def test_allowed_internal_post_reaches_the_engine_with_the_body_intact(self):
        payload = json.dumps({"tenant": "t1", "list": [1, 2], "text": "مرحبا"}).encode()
        for kwargs in ({}, {"chunked": True}):
            with self.subTest(chunked=bool(kwargs)):
                self.reached.clear()
                result = self.internal("POST", ADAPTER, body=payload, content_type=JSON, **kwargs)
                self.assertTrue(result[0].startswith("200"), result[0])
                (seen,) = self.reached
                self.assertEqual(seen["body"], payload)
                self.assertEqual(seen["environ"]["CONTENT_LENGTH"], str(len(payload)))
                self.assertNotIn("HTTP_TRANSFER_ENCODING", seen["environ"])

    def test_allowed_urlencoded_and_json_list_bodies_pass(self):
        for body, content_type in ((b"tenant=t1&x=2", FORM), (b'[{"a":1}]', JSON), (b"{}", JSON), (b"", JSON)):
            with self.subTest(body=body):
                self.reached.clear()
                self.assertTrue(self.internal("POST", ADAPTER, body=body, content_type=content_type)[0]
                                .startswith("200"))
                self.assertEqual(self.reached[0]["body"], body)

    # --- H1: the open ping route stays bare --------------------------------------------------
    def test_ping_refuses_any_body_and_login_oriented_headers(self):
        for kwargs in ({"body": b'{"cmd":"login","usr":"Administrator","pwd":"x"}', "content_type": JSON},
                       {"body": b"{}", "content_type": JSON}, {"body": b"x"},
                       {"body": b"{}", "content_type": JSON, "chunked": True}):
            for method in ("GET", "HEAD", "POST", "PUT"):
                with self.subTest(method=method, kwargs=kwargs):
                    self.assertPlain404(call(self.app, method, "/api/method/ping", **kwargs))
        for header in ("Authorization", "Cookie", "X-Frappe-Site-Name"):
            with self.subTest(header=header):
                self.assertPlain404(call(self.app, "GET", "/api/method/ping", headers={header: "x"}))
        self.assertNotReached()

    def test_ping_is_get_only(self):
        self.assertPlain404(call(self.app, "HEAD", "/api/method/ping"))
        self.assertNotReached()

    def test_site_selection_header_is_refused_everywhere(self):
        self.assertPlain404(self.internal("GET", "/api/resource/Customer/C-1", headers={"X-Frappe-Site-Name": "x"}))
        self.assertNotReached()

    def test_ping_hides_engine_errors_and_cookies(self):
        self.engine_status = "404 NOT FOUND"
        self.engine_headers = [("Content-Type", "text/html"), ("Set-Cookie", "sid=Guest")]
        self.assertPlain404(call(self.app, "GET", "/api/method/ping", headers={"Host": "nosuch.invalid"}))
        self.engine_status = "403 FORBIDDEN"
        self.assertPlain404(call(self.app, "GET", "/api/method/ping"))
        self.engine_status = "200 OK"
        self.engine_headers = [("Content-Type", "application/json"), ("Set-Cookie", "sid=Guest"),
                               ("Set-Cookie", "user_id=Guest"), ("X-Frappe-Cmd-Id", "1"), ("Server", "frappe")]
        status, headers, body, _ = call(self.app, "GET", "/api/method/ping")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(json.loads(body), {"message": "pong"})
        self.assertNotIn("set-cookie", {k.lower() for k, _ in headers})
        visible = (repr(headers) + body.decode()).lower()
        for marker in ("frappe", "erpnext"):
            self.assertNotIn(marker, visible)


class ApplicationEntryTests(unittest.TestCase):
    """`wsgi.application` is what gunicorn serves: the guard must actually wrap the engine app."""

    def setUp(self):
        self.reached = []

        def engine(environ, start_response):
            self.reached.append(environ["PATH_INFO"])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"engine"]

        frappe_pkg = types.ModuleType("frappe")
        frappe_app = types.ModuleType("frappe.app")
        frappe_app.application = engine
        frappe_pkg.app = frappe_app
        for patcher in (mock.patch.dict(sys.modules, {"frappe": frappe_pkg, "frappe.app": frappe_app}),
                        mock.patch.dict(os.environ, {rg.TOKEN_ENV: TOKEN}),
                        mock.patch.object(wsgi, "_inner", None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_application_is_guarded(self):
        status, _, body, _ = call(wsgi.application, "GET", "/login")
        self.assertTrue(status.startswith("404"))
        self.assertEqual(body, b"Not Found")
        status, _, body, _ = call(wsgi.application, "POST", ADAPTER, headers={rg.TOKEN_HEADER: TOKEN},
                                  body=b'{"cmd":"login"}', content_type=JSON)
        self.assertTrue(status.startswith("404"))
        self.assertEqual(self.reached, [])

    def test_application_reaches_the_engine_for_allowed_requests(self):
        self.assertTrue(call(wsgi.application, "GET", "/api/method/ping")[0].startswith("200"))
        self.assertEqual(self.reached, ["/api/method/ping"])

    def test_any_engine_import_error_fails_closed(self):
        class Broken(types.ModuleType):
            def __getattr__(self, name):
                raise RuntimeError("engine import side effect")

        with mock.patch.dict(sys.modules, {"frappe.app": Broken("frappe.app")}):
            with mock.patch.object(wsgi, "_inner", None):
                status, _, body, _ = call(wsgi.application, "GET", "/api/method/ping")
        self.assertTrue(status.startswith("404"))
        self.assertEqual(body, b"Not Found")

    def test_engine_import_failure_fails_closed(self):
        with mock.patch.dict(sys.modules, {"frappe.app": None}):
            with mock.patch.object(wsgi, "_inner", None):
                status, _, body, _ = call(wsgi.application, "GET", "/api/method/ping")
        self.assertTrue(status.startswith("404"))
        self.assertEqual(body, b"Not Found")


if __name__ == "__main__":
    unittest.main()
