"""ERP-020: engine headless route guard (ADR-0016). Standalone, no Frappe needed.

Run from apps/engine/change_engine:
    PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_route_guard
"""

import pathlib
import re
import types
import unittest

from change_engine.api import route_guard as rg

TOKEN = "t" * 48
OTHER = "x" * 48
ENDPOINTS_PY = pathlib.Path(rg.__file__).with_name("endpoints.py")


def decide(method, path, token=TOKEN, expected=TOKEN, cmd=False):
    return rg.decide(method, path, token, expected, has_cmd=cmd)


class BlockedForEveryoneTests(unittest.TestCase):
    PATHS = [
        "/", "/app", "/app/home", "/app/sales-invoice/view", "/desk", "/desk/x", "/login", "/login#signup",
        "/update-password", "/me", "/about", "/contact", "/blog", "/website", "/index", "/robots.txt",
        "/sitemap.xml", "/assets/frappe/js/x.js", "/files/x.png", "/private/files/x.pdf", "/backups",
        "/printview", "/api/method/login", "/api/method/logout", "/api/method/frappe.auth.get_logged_user",
        "/api/method/frappe.client.get_list", "/api/method/frappe.desk.search.search_link",
        "/api/method/upload_file", "/api/method/change_engine.api.endpoints.not_listed",
        "/api/method/change_engine.api.endpoints", "/api/method/ping/", "/api/method/ping/x",
        "/api/method/ping%2f", "/api/method/ping/../login", "/api/method/./ping", "//api/method/ping",
        "/API/method/ping", "/api/Method/ping", "/api/resource", "/api/resource/", "/api/v2/method/ping",
        "/api/", "/api", "/.well-known/security.txt", "/socket.io/", "", "api/method/ping",
        "/api/method/ping\x00", "/api/method/ping\n", "/api/method/ping ", "/api/resource/Customer/..",
        "/api/resource/Customer/a/b", "/api/resource/../x",
    ]

    def test_internal_caller_with_valid_token_is_still_blocked(self):
        for path in self.PATHS:
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertFalse(decide(method, path).allowed)

    def test_anonymous_caller_is_blocked(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertFalse(decide("GET", path, token=None).allowed)

    def test_legacy_cmd_rpc_is_blocked_on_any_path(self):
        for path in ("/", "/api/method/ping", "/app", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]):
            with self.subTest(path=path):
                self.assertFalse(decide("POST", path, cmd=True).allowed)

    def test_unknown_methods_are_blocked(self):
        for method in ("TRACE", "CONNECT", "PATCH", "OPTIONS", "get", "", None, "PROPFIND"):
            with self.subTest(method=method):
                self.assertFalse(decide(method, "/api/method/ping").allowed)


class PublicProbeTests(unittest.TestCase):
    def test_ping_allowed_without_token_for_get_and_head_only(self):
        for method in ("GET", "HEAD"):
            self.assertTrue(decide(method, "/api/method/ping", token=None).allowed)
        self.assertFalse(decide("POST", "/api/method/ping", token=None).allowed)

    def test_ping_allowed_when_no_token_is_configured(self):
        self.assertTrue(decide("GET", "/api/method/ping", token=None, expected=None).allowed)


class InternalSurfaceTests(unittest.TestCase):
    def test_every_adapter_method_allowed_with_token_via_post(self):
        for name in rg.ADAPTER_METHODS:
            with self.subTest(name=name):
                self.assertTrue(decide("POST", rg.METHOD_PREFIX + name).allowed)

    def test_adapter_methods_require_the_token(self):
        for name in rg.ADAPTER_METHODS:
            for token in (None, "", OTHER, TOKEN[:-1], TOKEN + "x"):
                with self.subTest(name=name, token=token):
                    d = decide("POST", rg.METHOD_PREFIX + name, token=token)
                    self.assertFalse(d.allowed)

    def test_adapter_methods_not_allowed_via_get_or_delete(self):
        for method in ("GET", "HEAD", "DELETE", "PUT"):
            self.assertFalse(decide(method, rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]).allowed)

    def test_resource_api_needs_the_token(self):
        shapes = (
            ("/api/resource/Customer", ("GET", "POST")),
            ("/api/resource/Customer/CUST-0001", ("GET", "PUT", "DELETE")),
            ("/api/resource/Sales Invoice/ACC-SINV-2026-00001", ("GET", "PUT", "DELETE")),
        )
        for path, methods in shapes:
            for method in methods:
                with self.subTest(path=path, method=method):
                    self.assertTrue(decide(method, path).allowed)
                    self.assertFalse(decide(method, path, token=None).allowed)
                    self.assertFalse(decide(method, path, token=OTHER).allowed)

    def test_collection_write_methods_follow_frappe_rest_shape(self):
        self.assertFalse(decide("PUT", "/api/resource/Customer").allowed)
        self.assertFalse(decide("DELETE", "/api/resource/Customer").allowed)
        self.assertFalse(decide("POST", "/api/resource/Customer/CUST-1").allowed)

    def test_resource_doctype_and_name_charset_is_strict(self):
        for path in ("/api/resource/Cust<script>", "/api/resource/Customer/a?b", "/api/resource/Customer/a#b",
                     "/api/resource/Customer/%2e%2e", "/api/resource/Customer/a\\b", "/api/resource/a;b"):
            with self.subTest(path=path):
                self.assertFalse(decide("GET", path).allowed)


class FailClosedTests(unittest.TestCase):
    def test_no_expected_token_means_no_internal_access(self):
        for expected in (None, "", "short", "x" * (rg.MIN_TOKEN_LENGTH - 1), 12345, b"x" * 64):
            with self.subTest(expected=expected):
                d = rg.decide("POST", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0], expected, expected, has_cmd=False)
                self.assertFalse(d.allowed)
                self.assertFalse(decide("GET", "/api/resource/Customer", token=expected, expected=expected).allowed)

    def test_non_string_token_is_denied(self):
        for token in (b"x" * 48, 123, ["a"], object()):
            self.assertFalse(decide("GET", "/api/resource/Customer", token=token).allowed)

    def test_decision_reason_never_contains_the_token(self):
        d = decide("POST", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0], token=OTHER)
        self.assertNotIn(OTHER, d.reason)
        self.assertNotIn(TOKEN, d.reason)

    def test_adapter_method_list_matches_whitelisted_endpoints(self):
        """Drift guard: every endpoint exposed with frappe.whitelist() is in the list, and vice versa."""
        text = ENDPOINTS_PY.read_text(encoding="utf-8")
        whitelisted = set(re.findall(r"^\s+(\w+) = frappe\.whitelist\(\)\(\1\)$", text, re.M))
        self.assertTrue(whitelisted)
        self.assertEqual(whitelisted, set(rg.ADAPTER_METHODS))


class HookTests(unittest.TestCase):
    """enforce_internal_only(): adapts the pure decision to the Frappe request."""

    def setUp(self):
        self.orig = rg.frappe
        self.logged = []

    def tearDown(self):
        rg.frappe = self.orig

    def _frappe(self, method, path, headers=None, conf=None, form=None):
        headers = headers or {}
        f = types.SimpleNamespace()
        f.local = types.SimpleNamespace(
            request=types.SimpleNamespace(method=method, path=path, headers=headers),
            conf=conf if conf is not None else {"internal_api_token": TOKEN},
        )
        f.form_dict = form if form is not None else {}
        f.logger = lambda *_a, **_k: types.SimpleNamespace(warning=lambda msg, *a: self.logged.append(msg % a if a else msg))
        rg.frappe = f

    def test_blocked_request_raises_not_found(self):
        NotFound = rg.NotFound
        for path in ("/app", "/login", "/", "/api/method/login"):
            self._frappe("GET", path)
            with self.assertRaises(NotFound):
                rg.enforce_internal_only()

    def test_allowed_request_returns(self):
        self._frappe("GET", "/api/method/ping")
        rg.enforce_internal_only()
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: TOKEN})
        rg.enforce_internal_only()

    def test_cmd_param_blocks(self):
        NotFound = rg.NotFound
        self._frappe("POST", "/api/method/ping", form={"cmd": "frappe.auth.get_logged_user"})
        with self.assertRaises(NotFound):
            rg.enforce_internal_only()

    def test_wrong_token_blocked_and_logged_without_secret(self):
        NotFound = rg.NotFound
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: OTHER})
        with self.assertRaises(NotFound):
            rg.enforce_internal_only()
        self.assertTrue(self.logged)
        for line in self.logged:
            self.assertNotIn(OTHER, line)
            self.assertNotIn(TOKEN, line)

    def test_token_from_environment_when_site_config_has_none(self):
        import os
        from unittest import mock
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: OTHER}, conf={})
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: OTHER}):
            rg.enforce_internal_only()

    def test_site_config_token_wins_over_environment(self):
        import os
        from unittest import mock
        NotFound = rg.NotFound
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: OTHER})
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: OTHER}):
            with self.assertRaises(NotFound):
                rg.enforce_internal_only()

    def test_any_unexpected_error_fails_closed(self):
        NotFound = rg.NotFound
        rg.frappe = types.SimpleNamespace(local=types.SimpleNamespace())  # no request at all
        with self.assertRaises(NotFound):
            rg.enforce_internal_only()

    def test_without_frappe_fails_closed(self):
        NotFound = rg.NotFound
        rg.frappe = None
        with self.assertRaises(NotFound):
            rg.enforce_internal_only()

    def test_hook_is_registered_in_hooks_py(self):
        from change_engine import hooks
        self.assertIn("change_engine.api.route_guard.enforce_internal_only", hooks.before_request)


if __name__ == "__main__":
    unittest.main()
