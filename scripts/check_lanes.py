#!/usr/bin/env python3
"""Lane guard: a founder (or their agent) edits only their own lane's paths (scripts/lanes.json).

A change to the other founder's lane fails unless the session log added in the same change has a line
  Cross-lane: approved by <eldon|partner> (where and when, e.g. PR comment, open-questions entry)
naming the owner of that lane. Shared paths are always allowed. Unknown actors (bots, unmapped logins) are skipped.
Usage: check_lanes.py --base <sha> [--head <sha>] [--actor <github login>]
Without --actor it tries ORRERY_FOUNDER, then `gh api user`; if the founder is unknown it skips (CI enforces).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "scripts" / "lanes.json").read_text(encoding="utf-8"))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()


def detect_actor():
    if os.environ.get("ORRERY_FOUNDER"):
        return os.environ["ORRERY_FOUNDER"]
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def lane_of(path):
    for lane, prefixes in CFG["lanes"].items():
        if any(path.startswith(p) for p in prefixes):
            return lane
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--actor", default="")
    a = ap.parse_args()
    actor = a.actor or detect_actor()
    founders = {k.lower(): v for k, v in CFG["founders"].items()}
    me = founders.get(actor.lower()) or (actor if actor in CFG["lanes"] else None)
    if not me:
        print(f"Lane check skipped: founder unknown for '{actor or '?'}' (CI enforces with the PR author).")
        return 0
    changed = git("diff", "--name-only", a.base, a.head)
    foreign = {}
    for f in changed:
        lane = lane_of(f)
        if lane and lane != me:
            foreign.setdefault(lane, []).append(f)
    if not foreign:
        print(f"Lane check OK ({me}: no edits in the other founder's lane).")
        return 0
    added = git("diff", "--name-only", "--diff-filter=A", a.base, a.head)
    logs = [f for f in added if f.startswith("docs/log/") and not re.search(r"/(README|TEMPLATE)\.md$", f)]
    waivers = []
    for f in logs:
        for ln in (ROOT / f).read_text(encoding="utf-8").splitlines():
            if ln.lower().startswith("cross-lane:"):
                waivers.append(ln.lower())
    errors = []
    for lane, files in foreign.items():
        if not any(f"approved by {lane}" in w for w in waivers):
            errors.append(f"{me} changed the {lane} lane without a waiver ({len(files)} file(s), e.g. {files[0]})")
    if errors:
        print("Lane guard FAILED:")
        for e in errors:
            print("  - " + e)
        print("Stay in your lane (docs/ONBOARDING.md). If the other founder agreed, add this line to your session log:")
        print("  Cross-lane: approved by <eldon|partner> (where and when)")
        return 1
    print("Lane check OK (cross-lane edits carry a waiver; reviewers: confirm it is real).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
