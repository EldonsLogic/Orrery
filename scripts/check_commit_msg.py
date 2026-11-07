#!/usr/bin/env python3
"""commit-msg hook: every commit message must name at least one plan ID (for example GOV-024 or CE-SEC-003).
Merge, revert and dependency-bot commits are exempt. Usage: check_commit_msg.py <message-file>
"""
import re
import sys

PLAN_ID = re.compile(r"\b[A-Z]{2,}(?:-[A-Z]+)*-\d{3}\b")
EXEMPT = re.compile(r"^(Merge |Revert |Bump |fixup! |squash! )")


def main():
    msg = open(sys.argv[1], encoding="utf-8").read()
    first = next((ln for ln in msg.splitlines() if ln.strip()), "")
    if EXEMPT.match(first) or PLAN_ID.search(msg):
        return 0
    print("Commit message must name a plan ID from docs/PLAN.md (for example 'GOV-024: add enforcement layers').")
    print("Every change traces to a plan row. If none fits, add a row first.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
