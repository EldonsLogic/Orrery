"""Exercise the live bench verifier against absent projects and sites."""

import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import unittest
from unittest import mock
from uuid import uuid4


DOCKER_DIR = Path(__file__).resolve().parents[1]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import verify_dev_bench  # noqa: E402


class TestBenchLiveVerifier(unittest.TestCase):
    """Check the verifier's exit status through its normal CLI entry point."""

    def test_missing_project_cannot_pass_verification(self):
        """A local image alone cannot prove this project's synthetic site is live."""
        project = f"erp001-missing-{uuid4().hex}"
        env = {
            **os.environ,
            "COMPOSE_PROJECT_NAME": project,
            "SITE_NAME": f"{project}.localhost",
            "ADMIN_PASSWORD": secrets.token_urlsafe(24),
            "DB_ROOT_PASSWORD": secrets.token_urlsafe(24),
        }
        result = subprocess.run(
            [sys.executable, str(DOCKER_DIR / "verify_dev_bench.py")],
            cwd=DOCKER_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, "Verifier passed an absent bench")
        self.assertTrue(
            "No running engine" in result.stdout + result.stderr,
            "Verifier failed without diagnosing the absent engine",
        )

    def test_eol_mariadb_10_6_fails_verification(self):
        """Verifier must reject MariaDB versions outside the pinned 11.4 LTS series."""
        site = "probe.localhost"
        responses = [
            subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=json.dumps({site: list(verify_dev_bench.EXPECTED_VERSIONS)}), stderr=""),
            subprocess.CompletedProcess([], 0, stdout=json.dumps(verify_dev_bench.EXPECTED_VERSIONS), stderr=""),
            subprocess.CompletedProcess([], 0, stdout=verify_dev_bench.EXPECTED_HRMS_COMMIT + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="10.6.28-MariaDB-ubu2004\n", stderr=""),
        ]
        stderr_buf = io.StringIO()
        with mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "probe-proj", "SITE_NAME": site}), \
             mock.patch.object(verify_dev_bench, "compose", side_effect=responses), \
             mock.patch("sys.stderr", stderr_buf):
            rc = verify_dev_bench.main()
        self.assertEqual(rc, 1)
        self.assertIn("MariaDB version '10.6.28-MariaDB-ubu2004'", stderr_buf.getvalue())

    @unittest.skipUnless(os.environ.get("BENCH_LIVE_PROJECT"), "Requires a live bench project")
    def test_missing_site_in_live_project_cannot_pass_verification(self):
        """A running engine must report when the requested site is unavailable."""
        result = subprocess.run(
            [sys.executable, str(DOCKER_DIR / "verify_dev_bench.py")],
            cwd=DOCKER_DIR,
            env={
                **os.environ,
                "COMPOSE_PROJECT_NAME": os.environ["BENCH_LIVE_PROJECT"],
                "SITE_NAME": f"missing-{uuid4().hex}.localhost",
                "ADMIN_PASSWORD": secrets.token_urlsafe(24),
                "DB_ROOT_PASSWORD": secrets.token_urlsafe(24),
            },
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, "Verifier passed an absent site")
        self.assertTrue(
            "Site is not ready" in result.stdout + result.stderr,
            "Verifier failed without diagnosing the absent site",
        )

    @unittest.skipUnless(os.environ.get("BENCH_LIVE_PROJECT"), "Requires a live bench project")
    def test_site_with_unreachable_http_port_cannot_pass_verification(self):
        """A provisioned site must also respond through its configured host port."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        result = subprocess.run(
            [sys.executable, str(DOCKER_DIR / "verify_dev_bench.py")],
            cwd=DOCKER_DIR,
            env={
                **os.environ,
                "COMPOSE_PROJECT_NAME": os.environ["BENCH_LIVE_PROJECT"],
                "SITE_NAME": os.environ.get("BENCH_LIVE_SITE", "erp001.localhost"),
                "ENGINE_PORT": str(free_port),
                "ADMIN_PASSWORD": secrets.token_urlsafe(24),
                "DB_ROOT_PASSWORD": secrets.token_urlsafe(24),
            },
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, "Verifier passed an unreachable HTTP endpoint")
        self.assertTrue(
            "HTTP endpoint is not ready" in result.stdout + result.stderr,
            "Verifier failed without diagnosing the unreachable HTTP endpoint",
        )


if __name__ == "__main__":
    unittest.main()
