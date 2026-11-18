"""Offline contract and fail-closed tests for CE-SEC-005 real-bench CI."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
ENGINE_TEST_FILE = (
    REPO_ROOT
    / "apps"
    / "engine"
    / "change_engine"
    / "change_engine"
    / "tests"
    / "test_ce_sec_005_real_bench.py"
)
REAL_BENCH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "real-bench.yml"

if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import run_real_bench_ci  # noqa: E402


class TestCeSec005RealBenchCI(unittest.TestCase):
    def test_integration_suite_has_zero_mocks(self) -> None:
        src = ENGINE_TEST_FILE.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(ENGINE_TEST_FILE))
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
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "change_engine.tests.test_ce_sec_005_real_bench",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertNotEqual(res.returncode, 0, "CE_SEC_005_REAL_BENCH=1 must fail closed without Frappe.")
        self.assertNotIn("OK (skipped=", res.stdout + res.stderr)

    def test_offline_run_skips_cleanly_without_real_bench_flag(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CE_SEC_005_REAL_BENCH", "CE_SEC_005_SITE")
        }
        env["PYTHONPATH"] = str(REPO_ROOT / "apps" / "engine" / "change_engine")
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "change_engine.tests.test_ce_sec_005_real_bench",
            ],
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
        self.assertTrue(any("change_engine.tests.test_ce_sec_005_real_bench" in args for args in compose_ops))
        self.assertIn(("down", "-v", "--remove-orphans"), compose_ops)
        self.assertTrue(any(kind == "verify" for kind, _ in calls))

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
