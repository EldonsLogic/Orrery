#!/usr/bin/env python3
"""Verify an explicitly selected, running local synthetic engine site.

Set COMPOSE_PROJECT_NAME and SITE_NAME to the project and .localhost site
created for the bench. This command only inspects existing services; it never
starts, recreates, or provisions them.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


DOCKER_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"
EXPECTED_VERSIONS = {
    "frappe": "15.126.0",
    "erpnext": "15.124.5",
    "hrms": "15.64.8",
    "change_engine": "0.1.0",
}
EXPECTED_HRMS_COMMIT = "186900a6e3db4e6f927f1ee20df745bbb082638a"


def compose(project, *args):
    """Run a read-only Compose inspection without exposing credentials."""
    environment = os.environ.copy()
    # These values satisfy Compose interpolation only; exec and ps never
    # recreate services or replace the running containers' credentials.
    environment.setdefault("DB_ROOT_PASSWORD", "verification-only")
    environment.setdefault("ADMIN_PASSWORD", "verification-only")
    try:
        return subprocess.run(
            [
                "docker", "compose", "--project-name", project, "--env-file",
                os.devnull, "-f", str(COMPOSE_FILE), *args,
            ],
            cwd=str(DOCKER_DIR),
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    """Check service availability, the real site's apps, and pinned versions."""
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
    listed = compose(project, "exec", "-T", "engine", "bench", "--site", site,
                     "list-apps", "--format", "json")
    try:
        installed = json.loads(listed.stdout).get(site, []) if listed and listed.returncode == 0 else []
    except (TypeError, ValueError, AttributeError):
        installed = []
    if not set(EXPECTED_VERSIONS).issubset(installed):
        print("Site is not ready or does not contain the expected apps.", file=sys.stderr)
        return 1

    versions = compose(
        project, "exec", "-T", "engine", "python", "-c",
        "import json, frappe, erpnext, hrms, change_engine; "
        "print(json.dumps({m.__name__: m.__version__ "
        "for m in (frappe, erpnext, hrms, change_engine)}))",
    )
    try:
        actual_versions = json.loads(versions.stdout) if versions and versions.returncode == 0 else {}
    except (TypeError, ValueError):
        actual_versions = {}
    if actual_versions != EXPECTED_VERSIONS:
        print("Installed app versions do not match the pinned set.", file=sys.stderr)
        return 1

    revision = compose(project, "exec", "-T", "engine", "git", "-C",
                       "apps/hrms", "rev-parse", "HEAD")
    if revision is None or revision.returncode != 0 or revision.stdout.strip() != EXPECTED_HRMS_COMMIT:
        print("The HRMS source commit does not match the pinned set.", file=sys.stderr)
        return 1
    for service in ("redis-cache", "redis-queue"):
        response = compose(project, "exec", "-T", service, "redis-cli", "ping")
        if response is None or response.returncode != 0 or response.stdout.strip() != "PONG":
            print(f"{service} is not responding.", file=sys.stderr)
            return 1
    print(f"Verified synthetic site {site} on project {project}: apps, versions, HRMS commit and Redis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
