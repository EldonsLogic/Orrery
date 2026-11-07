#!/usr/bin/env python3
"""End-of-session gate. Run it before you stop; do not end the session until it prints FINISHED.

Verifies, in order: you are on a branch (not main); everything is committed; status is regenerated and committed;
repo checks and the task-trail check pass; the branch is pushed and up to date; a pull request exists.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems = []


def out(*cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def check(label, ok, hint=""):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        problems.append(f"{label}: {hint}" if hint else label)


def main():
    _, branch = out("git", "branch", "--show-current")
    check("on a feature branch, not main", branch not in ("", "main"), "create a branch named with the plan ID")
    rc, status = out("git", "status", "--porcelain")
    check("working tree is committed", rc == 0 and status == "", "commit or discard your changes")
    out(sys.executable, "scripts/build_status.py")
    rc, diff = out("git", "diff", "--name-only", "docs/STATUS.md")
    check("docs/STATUS.md is regenerated and committed", diff == "", "run build_status.py and commit docs/STATUS.md")
    for s in ("check_docs.py", "check_repo_hygiene.py", "scan_secrets.py"):
        rc, o = out(sys.executable, f"scripts/{s}")
        check(f"scripts/{s}", rc == 0, o.splitlines()[-1] if o else "")
    out("git", "fetch", "-q", "origin")
    _, base = out("git", "merge-base", "origin/main", "HEAD")
    if base:
        rc, o = out(sys.executable, "scripts/check_pr_trail.py", "--base", base, "--head", "HEAD")
        check("task trail (session log with valid plan IDs, rows updated)", rc == 0, o)
        rc, o = out(sys.executable, "scripts/check_lanes.py", "--base", base, "--head", "HEAD")
        check("lane guard (you edited only your own lane, or logged a Cross-lane waiver)", rc == 0, o)
    rc, upstream = out("git", "rev-parse", "--abbrev-ref", "@{upstream}")
    if rc == 0:
        _, ahead = out("git", "rev-list", "--count", "@{upstream}..HEAD")
        check("branch is pushed and up to date", ahead == "0", "git push")
    else:
        check("branch is pushed", False, "git push -u origin " + branch)
    rc, o = out("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number", "--jq", "length")
    check("a pull request is open for this branch", rc == 0 and o.strip() not in ("", "0"), "gh pr create (say how to view the change)")
    if problems:
        print("\nNOT FINISHED. Fix:")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nFINISHED. Tell the founders the PR link.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
