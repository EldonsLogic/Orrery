"""Check the image references resolved by the local bench tooling."""

import json
import os
from pathlib import Path
import re
import subprocess
import unittest


class BenchImagePinTests(unittest.TestCase):
    """Verify that the bench uses immutable upstream images."""

    def test_engine_build_resolves_a_digest_pinned_base(self):
        """A changing upstream tag must not silently change the engine build."""
        docker_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                "docker", "buildx", "build", "--progress=plain", "--call=outline",
                str(docker_dir),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        references = re.findall(
            r"load metadata for (\S+)", result.stdout + "\n" + result.stderr
        )
        self.assertTrue(references, "BuildKit did not identify the engine base image")
        self.assertRegex(
            references[0],
            r"^docker\.io/frappe/erpnext@sha256:[0-9a-f]{64}$",
            "the engine base must resolve by immutable digest",
        )

    def test_data_services_resolve_digest_pinned_images(self):
        """Tag movement must not silently change database or cache binaries."""
        docker_dir = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment.update({"DB_ROOT_PASSWORD": "synthetic", "ADMIN_PASSWORD": "synthetic"})
        result = subprocess.run(
            [
                "docker", "compose", "--env-file", os.devnull, "-f",
                str(docker_dir / "docker-compose.dev.yml"), "config", "--format", "json",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        for service in ("mariadb", "redis-cache", "redis-queue"):
            with self.subTest(service=service):
                self.assertRegex(
                    services[service]["image"], r"@sha256:[0-9a-f]{64}$",
                    f"{service} must resolve by immutable digest",
                )


if __name__ == "__main__":
    unittest.main()
