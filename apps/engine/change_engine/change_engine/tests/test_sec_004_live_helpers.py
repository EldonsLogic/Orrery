"""SEC-004: offline tests for the pure helpers of the live isolation bench.

The live suite (`live_sec_004_bench_attacks.py`) only runs against a Docker bench, so its decision helpers
are tested here with fake responses: what counts as the adapter's refusal, when an RQ Job page is too full
to prove a negative, and which Compose project names the harness accepts. Standard library only; both
modules are loaded by file path.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
LIVE_PATH = Path(__file__).with_name("live_sec_004_bench_attacks.py")
PROJECT_PATH = REPO_ROOT / "infra/dev/docker/isolation/sec004_project.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


live = _load("live_sec_004_bench_attacks", LIVE_PATH)
project = _load("sec004_project", PROJECT_PATH)


def _error_body(*tracebacks: str, exception: str | None = None) -> bytes:
    """A frappe-style JSON error: `exc` is a JSON string holding a list of tracebacks."""
    doc = {"exc": json.dumps(list(tracebacks))}
    if exception is not None:
        doc["exception"] = exception
    return json.dumps(doc).encode()


REFUSAL_TB = (
    "Traceback (most recent call last):\n  File \"endpoints.py\", line 182, in _require_deploy\n"
    "PermissionError: Not permitted\n"
)
CHAINED_CRASH_TB = (
    "Traceback (most recent call last):\n  File \"endpoints.py\", line 182, in _require_deploy\n"
    "PermissionError: Not permitted\n\nDuring handling of the above exception, another exception occurred:\n\n"
    "Traceback (most recent call last):\n  File \"other.py\", line 9, in cleanup\nRuntimeError: database is gone\n"
)


class AppRefusalTests(unittest.TestCase):
    def test_final_permission_error_is_a_refusal(self):
        self.assertTrue(live.is_app_refusal(500, _error_body(REFUSAL_TB)))
        detailed = REFUSAL_TB.replace("Not permitted", "Not permitted: admin permission required")
        self.assertTrue(live.is_app_refusal(500, _error_body(detailed)))

    def test_chained_traceback_ending_in_another_exception_is_not_a_refusal(self):
        body = _error_body(CHAINED_CRASH_TB)
        self.assertIn(b"PermissionError: Not permitted", body)  # the old substring check accepted this
        self.assertFalse(live.is_app_refusal(500, body))

    def test_unrelated_final_exception_quoting_the_refusal_is_not_a_refusal(self):
        crash = "Traceback (most recent call last):\nRuntimeError: PermissionError: Not permitted was swallowed\n"
        self.assertFalse(live.is_app_refusal(500, _error_body(crash)))

    def test_last_traceback_decides(self):
        self.assertFalse(live.is_app_refusal(500, _error_body(REFUSAL_TB, "Traceback:\nValueError: x\n")))
        self.assertTrue(live.is_app_refusal(500, _error_body("Traceback:\nValueError: x\n", REFUSAL_TB)))

    def test_exception_field_used_when_there_is_no_traceback_field(self):
        ok = json.dumps({"exception": "PermissionError: Not permitted"}).encode()
        bad = json.dumps({"exception": "RuntimeError: boom"}).encode()
        self.assertTrue(live.is_app_refusal(500, ok))
        self.assertFalse(live.is_app_refusal(500, bad))

    def test_non_json_or_other_status_is_not_a_refusal(self):
        self.assertFalse(live.is_app_refusal(500, b"PermissionError: Not permitted"))
        self.assertFalse(live.is_app_refusal(500, b"[1, 2]"))
        self.assertFalse(live.is_app_refusal(500, b"{}"))
        self.assertFalse(live.is_app_refusal(200, _error_body(REFUSAL_TB)))


class BucketCompletenessTests(unittest.TestCase):
    @staticmethod
    def _page(n: int) -> bytes:
        return json.dumps({"data": [{"name": f"job-{i}"} for i in range(n)]}).encode()

    def test_short_page_is_complete(self):
        self.assertEqual(len(live.assert_bucket_complete(self._page(19), "A default/queued")), 19)
        self.assertEqual(live.assert_bucket_complete(self._page(0), "A default/queued"), [])

    def test_full_page_is_inconclusive(self):
        with self.assertRaisesRegex(AssertionError, "inconclusive"):
            live.assert_bucket_complete(self._page(live.RQ_PAGE), "A default/queued")

    def test_unparseable_page_is_inconclusive(self):
        for body in (b"not json", b"{}", b'{"data": null}'):
            with self.subTest(body=body), self.assertRaisesRegex(AssertionError, "inconclusive"):
                live.assert_bucket_complete(body, "A default/queued")


class ProjectNameTests(unittest.TestCase):
    def test_accepts_the_names_the_harness_uses(self):
        for name in ("sec004", "sec004-isolation", "sec004-ci-isolation", "sec004_run2"):
            with self.subTest(name=name):
                self.assertTrue(project.is_sec004_project(name))

    def test_refuses_names_that_only_contain_the_token(self):
        for name in ("prod-sec004", "sec004prod", "shared-sec004-isolation", "sec004-", "-sec004", "SEC004", "", "dev"):
            with self.subTest(name=name):
                self.assertFalse(project.is_sec004_project(name))


if __name__ == "__main__":
    unittest.main()
