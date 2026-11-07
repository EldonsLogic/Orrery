#!/usr/bin/env python3
"""
Verification suite for Orrery development bench (ERP-001).

Validates:
1. Pinned versions: Frappe (15.126.0), ERPNext (15.124.5), HRMS (15.64.8).
2. Infrastructure images: MariaDB 10.6, Redis 7.2.7-alpine (BSD-3-Clause).
3. Docker compose syntax and configuration.
4. Engine container Python environment and change_engine app importability.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKER_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"
ENV_EXAMPLE = DOCKER_DIR / ".env.example"
CHANGE_ENGINE_DIR = REPO_ROOT / "apps" / "engine" / "change_engine"

PINNED_VERSIONS = {
    "frappe": "15.126.0",
    "erpnext": "15.124.5",
    "hrms": "15.64.8",
    "change_engine": "0.1.0",
    "mariadb": "10.6",
    "redis": "7.2.7-alpine",
}


class TestDevBenchConfiguration(unittest.TestCase):
    def test_01_compose_syntax_and_env_example(self):
        """Validates docker-compose.dev.yml and .env.example format and version pins."""
        self.assertTrue(COMPOSE_FILE.is_file(), "docker-compose.dev.yml must exist")
        self.assertTrue(ENV_EXAMPLE.is_file(), ".env.example must exist")

        content = COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertIn("mariadb:10.6", content)
        self.assertIn("redis:7.2.7-alpine", content)
        self.assertIn("ce-engine-dev", content)
        self.assertIn("apps/engine/change_engine", content)

        env_content = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("FRAPPE_VERSION=v15.126.0", env_content)
        self.assertIn("ERPNEXT_VERSION=v15.124.5", env_content)
        self.assertIn("HRMS_VERSION=v15.64.8", env_content)
        self.assertIn("REDIS_VERSION=7.2.7-alpine", env_content)

    def test_02_docker_compose_config_validation(self):
        """Runs 'docker compose config' with dummy env to ensure compose file is valid."""
        env = dict(os.environ)
        env["DB_ROOT_PASSWORD"] = "test_root_pwd"
        env["ADMIN_PASSWORD"] = "test_admin_pwd"

        res = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            cwd=str(DOCKER_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"docker compose config failed: {res.stderr}")

    def test_03_engine_image_version_pins_and_mount(self):
        """Verifies Frappe, ERPNext, HRMS, and mounted change_engine inside engine image."""
        check_img = subprocess.run(
            ["docker", "image", "inspect", "orrery-engine-dev:v15"],
            capture_output=True,
            text=True,
        )
        if check_img.returncode != 0:
            self.skipTest("Image orrery-engine-dev:v15 not yet built or Docker unavailable")

        # Inspect Python package versions inside the container with change_engine mounted
        script = (
            "import json, frappe, erpnext, hrms, change_engine\n"
            "print(json.dumps({\n"
            "    'frappe': getattr(frappe, '__version__', None),\n"
            "    'erpnext': getattr(erpnext, '__version__', None),\n"
            "    'hrms': getattr(hrms, '__version__', None),\n"
            "    'change_engine': getattr(change_engine, '__version__', None),\n"
            "}))\n"
        )
        run_res = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{CHANGE_ENGINE_DIR}:/home/frappe/frappe-bench/apps/change_engine:rw",
                "orrery-engine-dev:v15",
                "python", "-c", script,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(run_res.returncode, 0, f"Failed running python in image: {run_res.stderr}")

        # The JSON output is on the last non-empty line
        output_lines = [l.strip() for l in run_res.stdout.splitlines() if l.strip()]
        self.assertTrue(output_lines, "Container produced no output")
        try:
            versions = json.loads(output_lines[-1])
        except Exception as e:
            self.fail(f"Could not parse version JSON from container: {output_lines[-1]} ({e})")

        self.assertEqual(versions.get("frappe"), PINNED_VERSIONS["frappe"])
        self.assertEqual(versions.get("erpnext"), PINNED_VERSIONS["erpnext"])
        self.assertEqual(versions.get("hrms"), PINNED_VERSIONS["hrms"])
        self.assertEqual(versions.get("change_engine"), PINNED_VERSIONS["change_engine"])


if __name__ == "__main__":
    unittest.main()
