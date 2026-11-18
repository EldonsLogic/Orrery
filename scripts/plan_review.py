#!/usr/bin/env python3
"""Periodic plan review (GOV-020): prints what to re-rank, close or unblock. Read-only, deterministic.

Usage: python3 scripts/plan_review.py [--logs N]
Findings: stale `doing` rows (not named in the latest N logs), ready `todo` rows by owner,
gate inversions (a row depends on a later gate), blocked rows, and the current gate's open rows.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import GATES, current_gate, log_files, parse_plan  # noqa: E402


def deps_of(row):
    d = row["Depends"]
    return [] if d in ("-", "") else [x.strip() for x in d.split(",")]


def log_ids(path):
    m = re.search(r"^Plan IDs:\s*(.*)$", path.read_text(encoding="utf-8"), re.M)
    return set(re.findall(r"[A-Z]+(?:-[A-Z]+)*-\d{3}", m.group(1))) if m else set()


def review(rows, recent_ids, gate):
    by_id = {r["ID"]: r for r in rows}
    done = {r["ID"] for r in rows if r["Status"] == "done"}
    out = {"stale_doing": [], "ready": {}, "gate_inversions": [], "blocked": [], "open_in_gate": []}
    for r in rows:
        if r["Status"] == "doing" and r["ID"] not in recent_ids:
            out["stale_doing"].append(r["ID"])
        if r["Status"] == "blocked":
            out["blocked"].append(r["ID"])
        if r["Status"] == "todo" and all(d in done for d in deps_of(r)):
            out["ready"].setdefault(r["Owner"], []).append(r["ID"])
        if r["Status"] != "done":
            for d in deps_of(r):
                if GATES.index(by_id[d]["Gate"]) > GATES.index(r["Gate"]):
                    out["gate_inversions"].append(f"{r['ID']} ({r['Gate']}) depends on {d} ({by_id[d]['Gate']})")
        if r["Gate"] == gate and r["Status"] != "done":
            out["open_in_gate"].append(f"{r['ID']} [{r['Status']}, {r['Owner']}]")
    return out


def render(out, gate, n):
    lines = [f"# Plan review (current gate {gate}, latest {n} logs)", ""]
    sections = [("Stale doing rows (no log names them): close, hand back or log progress", out["stale_doing"]),
                ("Blocked rows: name the blocker", out["blocked"]),
                ("Gate inversions: move a gate or drop the dependency", out["gate_inversions"]),
                (f"Open rows in {gate}", out["open_in_gate"])]
    for title, items in sections:
        lines += [f"## {title} ({len(items)})", ""] + [f"- {i}" for i in items] + [""]
    lines += ["## Ready todo rows by owner (all dependencies done)", ""]
    for owner in sorted(out["ready"]):
        lines.append(f"- {owner} ({len(out['ready'][owner])}): " + ", ".join(out["ready"][owner]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--logs", type=int, default=15, help="how many latest logs count as recent")
    a = ap.parse_args(argv)
    rows, errors = parse_plan()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    recent = set()
    for f in log_files()[: a.logs]:
        recent |= log_ids(f)
    gate = current_gate()
    print(render(review(rows, recent, gate), gate, a.logs), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
