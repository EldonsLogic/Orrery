#!/usr/bin/env python3
"""Task-trail gate for pull requests.

Fails when a PR changes project files without leaving a trail:
  - files outside docs/ and .github/ changed but no new session log was added;
  - a new log has no Plan IDs or names an ID that is not in docs/PLAN.md;
  - product files (not Markdown) changed under apps/, services/, web/, connectors/, components/, evals/, infra/, contracts/ but the
    log names only rows still `todo` (work on a row must show as `doing`, `done` or `blocked` in the plan).
    Docs and governance PRs may log planning work on rows that stay `todo`.
Usage: python3 scripts/check_pr_trail.py --base <sha> [--head <sha>]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import ROOT, parse_plan


CODE_PREFIXES = ("apps/", "services/", "web/", "connectors/", "components/", "evals/", "infra/", "contracts/")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    changed = git("diff", "--name-only", a.base, a.head)
    added = git("diff", "--name-only", "--diff-filter=A", a.base, a.head)
    new_logs = [f for f in added if f.startswith("docs/log/") and not re.search(r"/(README|TEMPLATE)\.md$", f)]
    outside = [f for f in changed if not (f.startswith("docs/") or f.startswith(".github/"))]
    code = [f for f in changed if f.startswith(CODE_PREFIXES) and not f.endswith(".md")]
    rows, _ = parse_plan()
    status = {r["ID"]: r["Status"] for r in rows}
    errors = []
    if outside and not new_logs:
        errors.append("files outside docs/ and .github/ changed but no new file under docs/log/ was added")
    for f in new_logs:
        text = (ROOT / f).read_text(encoding="utf-8")
        m = re.search(r"^Plan IDs:\s*(.*)$", text, re.M)
        ids = [i.strip() for i in (m.group(1) if m else "").split(",") if i.strip()]
        if not ids:
            errors.append(f"{f}: no Plan IDs listed")
            continue
        unknown = [i for i in ids if i not in status]
        if unknown:
            errors.append(f"{f}: Plan IDs not in docs/PLAN.md: {', '.join(unknown)}")
        known = [i for i in ids if i in status]
        if code and known and all(status[i] == "todo" for i in known):
            errors.append(f"{f}: every listed plan row is still `todo`; set the row you worked on to doing, done or blocked in docs/PLAN.md")
    if errors:
        print("Task trail FAILED:")
        for e in errors:
            print("  - " + e)
        return 1
    print(f"Task trail OK ({len(new_logs)} new log(s), {len(code)} product file(s) changed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
