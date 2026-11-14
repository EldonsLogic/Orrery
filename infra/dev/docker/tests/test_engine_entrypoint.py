"""Exercise the engine entrypoint with a deliberately invalid local app."""

from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest


BASE_IMAGE = (
    "frappe/erpnext@sha256:"
    "6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8"
)
CONTAINER_BENCH = PurePosixPath("/", "home", "frappe", "frappe-bench")


class EngineEntrypointTests(unittest.TestCase):
    """A broken app mount must prevent the engine from starting."""

    def test_invalid_app_mount_stops_startup(self):
        """Run the actual entrypoint against an empty, isolated app directory."""
        script = Path(__file__).resolve().parents[1] / "entrypoint.sh"
        with tempfile.TemporaryDirectory(prefix="bench-invalid-app-") as empty_app:
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "--network", "none", "--read-only",
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
                    "docker", "run", "--rm", "--network", "none", "--read-only",
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
                "docker", "run", "--rm", "--network", "none", "--read-only",
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


if __name__ == "__main__":
    unittest.main()
