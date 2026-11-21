"""Unit tests for the engine invisibility crawler (QA-016)."""
from __future__ import annotations

import http.server
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
import unittest

from infra.invisibility.crawler import (
    DEFAULT_MARKERS_FILE,
    InvisibilityCrawler,
    load_markers,
    run_crawl,
)


class StubCleanHandler(http.server.BaseHTTPRequestHandler):
    """Stub HTTP handler serving a clean site with no engine markers."""

    def log_message(self, format: str, *args: Any) -> None:
        # Silence standard HTTP request logging in test output
        pass

    def do_GET(self) -> None:
        url_path = self.path.split("?")[0]
        if url_path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Server", "OrreryGateway/1.0")
            self.send_header("Set-Cookie", "session_token=clean_token_abc; Path=/; HttpOnly; Secure")
            self.end_headers()
            html = (
                "<!DOCTYPE html><html><head>"
                '<link rel="stylesheet" href="/static/style.css">'
                '<script src="/static/app.js"></script>'
                "</head><body>"
                "<h1>Welcome to Orrery</h1>"
                '<a href="/about">About Us</a>'
                '<a href="https://external.example.com/terms">External Terms</a>'
                "</body></html>"
            )
            self.wfile.write(html.encode("utf-8"))
        elif url_path == "/about":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Server", "OrreryGateway/1.0")
            self.end_headers()
            self.wfile.write(b"<!DOCTYPE html><html><body><p>Clean about page.</p></body></html>")
        elif url_path == "/static/style.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            css = "@import '/static/theme.css';\nbody { margin: 0; font-family: sans-serif; }"
            self.wfile.write(css.encode("utf-8"))
        elif url_path == "/static/theme.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(b":root { --primary: #0F8A7E; }")
        elif url_path == "/static/app.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"console.log('Orrery client bundle running cleanly.');")
        elif url_path == "/api/v1/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Server", "OrreryGateway/1.0")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "gateway"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")


class StubLeakyHandler(http.server.BaseHTTPRequestHandler):
    """Stub HTTP handler serving leaky responses containing engine markers."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        url_path = self.path.split("?")[0]
        if url_path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Server", "Werkzeug/2.2.2 Python/3.11")
            self.send_header("Set-Cookie", "sid=frappe_sid_12345; Path=/; HttpOnly")
            self.send_header("Set-Cookie", "user_role=system_user; Path=/")
            self.send_header("X-Frappe-Site-Name", "tenant-alpha")
            self.end_headers()
            html = (
                "<!DOCTYPE html><html><head>"
                '<link rel="stylesheet" href="/static/bundle.css">'
                '<script src="/static/bundle.js"></script>'
                "</head><body>"
                "<h1>Welcome to the portal</h1>"
                "<p>Built with frappe engine.</p>"
                '<a href="/desk">Go to Desk</a>'
                "</body></html>"
            )
            self.wfile.write(html.encode("utf-8"))
        elif url_path == "/desk":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!DOCTYPE html><html><body><h1>desk interface</h1></body></html>")
        elif url_path == "/static/bundle.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"/* erpnext stylesheet */\n.btn { color: red; }")
        elif url_path == "/static/bundle.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.end_headers()
            js = (
                "function load() {\n"
                '  fetch("/api/method/frappe.auth.get_logged_user");\n'
                '  fetch("/api/resource/Customer");\n'
                "}\n"
            )
            self.wfile.write(js.encode("utf-8"))
        elif url_path == "/api/v1/customer":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            data = {"doctype": "Customer", "docstatus": 0, "naming_series": "CUST-.YYYY.-"}
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif url_path == "/api/v1/error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            err_data = {
                "exc_type": "OperationalError",
                "_server_messages": '["pymysql.err.OperationalError: Connection refused"]',
            }
            self.wfile.write(json.dumps(err_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


class StubPaginationHandler(http.server.BaseHTTPRequestHandler):
    """Stub handler creating a linked chain of pages for pagination testing."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        # /page/N links to /page/(N+1)
        path = self.path.strip("/")
        num = int(path.split("/")[-1]) if path.startswith("page/") else 1
        next_num = num + 1
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"<html><body>Page {num} <a href='/page/{next_num}'>Next</a></body></html>"
        self.wfile.write(html.encode("utf-8"))


class InvisibilityCrawlerTests(unittest.TestCase):
    """Verify crawler behavior on clean and leaky stub servers."""

    def _start_server(self, handler_cls: type[http.server.BaseHTTPRequestHandler]) -> tuple[http.server.HTTPServer, str]:
        server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        return server, base_url

    def test_clean_site_passes_with_zero_findings(self):
        """A clean site with no engine markers yields zero findings and exit code 0."""
        server, base_url = self._start_server(StubCleanHandler)
        try:
            exit_code, visited, findings = run_crawl(
                base_url=base_url,
                api_paths=["/api/v1/health"],
                max_pages=20,
                timeout=5.0,
            )
            self.assertEqual(exit_code, 0, f"Expected 0 exit code on clean site, got {exit_code}")
            self.assertEqual(findings, [], f"Expected 0 findings on clean site, got {findings}")
            # Ensure HTML, JS bundle, CSS bundles, and API were crawled
            visited_paths = [Path(u).name or "/" for u in visited]
            self.assertTrue(any("style.css" in u for u in visited))
            self.assertTrue(any("theme.css" in u for u in visited))
            self.assertTrue(any("app.js" in u for u in visited))
            self.assertTrue(any("/about" in u for u in visited))
            self.assertTrue(any("/api/v1/health" in u for u in visited))
        finally:
            server.shutdown()
            server.server_close()

    def test_leaky_site_fails_with_accurate_findings(self):
        """A leaky site fails with detailed findings for headers, cookies, bundles, and bodies."""
        server, base_url = self._start_server(StubLeakyHandler)
        try:
            exit_code, visited, findings = run_crawl(
                base_url=base_url,
                api_paths=["/api/v1/customer", "/api/v1/error"],
                max_pages=20,
                timeout=5.0,
            )
            self.assertEqual(exit_code, 1, "Expected non-zero exit code on leaky site")
            self.assertGreater(len(findings), 5, "Expected multiple findings on leaky site")

            marker_ids = {f.marker_id for f in findings}
            locations = [f.location for f in findings]

            # 1. Header leak: Server Werkzeug
            self.assertIn("MARKER-WERKZEUG", marker_ids)
            self.assertTrue(any("Server" in loc for loc in locations))

            # 2. Header leak: X-Frappe-Site-Name
            self.assertIn("MARKER-HEADER-X-FRAPPE", marker_ids)

            # 3. Cookie name leak: sid
            self.assertIn("MARKER-SID-COOKIE", marker_ids)
            self.assertTrue(any("cookie name 'sid'" in loc for loc in locations))

            # 4. Cookie value leak: system_user
            self.assertIn("MARKER-SYSTEM-USER", marker_ids)

            # 5. Body leak: frappe substring in index HTML
            self.assertIn("MARKER-FRAPPE", marker_ids)

            # 6. Body leak: desk word boundary in /desk
            self.assertIn("MARKER-DESK", marker_ids)

            # 7. CSS bundle leak: erpnext
            self.assertIn("MARKER-ERPNEXT", marker_ids)

            # 8. JS bundle leak: /api/method/ and /api/resource/
            self.assertIn("MARKER-API-METHOD", marker_ids)
            self.assertIn("MARKER-API-RESOURCE", marker_ids)

            # 9. API JSON leaks: doctype, docstatus, naming_series
            self.assertIn("MARKER-DOCTYPE", marker_ids)
            self.assertIn("MARKER-DOCSTATUS", marker_ids)
            self.assertIn("MARKER-NAMING-SERIES", marker_ids)

            # 10. HTTP 500 error leaks: pymysql and _server_messages
            self.assertIn("MARKER-PYMYSQL", marker_ids)
            self.assertIn("MARKER-SERVER-MESSAGES", marker_ids)
            self.assertIn("MARKER-EXC-TYPE", marker_ids)
        finally:
            server.shutdown()
            server.server_close()

    def test_same_origin_restriction_enforced(self):
        """Crawler never fetches external domains even if linked from pages."""
        server, base_url = self._start_server(StubCleanHandler)
        try:
            crawler = InvisibilityCrawler(
                base_url=base_url,
                markers=load_markers(DEFAULT_MARKERS_FILE),
                max_pages=20,
            )
            crawler.crawl()
            for visited_url in crawler.visited:
                self.assertTrue(
                    visited_url.startswith(base_url),
                    f"Visited external URL: {visited_url}",
                )
        finally:
            server.shutdown()
            server.server_close()

    def test_max_pages_limit_respected(self):
        """Crawler halts once max_pages limit is reached."""
        server, base_url = self._start_server(StubPaginationHandler)
        try:
            crawler = InvisibilityCrawler(
                base_url=f"{base_url}/page/1",
                markers=load_markers(DEFAULT_MARKERS_FILE),
                max_pages=3,
            )
            crawler.crawl()
            self.assertEqual(len(crawler.visited), 3)
        finally:
            server.shutdown()
            server.server_close()

    def test_cli_execution_clean_and_leaky(self):
        """Run crawler module as subprocess via CLI on clean and leaky sites."""
        clean_server, clean_base = self._start_server(StubCleanHandler)
        leaky_server, leaky_base = self._start_server(StubLeakyHandler)
        try:
            # Clean site CLI
            res_clean = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "infra.invisibility.crawler",
                    "--base-url",
                    clean_base,
                    "--api-paths",
                    "/api/v1/health",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_clean.returncode, 0, f"CLI clean failed: {res_clean.stderr}")
            data_clean = json.loads(res_clean.stdout)
            self.assertTrue(data_clean["passed"])
            self.assertEqual(data_clean["findings_count"], 0)

            # Leaky site CLI
            res_leaky = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "infra.invisibility.crawler",
                    "--base-url",
                    leaky_base,
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_leaky.returncode, 1, "CLI leaky should exit 1")
            data_leaky = json.loads(res_leaky.stdout)
            self.assertFalse(data_leaky["passed"])
            self.assertGreater(data_leaky["findings_count"], 0)
        finally:
            clean_server.shutdown()
            clean_server.server_close()
            leaky_server.shutdown()
            leaky_server.server_close()

    def test_connection_error_and_bad_targets_fail_closed(self):
        """Unreachable base URL, invalid URL, and missing API path fail closed (exit 1)."""
        # Closed port -> connection refused
        srv = http.server.HTTPServer(("127.0.0.1", 0), StubCleanHandler)
        dead_port = srv.server_port
        srv.server_close()
        dead_url = f"http://127.0.0.1:{dead_port}"

        errors: list[Any] = []
        exit_code, _, findings = run_crawl(dead_url, timeout=2.0, errors_out=errors)
        self.assertEqual(exit_code, 1)
        self.assertEqual(findings, [])
        self.assertGreater(len(errors), 0)

        # Invalid base URL via CLI -> fails closed
        res_bad = subprocess.run(
            [
                sys.executable,
                "-m",
                "infra.invisibility.crawler",
                "--base-url",
                "not-a-valid-url",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res_bad.returncode, 1)
        payload = json.loads(res_bad.stdout)
        self.assertFalse(payload["passed"])
        self.assertGreater(payload["errors_count"], 0)

        # Missing (404) explicit API path on live clean server -> fails closed
        clean_server, clean_base = self._start_server(StubCleanHandler)
        try:
            api_errors: list[Any] = []
            code, _, _ = run_crawl(
                clean_base,
                api_paths=["/api/v1/does-not-exist"],
                errors_out=api_errors,
            )
            self.assertEqual(code, 1)
            self.assertTrue(any("404" in e.error for e in api_errors))
        finally:
            clean_server.shutdown()
            clean_server.server_close()

    def test_invalid_regex_in_markers_raises_value_error(self):
        """Invalid regex in markers catalog raises ValueError instead of silently ignoring."""
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(
                [{"id": "BAD-RX", "pattern": "[unclosed(", "match_type": "regex"}],
                tf,
            )
            tmp_path = tf.name
        try:
            with self.assertRaises(ValueError):
                load_markers(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_unparseable_cookie_caught_and_cookie_values_redacted(self):
        """Malformed Set-Cookie still detects 'sid' and raw cookie values are redacted."""
        from infra.invisibility.crawler import format_report

        class MalformedCookieHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                # Brackets in attribute or invalid characters can break SimpleCookie
                self.send_header("Set-Cookie", "sid=super_secret_session_value_999; [invalid_attr]")
                self.send_header("Set-Cookie", "user_role=system_user; [invalid_attr]")
                self.end_headers()
                self.wfile.write(b"<!DOCTYPE html><html><body>OK</body></html>")

        srv, base_url = self._start_server(MalformedCookieHandler)
        try:
            code, visited, findings = run_crawl(base_url)
            self.assertEqual(code, 1)
            marker_ids = {f.marker_id for f in findings}
            self.assertIn("MARKER-SID-COOKIE", marker_ids)
            self.assertIn("MARKER-SYSTEM-USER", marker_ids)

            report = format_report(base_url, visited, findings)
            report_json = format_report(base_url, visited, findings, as_json=True)
            self.assertNotIn("super_secret_session_value_999", report)
            self.assertNotIn("super_secret_session_value_999", report_json)
            self.assertIn("<redacted>", report)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_off_origin_redirect_is_not_followed(self):
        """Crawler inspects 3xx headers but never sends HTTP requests to external redirect targets."""
        external_hits: list[str] = []

        class ExternalHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                external_hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"external")

        ext_srv, ext_base = self._start_server(ExternalHandler)

        class RedirectHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", f"{ext_base}/stolen")
                self.send_header("X-Frappe-Site-Name", "redirect-leak")
                self.end_headers()

        red_srv, red_base = self._start_server(RedirectHandler)
        try:
            errors: list[Any] = []
            code, _, findings = run_crawl(red_base, errors_out=errors)
            self.assertEqual(code, 1)
            self.assertEqual(external_hits, [], "Crawler followed redirect off-origin!")
            self.assertTrue(any(f.marker_id == "MARKER-HEADER-X-FRAPPE" for f in findings))
            self.assertTrue(any("off-origin redirect" in e.error for e in errors))
        finally:
            red_srv.shutdown()
            red_srv.server_close()
            ext_srv.shutdown()
            ext_srv.server_close()

    def test_js_chunks_sourcemaps_and_authenticated_pass(self):
        """Crawler follows JS dynamic imports, sourceMappingURL, and passes auth headers/cookies."""

        class JsAndAuthHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<!DOCTYPE html><html><script src='/assets/main.js'></script></html>"
                    )
                elif path == "/assets/main.js":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.end_headers()
                    self.wfile.write(
                        b"import('./chunk-1.js');\n//# sourceMappingURL=/assets/main.js.map\n"
                    )
                elif path == "/assets/chunk-1.js":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.end_headers()
                    self.wfile.write(b"window.cur_frm = {};")
                elif path == "/assets/main.js.map":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"sources":["frappe/desk.js"]}')
                elif path == "/api/v1/private":
                    auth = self.headers.get("Authorization", "")
                    if auth == "Bearer valid-test-token":
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"bootinfo":{"ok":true}}')
                    else:
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"error":"unauthorized"}')
                else:
                    self.send_response(404)
                    self.end_headers()

        srv, base_url = self._start_server(JsAndAuthHandler)
        try:
            code, visited, findings = run_crawl(
                base_url,
                api_paths=["/api/v1/private"],
                auth_headers={"Authorization": "Bearer valid-test-token"},
                cookies="orrery_sess=opaque",
            )
            self.assertEqual(code, 1)
            self.assertTrue(any(u.endswith("/assets/chunk-1.js") for u in visited))
            self.assertTrue(any(u.endswith("/assets/main.js.map") for u in visited))
            marker_ids = {f.marker_id for f in findings}
            self.assertIn("MARKER-CUR-GLOBALS", marker_ids)
            self.assertIn("MARKER-FRAPPE", marker_ids)
            self.assertIn("MARKER-BOOTINFO", marker_ids)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
