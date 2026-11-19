"""SEC-004 offline unit tests for verify_tenant_isolation.py and live-suite fail-closed gating.

NOTE: These tests mock Compose/HTTP calls to validate the verifier's own logic and CLI/CI
fail-closed gates. They are unit tests of the verifier and harness only — NEVER cite them as
live cross-tenant isolation evidence (live proof comes from `run_isolation_suite.py` /
`live_sec_004_bench_attacks.py`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import verify_tenant_isolation as iso  # noqa: E402


class TestTenantIsolationVerifier(unittest.TestCase):
    """Validate SEC-004 verifier input checks, strict encryption_key check, low-role checks, and fail-closed gates."""

    def test_rejects_invalid_project_and_site_names(self) -> None:
        with self.assertRaises(ValueError):
            iso.validate_project_name("../bad")
        with self.assertRaises(ValueError):
            iso.validate_site_name("prod.example.com")
        with self.assertRaises(ValueError):
            iso.verify_live_isolation(
                project="sec004-test",
                compose_file=iso.DEFAULT_COMPOSE_FILE,
                engine_port=18111,
                site_a="a.localhost",
                site_b="a.localhost",
            )

    def test_missing_project_cli_fails_closed(self) -> None:
        res = subprocess.run(
            [
                sys.executable,
                str(DOCKER_DIR / "verify_tenant_isolation.py"),
                "--compose-project", "../bad",
                "--site-a", "a.localhost",
                "--site-b", "b.localhost",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(res.returncode, 2)

    def test_missing_encryption_keys_fail_closed(self) -> None:
        """Verifier script must require non-empty distinct encryption keys (never pass when both are absent)."""
        src = (DOCKER_DIR / "verify_tenant_isolation.py").read_text(encoding="utf-8")
        self.assertIn("bool(enc_a) and bool(enc_b) and enc_a != enc_b", src)
        self.assertNotIn("(not enc_a and not enc_b)", src)

        missing_enc_payload = {
            "config_checks": {
                "distinct_db_name": True,
                "distinct_db_password": True,
                "no_shared_encryption_key": False,
            },
            "a_to_b": {"select": {"denied": True, "errno": 1142}},
            "b_to_a": {"select": {"denied": True, "errno": 1142}},
        }
        fake_proc = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="__ISOLATION_DB__" + json.dumps(missing_enc_payload),
            stderr="",
        )
        with mock.patch.object(iso, "compose_exec", return_value=fake_proc):
            rep = iso.check_site_configs_and_mariadb(
                "sec004-mock", iso.DEFAULT_COMPOSE_FILE, "a.localhost", "b.localhost"
            )
        self.assertFalse(rep["passed"])

    def test_live_suite_fails_closed_when_ci_requires_live_without_context(self) -> None:
        """CI_REQUIRE_LIVE_SEC004=1 without SEC004_CONTEXT must fail loudly instead of silently skipping."""
        live_suite = REPO_ROOT / "apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py"
        self.assertTrue(live_suite.is_file(), f"missing live suite at {live_suite}")
        env = dict(os.environ, CI_REQUIRE_LIVE_SEC004="1")
        env.pop("SEC004_CONTEXT", None)
        res = subprocess.run(
            [sys.executable, "-m", "unittest", str(live_suite)],
            env=env,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(res.returncode, 0, "live suite must fail closed when CI_REQUIRE_LIVE_SEC004=1")
        self.assertIn("SEC004_CONTEXT is required", res.stderr + res.stdout)

    def test_mocked_live_isolation_pass_and_fail_closed(self) -> None:
        db_ok = {
            "passed": True,
            "config_checks": {"distinct_db_name": True, "distinct_db_password": True, "no_shared_encryption_key": True},
            "a_to_b": {"select": {"denied": True, "errno": 1142}},
            "b_to_a": {"select": {"denied": True, "errno": 1142}},
        }
        rt_ok = {
            "passed": True,
            "created": {"a.localhost": "TD-0001", "b.localhost": "TD-0002"},
            "low_users": {"a.localhost": "sec004-low@example.invalid"},
            "cross": {
                "a.localhost": {"orm_isolated": True, "cache_isolated": True},
                "b.localhost": {"orm_isolated": True, "cache_isolated": True},
            },
        }
        tokens = {"a.localhost": "ka:sa", "b.localhost": "kb:sb", "low_a": "kl:sl"}

        def fake_http(port, host, path, headers=None, timeout=15.0):
            tok = (headers or {}).get("Authorization", "")
            if host == "a.localhost" and tok == "token ka:sa" and "TD-0001" in path:
                return 200, '{"data":{"description":"sec004-canary-a-123"}}'
            if host == "b.localhost" and tok == "token kb:sb" and "TD-0002" in path:
                return 200, '{"data":{"description":"sec004-canary-b-456"}}'
            if host == "a.localhost" and tok == "token kl:sl" and "get_logged_user" in path:
                return 200, '{"message":"sec004-low@example.invalid"}'
            if host == "b.localhost" and tok == "token kb:sb" and "TD-0001" in path:
                return 404, '{"exc_type":"DoesNotExistError"}'
            return 401, '{"exc_type":"AuthenticationError"}'

        with mock.patch.object(iso, "check_site_configs_and_mariadb", return_value=db_ok), \
             mock.patch.object(iso, "probe_runtime_orm_cache_and_tokens", return_value=(rt_ok, tokens)), \
             mock.patch.object(iso, "cleanup_runtime_canaries") as mock_clean, \
             mock.patch.object(iso, "host_http_get", side_effect=fake_http), \
             mock.patch.object(iso.secrets, "token_hex", side_effect=["123", "456"]):
            rep = iso.verify_live_isolation(
                project="sec004-mock",
                compose_file=iso.DEFAULT_COMPOSE_FILE,
                engine_port=18111,
                site_a="a.localhost",
                site_b="b.localhost",
            )
        self.assertTrue(rep["passed"])
        self.assertTrue(rep["http_host_and_token"]["checks"]["low_role_a_200"])
        self.assertTrue(rep["http_host_and_token"]["checks"]["low_role_a_rejected_on_host_b"])
        mock_clean.assert_called_once()

        # If a swapped Admin or low-role token returns HTTP 200, overall report must fail closed.
        def leaky_http(port, host, path, headers=None, timeout=15.0):
            if host == "b.localhost" and (headers or {}).get("Authorization") in ("token ka:sa", "token kl:sl"):
                return 200, '{"data":{"description":"sec004-canary-b-456"}}'
            return fake_http(port, host, path, headers, timeout)

        with mock.patch.object(iso, "check_site_configs_and_mariadb", return_value=db_ok), \
             mock.patch.object(iso, "probe_runtime_orm_cache_and_tokens", return_value=(rt_ok, tokens)), \
             mock.patch.object(iso, "cleanup_runtime_canaries"), \
             mock.patch.object(iso, "host_http_get", side_effect=leaky_http), \
             mock.patch.object(iso.secrets, "token_hex", side_effect=["123", "456"]):
            bad = iso.verify_live_isolation(
                project="sec004-mock",
                compose_file=iso.DEFAULT_COMPOSE_FILE,
                engine_port=18111,
                site_a="a.localhost",
                site_b="b.localhost",
            )
        self.assertFalse(bad["passed"])
        self.assertFalse(bad["http_host_and_token"]["checks"]["token_a_rejected_on_host_b"])
        self.assertFalse(bad["http_host_and_token"]["checks"]["low_role_a_rejected_on_host_b"])


if __name__ == "__main__":
    unittest.main()
