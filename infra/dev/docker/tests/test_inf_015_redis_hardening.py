"""INF-015 review fixes: specific refusals, password redaction, minimum length, restart-safe config.

Offline: runs the real Redis start script and the entrypoint's password guard with stubs, and drives
the runners with mocked Docker calls. Live Docker checks stay in the runners themselves.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
for path in (DOCKER_DIR, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_real_bench_ci  # noqa: E402
import smoke_headless_engine as smoke  # noqa: E402
import verify_dev_bench  # noqa: E402
from test_inf_015_redis_auth import STACKS, resolve  # noqa: E402

LIVE_SUITE = REPO_ROOT / "apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py"
GOOD = "G" * 32
SHORT = "S" * 31


def load_isolation_suite():
    spec = importlib.util.spec_from_file_location("run_isolation_suite", DOCKER_DIR / "isolation/run_isolation_suite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RedisStartScriptTests(unittest.TestCase):
    """Run each stack's real Redis start script with stubbed chown and redis entrypoint."""

    def run_script(self, stack, password, pre_existing=False):
        config = resolve(STACKS[stack], GOOD)
        script = config["services"]["redis-cache"]["command"][2].replace("$$", "$")
        tmp = Path(tempfile.mkdtemp(prefix="inf015-redis-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)], check=False)
        conf = tmp / "redis.conf"
        self.assertIn("/tmp/redis.conf", script)
        script = script.replace("/tmp/redis.conf", str(conf))
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for name, body in (("chown", "exit 0"), ("docker-entrypoint.sh", 'echo "started $*"')):
            (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            (bin_dir / name).chmod(0o755)
        if pre_existing:
            # A conf left by the previous start that this user may not overwrite in place
            # (what fs.protected_regular does to root in sticky /tmp for a redis-owned file).
            conf.write_text("requirepass old\n", encoding="utf-8")
            conf.chmod(0o400)
        env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "REDIS_PASSWORD": password}
        result = subprocess.run(["sh", "-ec", script], env=env, capture_output=True, text=True, timeout=30)
        return result, conf

    def test_short_password_stops_redis_before_writing_config(self):
        for stack in STACKS:
            with self.subTest(stack=stack):
                result, conf = self.run_script(stack, SHORT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("at least 32", result.stderr)
                self.assertNotIn(SHORT, result.stdout + result.stderr)
                self.assertFalse(conf.exists())

    def test_restart_replaces_a_config_it_cannot_overwrite(self):
        for stack in STACKS:
            with self.subTest(stack=stack):
                result, conf = self.run_script(stack, GOOD, pre_existing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"started redis-server {conf}", result.stdout)
                self.assertEqual(conf.read_text(encoding="utf-8"), f"requirepass {GOOD}\nprotected-mode yes\n")
                self.assertEqual(stat.S_IMODE(conf.stat().st_mode), 0o600)
                self.assertNotIn(GOOD, result.stdout + result.stderr)


class EntrypointMinimumLengthTests(unittest.TestCase):
    def test_entrypoint_refuses_a_short_password_before_any_setup(self):
        with tempfile.TemporaryDirectory(prefix="inf015-home-") as home:
            env = {"PATH": os.environ["PATH"], "HOME": home, "REDIS_PASSWORD": SHORT}
            result = subprocess.run(["bash", str(DOCKER_DIR / "entrypoint.sh"), "true"], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("at least 32", result.stderr)
            self.assertNotIn(SHORT, result.stdout + result.stderr)
            self.assertEqual(list(Path(home).iterdir()), [], "setup ran before the password check")


class VerifierSpecificRefusalTests(unittest.TestCase):
    """An anonymous PING must be refused with NOAUTH; any other outcome fails the check."""

    def check(self, anonymous):
        def fake_compose(project, *args):
            if "REDISCLI_AUTH" in " ".join(args):
                return subprocess.CompletedProcess([], 0, stdout="PONG\n", stderr="")
            return anonymous

        with mock.patch.object(verify_dev_bench, "compose", side_effect=fake_compose), redirect_stderr(io.StringIO()):
            return verify_dev_bench.redis_requires_auth("proj")

    def test_noauth_refusal_passes(self):
        self.assertTrue(self.check(subprocess.CompletedProcess([], 0, stdout="NOAUTH Authentication required.\n",
                                                               stderr="")))

    def test_other_failures_do_not_count_as_a_refusal(self):
        cases = {
            "exec error": None,
            "empty output": subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            "missing service": subprocess.CompletedProcess([], 1, stdout="", stderr="service \"redis-cache\" is not running"),
            "dns miss": subprocess.CompletedProcess([], 1, stdout="", stderr="Could not connect to Redis: Name does not resolve"),
            "other error": subprocess.CompletedProcess([], 0, stdout="ERR unknown command\n", stderr=""),
        }
        for name, anonymous in cases.items():
            with self.subTest(case=name):
                self.assertFalse(self.check(anonymous))


class LiveSuiteRedisChecksTests(unittest.TestCase):
    """Static checks on the live SEC-004 Redis tests (they need a running bench to execute)."""

    @classmethod
    def setUpClass(cls):
        cls.text = LIVE_SUITE.read_text(encoding="utf-8")

    def section(self, name):
        start = self.text.index(f"def {name}(")
        return self.text[start:self.text.index("\n    def ", start + 1)]

    def test_shared_cache_inspector_authenticates_with_the_bench_urls(self):
        body = self.section("test_shared_cache_keys_hold_no_tenant_data")
        self.assertIn("common_site_config.json", body)
        self.assertIn("redis.Redis.from_url(", body)
        self.assertNotIn("redis.Redis(host=host)", body)
        self.assertIn('("redis_cache", cache_prefixes)', body)
        self.assertIn('("redis_queue", queue_prefixes)', body)

    def test_auth_check_asserts_noauth_with_a_positive_control(self):
        body = self.section("test_redis_requires_authentication")
        self.assertNotIn("CONFIRMED LEAK", body)
        self.assertIn("from_url", body)
        self.assertIn("AuthenticationError", body)
        self.assertNotIn('assertNotIn("True"', body)
        self.assertNotIn("@unittest.expectedFailure\n    def test_redis_requires_authentication", self.text)


class RedactionTests(unittest.TestCase):
    def test_redact_hides_secret_values_and_url_credentials(self):
        env = {"REDIS_PASSWORD": GOOD, "ENGINE_INTERNAL_TOKEN": "tok-" + "t" * 40, "SITE_NAME": "keep.localhost"}
        text = (f"redis://:{GOOD}@redis-queue:6379 token tok-{'t' * 40} redis://:other-unknown@redis-cache:6379 "
                "keep.localhost")
        out = run_real_bench_ci.redact(text, env)
        self.assertNotIn(GOOD, out)
        self.assertNotIn("t" * 40, out)
        self.assertNotIn("other-unknown", out)
        self.assertIn("redis://:<REDACTED>@redis-cache:6379", out)
        self.assertIn("keep.localhost", out)

    def test_verifier_output_is_captured_and_redacted(self):
        seen = {}

        def fake_compose(project, compose_file, env, *args, **kwargs):
            return subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\nredis-cache\nredis-queue\n", stderr="")

        def fake_run(cmd, **kwargs):
            seen.update(kwargs)
            pw = kwargs["env"]["REDIS_PASSWORD"]
            return subprocess.CompletedProcess(cmd, 1, stdout=f"redis://:{pw}@redis-cache\n", stderr=f"err {pw}\n")

        out = io.StringIO()
        with (
            mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_compose),
            mock.patch.object(run_real_bench_ci, "_verify_http_ready"),
            mock.patch.object(run_real_bench_ci.subprocess, "run", side_effect=fake_run),
            redirect_stdout(out),
            redirect_stderr(out),
        ):
            self.assertEqual(run_real_bench_ci.run_real_bench_ci(engine_port=18998), 1)
        self.assertTrue(seen.get("capture_output"), "verifier output must be captured to be redacted")
        self.assertNotIn(seen["env"]["REDIS_PASSWORD"], out.getvalue())
        self.assertIn("<REDACTED>", out.getvalue())

    def test_smoke_redacts_failed_compose_output(self):
        for failing in ("up", "new-site"):
            with self.subTest(step=failing):
                out = io.StringIO()
                seen = {}

                def fake_compose(env, *args, stdin=None, timeout=900, failing=failing):
                    seen["pw"] = env["REDIS_PASSWORD"]
                    leak = f"redis://:{env['REDIS_PASSWORD']}@redis-queue:6379 {env['DB_ROOT_PASSWORD']}"
                    joined = " ".join(args)
                    if (failing == "up" and args[0] == "up") or (failing == "new-site" and "new-site" in joined):
                        return subprocess.CompletedProcess([], 1, stdout=leak, stderr=leak)
                    return subprocess.CompletedProcess([], 0, stdout="", stderr="")

                with (
                    mock.patch.object(smoke, "compose", side_effect=fake_compose),
                    mock.patch.object(sys, "argv", ["smoke"]),
                    redirect_stdout(out),
                    redirect_stderr(out),
                ):
                    self.assertEqual(smoke.main(), 2)
                self.assertNotIn(seen["pw"], out.getvalue())
                self.assertIn("<REDACTED>", out.getvalue())

    def test_isolation_provisioning_failure_is_redacted(self):
        iso = load_isolation_suite()
        env = {"REDIS_PASSWORD": GOOD, "DB_ROOT_PASSWORD": "db-" + "d" * 24}
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr=f"redis://:{GOOD}@redis-cache {env['DB_ROOT_PASSWORD']}")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(iso.subprocess, "run", return_value=failed):
            with self.assertRaises(SystemExit) as error:
                iso.provision("sec004-x", "a", iso.TENANTS["a"], Path(tmp), env)
        message = str(error.exception)
        self.assertIn("provisioning a failed", message)
        self.assertNotIn(GOOD, message)
        self.assertNotIn(env["DB_ROOT_PASSWORD"], message)


class ReuseProjectPasswordTests(unittest.TestCase):
    def run_reused(self, environ):
        envs = []

        def fake_compose(project, compose_file, env, *args, **kwargs):
            envs.append(env)
            return subprocess.CompletedProcess([], 1, stdout="", stderr="")

        with (
            mock.patch.dict(os.environ, environ),
            mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_compose),
            mock.patch.object(run_real_bench_ci, "_wait_for_engine_ready",
                              side_effect=lambda project, compose_file, env: envs.append(env) or 1 / 0),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            try:
                run_real_bench_ci.run_real_bench_ci(project="reused", reuse_project=True, engine_port=18997,
                                                    keep_stack=True)
            except ZeroDivisionError:
                pass  # the fake readiness check stops the run; only the environment matters here
        return envs

    def test_reused_project_keeps_the_running_stack_password(self):
        envs = self.run_reused({"ENGINE_INTERNAL_TOKEN": "t" * 48, "REDIS_PASSWORD": GOOD})
        self.assertTrue(envs)
        self.assertTrue(all(env["REDIS_PASSWORD"] == GOOD for env in envs))

    def test_reused_project_without_a_password_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "REDIS_PASSWORD"):
            self.run_reused({"ENGINE_INTERNAL_TOKEN": "t" * 48, "REDIS_PASSWORD": ""})


class CrossNetworkProbeTests(unittest.TestCase):
    """The smoke sidecar classifies reachability; the smoke run fails unless Redis is unreachable."""

    def setUp(self):
        self.ns = {}
        exec(smoke.REACH_PROBE, self.ns)  # noqa: S102 - the probe source is a constant in this repo

    def test_probe_reports_dns_miss_refusal_and_connection(self):
        self.assertEqual(self.ns["reach"]("inf015-no-such-host.invalid", 6379), "dns")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.assertEqual(self.ns["reach"]("127.0.0.1", port), "refused")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            self.assertEqual(self.ns["reach"]("127.0.0.1", listener.getsockname()[1]), "connected")

    def test_sidecar_probes_both_redis_services_and_the_engine(self):
        self.assertIn(smoke.REACH_PROBE, smoke.SIDECAR)
        for target in ('"redis-cache"', '"redis-queue"', '"engine", 8000'):
            self.assertIn(target, smoke.SIDECAR)

    def test_cross_network_checks(self):
        cases = {
            "isolated": ({"redis-cache": "dns", "redis-queue": "refused"}, "connected", "True", True),
            "redis reachable": ({"redis-cache": "connected", "redis-queue": "dns"}, "connected", "True", False),
            "probe timed out": ({"redis-cache": "timeout", "redis-queue": "dns"}, "connected", "True", False),
            "probe broken": ({"redis-cache": "dns", "redis-queue": "dns"}, "dns", "True", False),
            "engine cannot reach redis": ({"redis-cache": "dns", "redis-queue": "dns"}, "connected", "False", False),
        }
        for name, (redis_reach, engine_reach, engine_ping, expected) in cases.items():
            with self.subTest(case=name):
                checks = smoke.cross_network_checks({"redis": redis_reach, "engine": engine_reach}, engine_ping)
                self.assertEqual(all(ok for _, ok in checks), expected, checks)
                self.assertGreaterEqual(len(checks), 3)


if __name__ == "__main__":
    unittest.main()
