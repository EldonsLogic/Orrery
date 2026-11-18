"""SEC-004 offline unit & contract tests for verify_tenant_isolation.py."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import verify_tenant_isolation as iso  # noqa: E402


class TestTenantIsolationVerifier(unittest.TestCase):
    """Validate SEC-004 verifier input checks, secret redaction, and fail-closed outcomes."""

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

    def test_mocked_live_isolation_pass_and_fail_closed(self) -> None:
        db_ok = {
            "passed": True,
            "config_checks": {"distinct_db_name": True, "distinct_db_password": True, "distinct_encryption_key": True},
            "a_to_b": {"select": {"denied": True, "errno": 1142}},
            "b_to_a": {"select": {"denied": True, "errno": 1142}},
        }
        rt_ok = {
            "passed": True,
            "created": {"a.localhost": "TD-0001", "b.localhost": "TD-0002"},
            "cross": {
                "a.localhost": {"orm_isolated": True, "cache_isolated": True},
                "b.localhost": {"orm_isolated": True, "cache_isolated": True},
            },
        }
        tokens = {"a.localhost": "ka:sa", "b.localhost": "kb:sb"}

        def fake_http(port, host, path, headers=None, timeout=15.0):
            tok = (headers or {}).get("Authorization", "")
            if host == "a.localhost" and tok == "token ka:sa" and "TD-0001" in path:
                return 200, '{"data":{"description":"sec004-canary-a-123"}}'
            if host == "b.localhost" and tok == "token kb:sb" and "TD-0002" in path:
                return 200, '{"data":{"description":"sec004-canary-b-456"}}'
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
        mock_clean.assert_called_once()

        # If a swapped token returns HTTP 200, overall report must fail closed even if DB/ORM pass.
        def leaky_http(port, host, path, headers=None, timeout=15.0):
            if host == "b.localhost" and (headers or {}).get("Authorization") == "token ka:sa":
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


if __name__ == "__main__":
    unittest.main()
