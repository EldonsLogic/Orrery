#!/usr/bin/env python3
"""Stand up a real pinned Frappe bench and execute CE-SEC-005 integration tests.

Used by `.github/workflows/real-bench.yml` and local developers to verify the
change engine against real Frappe v15 / ERPNext / HRMS / MariaDB 11.4 / Redis
services instead of mocks. Keeps database, admin and internal credentials out of runner logs.

Startup and the CE-SEC-005 tests each have a five-minute limit; provisioning, with its index sync, eight minutes.
ERP-031 adds the ERP-014 and ERP-015 live valuation layers: each gets its own freshly provisioned site (with
``tenant_id``, as the probes refuse a used site), runs with its REQUIRE flag so a missing bench is a failure, and a layer that reports any
skip, or that ran fewer than its expected live tests (a vacuous run), fails the run. BPL-046 judges the BPL-027
bench class by the same rules: it runs inside the engine container, which gets the BPL-027 read-only mounts from
``docker-compose.bpl027-test.yml`` and the compiler's pinned test dependency, on its own fresh site with
``REQUIRE_BPL027_LIVE=1``. ``PHASES`` lists every sequential
phase's limit; ``TOTAL_PHASE_LIMIT_SECONDS`` is their sum, and the CI job limit must cover it plus setup and cleanup headroom.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


DOCKER_DIR = Path(__file__).resolve().parent
DEFAULT_COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"
# BPL-046: always layered on the stack: read-only mounts of the Blueprint compiler and contracts.
BPL027_COMPOSE_FILE = DOCKER_DIR / "docker-compose.bpl027-test.yml"
SAFE_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REPO_ROOT = DOCKER_DIR.parents[2]
ENGINE_PYTHONPATH = REPO_ROOT / "apps" / "engine" / "change_engine"
# BPL-046: every site gets the tenant provisioning's index sync, so the bench sites match production ones.
sys.path.append(str(REPO_ROOT / "scripts"))  # appended: nothing there shadows a module imported elsewhere
from provision_tenant_site import INDEX_SYNC_PY  # noqa: E402
# ERP-031: (site prefix, live test class, bench project var, bench site var, REQUIRE flag, minimum tests that must run)
# of each live valuation layer. Only the live class is run, so a run that executed fewer tests proved nothing.
VALUATION_LAYERS = (
    ("erp014", "change_engine.tests.test_erp_014_accounting_properties.TestLiveEngineProperties",
     "ERP014_COMPOSE_PROJECT", "ERP014_SITE", "REQUIRE_ERP014_LIVE", 7),
    ("erp015", "change_engine.tests.test_erp_015_inventory_valuation.TestLiveInventoryValuation",
     "ERP015_COMPOSE_PROJECT", "ERP015_BENCH_SITE", "REQUIRE_ERP015_LIVE", 10),
)
# BPL-046: only the bench class (the module's offline tests skip when a bench is configured), and all of its tests.
BPL027_LIVE_CLASS = "change_engine.tests.test_bpl_027_fixture_real_adapter.TestBpl027FixtureRealAdapter"
BPL027_MINIMUM_TESTS = 10
STARTUP_TIMEOUT = 300
ENGINE_READY_TIMEOUT = 120
# BPL-046: bench new-site took 297 to 306 s on a local machine (well under that in CI), the index sync about 45 s.
NEW_SITE_TIMEOUT = 360
INDEX_SYNC_TIMEOUT = 120
PROVISION_TIMEOUT = NEW_SITE_TIMEOUT + INDEX_SYNC_TIMEOUT
HTTP_READY_TIMEOUT = 60
VERIFIER_TIMEOUT = 120
SEC005_TEST_TIMEOUT = 300
VALUATION_TEST_TIMEOUT = 600  # BPL-046: the layers took 22 to 36 s in CI
BPL027_DEPS_TIMEOUT = 120
BPL027_TEST_TIMEOUT = 600
TEARDOWN_TIMEOUT = 120
DIAGNOSTICS_TIMEOUT = 30
# Every sequential phase of a fresh-stack run (CI), in order, with its limit in seconds.
PHASES = (
    ("startup", STARTUP_TIMEOUT),
    ("engine readiness", ENGINE_READY_TIMEOUT),
    ("provision ce-sec-005 site", PROVISION_TIMEOUT),
    ("http readiness", HTTP_READY_TIMEOUT),
    ("verifier", VERIFIER_TIMEOUT),
    ("ce-sec-005 tests", SEC005_TEST_TIMEOUT),
    *((f"provision {layer[0]} site", PROVISION_TIMEOUT) for layer in VALUATION_LAYERS),
    *((f"live layer {layer[0]}", VALUATION_TEST_TIMEOUT) for layer in VALUATION_LAYERS),
    ("install bpl-027 test dependency", BPL027_DEPS_TIMEOUT),
    ("provision bpl027 site", PROVISION_TIMEOUT),
    ("bpl-027 bench class", BPL027_TEST_TIMEOUT),
    ("diagnostics", DIAGNOSTICS_TIMEOUT),
    ("teardown", TEARDOWN_TIMEOUT),
)
TOTAL_PHASE_LIMIT_SECONDS = sum(seconds for _, seconds in PHASES)
RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
SKIP_RE = re.compile(r"\bskipped=\d+|\.\.\. skipped\b")
SAFE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.localhost$")
SECRET_KEY_PARTS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY")
# INF-015: the bench's Redis URLs carry the password as redis://:<password>@host.
REDIS_URL_CREDENTIAL_RE = re.compile(r"(rediss?://[^:@/\s]*:)[^@\s]+@")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _compose_env(
    *,
    db_root_password: str,
    admin_password: str,
    internal_token: str,
    redis_password: str,
    site_name: str,
    engine_port: int,
) -> dict[str, str]:
    env = os.environ.copy()
    env["DB_ROOT_PASSWORD"] = db_root_password
    env["ADMIN_PASSWORD"] = admin_password
    env["ENGINE_INTERNAL_TOKEN"] = internal_token
    env["REDIS_PASSWORD"] = redis_password
    env["SITE_NAME"] = site_name
    env["ENGINE_PORT"] = str(engine_port)
    return env


def _compose_cmd(project: str, compose_file: Path, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        os.devnull,
        "-f",
        str(compose_file),
        "-f",
        str(BPL027_COMPOSE_FILE),
        *args,
    ]


def _run_compose(
    project: str,
    compose_file: Path,
    env: dict[str, str],
    *args: str,
    timeout: int = 900,
    stream: bool = False,
) -> subprocess.CompletedProcess:
    cmd = _compose_cmd(project, compose_file, *args)
    if stream:
        return subprocess.run(cmd, cwd=str(compose_file.parent), env=env, timeout=timeout, check=False)
    return subprocess.run(
        cmd,
        cwd=str(compose_file.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _wait_for_engine_ready(
    project: str,
    compose_file: Path,
    env: dict[str, str],
    timeout_seconds: int = ENGINE_READY_TIMEOUT,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_err = ""
    while time.monotonic() < deadline:
        ps = _run_compose(project, compose_file, env, "ps", "--status", "running", "--services", timeout=30)
        if ps.returncode == 0 and {"engine", "mariadb", "redis-cache", "redis-queue"}.issubset(ps.stdout.splitlines()):
            probe = _run_compose(
                project,
                compose_file,
                env,
                "exec",
                "-T",
                "engine",
                "env/bin/python",
                "-c",
                "import json, socket, redis; "
                "from change_engine.api.route_guard import validate_internal_tokens; "
                "validate_internal_tokens(); "
                # INF-015: authenticate with the URLs the bench itself uses (they carry the password).
                "conf = json.load(open('sites/common_site_config.json')); "
                "assert all(redis.Redis.from_url(conf[key], socket_timeout=2).ping() "
                "for key in ('redis_cache', 'redis_queue')); "
                "s = socket.create_connection(('127.0.0.1', 8000), timeout=2); s.close()",
                timeout=30,
            )
            if probe.returncode == 0:
                return
            last_err = f"gunicorn probe exited {probe.returncode}"
        else:
            last_err = "required compose services not running"
        time.sleep(3)
    raise RuntimeError(f"Engine container did not become ready within {timeout_seconds}s: {last_err}")


def _provision_site(
    project: str,
    compose_file: Path,
    env: dict[str, str],
    site_name: str,
) -> None:
    if not SAFE_SITE_RE.fullmatch(site_name):
        raise ValueError(f"Unsafe site name: {site_name}")
    db_name = f"_ce005_{uuid.uuid4().hex[:10]}"
    tenant_slug = re.sub(r"[^A-Za-z0-9_]", "_", site_name.split(".", 1)[0])
    tenant_id = f"t_{tenant_slug}"[:64]
    script = (
        'index_sync="$1"; site="$2"; db_name="$3"; tenant_id="$4"; '
        'bench new-site "$site" '
        '--db-host mariadb '
        '--mariadb-user-host-login-scope=% '
        '--db-root-password "$DB_ROOT_PASSWORD" '
        '--admin-password "$ADMIN_PASSWORD" '
        '--db-name "$db_name" '
        '--db-password "$ADMIN_PASSWORD" '
        '--install-app erpnext --install-app hrms --install-app change_engine && '
        'bench --site "$site" set-config tenant_id "$tenant_id" && '
        'cd sites && ../env/bin/python -c "$index_sync" "$site"'
    )
    res = _run_compose(
        project,
        compose_file,
        env,
        "exec",
        "-T",
        "-e",
        "DB_ROOT_PASSWORD",
        "-e",
        "ADMIN_PASSWORD",
        "engine",
        "sh",
        "-ec",
        script,
        "ce_sec_005_provision",
        INDEX_SYNC_PY,
        site_name,
        db_name,
        tenant_id,
        timeout=PROVISION_TIMEOUT,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed provisioning site {site_name} (exit {res.returncode}).")
    report = (res.stdout or "").strip().splitlines()[-1:] or [""]
    print(f"Index sync on {site_name}: {redact(report[0], env)}")


def _drop_site(
    project: str,
    compose_file: Path,
    env: dict[str, str],
    site_name: str,
) -> None:
    if not SAFE_SITE_RE.fullmatch(site_name):
        raise ValueError("Invalid site name for cleanup")
    result = _run_compose(
        project,
        compose_file,
        env,
        "exec",
        "-T",
        "-e",
        "DB_ROOT_PASSWORD",
        "engine",
        "sh",
        "-ec",
        'site="$1"; bench drop-site "$site" --force --no-backup --db-root-password "$DB_ROOT_PASSWORD"',
        "ce_sec_005_drop",
        site_name,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"Failed dropping site {site_name} (exit {result.returncode}).")


def _verify_http_ready(site_name: str, engine_port: int, timeout_seconds: int = HTTP_READY_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        req = urllib.request.Request(
            f"http://127.0.0.1:{engine_port}/api/method/ping",
            headers={"Host": site_name},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200 and b"pong" in resp.read():
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Engine HTTP endpoint did not respond on 127.0.0.1:{engine_port} for {site_name}")


def unittest_reported_skips(output: str) -> bool:
    """True when unittest output says any test was skipped: a live layer that skips proved nothing (ERP-031)."""
    return bool(SKIP_RE.search(output))


def unittest_tests_run(stderr: str) -> int:
    """How many tests unittest's own `Ran N tests in ...` summary says ran. Pass the child's stderr only (unittest
    writes its summary there; test prints go to stdout). 0 when there is no summary or more than one (ambiguous)."""
    matches = RAN_RE.findall(stderr)
    return int(matches[0]) if len(matches) == 1 else 0


def _judge_live_run(label: str, res: subprocess.CompletedProcess, env: dict[str, str], minimum: int) -> int:
    """Print a live run's redacted output. Skips, failures and runs that executed fewer than the expected live tests
    all return non-zero."""
    output = redact((res.stdout or "") + (res.stderr or ""), env)
    print(output.rstrip("\n"), file=sys.stdout if res.returncode == 0 else sys.stderr)
    if res.returncode == 0 and unittest_reported_skips(output):
        print(f"{label} live layer skipped tests: that is a failure in real-bench CI.", file=sys.stderr)
        return 1
    ran = unittest_tests_run(redact(res.stderr or "", env))
    if res.returncode == 0 and ran < minimum:
        print(f"{label} live layer ran {ran} tests, expected at least {minimum}: a vacuous run is a failure "
              "in real-bench CI.", file=sys.stderr)
        return 1
    return res.returncode


def _run_valuation_layer(env: dict[str, str], project: str, site: str, layer: tuple[str, ...]) -> int:
    """Run one ERP-014/ERP-015 live class on the host against its own site and judge it."""
    prefix, live_class, project_var, site_var, require_var, minimum = layer
    print(f"Running {prefix.upper()} live valuation layer against {site}...")
    res = subprocess.run(
        [sys.executable, "-m", "unittest", live_class, "-v"],
        cwd=str(REPO_ROOT),
        env={**env, "PYTHONPATH": str(ENGINE_PYTHONPATH), "PYTHONUNBUFFERED": "1",
             project_var: project, site_var: site, require_var: "1"},
        timeout=VALUATION_TEST_TIMEOUT,
        check=False,
        capture_output=True,
        text=True,
    )
    return _judge_live_run(prefix.upper(), res, env, minimum)


def _install_bpl027_dependencies(project: str, compose_file: Path, env: dict[str, str]) -> None:
    """Install the Blueprint compiler's pinned requirements (test-only, not in the image) into the bench environment.
    pytest is left out: the class runs under unittest."""
    requirements = (REPO_ROOT / "services" / "blueprint" / "requirements.txt").read_text(encoding="utf-8")
    pins = [line.strip() for line in requirements.splitlines()
            if line.strip() and not line.startswith("#") and not re.match(r"pytest\b", line.strip())]
    res = _run_compose(
        project,
        compose_file,
        env,
        "exec",
        "-T",
        "engine",
        "env/bin/pip",
        "install",
        "-q",
        *pins,
        timeout=BPL027_DEPS_TIMEOUT,
    )
    if res.returncode != 0:
        print(redact((res.stdout or "") + (res.stderr or ""), env), file=sys.stderr)
        raise RuntimeError(f"Failed installing the BPL-027 test dependency (exit {res.returncode}).")


def _run_bpl027_class(project: str, compose_file: Path, env: dict[str, str], site: str) -> int:
    """Run the BPL-027 bench class inside the engine container against its own fresh site and judge it."""
    print(f"Running BPL027 bench class against {site}...")
    res = _run_compose(
        project,
        compose_file,
        env,
        "exec",
        "-T",
        "-e",
        f"BPL027_BENCH_SITE={site}",
        "-e",
        "REQUIRE_BPL027_LIVE=1",
        "-e",
        "PYTHONUNBUFFERED=1",
        "engine",
        "sh",
        "-ec",
        'cd sites && exec ../env/bin/python -m unittest -v "$1"',
        "bpl_046_tests",
        BPL027_LIVE_CLASS,
        timeout=BPL027_TEST_TIMEOUT,
    )
    return _judge_live_run("BPL027", res, env, BPL027_MINIMUM_TESTS)


def redact(text: str, env: dict[str, str]) -> str:
    """Hide the stack's credentials, and any credential in a redis:// URL, before printing child output."""
    for key, value in env.items():
        if value and any(part in key.upper() for part in SECRET_KEY_PARTS):
            text = text.replace(value, "<REDACTED>")
    return REDIS_URL_CREDENTIAL_RE.sub(r"\1<REDACTED>@", text)


def _failure_diagnostics(project: str, compose_file: Path, env: dict[str, str]) -> None:
    """Collect bounded synthetic-stack diagnostics before teardown, without its credentials."""
    try:
        result = _run_compose(project, compose_file, env, "logs", "--no-color", "--tail", "80", timeout=DIAGNOSTICS_TIMEOUT)
        output = redact((result.stdout or "") + (result.stderr or ""), env)
        print(output[-12000:], file=sys.stderr)
    except Exception:
        print("Could not collect bench failure diagnostics.", file=sys.stderr)


def run_real_bench_ci(
    *,
    project: str | None = None,
    compose_file: Path = DEFAULT_COMPOSE_FILE,
    site_name: str | None = None,
    engine_port: int | None = None,
    build: bool = True,
    reuse_project: bool = False,
    keep_stack: bool = False,
) -> int:
    run_id = uuid.uuid4().hex[:8]
    project_name = project or f"ce-sec-005-{run_id}"
    if not SAFE_PROJECT_RE.fullmatch(project_name):
        raise ValueError(f"Unsafe Compose project name: {project_name}")

    site = site_name or f"ce005-{run_id}.localhost"
    if not SAFE_SITE_RE.fullmatch(site):
        raise ValueError(f"Unsafe synthetic site name: {site}")

    port = engine_port if engine_port is not None else _pick_free_port()
    db_root_password = os.environ.get("DB_ROOT_PASSWORD") or secrets.token_urlsafe(24)
    admin_password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(24)
    # A reused engine already has its credential. Fresh stacks always mint a new one.
    internal_token = os.environ.get("ENGINE_INTERNAL_TOKEN") if reuse_project else secrets.token_urlsafe(32)
    if not internal_token:
        raise ValueError("Set ENGINE_INTERNAL_TOKEN to the reused engine's internal token")
    # INF-015: every fresh stack mints its own Redis password. A reused stack keeps the one it started
    # with, supplied in the environment like the internal token, so redaction covers the real value.
    redis_password = os.environ.get("REDIS_PASSWORD") if reuse_project else secrets.token_urlsafe(32)
    if not redis_password:
        raise ValueError("Set REDIS_PASSWORD to the reused stack's Redis password")
    env = _compose_env(
        db_root_password=db_root_password,
        admin_password=admin_password,
        internal_token=internal_token,
        redis_password=redis_password,
        site_name=site,
        engine_port=port,
    )

    provisioned_sites: list[str] = []
    valuation_sites = {layer[0]: f"{layer[0]}-{run_id}.localhost" for layer in VALUATION_LAYERS}
    bpl027_site = f"bpl027-{run_id}.localhost"
    succeeded = False
    try:
        if not reuse_project:
            up_args = ["up", "-d"]
            if build:
                up_args.append("--build")
            print(f"Starting pinned Frappe bench stack ({project_name}, port {port})...")
            up = _run_compose(project_name, compose_file, env, *up_args, timeout=STARTUP_TIMEOUT, stream=True)
            if up.returncode != 0:
                print(f"Failed starting Compose stack {project_name}.", file=sys.stderr)
                return up.returncode

        _wait_for_engine_ready(project_name, compose_file, env)
        print(f"Provisioning synthetic site {site} (erpnext, hrms, change_engine)...")
        _provision_site(project_name, compose_file, env, site)
        provisioned_sites.append(site)
        _verify_http_ready(site, port)

        print(f"Running pinned bench verifier for {site}...")
        verify_res = subprocess.run(
            [sys.executable, str(DOCKER_DIR / "verify_dev_bench.py")],
            cwd=str(DOCKER_DIR),
            env={**env, "COMPOSE_PROJECT_NAME": project_name, "SITE_NAME": site, "ENGINE_PORT": str(port)},
            timeout=VERIFIER_TIMEOUT,
            check=False,
            capture_output=True,
            text=True,
        )
        # The verifier's child output can carry the bench's Redis URLs: print it redacted.
        verifier_output = redact((verify_res.stdout or "") + (verify_res.stderr or ""), env)
        if verifier_output:
            print(verifier_output.rstrip("\n"), file=sys.stdout if verify_res.returncode == 0 else sys.stderr)
        if verify_res.returncode != 0:
            print("Pinned bench verification failed.", file=sys.stderr)
            return verify_res.returncode

        print(f"Running CE-SEC-005 real-bench integration suite against {site}...")
        test_res = _run_compose(
            project_name,
            compose_file,
            env,
            "exec",
            "-T",
            "-e",
            "ENGINE_INTERNAL_TOKEN",
            "-e",
            "CE_SEC_005_REAL_BENCH=1",
            "-e",
            f"CE_SEC_005_SITE={site}",
            "-e",
            "ENGINE_PORT=8000",
            "-e",
            "PYTHONUNBUFFERED=1",
            "engine",
            "env/bin/python",
            "-m",
            "unittest",
            "change_engine.tests.test_ce_sec_005_real_bench",
            "change_engine.tests.test_ce_sec_005_live_http",
            "-v",
            timeout=SEC005_TEST_TIMEOUT,
            stream=True,
        )
        results = [test_res.returncode]

        # ERP-031: the live valuation layers, each on a fresh site that carries tenant_id (the event stream needs it).
        for layer in VALUATION_LAYERS:
            layer_site = valuation_sites[layer[0]]
            print(f"Provisioning synthetic site {layer_site} for the {layer[0].upper()} live layer...")
            _provision_site(project_name, compose_file, env, layer_site)
            provisioned_sites.append(layer_site)
            results.append(_run_valuation_layer(env, project_name, layer_site, layer))

        # BPL-046: last, so a failure to set it up cannot hide the layers above.
        _install_bpl027_dependencies(project_name, compose_file, env)
        print(f"Provisioning synthetic site {bpl027_site} for the BPL027 bench class...")
        _provision_site(project_name, compose_file, env, bpl027_site)
        provisioned_sites.append(bpl027_site)
        results.append(_run_bpl027_class(project_name, compose_file, env, bpl027_site))
        succeeded = not any(results)
        return next((rc for rc in results if rc), 0)
    finally:
        if not succeeded:
            _failure_diagnostics(project_name, compose_file, env)
        if not keep_stack:
            if reuse_project and provisioned_sites:
                drop_errors = []
                for dropped in provisioned_sites:  # attempt every drop: one failure must not leak the other sites
                    print(f"Dropping ephemeral site {dropped} from reused project {project_name}...")
                    try:
                        _drop_site(project_name, compose_file, env, dropped)
                    except Exception as exc:
                        drop_errors.append(str(exc))
                if drop_errors:
                    raise RuntimeError("Site cleanup failed: " + " ".join(drop_errors))
            elif not reuse_project:
                print(f"Tearing down ephemeral bench stack {project_name}...")
                cleanup = _run_compose(
                    project_name,
                    compose_file,
                    env,
                    "down",
                    "-v",
                    "--remove-orphans",
                    timeout=TEARDOWN_TIMEOUT,
                )
                if cleanup.returncode:
                    raise RuntimeError(f"Compose teardown failed (exit {cleanup.returncode}).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run CE-SEC-005 change-engine integration tests against a real pinned Frappe bench."
    )
    ap.add_argument("--compose-project", default=None, help="Explicit Compose project name.")
    ap.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE), help="Path to docker-compose.dev.yml.")
    ap.add_argument("--site", default=None, help="Synthetic .localhost site name to provision and test.")
    ap.add_argument("--engine-port", type=int, default=None, help="Host port mapped to engine HTTP (default: ephemeral).")
    ap.add_argument("--no-build", action="store_true", help="Skip docker compose build and reuse existing image.")
    ap.add_argument(
        "--reuse-project",
        action="store_true",
        help="Reuse a running Compose project with its existing ENGINE_INTERNAL_TOKEN and REDIS_PASSWORD "
        "supplied in the environment.",
    )
    ap.add_argument("--keep-stack", action="store_true", help="Keep containers and volumes running after exit.")
    args = ap.parse_args(argv)

    return run_real_bench_ci(
        project=args.compose_project,
        compose_file=Path(args.compose_file),
        site_name=args.site,
        engine_port=args.engine_port,
        build=not args.no_build,
        reuse_project=args.reuse_project,
        keep_stack=args.keep_stack,
    )


if __name__ == "__main__":
    def terminate(signum, _frame):
        """Unwind through the same cleanup path as a local interruption."""
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    sys.exit(main())
