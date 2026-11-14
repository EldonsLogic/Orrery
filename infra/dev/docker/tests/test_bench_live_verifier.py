"""Exercise the live bench verifier against absent projects and sites."""

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import unittest
from uuid import uuid4


class TestBenchLiveVerifier(unittest.TestCase):
    """Check the verifier's exit status through its normal CLI entry point."""

    def test_missing_project_cannot_pass_verification(self):
        """A local image alone cannot prove this project's synthetic site is live."""
        docker_dir = Path(__file__).resolve().parents[1]
        project = f"erp001-missing-{uuid4().hex}"
        env = {
            **os.environ,
            "COMPOSE_PROJECT_NAME": project,
            "SITE_NAME": f"{project}.localhost",
            "ADMIN_PASSWORD": secrets.token_urlsafe(24),
            "DB_ROOT_PASSWORD": secrets.token_urlsafe(24),
        }
        result = subprocess.run(
            [sys.executable, str(docker_dir / "verify_dev_bench.py")],
            cwd=docker_dir,
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

    @unittest.skipUnless(os.environ.get("BENCH_LIVE_PROJECT"), "Requires a live bench project")
    def test_missing_site_in_live_project_cannot_pass_verification(self):
        """A running engine must report when the requested site is unavailable."""
        docker_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(docker_dir / "verify_dev_bench.py")],
            cwd=docker_dir,
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
        docker_dir = Path(__file__).resolve().parents[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        result = subprocess.run(
            [sys.executable, str(docker_dir / "verify_dev_bench.py")],
            cwd=docker_dir,
            env={
                **os.environ,
                "COMPOSE_PROJECT_NAME": os.environ["BENCH_LIVE_PROJECT"],
                "SITE_NAME": "erp001.localhost",
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
