"""ERP-020: the headless override leaves the engine with no host port and no external network."""

import json
import os
from pathlib import Path
import subprocess
import unittest

DOCKER_DIR = Path(__file__).resolve().parents[1]
TOKEN = "t" * 48


def resolve(extra_env=None, files=("docker-compose.headless.yml",)):
    environment = os.environ.copy()
    environment.update(
        {
            "DB_ROOT_PASSWORD": "synthetic-placeholder",
            "ADMIN_PASSWORD": "synthetic-placeholder",
            "SITE_NAME": "synthetic.localhost",
            "ENGINE_PORT": "18000",
            "ENGINE_INTERNAL_TOKEN": TOKEN,
        }
    )
    environment.update(extra_env or {})
    for key, value in list(environment.items()):
        if value is None:
            del environment[key]
    command = ["docker", "compose", "--project-name", "erp020contract", "--env-file", os.devnull]
    for name in files:
        command += ["-f", str(DOCKER_DIR / name)]
    return subprocess.run(
        command + ["config", "--format", "json"],
        env=environment, capture_output=True, text=True, timeout=30, check=False,
    )


class HeadlessComposeTests(unittest.TestCase):
    def setUp(self):
        result = resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.config = json.loads(result.stdout)

    def test_no_service_publishes_a_host_port(self):
        for name, service in self.config["services"].items():
            with self.subTest(service=name):
                self.assertFalse(service.get("ports"), f"{name} must not publish a host port")

    def test_every_network_is_internal(self):
        self.assertEqual(set(self.config["networks"]), {"data", "engine_internal"})
        for name in ("data", "engine_internal"):
            with self.subTest(network=name):
                self.assertIs(self.config["networks"][name].get("internal"), True)

    def test_no_service_uses_host_network_or_the_default_network(self):
        for name, service in self.config["services"].items():
            with self.subTest(service=name):
                self.assertNotEqual(service.get("network_mode"), "host")
                self.assertNotIn("default", service.get("networks", {}))
                self.assertTrue(service.get("networks"))

    def test_database_and_caches_are_not_on_the_gateway_facing_network(self):
        for name in ("mariadb", "redis-cache", "redis-queue"):
            with self.subTest(service=name):
                self.assertEqual(set(self.config["services"][name]["networks"]), {"data"})
        self.assertEqual(set(self.config["services"]["engine"]["networks"]), {"data", "engine_internal"})

    def test_engine_receives_the_internal_token(self):
        self.assertEqual(self.config["services"]["engine"]["environment"]["ENGINE_INTERNAL_TOKEN"], TOKEN)

    def test_engine_is_served_through_the_wsgi_guard(self):
        command = self.config["services"]["engine"]["command"]
        script = " ".join(command)
        self.assertIn("exec gunicorn", script)
        self.assertIn("python3 -m change_engine.api.route_guard &&", script)
        self.assertTrue(script.endswith("change_engine.wsgi:application"))
        self.assertNotIn("frappe.app:application", script)

    def test_pins_volumes_and_build_match_the_dev_compose(self):
        """The headless file is a copy of the dev file; keep the pinned images and mounts identical."""
        dev = json.loads(resolve(files=("docker-compose.dev.yml",)).stdout)["services"]
        for name, service in self.config["services"].items():
            with self.subTest(service=name):
                env = service.get("environment", {}).copy()
                build = service.get("build", {}).copy()
                if name == "engine":
                    self.assertEqual(build.pop("target", None), "headless")
                    env.pop("ENGINE_INTERNAL_TOKEN_PREVIOUS")
                self.assertEqual(build, dev[name].get("build", {}))
                self.assertEqual(env, dev[name].get("environment", {}))
                for key in ("image", "restart", "volumes", "healthcheck", "depends_on", "command"):
                    if key == "command" and name == "engine":
                        continue
                    self.assertEqual(service.get(key), dev[name].get(key), key)

    def test_missing_internal_token_rejects_configuration(self):
        result = resolve({"ENGINE_INTERNAL_TOKEN": None})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ENGINE_INTERNAL_TOKEN", result.stderr)

    def test_dev_compose_alone_is_only_loopback(self):
        """The dev file keeps its documented loopback-only port; the override is what removes it."""
        result = resolve(files=("docker-compose.dev.yml",))
        self.assertEqual(result.returncode, 0, result.stderr)
        for port in json.loads(result.stdout)["services"]["engine"].get("ports", []):
            self.assertEqual(port.get("host_ip"), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
