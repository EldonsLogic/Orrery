"""ERP-020: WSGI-level guard that runs before Frappe sees the request. Standalone.

Run from apps/engine/change_engine:
    PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_wsgi_guard
"""

import os
import unittest
from unittest import mock

from change_engine import wsgi
from change_engine.api import route_guard as rg

TOKEN = "t" * 48


def call(app, method, path, query="", headers=None):
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query}
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    seen = {}

    def start_response(status, response_headers, exc_info=None):
        seen["status"] = status
        seen["headers"] = response_headers

    body = b"".join(app(environ, start_response))
    return seen["status"], seen["headers"], body


class WsgiGuardTests(unittest.TestCase):
    def setUp(self):
        self.reached = []

        def inner(environ, start_response):
            self.reached.append(environ["PATH_INFO"])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"inner"]

        self.app = wsgi.guard(inner)
        patcher = mock.patch.dict(os.environ, {rg.TOKEN_ENV: TOKEN})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_blocked_paths_never_reach_the_engine(self):
        for method, path in (("GET", "/"), ("GET", "/app"), ("GET", "/login"), ("POST", "/api/method/login"),
                             ("GET", "/api/method/login"), ("GET", "/assets/x.js"), ("GET", "/files/a.png"),
                             ("POST", "/api/method/frappe.auth.get_logged_user"), ("GET", "")):
            with self.subTest(path=path):
                status, headers, body = call(self.app, method, path, headers={rg.TOKEN_HEADER: TOKEN})
                self.assertTrue(status.startswith("404"))
                self.assertEqual(body, b"Not Found")
                self.assertEqual({k.lower() for k, _ in headers}, {"content-type", "content-length"})
        self.assertEqual(self.reached, [])

    def test_allowed_paths_reach_the_engine(self):
        self.assertTrue(call(self.app, "GET", "/api/method/ping")[0].startswith("200"))
        status = call(self.app, "GET", "/api/resource/User/Administrator", headers={rg.TOKEN_HEADER: TOKEN})[0]
        self.assertTrue(status.startswith("200"))
        self.assertEqual(self.reached, ["/api/method/ping", "/api/resource/User/Administrator"])

    def test_internal_tier_needs_the_environment_token(self):
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: ""}):
            status = call(self.app, "GET", "/api/resource/User/Administrator", headers={rg.TOKEN_HEADER: TOKEN})[0]
        self.assertTrue(status.startswith("404"))
        self.assertEqual(self.reached, [])

    def test_cmd_in_query_string_is_blocked(self):
        for query in ("cmd=frappe.auth.get_logged_user", "a=1&cmd=x", "cmd="):
            with self.subTest(query=query):
                status = call(self.app, "GET", "/api/method/ping", query=query)[0]
                self.assertTrue(status.startswith("404"))
        self.assertEqual(self.reached, [])

    def test_malformed_environ_fails_closed(self):
        out = b"".join(self.app({}, lambda *a, **k: None))
        self.assertEqual(out, b"Not Found")
        self.assertEqual(self.reached, [])


if __name__ == "__main__":
    unittest.main()
