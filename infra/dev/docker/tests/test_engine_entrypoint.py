"""Exercise the engine entrypoint with a deliberately invalid local app."""

import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest


BASE_IMAGE = (
    "frappe/erpnext@sha256:"
    "6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8"
)
CONTAINER_BENCH = PurePosixPath("/", "home", "frappe", "frappe-bench")
# INF-015: the entrypoint refuses to start without a URL-safe Redis password.
REDIS_ENV = ["-e", "REDIS_PASSWORD=" + "p" * 32]


class EngineEntrypointTests(unittest.TestCase):
    """A broken app mount must prevent the engine from starting."""

    def test_invalid_app_mount_stops_startup(self):
        """Run the actual entrypoint against an empty, isolated app directory."""
        script = Path(__file__).resolve().parents[1] / "entrypoint.sh"
        with tempfile.TemporaryDirectory(prefix="bench-invalid-app-") as empty_app:
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "--network", "none", "--read-only", *REDIS_ENV,
                    "--tmpfs", "/tmp:rw,mode=1777",
                    "--tmpfs", f"{CONTAINER_BENCH / 'sites'}:rw,mode=1777",
                    "--mount", f"type=bind,src={empty_app},dst={CONTAINER_BENCH / 'apps' / 'change_engine'},readonly",
                    "--mount", f"type=bind,src={script},dst=/tmp/bench-entrypoint.sh,readonly",
                    "--entrypoint", "/bin/bash", BASE_IMAGE,
                    "/tmp/bench-entrypoint.sh", "true",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0, "invalid app mount was accepted")
        self.assertIn(
            "Cannot install change_engine app", result.stdout + result.stderr,
            "startup failed for a reason other than the invalid app",
        )

    def test_register_app_after_unterminated_last_line(self):
        """Preserve every app name when the base list lacks a final newline."""
        script = Path(__file__).resolve().parents[1] / "entrypoint.sh"
        with tempfile.TemporaryDirectory(prefix="bench-app-list-") as temporary_dir:
            sites = Path(temporary_dir) / "sites"
            sites.mkdir()
            # The container user needs access inside the private temporary directory.
            sites.chmod(0o777)
            apps = sites / "apps.txt"
            apps.write_bytes(b"frappe\nerpnext")
            apps.chmod(0o666)
            subprocess.run(
                [
                    "docker", "run", "--rm", "--network", "none", "--read-only", *REDIS_ENV,
                    "--tmpfs", str(CONTAINER_BENCH / "apps" / "hrms"),
                    "--mount", f"type=bind,src={sites},dst={CONTAINER_BENCH / 'sites'}",
                    "--mount", f"type=bind,src={script},dst=/tmp/bench-entrypoint.sh,readonly",
                    "--entrypoint", "/bin/bash", BASE_IMAGE,
                    "/tmp/bench-entrypoint.sh", "true",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            self.assertEqual(apps.read_text().splitlines(), ["frappe", "erpnext", "hrms"])

    def test_links_built_assets_into_sites(self):
        """The engine reads compiled translations and assets from sites/assets."""
        script = Path(__file__).resolve().parents[1] / "entrypoint.sh"
        result = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none", "--read-only", *REDIS_ENV,
                "--tmpfs", "/tmp:rw,mode=1777",
                "--tmpfs", f"{CONTAINER_BENCH / 'sites'}:rw,mode=1777",
                "--tmpfs", str(CONTAINER_BENCH / "apps" / "hrms"),
                "--mount", f"type=bind,src={script},dst=/tmp/bench-entrypoint.sh,readonly",
                "--entrypoint", "/bin/bash", BASE_IMAGE,
                "/tmp/bench-entrypoint.sh", "readlink", str(CONTAINER_BENCH / "sites" / "assets"),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        self.assertEqual(result.stdout.strip().splitlines()[-1], str(CONTAINER_BENCH / "assets"))

    def run_entrypoint(self, redis_env, *command):
        script = Path(__file__).resolve().parents[1] / "entrypoint.sh"
        return subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none", "--read-only", *redis_env,
                "--tmpfs", "/tmp:rw,mode=1777",
                "--tmpfs", f"{CONTAINER_BENCH / 'sites'}:rw,mode=1777",
                "--tmpfs", str(CONTAINER_BENCH / "apps" / "hrms"),
                "--mount", f"type=bind,src={script},dst=/tmp/bench-entrypoint.sh,readonly",
                "--entrypoint", "/bin/bash", BASE_IMAGE,
                "/tmp/bench-entrypoint.sh", *command,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_missing_or_unsafe_redis_password_stops_startup(self):
        """INF-015: no Redis password (or one that would break the URL) means no engine."""
        for redis_env in ([], ["-e", "REDIS_PASSWORD="], ["-e", "REDIS_PASSWORD=bad@pass/word"]):
            with self.subTest(env=redis_env[1:]):
                result = self.run_entrypoint(redis_env, "true")
                self.assertNotEqual(result.returncode, 0, "entrypoint started without a usable password")
                self.assertIn("REDIS_PASSWORD", result.stderr)
                self.assertNotIn("bad@pass/word", result.stdout + result.stderr)

    def test_bench_redis_urls_carry_the_password_owner_only(self):
        """INF-015: the bench config authenticates to both Redis services and is not world-readable."""
        password = "inf015" + "Q" * 26
        result = self.run_entrypoint(
            ["-e", f"REDIS_PASSWORD={password}"], "sh", "-c",
            f"stat -c %a {CONTAINER_BENCH / 'sites' / 'common_site_config.json'} && "
            f"cat {CONTAINER_BENCH / 'sites' / 'common_site_config.json'}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(password, result.stderr, "the entrypoint logged the password")
        before_config = result.stdout[: result.stdout.index("{")]
        self.assertEqual(before_config.strip().splitlines()[-1], "600")
        config = json.loads(result.stdout[result.stdout.index("{"):])
        self.assertEqual(config["redis_cache"], f"redis://:{password}@redis-cache:6379")
        self.assertEqual(config["redis_queue"], f"redis://:{password}@redis-queue:6379")
        self.assertEqual(config["redis_socketio"], f"redis://:{password}@redis-queue:6379")


if __name__ == "__main__":
    unittest.main()
