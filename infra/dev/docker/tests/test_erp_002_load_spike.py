"""Offline unit and contract tests for ERP-002 50-tenant load spike tooling."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import run_50_tenant_load_spike as spike  # noqa: E402


class TestLoadSpikeHelpers(unittest.TestCase):
    """Validate input checks, statistics, and secret redaction."""

    def test_site_names_and_deterministic_db_names(self):
        sites = spike.site_names_for_count(50)
        self.assertEqual(len(sites), 50)
        self.assertEqual(sites[0], "load-001.localhost")
        self.assertEqual(sites[-1], "load-050.localhost")
        dbs = {spike.db_name_for_site(s) for s in sites}
        self.assertEqual(len(dbs), 50)
        for db in dbs:
            self.assertRegex(db, r"^_l50_[a-f0-9]{10}$")

    def test_rejects_unsafe_identifiers(self):
        with self.assertRaises(ValueError):
            spike.validate_project_name("../bad")
        with self.assertRaises(ValueError):
            spike.validate_site_name("prod.example.com")
        with self.assertRaises(ValueError):
            spike.site_names_for_count(1)
        with self.assertRaises(ValueError):
            spike.parse_concurrency_levels("0,10")
        with self.assertRaises(ValueError):
            spike.parse_concurrency_levels("999")

    def test_latency_percentiles_and_docker_mem_parser(self):
        self.assertEqual(spike.compute_latency_stats([])["p95_ms"], 0.0)
        stats = spike.compute_latency_stats([10.0, 20.0, 30.0, 40.0, 100.0])
        self.assertEqual(stats["min_ms"], 10.0)
        self.assertEqual(stats["p50_ms"], 30.0)
        self.assertGreaterEqual(stats["p95_ms"], 88.0)
        self.assertEqual(stats["max_ms"], 100.0)

        self.assertEqual(spike.parse_docker_mem_to_mib("199.2MiB / 62.76GiB"), 199.2)
        self.assertEqual(spike.parse_docker_mem_to_mib("1.5GiB / 62.76GiB"), 1536.0)
        self.assertEqual(spike.parse_docker_mem_to_mib("512KiB / 62.76GiB"), 0.5)

    def test_secret_redaction(self):
        raw = "failed with -p'super-secret-root' and admin='adm-secret'"
        masked = spike.redact_secrets(raw, ["super-secret-root", "adm-secret"])
        self.assertNotIn("super-secret-root", masked)
        self.assertNotIn("adm-secret", masked)
        self.assertIn("<REDACTED>", masked)


class TestLoadSpikeCliAndFlow(unittest.TestCase):
    """Validate CLI entry points and orchestrated spike logic offline."""

    def test_dry_run_cli_outputs_valid_json_plan(self):
        res = subprocess.run(
            [
                sys.executable,
                str(DOCKER_DIR / "run_50_tenant_load_spike.py"),
                "--compose-project", "erp002-dry",
                "--tenants", "50",
                "--concurrency-levels", "10,25,50",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        plan = json.loads(res.stdout)
        self.assertEqual(plan["status"], "dry_run")
        self.assertEqual(plan["tenant_count"], 50)
        self.assertEqual(plan["concurrency_levels"], [10, 25, 50])

    def test_missing_passwords_fail_closed(self):
        env = {k: v for k, v in os.environ.items() if k not in ("DB_ROOT_PASSWORD", "ADMIN_PASSWORD")}
        res = subprocess.run(
            [
                sys.executable,
                str(DOCKER_DIR / "run_50_tenant_load_spike.py"),
                "--compose-project", "erp002-missing-pw",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("DB_ROOT_PASSWORD", res.stderr)

    def test_mocked_run_spike_flow(self):
        def fake_http(port, host, method, path, headers=None, body=None, timeout=30.0):
            if "get_logged_user" in path:
                return 200, '{"message":"Administrator"}', 4.5
            if method == "POST" and "/ToDo" in path:
                return 200, body or "{}", 8.0
            return 200, '{"message":"pong"}', 2.0

        fake_snap = {"containers": {}, "mariadb": {"load_db_count": 3}, "redis_cache": {"dbsize": 12}}
        fake_tokens = {f"load-{i:03d}.localhost": f"key{i}:sec{i}" for i in range(1, 4)}

        with mock.patch.object(spike, "_collect_snapshots", return_value=fake_snap), \
             mock.patch.object(spike, "_provision_template_site", return_value={"site_name": "load-001.localhost", "db_name": "_l50_x", "cold_provision_seconds": 120.0}), \
             mock.patch.object(spike, "_dump_template_db", return_value={"dump_seconds": 1.2, "dump_bytes": 1024, "dump_path": "/tmp/t.sql"}), \
             mock.patch.object(spike, "_clone_single_site", return_value=1.5), \
             mock.patch.object(spike, "compose_exec", return_value=subprocess.CompletedProcess([], 0, "", "")), \
             mock.patch.object(spike, "_generate_per_site_api_tokens", return_value=fake_tokens), \
             mock.patch.object(spike, "_verify_cross_tenant_db_isolation", return_value={"isolated": True, "errno": 1142}), \
             mock.patch.object(spike, "_host_http_request", side_effect=fake_http):
            report = spike.run_spike(
                project="erp002-mock",
                compose_file=spike.DEFAULT_COMPOSE_FILE,
                engine_port=18222,
                tenant_count=3,
                concurrency_levels=[2],
                requests_per_level=6,
                clone_workers=2,
                db_root_password="mock-root-password",
                admin_password="mock-admin-password",
            )

        self.assertEqual(report["tenant_count"], 3)
        self.assertTrue(report["cross_tenant_db_check"]["isolated"])
        self.assertEqual(report["cold_cache_warming"]["sites_verified_200"], 3)
        self.assertEqual(len(report["load_waves"]), 1)
        self.assertEqual(report["load_waves"][0]["http_200"], 6)
        self.assertEqual(report["load_waves"][0]["isolation_mismatches"], 0)


if __name__ == "__main__":
    unittest.main()
