#!/usr/bin/env python3
"""pre-push hook: block pushes to main, then run the repo checks and the task-trail check.
Emergency founder override (never for agents): ORRERY_ALLOW_MAIN_PUSH=founder-emergency (the main-guard workflow still audits it).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT).returncode


def current_branch():
    return subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main():
    remote_ref = os.environ.get("PRE_COMMIT_REMOTE_BRANCH", "")
    target_main = remote_ref.endswith("/main") or (not remote_ref and current_branch() == "main")
    if target_main and os.environ.get("ORRERY_ALLOW_MAIN_PUSH") != "founder-emergency":
        print("Blocked: never push to main. Push a branch named with the plan ID and open a PR (AGENTS.md).")
        return 1
    rc = 0
    rc |= run(sys.executable, "scripts/build_status.py")
    rc |= run("git", "diff", "--exit-code", "docs/STATUS.md")
    for s in ("check_docs.py", "check_repo_hygiene.py", "scan_secrets.py"):
        rc |= run(sys.executable, f"scripts/{s}")
    base = subprocess.run(["git", "merge-base", "origin/main", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if base:
        rc |= run(sys.executable, "scripts/check_pr_trail.py", "--base", base, "--head", "HEAD")
        rc |= run(sys.executable, "scripts/check_lanes.py", "--base", base, "--head", "HEAD")
    if rc:
        print("Pre-push checks failed. Fix them (run python3 scripts/finish_session.py) and push again.")
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
