"""Tests for infra/dev/docker/audit_arabic_translations.py (ERP-006)."""

import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest
from uuid import uuid4


class TestArabicAuditCLI(unittest.TestCase):
    def test_missing_project_fails_closed(self):
        docker_dir = Path(__file__).resolve().parents[1]
        project = f"erp006-missing-{uuid4().hex}"
        env = {
            **os.environ,
            "COMPOSE_PROJECT_NAME": project,
            "SITE_NAME": f"{project}.localhost",
            "ADMIN_PASSWORD": secrets.token_urlsafe(24),
            "DB_ROOT_PASSWORD": secrets.token_urlsafe(24),
        }
        result = subprocess.run(
            [sys.executable, str(docker_dir / "audit_arabic_translations.py")],
            cwd=docker_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No running engine", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
