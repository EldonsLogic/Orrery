"""ERP-020: engine headless route guard (ADR-0016). Standalone, no Frappe needed.

Run from apps/engine/change_engine:
    PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_route_guard
"""

import ast
import os
import pathlib
import re
import types
import unittest
from unittest import mock

from change_engine.api import route_guard as rg

TOKEN = "t" * 48
OTHER = "x" * 48
ENDPOINTS_PY = pathlib.Path(rg.__file__).with_name("endpoints.py")
ENGINE_DIR = pathlib.Path(rg.__file__).resolve().parents[1]
MAPPING_PY = ENGINE_DIR / "adapter" / "mapping.py"
GUARDRAILS_PY = ENGINE_DIR / "guarded_apply" / "safety_guardrails.py"


def decide(method, path, token=TOKEN, expected=TOKEN, cmd=False, previous=None):
    return rg.decide(method, path, token, expected, has_rpc_param=cmd, previous_token=previous)


def literal_assignment(path, name):
    """Value of a top-level literal assignment, read with ast so no engine import is needed."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


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

    def test_legacy_cmd_rpc_and_run_method_are_blocked_on_any_path(self):
        for path in ("/", "/api/method/ping", "/app", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0],
                     "/api/resource/Customer/C-1"):
            with self.subTest(path=path):
                self.assertFalse(decide("POST", path, cmd=True).allowed)
                self.assertFalse(decide("GET", path, cmd=True).allowed)

    def test_rpc_parameter_names(self):
        for key in ("cmd", "run_method", "CMD", " Run_Method ", "cmd\t"):
            self.assertTrue(rg.is_rpc_param(key), key)
        for key in ("command", "fields", "filters", "", None, 1):
            self.assertFalse(rg.is_rpc_param(key), key)

    def test_unknown_methods_are_blocked(self):
        for method in ("TRACE", "CONNECT", "PATCH", "OPTIONS", "get", "", None, "PROPFIND"):
            with self.subTest(method=method):
                self.assertFalse(decide(method, "/api/method/ping").allowed)


class PublicProbeTests(unittest.TestCase):
    def test_ping_allowed_without_token_for_get_only(self):
        self.assertTrue(decide("GET", "/api/method/ping", token=None).allowed)
        for method in ("HEAD", "POST", "PUT", "DELETE"):
            self.assertFalse(decide(method, "/api/method/ping", token=None).allowed)

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

    def test_resource_api_is_read_only_per_allowlisted_doctype(self):
        self.assertTrue(rg.RESOURCE_ALLOWLIST)
        for doctype, methods in rg.RESOURCE_ALLOWLIST.items():
            self.assertEqual(methods, ("GET",), doctype)
            for path in (f"/api/resource/{doctype}", f"/api/resource/{doctype}/X-0001"):
                with self.subTest(path=path):
                    self.assertTrue(decide("GET", path).allowed)
                    self.assertFalse(decide("GET", path, token=None).allowed)
                    self.assertFalse(decide("GET", path, token=OTHER).allowed)
                    for method in ("POST", "PUT", "DELETE", "HEAD", "PATCH"):
                        self.assertFalse(decide(method, path).allowed, method)

    def test_doctype_not_on_the_allowlist_is_refused_even_with_a_valid_token(self):
        for doctype in ("ToDo", "Customer Group", "Sales Order Item", "Custom Field", "Property Setter", "DocType",
                        "Server Script", "Client Script", "Webhook", "File", "Connected App", "OAuth Client",
                        "Email Account", "Workflow", "Report", "Warehouse", "customer", "CUSTOMER", "Customer "):
            for path in (f"/api/resource/{doctype}", f"/api/resource/{doctype}/X-1"):
                with self.subTest(path=path):
                    self.assertFalse(decide("GET", path).allowed)

    def test_locked_doctypes_are_refused_even_with_a_valid_token(self):
        locked = literal_assignment(GUARDRAILS_PY, "ZONE_2_LOCKED_DOCTYPES")
        self.assertIn("User", locked)
        for doctype in sorted(locked):
            for path in (f"/api/resource/{doctype}", f"/api/resource/{doctype}/Administrator"):
                with self.subTest(path=path):
                    self.assertFalse(decide("GET", path).allowed)
        self.assertFalse(decide("POST", "/api/resource/User").allowed)

    def test_allowlist_never_contains_a_locked_doctype(self):
        locked = literal_assignment(GUARDRAILS_PY, "ZONE_2_LOCKED_DOCTYPES")
        self.assertFalse(set(rg.RESOURCE_ALLOWLIST) & locked)

    def test_allowlist_is_derived_from_the_adapter_entity_map(self):
        """Drift guard: the adapter's tenant-data doctypes (mapping.ENTITY_TO_DOCTYPE), minus the locked ones
        and the child tables, are exactly the allowlist. A new adapter entity must be added here on purpose."""
        entity_map = literal_assignment(MAPPING_PY, "ENTITY_TO_DOCTYPE")
        locked = literal_assignment(GUARDRAILS_PY, "ZONE_2_LOCKED_DOCTYPES")
        protected = literal_assignment(MAPPING_PY, "PROTECTED_ENTITY_IDS")
        derived = {d for k, d in entity_map.items() if k not in protected and d not in locked
                   and d not in {"Sales Order Item", "Delivery Note Item", "Sales Invoice Item"}}
        self.assertEqual(set(rg.RESOURCE_ALLOWLIST), derived)
        self.assertNotIn("Session", rg.RESOURCE_ALLOWLIST)

    def test_run_method_and_rpc_parameters_are_refused_on_every_resource_path(self):
        for doctype in rg.RESOURCE_ALLOWLIST:
            for path in (f"/api/resource/{doctype}", f"/api/resource/{doctype}/X-1"):
                with self.subTest(path=path):
                    self.assertFalse(decide("GET", path, cmd=True).allowed)

    def test_collection_write_methods_stay_refused(self):
        self.assertFalse(decide("PUT", "/api/resource/Customer").allowed)
        self.assertFalse(decide("DELETE", "/api/resource/Customer").allowed)
        self.assertFalse(decide("POST", "/api/resource/Customer/CUST-1").allowed)

    def test_resource_doctype_and_name_charset_is_strict(self):
        for path in ("/api/resource/Customer/a<b", "/api/resource/Customer/a?b", "/api/resource/Customer/a#b",
                     "/api/resource/Customer/%2e%2e", "/api/resource/Customer/a\\b", "/api/resource/Customer/a;b",
                     "/api/resource/Customer/a ", "/api/resource/Customer/a.", "/api/resource/Customer/a/",
                     "/api/resource/Customer/ a"):
            with self.subTest(path=path):
                self.assertFalse(decide("GET", path).allowed)
        for path in ("/api/resource/Customer/CUST-0001", "/api/resource/Customer/a b", "/api/resource/Customer/a.b",
                     "/api/resource/Sales Order/SAL-ORD-2026-00001"):
            with self.subTest(path=path):
                self.assertTrue(decide("GET", path).allowed)


class FailClosedTests(unittest.TestCase):
    def test_startup_requires_valid_current_and_optional_previous_tokens(self):
        for current, previous in ((None, None), ("short", None), (TOKEN, "short")):
            with self.subTest(current_valid=current == TOKEN, previous_valid=previous is None):
                with mock.patch.dict(os.environ, {}, clear=True):
                    if current is not None:
                        os.environ[rg.TOKEN_ENV] = current
                    if previous is not None:
                        os.environ[rg.PREVIOUS_TOKEN_ENV] = previous
                    with self.assertRaises(ValueError):
                        rg.validate_internal_tokens()
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: TOKEN, rg.PREVIOUS_TOKEN_ENV: OTHER}):
            rg.validate_internal_tokens()

    def test_no_expected_token_means_no_internal_access(self):
        for expected in (None, "", "short", TOKEN + ",", TOKEN + " ", TOKEN + "\r", "x" * (rg.MIN_TOKEN_LENGTH - 1), 12345, b"x" * 64):
            with self.subTest(expected=expected):
                d = rg.decide("POST", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0], expected, expected, has_rpc_param=False)
                self.assertFalse(d.allowed)
                self.assertFalse(decide("GET", "/api/resource/Customer", token=expected, expected=expected).allowed)

    def test_previous_token_allows_rotation_overlap(self):
        path = rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]
        self.assertTrue(decide("POST", path, token=OTHER, expected=TOKEN, previous=OTHER).allowed)
        self.assertTrue(decide("POST", path, token=TOKEN, expected=TOKEN, previous=OTHER).allowed)
        self.assertFalse(decide("POST", path, token="z" * 48, expected=TOKEN, previous=OTHER).allowed)

    def test_previous_token_alone_never_enables_the_internal_tier(self):
        path = rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]
        for expected in (None, "", "short"):
            self.assertFalse(decide("POST", path, token=OTHER, expected=expected, previous=OTHER).allowed)

    def test_short_or_invalid_previous_token_is_ignored(self):
        path = rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0]
        for previous in ("", "short", 123, b"x" * 48, "é" * 40):
            self.assertFalse(decide("POST", path, token="short", expected=TOKEN, previous=previous).allowed)
            self.assertFalse(decide("POST", path, token=previous, expected=TOKEN, previous=previous).allowed)

    def test_tokens_are_compared_in_constant_time(self):
        with mock.patch.object(rg.hmac, "compare_digest", wraps=rg.hmac.compare_digest) as compare:
            decide("POST", rg.METHOD_PREFIX + rg.ADAPTER_METHODS[0], token=OTHER, previous=OTHER)
        self.assertGreaterEqual(compare.call_count, 2)  # both configured tokens are always compared

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
        patcher = mock.patch.dict(os.environ, {rg.TOKEN_ENV: TOKEN})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        rg.frappe = self.orig

    def _frappe(self, method, path, headers=None, conf=None, form=None, args=None):
        headers = headers or {}
        f = types.SimpleNamespace()
        f.local = types.SimpleNamespace(
            request=types.SimpleNamespace(method=method, path=path, headers=headers, args=args or {}),
            conf=conf if conf is not None else {},
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

    def test_not_found_is_plain_text_without_engine_markup(self):
        self._frappe("GET", "/app")
        with self.assertRaises(rg.NotFound) as caught:
            rg.enforce_internal_only()
        response = getattr(caught.exception, "response", None)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_data(as_text=True), "Not Found")
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain"))

    def test_cmd_and_run_method_in_form_or_query_block(self):
        NotFound = rg.NotFound
        for kwargs in ({"form": {"cmd": "frappe.auth.get_logged_user"}}, {"form": {"run_method": "x"}},
                       {"args": {"run_method": "x"}}, {"args": {"cmd": "login"}}):
            self._frappe("GET", "/api/resource/Customer/C-1", headers={rg.TOKEN_HEADER: TOKEN}, **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(NotFound):
                rg.enforce_internal_only()

    def test_doctype_outside_the_allowlist_blocked_in_the_hook_too(self):
        NotFound = rg.NotFound
        for path in ("/api/resource/User/Administrator", "/api/resource/ToDo"):
            self._frappe("GET", path, headers={rg.TOKEN_HEADER: TOKEN})
            with self.subTest(path=path), self.assertRaises(NotFound):
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

    def test_site_config_token_is_not_consulted(self):
        """One token source (the environment) for both layers; a site config value cannot widen or shadow it."""
        NotFound = rg.NotFound
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: OTHER},
                     conf={"internal_api_token": OTHER})
        with self.assertRaises(NotFound):
            rg.enforce_internal_only()

    def test_no_token_in_the_environment_fails_closed(self):
        NotFound = rg.NotFound
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: TOKEN})
        with mock.patch.dict(os.environ, {rg.TOKEN_ENV: ""}):
            with self.assertRaises(NotFound):
                rg.enforce_internal_only()
        with mock.patch.dict(os.environ):
            os.environ.pop(rg.TOKEN_ENV, None)
            with self.assertRaises(NotFound):
                rg.enforce_internal_only()

    def test_previous_token_from_the_environment_is_accepted(self):
        self._frappe("GET", "/api/resource/Customer", headers={rg.TOKEN_HEADER: OTHER})
        with mock.patch.dict(os.environ, {rg.PREVIOUS_TOKEN_ENV: OTHER}):
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
