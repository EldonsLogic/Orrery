"""Regression tests for incomplete QA-016 inspection coverage."""
import json
import subprocess
import sys

import unittest
import test_crawler
from test_crawler import StubCleanHandler
from infra.invisibility.crawler import run_crawl


class FailClosedTests(unittest.TestCase):
    """Exercise real HTTP and CLI boundaries for remaining review defects."""

    _start_server = test_crawler.InvisibilityCrawlerTests._start_server

    def test_missing_linked_bundle_fails(self):
        """A broken asset must not count as inspected and clean."""
        class MissingBundle(StubCleanHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b'<script src="/missing.js"></script>')
                else:
                    super().do_GET()

        server, base = self._start_server(MissingBundle)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        errors = []
        code, _, _ = run_crawl(base, errors_out=errors)
        self.assertEqual(code, 1)
        self.assertTrue(any('404' in e.error for e in errors))

    def test_rejected_authenticated_pass_fails(self):
        """Invalid credentials must not certify a private response as inspected."""
        class RejectedAuth(StubCleanHandler):
            def do_GET(self):
                if self.path == '/private':
                    self.send_response(401)
                    self.end_headers()
                else:
                    super().do_GET()

        server, base = self._start_server(RejectedAuth)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        for credentials in ({'auth_headers': {'Authorization': 'Bearer synthetic'}},
                            {'cookies': 'session=synthetic'}):
            with self.subTest(credentials=list(credentials)):
                code, _, _ = run_crawl(base, api_paths=['/private'], **credentials)
                self.assertEqual(code, 1)

    def test_page_budget_cannot_skip_required_api(self):
        """Budget exhaustion must fail even when the pages inspected were clean."""
        server, base = self._start_server(StubCleanHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        errors = []
        code, _, _ = run_crawl(base, api_paths=['/missing'], max_pages=1, errors_out=errors)
        self.assertEqual(code, 1)
        self.assertTrue(errors)

    def test_cli_empty_api_path_fails(self):
        """An explicitly empty API path must not be silently discarded."""
        server, base = self._start_server(StubCleanHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        result = subprocess.run(
            [sys.executable, '-m', 'infra.invisibility', '--base-url', base,
             '--api-paths', ',', '--json'], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['passed'])
