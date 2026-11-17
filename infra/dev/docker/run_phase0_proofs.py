#!/usr/bin/env python3
"""
Execute the ERP-021 Phase 0 Engine Proof Suite against a live pinned bench.

Creates two disposable synthetic tenant sites (<tag>a.localhost and <tag>b.localhost)
using the platform's Compose runtime, executes E0-1 through E0-6 against live
Frappe/ERPNext/HRMS/change_engine/MariaDB, captures structured proof evidence as JSON,
and drops the disposable sites cleanly on exit.

Never prints DB root or site passwords.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


DOCKER_DIR = Path(__file__).resolve().parent
REPO_ROOT = DOCKER_DIR.parents[2]
DEFAULT_COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"
ARTIFACTS_BUNDLE_FILES = {
    "mapping": REPO_ROOT / "contracts" / "examples" / "engine-mapping-golden-path.json",
    "blueprint": REPO_ROOT / "contracts" / "examples" / "blueprint-trading-minimal.json",
    "add_field_artifact": REPO_ROOT / "contracts" / "examples" / "compiled-artifact-add-field.json",
    "remove_field_artifact": REPO_ROOT / "contracts" / "examples" / "compiled-artifact-remove-field.json",
    "zatca_manifest": REPO_ROOT / "components" / "compliance" / "zatca_sa" / "manifest.json",
}
SAFE_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.localhost$")


def build_artifacts_bundle() -> dict:
    """Load the repo's contract examples and component manifest into a single JSON bundle."""
    return {
        key: json.loads(path.read_text(encoding="utf-8"))
        for key, path in ARTIFACTS_BUNDLE_FILES.items()
    }


def compose_exec(
    project: str,
    compose_file: Path,
    *args: str,
    input_text: str | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("DB_ROOT_PASSWORD", "bench-runner-placeholder")
    env.setdefault("ADMIN_PASSWORD", "bench-runner-placeholder")
    cmd = [
        "docker", "compose",
        "--project-name", project,
        "--env-file", os.devnull,
        "-f", str(compose_file),
        "exec", "-T", "engine",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(compose_file.parent),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _provision_ephemeral_site(
    project: str,
    compose_file: Path,
    site_name: str,
    tenant_id: str,
    country_code: str,
    currency: str,
) -> None:
    if not SAFE_SITE_RE.fullmatch(site_name):
        raise ValueError(f"Unsafe site name: {site_name}")
    db_name = f"_p0_{uuid.uuid4().hex[:10]}"
    script = (
        'site="$1"; db_name="$2"; tenant_id="$3"; country_code="$4"; currency="$5"; '
        'bench new-site "$site" '
        '--db-host mariadb '
        '--mariadb-user-host-login-scope=% '
        '--db-root-password "$DB_ROOT_PASSWORD" '
        '--admin-password "$ADMIN_PASSWORD" '
        '--db-name "$db_name" '
        '--db-password "$ADMIN_PASSWORD" '
        '--install-app erpnext --install-app hrms --install-app change_engine && '
        'bench --site "$site" set-config tenant_id "$tenant_id" && '
        'bench --site "$site" set-config country_code "$country_code" && '
        'bench --site "$site" set-config currency "$currency"'
    )
    res = compose_exec(
        project,
        compose_file,
        "sh", "-ec", script,
        "erp021_provision",
        site_name, db_name, tenant_id, country_code, currency,
        timeout=300,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed provisioning site {site_name}: {res.stderr or res.stdout}")


def _drop_ephemeral_site(project: str, compose_file: Path, site_name: str) -> None:
    if not SAFE_SITE_RE.fullmatch(site_name):
        return
    compose_exec(
        project,
        compose_file,
        "sh", "-ec",
        'site="$1"; bench drop-site "$site" --force --no-backup --db-root-password "$DB_ROOT_PASSWORD" || true',
        "erp021_drop",
        site_name,
        timeout=180,
    )


def _sync_components_to_container(project: str, compose_file: Path) -> None:
    """Stream components/ into /tmp/erp021_components inside container without exposing paths."""
    comp_dir = REPO_ROOT / "components"
    tar_proc = subprocess.run(
        ["tar", "-cf", "-", "-C", str(REPO_ROOT), "components"],
        capture_output=True,
        check=True,
    )
    b64_tar = base64.b64encode(tar_proc.stdout).decode("ascii")
    res = compose_exec(
        project,
        compose_file,
        "env/bin/python",
        "-c",
        "import base64, io, shutil, sys, tarfile; "
        "shutil.rmtree('/tmp/erp021_comp_root', ignore_errors=True); "
        "raw = base64.b64decode(sys.stdin.read().strip()); "
        "tarfile.open(fileobj=io.BytesIO(raw)).extractall('/tmp/erp021_comp_root')",
        input_text=b64_tar,
        timeout=60,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed syncing components into bench container: {res.stderr or res.stdout}")


def run_live_suite(
    project: str,
    compose_file: Path = DEFAULT_COMPOSE_FILE,
    engine_port: int = 8000,
    keep_sites: bool = False,
    site_a: str | None = None,
    site_b: str | None = None,
    skip_provision: bool = False,
) -> dict:
    if not SAFE_PROJECT_RE.fullmatch(project):
        raise ValueError(f"Invalid Compose project name: {project}")

    run_tag = uuid.uuid4().hex[:6]
    site_a = site_a or f"p0a-{run_tag}.localhost"
    site_b = site_b or f"p0b-{run_tag}.localhost"
    if not SAFE_SITE_RE.fullmatch(site_a) or not SAFE_SITE_RE.fullmatch(site_b):
        raise ValueError(f"Unsafe site names: {site_a}, {site_b}")
    bundle = build_artifacts_bundle()

    _sync_components_to_container(project, compose_file)
    try:
        if not skip_provision:
            _provision_ephemeral_site(project, compose_file, site_a, f"p0-tenant-a-{run_tag}", "SA", "SAR")
            _provision_ephemeral_site(project, compose_file, site_b, f"p0-tenant-b-{run_tag}", "AE", "AED")

        runner_code = (
            "import json, os, sys; "
            "sys.path.insert(0, '/tmp/erp021_comp_root'); "
            "sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'change_engine')); "
            "from components.compliance.zatca_sa.phase1 import generate_phase1_invoice; "
            "from change_engine.proofs.phase0_bench_proof import run_phase0_proofs; "
            "bundle = json.load(sys.stdin); "
            "res = run_phase0_proofs("
            f"site_a={site_a!r}, site_b={site_b!r}, bundle=bundle, "
            "engine_port=8000, zatca_generate_fn=generate_phase1_invoice"
            "); "
            "print(json.dumps(res, indent=2, default=str))"
        )
        res = compose_exec(
            project,
            compose_file,
            "env/bin/python",
            "-c",
            runner_code,
            input_text=json.dumps(bundle),
            timeout=540,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Phase 0 bench suite failed (rc={res.returncode}):\n{res.stderr}\n{res.stdout}")
        # Extract JSON object from stdout (last complete JSON payload if frappe prints banners)
        stdout = res.stdout.strip()
        start = stdout.find("{")
        if start == -1:
            raise RuntimeError(f"Expected JSON output from phase0 runner, got:\n{stdout}")
        return json.loads(stdout[start:])
    finally:
        if not keep_sites:
            _drop_ephemeral_site(project, compose_file, site_a)
            _drop_ephemeral_site(project, compose_file, site_b)
        compose_exec(
            project,
            compose_file,
            "rm", "-rf", "/tmp/erp021_comp_root",
            timeout=30,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run ERP-021 Phase 0 Engine Proof Suite against live pinned bench.")
    ap.add_argument("--compose-project", default=os.environ.get("COMPOSE_PROJECT_NAME", ""), required=False)
    ap.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    ap.add_argument("--engine-port", type=int, default=int(os.environ.get("ENGINE_PORT", "8000")))
    ap.add_argument("--site-a", default=None, help="Existing synthetic tenant A site (used with --skip-provision).")
    ap.add_argument("--site-b", default=None, help="Existing synthetic tenant B site (used with --skip-provision).")
    ap.add_argument("--skip-provision", action="store_true", help="Reuse --site-a and --site-b instead of creating new sites.")
    ap.add_argument("--keep-sites", action="store_true", help="Do not drop synthetic tenant sites after run.")
    ap.add_argument("--output-json", help="Optional host file path to save the structured JSON result.")
    args = ap.parse_args(argv)

    if not args.compose_project:
        print("Error: --compose-project or COMPOSE_PROJECT_NAME is required.", file=sys.stderr)
        return 2
    if args.skip_provision and not (args.site_a and args.site_b):
        print("Error: --skip-provision requires both --site-a and --site-b.", file=sys.stderr)
        return 2

    result = run_live_suite(
        project=args.compose_project,
        compose_file=Path(args.compose_file),
        engine_port=args.engine_port,
        keep_sites=args.keep_sites,
        site_a=args.site_a,
        site_b=args.site_b,
        skip_provision=args.skip_provision,
    )
    rendered = json.dumps(result, indent=2, default=str)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("all_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
