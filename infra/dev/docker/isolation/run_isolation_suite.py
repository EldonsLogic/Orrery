#!/usr/bin/env python3
"""SEC-004 harness: throwaway bench, two tenant sites via ERP-003, isolation suite.

Steps (each fails closed):
1. `docker compose up` the dev bench plus a worker under a project name that must
   be `sec004` or start with `sec004-` (never a shared or load-test project) on a non-default port.
2. Provision tenant A, tenant B and a prefix-twin site (`<A's site>.sa`, change_engine
   only) with infra/dev/docker/provision_tenant.sh, each with its own random admin
   password; credentials go to 0600 files in a private temp directory.
3. Write the context file and run
   apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py.
4. `docker compose down -v` for this project only (skip with --keep).

Synthetic data only; secrets never touch the repo or the host command line.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DOCKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCKER_DIR.parents[2]
COMPOSE_FILES = [DOCKER_DIR / "docker-compose.dev.yml", DOCKER_DIR / "isolation" / "docker-compose.isolation.yml"]
for _path in (DOCKER_DIR, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from sec004_project import PROJECT_RE  # noqa: E402  one project-name rule, shared with raw_engine_wsgi.py
from run_real_bench_ci import redact  # noqa: E402  INF-015: same redaction as the real-bench runner

SUITE = REPO_ROOT / "apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py"
TENANTS = {
    "a": {"tenant_id": "sec004-tenant-a", "country": "SA", "site": None, "apps": None},
    "b": {"tenant_id": "sec004-tenant-b", "country": "AE", "site": None, "apps": None},
    # Same name as A plus ".sa" (think acme.com vs acme.com.sa): probes prefix-matching bugs.
    "twin": {"tenant_id": "sec004-tenant-t", "country": "SA", "site": "sec004-tenant-a.localhost.sa",
             "apps": "change_engine"},
}


def compose(project: str, *args: str, env: dict, timeout: int = 1800) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "--project-name", project, "--env-file", os.devnull]
    for f in COMPOSE_FILES:
        cmd += ["-f", str(f)]
    return subprocess.run(cmd + list(args), env=env, timeout=timeout, text=True)


def wait_for_engine(port: int, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # Unknown Host -> 404 from the engine; any HTTP answer means gunicorn is up.
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/method/ping", timeout=5)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(3)
    raise SystemExit(f"engine did not answer on 127.0.0.1:{port}")


def provision(project: str, key: str, spec: dict, creds_dir: Path, env: dict) -> dict:
    creds = creds_dir / f"{key}.json"
    cmd = [str(DOCKER_DIR / "provision_tenant.sh"), spec["tenant_id"], spec["country"], spec["site"] or ""]
    cmd += ["--credentials-file", str(creds), "--json"]
    if spec["apps"]:
        cmd += ["--apps", spec["apps"]]
    child_env = dict(env, COMPOSE_PROJECT_NAME=project)
    child_env.pop("ADMIN_PASSWORD", None)  # each tenant gets its own random admin password
    res = subprocess.run(cmd, env=child_env, text=True, capture_output=True, timeout=3600)
    if res.returncode != 0:
        raise SystemExit(f"provisioning {key} failed:\n{redact(res.stderr or '', env)[-3000:]}")
    data = json.loads(creds.read_text(encoding="utf-8"))
    return {"site": data["site_name"], "admin_password": data["admin_password"],
            "db_name": data["db_name"], "db_user": data["db_user"], "db_password": data["db_password"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default="sec004-isolation")
    ap.add_argument("--port", type=int, default=18404)
    ap.add_argument("--keep", action="store_true", help="leave the stack running afterwards")
    ap.add_argument("--reuse", metavar="CONTEXT", help="skip up/provision; reuse a context file from --keep")
    args = ap.parse_args()
    if not PROJECT_RE.fullmatch(args.project):
        raise SystemExit("project name must be 'sec004' or start with 'sec004-' (refusing to touch other stacks)")
    if args.port in (8000, 18111, 18222):
        raise SystemExit("use a non-default port not shared with other benches")

    workdir = Path(tempfile.mkdtemp(prefix="sec004-"))
    os.chmod(workdir, 0o700)
    env = dict(os.environ, COMPOSE_PROJECT_NAME=args.project, ENGINE_PORT=str(args.port),
               DB_ROOT_PASSWORD=os.environ.get("DB_ROOT_PASSWORD") or secrets.token_urlsafe(24),
               ADMIN_PASSWORD=secrets.token_urlsafe(24),
               # INF-015: per-run Redis password; containers get it by name from this environment.
               REDIS_PASSWORD=secrets.token_urlsafe(32))
    rc = 1
    try:
        if args.reuse:
            ctx_path = Path(args.reuse)
        else:
            if compose(args.project, "up", "-d", "--build", env=env).returncode != 0:
                raise SystemExit("compose up failed")
            wait_for_engine(args.port)
            tenants = {k: provision(args.project, k, spec, workdir, env) for k, spec in TENANTS.items()}
            ctx = {"compose_project": args.project, "compose_files": [str(f) for f in COMPOSE_FILES],
                   "engine_port": args.port, "tenants": tenants}
            ctx_path = workdir / "context.json"
            fd = os.open(ctx_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(ctx, fh)
        suite_env = dict(os.environ, SEC004_CONTEXT=str(ctx_path), CI_REQUIRE_LIVE_SEC004="1")
        rc = subprocess.run([sys.executable, "-m", "unittest", "-v", str(SUITE.relative_to(REPO_ROOT))],
                            env=suite_env, cwd=REPO_ROOT).returncode
    finally:
        if args.reuse:
            shutil.rmtree(workdir, ignore_errors=True)
            print(f"stack kept: project {args.project}; context {args.reuse}", file=sys.stderr)
        elif args.keep:
            print(f"stack kept: project {args.project}; context {workdir / 'context.json'}", file=sys.stderr)
        else:
            compose(args.project, "down", "-v", "--remove-orphans", env=env)
            shutil.rmtree(workdir, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
