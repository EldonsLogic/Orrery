#!/usr/bin/env python3
"""Stand up a real pinned Frappe bench and execute CE-SEC-005 integration tests.

Used by `.github/workflows/real-bench.yml` and local developers to verify the
change engine against real Frappe v15 / ERPNext / HRMS / MariaDB 11.4 / Redis
services instead of mocks. Never prints database or admin passwords.

Startup, provisioning and tests each have a five-minute limit. The normal CI
path's phase limits total 22.5 minutes, including diagnostics and teardown,
leaving headroom for readiness polling and setup within the 25-minute CI job.
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
SAFE_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.localhost$")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _compose_env(
    *,
    db_root_password: str,
    admin_password: str,
    site_name: str,
    engine_port: int,
) -> dict[str, str]:
    env = os.environ.copy()
    env["DB_ROOT_PASSWORD"] = db_root_password
    env["ADMIN_PASSWORD"] = admin_password
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
    timeout_seconds: int = 120,
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
                "import socket, redis, change_engine; "
                "assert all(redis.Redis(host=host, socket_timeout=2).ping() for host in ('redis-cache', 'redis-queue')); "
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
    script = (
        'site="$1"; db_name="$2"; '
        'bench new-site "$site" '
        '--db-host mariadb '
        '--mariadb-user-host-login-scope=% '
        '--db-root-password "$DB_ROOT_PASSWORD" '
        '--admin-password "$ADMIN_PASSWORD" '
        '--db-name "$db_name" '
        '--db-password "$ADMIN_PASSWORD" '
        '--install-app erpnext --install-app hrms --install-app change_engine'
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
        site_name,
        db_name,
        timeout=300,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed provisioning site {site_name} (exit {res.returncode}).")


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


def _verify_http_ready(site_name: str, engine_port: int, timeout_seconds: int = 60) -> None:
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


def _failure_diagnostics(project: str, compose_file: Path, env: dict[str, str]) -> None:
    """Collect bounded synthetic-stack diagnostics before teardown, without its credentials."""
    try:
        result = _run_compose(project, compose_file, env, "logs", "--no-color", "--tail", "80", timeout=30)
        output = (result.stdout or "") + (result.stderr or "")
        for key, value in env.items():
            if value and any(part in key.upper() for part in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")):
                output = output.replace(value, "<REDACTED>")
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
    env = _compose_env(
        db_root_password=db_root_password,
        admin_password=admin_password,
        site_name=site,
        engine_port=port,
    )

    provisioned = False
    succeeded = False
    try:
        if not reuse_project:
            up_args = ["up", "-d"]
            if build:
                up_args.append("--build")
            print(f"Starting pinned Frappe bench stack ({project_name}, port {port})...")
            up = _run_compose(project_name, compose_file, env, *up_args, timeout=300, stream=True)
            if up.returncode != 0:
                print(f"Failed starting Compose stack {project_name}.", file=sys.stderr)
                return up.returncode

        _wait_for_engine_ready(project_name, compose_file, env)
        print(f"Provisioning synthetic site {site} (erpnext, hrms, change_engine)...")
        _provision_site(project_name, compose_file, env, site)
        provisioned = True
        _verify_http_ready(site, port)

        print(f"Running pinned bench verifier for {site}...")
        verify_res = subprocess.run(
            [sys.executable, str(DOCKER_DIR / "verify_dev_bench.py")],
            cwd=str(DOCKER_DIR),
            env={**env, "COMPOSE_PROJECT_NAME": project_name, "SITE_NAME": site, "ENGINE_PORT": str(port)},
            timeout=120,
            check=False,
        )
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
            timeout=300,
            stream=True,
        )
        succeeded = test_res.returncode == 0
        return test_res.returncode
    finally:
        if not succeeded:
            _failure_diagnostics(project_name, compose_file, env)
        if not keep_stack:
            if reuse_project and provisioned:
                print(f"Dropping ephemeral site {site} from reused project {project_name}...")
                _drop_site(project_name, compose_file, env, site)
            elif not reuse_project:
                print(f"Tearing down ephemeral bench stack {project_name}...")
                cleanup = _run_compose(
                    project_name,
                    compose_file,
                    env,
                    "down",
                    "-v",
                    "--remove-orphans",
                    timeout=120,
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
        help="Provision and test an ephemeral site inside an already-running Compose project without tearing it down.",
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
