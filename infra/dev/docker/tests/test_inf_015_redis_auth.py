"""INF-015: Redis requires a per-run password and only engine services can reach it.

Resolves every Compose stack with `docker compose config` (no daemon or containers needed)
and checks the runners mint a fresh password that never reaches argv or output.
"""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

DOCKER_DIR = Path(__file__).resolve().parents[1]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import run_real_bench_ci  # noqa: E402

STACKS = {
    "dev": ("docker-compose.dev.yml",),
    "headless": ("docker-compose.headless.yml",),
    "isolation": ("docker-compose.dev.yml", "isolation/docker-compose.isolation.yml"),
    "bpl027": ("docker-compose.dev.yml", "docker-compose.bpl027-test.yml"),
}
REDIS_SERVICES = {"redis-cache", "redis-queue"}
# Services that run engine code and must talk to Redis (socketio and scheduler included for later stacks).
ENGINE_SERVICES = {"engine", "worker", "scheduler", "socketio"}
REDIS_NETWORK = "redis_internal"
SENTINELS = ("inf015-sentinel-one-" + "a" * 12, "inf015-sentinel-two-" + "b" * 12)


def resolve(files, redis_password):
    env = os.environ.copy()
    env.update(
        DB_ROOT_PASSWORD="synthetic-placeholder",
        ADMIN_PASSWORD="synthetic-placeholder",
        SITE_NAME="synthetic.localhost",
        ENGINE_PORT="18000",
        ENGINE_INTERNAL_TOKEN="t" * 48,
    )
    env.pop("REDIS_PASSWORD", None)
    if redis_password is not None:
        env["REDIS_PASSWORD"] = redis_password
    cmd = ["docker", "compose", "--project-name", "inf015contract", "--env-file", os.devnull]
    for name in files:
        cmd += ["-f", str(DOCKER_DIR / name)]
    result = subprocess.run(cmd + ["config", "--format", "json"], env=env, capture_output=True,
                            text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class RedisComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configs = {name: resolve(files, SENTINELS[0]) for name, files in STACKS.items()}

    def redis_services(self, config):
        found = {n: s for n, s in config["services"].items() if s.get("image", "").startswith("redis:")}
        self.assertEqual(set(found), REDIS_SERVICES)
        return found

    def test_redis_requires_a_password_from_the_environment(self):
        for stack, config in self.configs.items():
            for name, service in self.redis_services(config).items():
                with self.subTest(stack=stack, service=name):
                    self.assertEqual(service["environment"]["REDIS_PASSWORD"], SENTINELS[0])
                    # Compose keeps the $$ escape in resolved output; the container shell sees one $.
                    script = " ".join(service["command"]).replace("$$", "$")
                    self.assertIn("requirepass", script)
                    self.assertIn('"$REDIS_PASSWORD"', script)
                    self.assertIn("protected-mode yes", script)
                    # Fails closed on an empty or config-injecting password.
                    self.assertIn('test -n "$REDIS_PASSWORD"', script)
                    self.assertIn("*[!A-Za-z0-9_-]*", script)
                    self.assertNotIn(SENTINELS[0], script, "password must not be on the command line")

    def test_password_is_never_a_committed_literal(self):
        for stack, files in STACKS.items():
            config = resolve(files, None)
            for name, service in config["services"].items():
                with self.subTest(stack=stack, service=name):
                    self.assertIn(service.get("environment", {}).get("REDIS_PASSWORD", ""), ("", None))
        for path in DOCKER_DIR.glob("**/*.yml"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                for line in re.findall(r"REDIS_PASSWORD\s*[:=].*", text):
                    self.assertRegex(line, r"REDIS_PASSWORD\s*[:=]\s*\$\{REDIS_PASSWORD:-\}\s*$")
                self.assertNotRegex(text, r"requirepass\s+[^%\s]")

    def test_healthcheck_does_not_embed_the_password(self):
        for stack, config in self.configs.items():
            for name, service in self.redis_services(config).items():
                with self.subTest(stack=stack, service=name):
                    test = json.dumps(service["healthcheck"]["test"])
                    self.assertIn("REDISCLI_AUTH", test)
                    self.assertNotIn(SENTINELS[0], test)

    def test_redis_publishes_no_host_port(self):
        for stack, config in self.configs.items():
            for name, service in self.redis_services(config).items():
                with self.subTest(stack=stack, service=name):
                    self.assertFalse(service.get("ports"))
                    self.assertFalse(service.get("expose"))
                    self.assertNotEqual(service.get("network_mode"), "host")

    def test_redis_is_only_on_the_internal_redis_network(self):
        for stack, config in self.configs.items():
            with self.subTest(stack=stack, network=REDIS_NETWORK):
                self.assertIs(config["networks"][REDIS_NETWORK].get("internal"), True)
            for name, service in self.redis_services(config).items():
                with self.subTest(stack=stack, service=name):
                    self.assertEqual(set(service["networks"]), {REDIS_NETWORK})

    def test_only_engine_services_share_the_redis_network(self):
        for stack, config in self.configs.items():
            for name, service in config["services"].items():
                on_redis = REDIS_NETWORK in (service.get("networks") or {})
                with self.subTest(stack=stack, service=name):
                    if name in REDIS_SERVICES:
                        continue
                    if name in ENGINE_SERVICES:
                        self.assertTrue(on_redis, f"{name} needs Redis")
                        self.assertEqual(service["environment"]["REDIS_PASSWORD"], SENTINELS[0])
                    else:
                        self.assertFalse(on_redis, f"{name} must not reach Redis")
                        self.assertNotIn("REDIS_PASSWORD", service.get("environment", {}))

    def test_engine_waits_for_authenticated_redis(self):
        for stack, config in self.configs.items():
            for name in REDIS_SERVICES:
                with self.subTest(stack=stack, service=name):
                    self.assertEqual(config["services"]["engine"]["depends_on"][name]["condition"],
                                     "service_healthy")

    def test_a_different_run_gets_a_different_password(self):
        other = resolve(STACKS["dev"], SENTINELS[1])
        for name in REDIS_SERVICES | {"engine"}:
            with self.subTest(service=name):
                self.assertEqual(other["services"][name]["environment"]["REDIS_PASSWORD"], SENTINELS[1])


class EntrypointRedisConfigTests(unittest.TestCase):
    """Static checks on how entrypoint.sh hands the password to the bench (live checks run in Docker)."""

    def setUp(self):
        self.text = (DOCKER_DIR / "entrypoint.sh").read_text(encoding="utf-8")

    def test_entrypoint_fails_closed_without_a_url_safe_password(self):
        self.assertIn('if [ -z "${REDIS_PASSWORD:-}" ]', self.text)
        self.assertIn("*[!A-Za-z0-9_-]*", self.text)

    def test_bench_redis_urls_carry_the_password(self):
        for key, host in (("redis_cache", "REDIS_CACHE_HOST"), ("redis_queue", "REDIS_QUEUE_HOST"),
                          ("redis_socketio", "REDIS_QUEUE_HOST")):
            with self.subTest(key=key):
                self.assertIn(f'"{key}": "redis://:${{REDIS_PASSWORD}}@${{{host}}}:6379"', self.text)
        self.assertNotRegex(self.text, r'"redis://\$\{REDIS_(CACHE|QUEUE)_HOST\}')

    def test_config_with_the_password_is_owner_only(self):
        self.assertIn("umask 077", self.text)
        self.assertNotRegex(self.text, r"(echo|printf)[^\n]*\$\{?REDIS_PASSWORD", "never print the value")


class RunnerPasswordTests(unittest.TestCase):
    """The real-bench runner mints a fresh Redis password per stack and never logs it."""

    def test_runner_generates_a_fresh_password_passed_only_by_environment(self):
        passwords, commands = [], []
        output = io.StringIO()

        def fake_run_compose(project, compose_file, env, *args, **kwargs):
            commands.append(args)
            if args[0] == "up":
                passwords.append(env.get("REDIS_PASSWORD"))
            return subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\nredis-cache\nredis-queue\n",
                                               stderr="")

        verify_envs = []

        def fake_run(cmd, **kwargs):
            verify_envs.append(kwargs.get("env", {}))
            return subprocess.CompletedProcess(cmd, 0)

        with (
            mock.patch.dict(os.environ, {"REDIS_PASSWORD": "inherited-weak"}),
            mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_run_compose),
            mock.patch.object(run_real_bench_ci, "_verify_http_ready"),
            mock.patch.object(run_real_bench_ci.subprocess, "run", side_effect=fake_run),
            redirect_stdout(output),
            redirect_stderr(output),
        ):
            for _ in range(2):
                self.assertEqual(run_real_bench_ci.run_real_bench_ci(engine_port=18999), 0)

        self.assertEqual(len(passwords), 2)
        self.assertNotEqual(passwords[0], passwords[1], "each stack needs its own Redis password")
        for pw in passwords:
            self.assertRegex(pw or "", r"^[A-Za-z0-9_-]{32,}$")
            self.assertNotEqual(pw, "inherited-weak")
            self.assertNotIn(pw, output.getvalue())
            self.assertFalse(any(pw in str(arg) for args in commands for arg in args))
        self.assertEqual([e.get("REDIS_PASSWORD") for e in verify_envs], passwords)

    def test_readiness_probe_authenticates_from_the_bench_config(self):
        probes = []

        def fake_run_compose(project, compose_file, env, *args, **kwargs):
            if args[:2] == ("ps", "--status"):
                return subprocess.CompletedProcess([], 0, stdout="engine\nmariadb\nredis-cache\nredis-queue\n",
                                                   stderr="")
            probes.append(args)
            return subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with mock.patch.object(run_real_bench_ci, "_run_compose", side_effect=fake_run_compose):
            run_real_bench_ci._wait_for_engine_ready("p", Path("c.yml"), {"REDIS_PASSWORD": "x" * 32})
        script = probes[0][-1]
        self.assertIn("common_site_config.json", script)
        self.assertIn("from_url", script)
        self.assertNotIn("x" * 32, " ".join(probes[0]))

    def test_failure_diagnostics_redact_the_redis_password(self):
        env = {"REDIS_PASSWORD": "private-redis-marker-inf015"}
        result = subprocess.CompletedProcess([], 0, stdout="log redis://:private-redis-marker-inf015@redis-cache",
                                             stderr="")
        out = io.StringIO()
        with mock.patch.object(run_real_bench_ci, "_run_compose", return_value=result), redirect_stderr(out):
            run_real_bench_ci._failure_diagnostics("p", Path("c.yml"), env)
        self.assertNotIn(env["REDIS_PASSWORD"], out.getvalue())

    def test_other_stack_starters_mint_a_redis_password(self):
        for script in ("isolation/run_isolation_suite.py", "smoke_headless_engine.py"):
            with self.subTest(script=script):
                text = (DOCKER_DIR / script).read_text(encoding="utf-8")
                self.assertRegex(text, r"REDIS_PASSWORD=secrets\.token_urlsafe\(32\)")


class VerifierRedisAuthTests(unittest.TestCase):
    """verify_dev_bench.py must prove Redis answers with the password and refuses without it."""

    def setUp(self):
        import verify_dev_bench
        self.verifier = verify_dev_bench

    def run_redis_checks(self, auth_reply, anon_reply):
        calls = []

        def fake_compose(project, *args):
            calls.append(args)
            if "redis-cli" in " ".join(args):
                reply = auth_reply if "REDISCLI_AUTH" in " ".join(args) else anon_reply
                return subprocess.CompletedProcess([], 0, stdout=reply + "\n", stderr="")
            return None

        err = io.StringIO()
        with mock.patch.object(self.verifier, "compose", side_effect=fake_compose), redirect_stderr(err):
            ok = self.verifier.redis_requires_auth("proj")
        return ok, calls, err.getvalue()

    def test_authenticated_ping_and_refused_anonymous_ping_pass(self):
        ok, calls, _ = self.run_redis_checks("PONG", "NOAUTH Authentication required.")
        self.assertTrue(ok)
        services = {args[2] for args in calls}
        self.assertEqual(services, REDIS_SERVICES)

    def test_anonymous_ping_answered_fails(self):
        ok, _, err = self.run_redis_checks("PONG", "PONG")
        self.assertFalse(ok)
        self.assertIn("unauthenticated", err)

    def test_authenticated_ping_refused_fails(self):
        ok, _, _ = self.run_redis_checks("NOAUTH Authentication required.", "NOAUTH Authentication required.")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
