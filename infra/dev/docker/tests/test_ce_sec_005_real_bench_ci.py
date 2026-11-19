"""Offline contract and fail-closed tests for CE-SEC-005 real-bench CI."""
from __future__ import annotations

import ast
import io
from contextlib import redirect_stderr
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
ENGINE_TEST_DIR = (
    REPO_ROOT
    / "apps"
    / "engine"
    / "change_engine"
    / "change_engine"
    / "tests"
)
ENGINE_TEST_FILES = (
    ENGINE_TEST_DIR / "test_ce_sec_005_real_bench.py",
    ENGINE_TEST_DIR / "test_ce_sec_005_live_http.py",
)
REAL_BENCH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "real-bench.yml"

if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import run_real_bench_ci  # noqa: E402


class TestCeSec005RealBenchCI(unittest.TestCase):
    def test_failure_diagnostics_redact_credentials(self) -> None:
        env = {"DB_ROOT_PASSWORD": "private-root-marker", "ADMIN_PASSWORD": "private-admin-marker"}
        result = subprocess.CompletedProcess([], 0, stdout="failure private-root-marker private-admin-marker", stderr="")
        out = io.StringIO()
        with mock.patch.object(run_real_bench_ci, "_run_compose", return_value=result), redirect_stderr(out):
            run_real_bench_ci._failure_diagnostics("ce005", Path("compose.yml"), env)
        self.assertIn("failure", out.getvalue())
        for value in env.values():
            self.assertNotIn(value, out.getvalue())

    def test_integration_suite_has_zero_mocks(self) -> None:
        for test_file in ENGINE_TEST_FILES:
            with self.subTest(suite=test_file.stem):
                src = test_file.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(test_file))
                imported_modules: set[str] = set()
                used_names: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imported_modules.add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imported_modules.add(node.module)
                        for alias in node.names:
                            imported_modules.add(f"{node.module or ''}.{alias.name}")
                    elif isinstance(node, ast.Name):
                        used_names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        used_names.add(node.attr)

                self.assertFalse(any("mock" in mod.lower() for mod in imported_modules), imported_modules)
                self.assertNotIn("SimulatedFrappeRuntime", used_names)
                self.assertNotIn("MagicMock", used_names)

    def test_require_real_bench_fails_closed_without_frappe(self) -> None:
        env = {
            **os.environ,
            "CE_SEC_005_REAL_BENCH": "1",
            "PYTHONPATH": str(REPO_ROOT / "apps" / "engine" / "change_engine"),
        }
        for test_file in ENGINE_TEST_FILES:
            with self.subTest(suite=test_file.stem):
                res = subprocess.run(
                    [sys.executable, "-m", "unittest", f"change_engine.tests.{test_file.stem}"],
                    cwd=str(REPO_ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertNotEqual(res.returncode, 0, "CE_SEC_005_REAL_BENCH=1 must fail closed without Frappe.")
                self.assertIn("CE_SEC_005_REAL_BENCH=1 requires real Frappe runtime", res.stderr)

    def test_offline_run_skips_cleanly_without_real_bench_flag(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CE_SEC_005_REAL_BENCH", "CE_SEC_005_SITE")
        }
        env["PYTHONPATH"] = str(REPO_ROOT / "apps" / "engine" / "change_engine")
        for test_file in ENGINE_TEST_FILES:
            with self.subTest(suite=test_file.stem):
                res = subprocess.run(
                    [sys.executable, "-m", "unittest", f"change_engine.tests.{test_file.stem}"],
                    cwd=str(REPO_ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
                self.assertIn("skipped=", res.stdout + res.stderr)

    def test_orchestrator_rejects_unsafe_project_and_site_names(self) -> None:
        with self.assertRaises(ValueError):
            run_real_bench_ci.run_real_bench_ci(project="Bad Project!")
        with self.assertRaises(ValueError):
            run_real_bench_ci.run_real_bench_ci(project="valid-proj", site_name="tenant.example.com")

    def test_orchestrator_invokes_build_verify_test_and_teardown(self) -> None:
        calls: list[tuple[str, tuple]] = []

        def fake_run_compose(project, compose_file, env, *args, **kwargs):
            calls.append(("compose", args))
            if args[:2] == ("ps", "--status"):
                return subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\nredis-cache\nredis-queue\n", stderr="")
            return subprocess.CompletedProcess([], 0, stdout="ok", stderr="")

        def fake_verify_run(cmd, **kwargs):
            calls.append(("verify", tuple(cmd)))
            return subprocess.CompletedProcess(cmd, 0, stdout="Verified", stderr="")

        with mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_run_compose), \
             mock.patch.object(run_real_bench_ci, "_verify_http_ready"), \
             mock.patch.object(run_real_bench_ci.subprocess, "run", side_effect=fake_verify_run):
            rc = run_real_bench_ci.run_real_bench_ci(project="ce-sec-005-unit", engine_port=18999)

        self.assertEqual(rc, 0)
        compose_ops = [args for kind, args in calls if kind == "compose"]
        self.assertIn(("up", "-d", "--build"), compose_ops)
        modules = ("change_engine.tests.test_ce_sec_005_real_bench", "change_engine.tests.test_ce_sec_005_live_http")
        self.assertTrue(any(all(module in args for module in modules) for args in compose_ops))
        self.assertIn(("down", "-v", "--remove-orphans"), compose_ops)
        self.assertTrue(any(kind == "verify" for kind, _ in calls))

    def test_provision_failure_keeps_synthetic_credentials_private(self) -> None:
        """Compose must inherit credentials by name, and failures must omit child output."""
        env = {"DB_ROOT_PASSWORD": "db-marker-005", "ADMIN_PASSWORD": "admin-marker-005"}
        failed = subprocess.CompletedProcess([], 1, stdout=env["ADMIN_PASSWORD"], stderr=env["DB_ROOT_PASSWORD"])
        with mock.patch.object(run_real_bench_ci, "_run_compose", return_value=failed) as compose:
            with self.assertRaises(RuntimeError) as error:
                run_real_bench_ci._provision_site("ce005", Path("compose.yml"), env, "ce005.localhost")
        for secret in env.values():
            self.assertNotIn(secret, str(error.exception))
            self.assertFalse(any(secret in str(arg) for arg in compose.call_args.args[3:]))

    def test_drop_failure_is_reported(self) -> None:
        """A reused stack must expose site cleanup failures."""
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with mock.patch.object(run_real_bench_ci, "_run_compose", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "dropping"):
                run_real_bench_ci._drop_site("ce005", Path("compose.yml"), {"DB_ROOT_PASSWORD": "marker"}, "ce005.localhost")

    def test_workflow_follows_gov_049_and_runs_real_bench_ci(self) -> None:
        self.assertTrue(REAL_BENCH_WORKFLOW.is_file(), "Missing .github/workflows/real-bench.yml")
        text = REAL_BENCH_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("apps/engine/**", text)
        self.assertIn("infra/dev/docker/**", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertIn("contents: read", text)
        self.assertIn("python3 infra/dev/docker/run_real_bench_ci.py", text)


if __name__ == "__main__":
    unittest.main()
