"""Verify the isolation boundaries of the development bench configuration."""

import json
import os
from pathlib import Path
import subprocess
import unittest


class DevBenchContractTests(unittest.TestCase):
    """Validate Compose's resolved service configuration without starting it."""

    def setUp(self):
        """Resolve the actual Compose file with isolated synthetic settings."""
        self.services = self.resolve_services("benchcontracta")

    def resolve_services(self, project_name):
        """Return the resolved services for a specific synthetic project."""
        compose_file = Path(__file__).resolve().parents[1] / "docker-compose.dev.yml"
        environment = os.environ.copy()
        environment.update(
            {
                "DB_ROOT_PASSWORD": "synthetic-placeholder",
                "ADMIN_PASSWORD": "synthetic-placeholder",
                "SITE_NAME": "synthetic.localhost",
                "DB_PORT": "13306",
                "REDIS_CACHE_PORT": "12001",
                "REDIS_QUEUE_PORT": "11001",
                "ENGINE_PORT": "18000",
            }
        )
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                project_name,
                "--env-file",
                os.devnull,
                "-f",
                str(compose_file),
                "config",
                "--format",
                "json",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["services"]

    def test_database_and_caches_do_not_publish_host_ports(self):
        """Keep the database and both caches on the private Compose network."""
        for name in ("mariadb", "redis-cache", "redis-queue"):
            with self.subTest(service=name):
                self.assertIn(name, self.services)
                self.assertFalse(
                    self.services[name].get("ports"),
                    f"{name} must not publish a host port",
                )

    def test_engine_host_ports_bind_only_to_ipv4_loopback(self):
        """Allow engine ports only when they are bound to IPv4 loopback."""
        self.assertIn("engine", self.services)
        for port in self.services["engine"].get("ports", []):
            with self.subTest(port=port):
                self.assertEqual(
                    port.get("host_ip"),
                    "127.0.0.1",
                    "engine host ports must bind only to IPv4 loopback",
                )

    def test_project_names_isolate_containers_and_engine_image(self):
        """Keep explicit container names and built engine images project-scoped."""
        other_services = self.resolve_services("benchcontractb")
        self.assertEqual(self.services.keys(), other_services.keys())

        for service, config in self.services.items():
            with self.subTest(service=service):
                first_name = config.get("container_name")
                other_name = other_services[service].get("container_name")
                if first_name is not None or other_name is not None:
                    self.assertTrue(first_name)
                    self.assertTrue(other_name)
                    self.assertNotEqual(
                        first_name, other_name, "container name is shared by projects"
                    )

        with self.subTest(resource="engine image"):
            first_image = self.services["engine"].get("image")
            other_image = other_services["engine"].get("image")
            if first_image is not None or other_image is not None:
                self.assertTrue(first_image)
                self.assertTrue(other_image)
                self.assertNotEqual(
                    first_image, other_image, "built engine image is shared by projects"
                )

    def test_missing_admin_password_rejects_configuration(self):
        """Require an explicit administrator password instead of a fallback."""
        compose_file = Path(__file__).resolve().parents[1] / "docker-compose.dev.yml"
        environment = os.environ.copy()
        environment.update(
            {
                "DB_ROOT_PASSWORD": "synthetic-placeholder",
                "SITE_NAME": "synthetic.localhost",
                "ENGINE_PORT": "18000",
            }
        )
        environment.pop("ADMIN_PASSWORD", None)
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                "benchcontracta",
                "--env-file",
                os.devnull,
                "-f",
                str(compose_file),
                "config",
                "--quiet",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(
            result.returncode, 0, "missing ADMIN_PASSWORD must reject configuration"
        )
        self.assertIn("ADMIN_PASSWORD", result.stderr)

    def test_mariadb_healthcheck_does_not_embed_database_password(self):
        """Keep database credentials out of resolved healthcheck commands."""
        healthcheck = self.services["mariadb"]["healthcheck"]["test"]
        self.assertTrue(healthcheck)
        self.assertNotIn(
            "synthetic-placeholder",
            json.dumps(healthcheck),
            "the healthcheck must not embed the database password",
        )


if __name__ == "__main__":
    unittest.main()
