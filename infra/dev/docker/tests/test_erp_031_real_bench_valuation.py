"""ERP-031 offline tests: the ERP-014 and ERP-015 live layers run in real-bench CI and cannot skip there.

No bench is needed. They prove that the runner gives each live layer its own fresh site with a
``tenant_id``, sets the REQUIRE flags, and fails when a live layer reports a skip; that a REQUIRE flag
turns the live layers' skip into a failure while local runs without it still skip; and that the workflow
leaves enough time for the live layers. What the live layers prove about the engine is checked by the
real bench in CI, not here.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
ENGINE_ROOT = REPO_ROOT / "apps" / "engine" / "change_engine"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "real-bench.yml"
LIVE_CLASSES = {
    "ERP014": "change_engine.tests.test_erp_014_accounting_properties.TestLiveEngineProperties",
    "ERP015": "change_engine.tests.test_erp_015_inventory_valuation.TestLiveInventoryValuation",
}
BENCH_VARS = {"ERP014": ("ERP014_COMPOSE_PROJECT", "ERP014_SITE"), "ERP015": ("ERP015_COMPOSE_PROJECT", "ERP015_BENCH_SITE")}

for path in (str(DOCKER_DIR), str(ENGINE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import run_real_bench_ci  # noqa: E402
from change_engine.tests import test_erp_014_accounting_properties as erp014  # noqa: E402


def _live_run(layer: str, **extra: str) -> subprocess.CompletedProcess:
    """Run one live class of the real suites with no bench configured, as a developer or the runner would."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ERP014_", "ERP015_", "REQUIRE_ERP01"))}
    env.update(extra, PYTHONPATH=str(ENGINE_ROOT))
    return subprocess.run([sys.executable, "-m", "unittest", LIVE_CLASSES[layer]], cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True, timeout=120, check=False)


class TestRequireFlagTurnsSkipIntoFailure(unittest.TestCase):
    def test_without_the_flag_and_without_a_bench_the_live_layer_still_skips(self) -> None:
        for layer in LIVE_CLASSES:
            with self.subTest(layer):
                res = _live_run(layer)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertTrue(run_real_bench_ci.unittest_reported_skips(res.stderr), res.stderr)

    def test_with_the_flag_and_without_a_bench_the_live_layer_fails_and_does_not_skip(self) -> None:
        for layer in LIVE_CLASSES:
            with self.subTest(layer):
                res = _live_run(layer, **{f"REQUIRE_{layer}_LIVE": "1"})
                self.assertNotEqual(res.returncode, 0, res.stderr)
                self.assertFalse(run_real_bench_ci.unittest_reported_skips(res.stderr), res.stderr)
                self.assertIn(f"REQUIRE_{layer}_LIVE=1", res.stderr)

    def test_gate_helpers_decide_per_variable_set(self) -> None:
        project, site = BENCH_VARS["ERP014"]
        gate = lambda env: (erp014.live_skip_reason(env, project, site, "REQUIRE_ERP014_LIVE"),  # noqa: E731
                            erp014.live_config_problem(env, project, site, "REQUIRE_ERP014_LIVE"))
        self.assertIsNone(gate({})[1])
        self.assertTrue(gate({})[0], "no bench, no flag: skip")
        self.assertEqual(gate({"REQUIRE_ERP014_LIVE": "1"})[0], None, "the flag stops the skip")
        self.assertIn("REQUIRE_ERP014_LIVE=1", gate({"REQUIRE_ERP014_LIVE": "1"})[1])
        self.assertEqual(gate({project: "p", site: "s", "REQUIRE_ERP014_LIVE": "1"}), (None, None))
        self.assertEqual(gate({project: "p", site: "s"}), (None, None))
        self.assertIn("both", gate({project: "p"})[1], "one variable alone is a configuration error")
        self.assertTrue(gate({"REQUIRE_ERP014_LIVE": "0"})[0], "only 1 turns the flag on")


RAN_OK = "Ran 99 tests in 1.0s\n\nOK\n"


class TestRunnerRunsTheValuationLayers(unittest.TestCase):
    def _run(self, unittest_output: str = RAN_OK, unittest_rc: int = 0, reuse: bool = False, drop_rcs=None,
             outputs_by_layer=None):
        """Run the runner with docker and the children faked. ``drop_rcs`` are the exit codes of successive
        site drops; ``outputs_by_layer`` maps ERP014/ERP015 to that layer's unittest output."""
        compose_calls, unittest_calls, other_calls = [], [], []
        drop_rcs = iter(drop_rcs or ())
        self.compose_calls, self.verifier_calls = compose_calls, other_calls  # visible even when the run raises

        def fake_compose(project, compose_file, env, *args, **kwargs):
            compose_calls.append(args)
            if args[:2] == ("ps", "--status"):
                return subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\nredis-cache\nredis-queue\n", stderr="")
            if "ce_sec_005_drop" in args:
                return subprocess.CompletedProcess([], next(drop_rcs, 0), stdout="", stderr="")
            return subprocess.CompletedProcess([], 0, stdout="ok", stderr="")

        def fake_subprocess(cmd, **kwargs):
            if "unittest" in cmd:
                unittest_calls.append((tuple(cmd), kwargs))
                layer = "ERP014" if "test_erp_014_accounting_properties" in " ".join(cmd) else "ERP015"
                out = (outputs_by_layer or {}).get(layer, unittest_output)
                return subprocess.CompletedProcess(cmd, unittest_rc, stdout=out, stderr="")
            other_calls.append((tuple(cmd), kwargs))
            return subprocess.CompletedProcess(cmd, 0, stdout="Verified", stderr="")

        env = {"ENGINE_INTERNAL_TOKEN": "reused-token-0123456789abcdef", "REDIS_PASSWORD": "reused-redis-0123456789"}
        with mock.patch.dict(os.environ, env if reuse else {}), \
             mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_compose), \
             mock.patch.object(run_real_bench_ci, "_verify_http_ready"), \
             mock.patch.object(run_real_bench_ci.subprocess, "run", side_effect=fake_subprocess):
            rc = run_real_bench_ci.run_real_bench_ci(project="ce-sec-005-unit", engine_port=18999, reuse_project=reuse)
        return rc, compose_calls, unittest_calls

    @staticmethod
    def _provisioned(compose_calls):
        """[(site, tenant_id)] of every `bench new-site` the runner ran, in order."""
        return [(args[-3], args[-1]) for args in compose_calls if "sh" in args and "set-config tenant_id" in " ".join(args)]

    def test_each_live_layer_gets_its_own_fresh_site_with_a_tenant_id(self) -> None:
        rc, compose_calls, unittest_calls = self._run()
        self.assertEqual(rc, 0)
        provisioned = self._provisioned(compose_calls)
        self.assertEqual(len(provisioned), 3, provisioned)
        self.assertEqual(len({site for site, _ in provisioned}), 3, "no site is shared: the probes need a fresh one")
        for site, tenant_id in provisioned:
            self.assertRegex(tenant_id, r"^t_[A-Za-z0-9_]+$", site)
        self.assertEqual({s.split("-")[0] for s, _ in provisioned}, {"ce005", "erp014", "erp015"})
        self.assertEqual(len(unittest_calls), 2)

    def test_the_live_layers_run_with_site_project_and_require_flags(self) -> None:
        rc, compose_calls, unittest_calls = self._run()
        self.assertEqual(rc, 0)
        sites = {s.split("-")[0]: s for s, _ in self._provisioned(compose_calls)}
        by_layer = {}
        for cmd, kwargs in unittest_calls:
            layer = "ERP014" if "test_erp_014_accounting_properties" in " ".join(cmd) else "ERP015"
            by_layer[layer] = kwargs["env"]
            self.assertEqual(kwargs["env"]["PYTHONPATH"], str(ENGINE_ROOT))
            self.assertEqual(kwargs["cwd"], str(REPO_ROOT))
        self.assertEqual(set(by_layer), {"ERP014", "ERP015"})
        for layer, env in by_layer.items():
            project_var, site_var = BENCH_VARS[layer]
            self.assertEqual(env[project_var], "ce-sec-005-unit")
            self.assertEqual(env[site_var], sites[layer.lower()])
            self.assertEqual(env[f"REQUIRE_{layer}_LIVE"], "1")

    def test_a_live_layer_that_skips_fails_the_run_even_with_exit_code_zero(self) -> None:
        rc, _, _ = self._run(unittest_output="Ran 12 tests in 1s\n\nOK (skipped=3)\n")
        self.assertNotEqual(rc, 0)

    def test_a_live_layer_that_ran_no_tests_fails_the_run(self) -> None:
        for layer in LIVE_CLASSES:
            with self.subTest(layer):
                rc, _, _ = self._run(outputs_by_layer={layer: "Ran 0 tests in 0.000s\n\nNO TESTS RAN\n"})
                self.assertNotEqual(rc, 0)
        rc, _, _ = self._run(unittest_output="OK\n")
        self.assertNotEqual(rc, 0, "no `Ran N tests` line proves nothing")

    def test_a_live_layer_that_ran_too_few_tests_fails_the_run(self) -> None:
        """Live discovery removed: only a few pure-looking tests ran, exit status 0, no skip."""
        for layer, minimum in ((p.upper(), n) for p, _, _, _, _, n in run_real_bench_ci.VALUATION_LAYERS):
            with self.subTest(layer):
                rc, _, _ = self._run(outputs_by_layer={layer: f"Ran {minimum - 1} tests in 1s\n\nOK\n"})
                self.assertNotEqual(rc, 0)
                rc, _, _ = self._run(outputs_by_layer={layer: f"Ran {minimum} tests in 1s\n\nOK\n"})
                self.assertEqual(rc, 0, "the expected count passes")

    def test_the_runner_selects_the_live_classes_and_their_minimum_counts_match_the_real_ones(self) -> None:
        _, _, unittest_calls = self._run()
        selected = {name for cmd, _ in unittest_calls for name in cmd if name.startswith("change_engine.tests.")}
        self.assertEqual(selected, set(LIVE_CLASSES.values()), "the live classes, not whole modules")
        for prefix, live_class, *_rest, minimum in run_real_bench_ci.VALUATION_LAYERS:
            module, _, cls = live_class.rpartition(".")
            real = unittest.defaultTestLoader.loadTestsFromTestCase(getattr(importlib.import_module(module), cls))
            self.assertLessEqual(minimum, real.countTestCases(), prefix)
            self.assertGreaterEqual(minimum, real.countTestCases(), f"{prefix}: raise the minimum with a new live test")

    def test_the_run_counter(self) -> None:
        ran = run_real_bench_ci.unittest_tests_run
        self.assertEqual(ran("Ran 18 tests in 1.1s\n\nOK\n"), 18)
        self.assertEqual(ran("Ran 1 test in 0.1s\n\nOK\n"), 1)
        self.assertEqual(ran("Ran 0 tests in 0.0s\n\nNO TESTS RAN\n"), 0)
        self.assertEqual(ran("OK\n"), 0)
        self.assertEqual(ran("noise Ran 50 tests in a log line\n"), 0, "only unittest's own summary line counts")

    def test_a_failing_live_layer_fails_the_run_and_both_layers_still_run(self) -> None:
        rc, _, unittest_calls = self._run(unittest_rc=1, unittest_output="FAILED (failures=1)\n")
        self.assertEqual(rc, 1)
        self.assertEqual(len(unittest_calls), 2, "one layer failing does not hide the other")

    def test_reused_project_drops_every_site_it_provisioned(self) -> None:
        rc, compose_calls, _ = self._run(reuse=True)
        self.assertEqual(rc, 0)
        dropped = [args[-1] for args in compose_calls if "ce_sec_005_drop" in args]
        self.assertEqual(sorted(dropped), sorted(s for s, _ in self._provisioned(compose_calls)))

    def test_reused_project_attempts_every_drop_when_the_first_fails(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            self._run(reuse=True, drop_rcs=[1, 0, 0])
        provisioned = [s for s, _ in self._provisioned(self.compose_calls)]
        dropped = [args[-1] for args in self.compose_calls if "ce_sec_005_drop" in args]
        self.assertEqual(len(provisioned), 3)
        self.assertEqual(dropped, provisioned, "every site is dropped even though the first drop failed")
        self.assertIn(provisioned[0], str(caught.exception))

    def test_reused_project_reports_every_failed_drop(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            self._run(reuse=True, drop_rcs=[1, 0, 2])
        sites = [s for s, _ in self._provisioned(self.compose_calls)]
        self.assertIn(sites[0], str(caught.exception))
        self.assertIn(sites[2], str(caught.exception))
        self.assertNotIn(sites[1], str(caught.exception))

    def test_the_verifier_gets_its_declared_time_limit(self) -> None:
        self._run()
        (_, kwargs), = self.verifier_calls
        self.assertEqual(kwargs["timeout"], run_real_bench_ci.VERIFIER_TIMEOUT)

    def test_skip_detector(self) -> None:
        skipped = run_real_bench_ci.unittest_reported_skips
        self.assertTrue(skipped("OK (skipped=10)"))
        self.assertTrue(skipped("test_x (m.C.test_x) ... skipped 'No bench configured'"))
        self.assertFalse(skipped("Ran 18 tests in 1.1s\n\nOK\n"))
        self.assertFalse(skipped(""))


class TestWorkflowLeavesTimeForTheLiveLayers(unittest.TestCase):
    HEADROOM_SECONDS = 300  # Actions setup (checkout, Python) and the runner's own cleanup, outside the phase limits

    def _job_seconds(self) -> int:
        return int(re.search(r"timeout-minutes:\s*(\d+)", WORKFLOW.read_text(encoding="utf-8")).group(1)) * 60

    def test_every_sequential_phase_is_in_the_budget(self) -> None:
        names = [name for name, _ in run_real_bench_ci.PHASES]
        for needed in ("startup", "engine readiness", "http readiness", "verifier", "ce-sec-005 tests", "teardown"):
            self.assertIn(needed, names)
        self.assertEqual(sum(n.startswith("provision") for n in names), 1 + len(run_real_bench_ci.VALUATION_LAYERS))
        self.assertEqual(sum(n.startswith("live layer") for n in names), len(run_real_bench_ci.VALUATION_LAYERS))
        self.assertEqual(run_real_bench_ci.TOTAL_PHASE_LIMIT_SECONDS, sum(s for _, s in run_real_bench_ci.PHASES))

    def test_declared_limits_are_the_ones_the_code_uses(self) -> None:
        import inspect
        limits = dict(run_real_bench_ci.PHASES)
        defaults = lambda fn, arg: inspect.signature(fn).parameters[arg].default  # noqa: E731
        self.assertEqual(defaults(run_real_bench_ci._wait_for_engine_ready, "timeout_seconds"), limits["engine readiness"])
        self.assertEqual(defaults(run_real_bench_ci._verify_http_ready, "timeout_seconds"), limits["http readiness"])
        self.assertEqual(run_real_bench_ci.VALUATION_TEST_TIMEOUT * len(run_real_bench_ci.VALUATION_LAYERS),
                         sum(s for n, s in run_real_bench_ci.PHASES if n.startswith("live layer")))

    def test_job_limit_covers_all_phases_plus_setup_and_cleanup_headroom(self) -> None:
        job = self._job_seconds()
        total = run_real_bench_ci.TOTAL_PHASE_LIMIT_SECONDS
        self.assertGreaterEqual(job - total, self.HEADROOM_SECONDS, f"job {job}s, phases {total}s")
        self.assertLessEqual(job, 90 * 60, "keep the job at or under 90 minutes")
        self.assertIn("python3 infra/dev/docker/run_real_bench_ci.py", WORKFLOW.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
