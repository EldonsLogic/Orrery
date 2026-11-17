#!/usr/bin/env python3
"""Rerunnable Arabic translation & RTL readiness audit for the pinned dev bench (ERP-006).

Runs against an already-running Compose project (COMPOSE_PROJECT_NAME, SITE_NAME) via
`docker compose exec -T engine`. Read-only by default; pass `--apply` to sync the 107
missing translatable site `Translation` records from `components/core/trading_ar` and
verify 100% coverage of translatable in-scope strings with zero excluded codes translated.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

DOCKER_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"


def compose(project: str, *args: str):
    env = os.environ.copy()
    env.setdefault("DB_ROOT_PASSWORD", "verification-only")
    env.setdefault("ADMIN_PASSWORD", "verification-only")
    try:
        return subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                project,
                "--env-file",
                os.devnull,
                "-f",
                str(COMPOSE_FILE),
                *args,
            ],
            cwd=str(DOCKER_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit (and optionally apply) ERP-006 Arabic translations on a bench site.")
    parser.add_argument("--apply", action="store_true", help="Upsert the 107 core.trading_ar Translation records before auditing.")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON audit payload.")
    args = parser.parse_args(argv)

    project = os.environ.get("COMPOSE_PROJECT_NAME", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        print("Set COMPOSE_PROJECT_NAME to the local bench project.", file=sys.stderr)
        return 1

    running = compose(project, "ps", "--status", "running", "--services")
    if running is None or running.returncode != 0 or "engine" not in running.stdout.splitlines():
        print("No running engine for the selected Compose project.", file=sys.stderr)
        return 1

    site = os.environ.get("SITE_NAME", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.localhost", site):
        print("Set SITE_NAME to the synthetic .localhost site.", file=sys.stderr)
        return 1

    apply_flag = "True" if args.apply else "False"
    inline = f"""
import json, os
os.chdir("sites")
import frappe
frappe.init(site={site!r})
frappe.connect()
try:
    from change_engine.i18n import audit_trading_arabic_coverage, sync_trading_arabic_translations
    sync_info = sync_trading_arabic_translations(dry_run=False) if {apply_flag} else None
    report = audit_trading_arabic_coverage()
    print(json.dumps({{"sync": sync_info, "audit": report}}, ensure_ascii=False))
finally:
    frappe.destroy()
"""
    proc = compose(project, "exec", "-T", "engine", "python", "-c", inline)
    if proc is None or proc.returncode != 0:
        detail = (proc.stderr if proc else "") or (proc.stdout if proc else "exec failed")
        print(f"Arabic audit failed inside engine container:\n{detail}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        print(f"Could not parse audit output ({exc}):\n{proc.stdout}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        audit = payload["audit"]
        print(
            f"Site {site}: {audit['translatable_covered']}/{audit['translatable_total']} "
            f"translatable strings covered ({audit['translatable_coverage_pct']}%), "
            f"missing_translatable={audit['missing_translatable_unique']}, "
            f"excluded_skipped={audit['missing_excluded_unique']}, "
            f"reports={audit['reports_translated']}/{audit['reports_total']}, "
            f"rtl={audit['rtl_and_runtime']['rtl_active']}, "
            f"app_ar_strings={audit['rtl_and_runtime']['runtime_app_strings']}"
        )
        if payload.get("sync"):
            s = payload["sync"]
            print(
                f"Synced core.trading_ar: created={s['created']}, "
                f"updated={s['updated']}, unchanged={s['unchanged']}"
            )

    audit = payload["audit"]
    if audit["excluded_site_translations"]:
        print(f"Excluded site translations present: {audit['excluded_site_translations']}", file=sys.stderr)
        return 1
    if audit["reports_missing"]:
        print(f"Missing report translations: {audit['reports_missing']}", file=sys.stderr)
        return 1
    if args.apply and audit["missing_translatable_unique"] != 0:
        print(f"Remaining missing translatable strings: {audit['missing_translatable_strings']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
