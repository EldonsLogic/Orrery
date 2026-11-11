#!/usr/bin/env python3
"""Phase and gate exit check (docs/RULES.md rule 48, docs/GATES.md).

A phase closes only after an exit run is recorded. This script:
  1. runs the automated repo checks and the test suites that exist;
  2. reads docs/specs/phase-exit-criteria.json for the phase: plan rows that must be `done` and evidence items;
  3. looks for a session log with the header `Phase exit: <phase>` that records every evidence item as
     `- <evidence-id>: PASS <note or link>` and a `Reviewed by: <name> (<model>)` line.
Exit 0 only if every part passes. Never edit the criteria or the log to make a failing run pass.

Usage:
  python3 scripts/phase_exit_check.py --list
  python3 scripts/phase_exit_check.py --phase 1A
  python3 scripts/phase_exit_check.py --phase 1A --skip-run     # criteria and log only
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import ROOT, parse_plan, log_files

CRITERIA = ROOT / "docs" / "specs" / "phase-exit-criteria.json"
CHECKS = [
    ("docs gate", ["scripts/check_docs.py"]),
    ("repo hygiene", ["scripts/check_repo_hygiene.py"]),
    ("secret scan", ["scripts/scan_secrets.py"]),
    ("plan independence", ["scripts/check_plan_independence.py"]),
    ("contracts", ["scripts/check_contracts.py"]),
]
SUITES = [("services/blueprint/tests", "blueprint tests"), ("evals/tests", "eval tests"),
          ("services/discovery/tests", "discovery tests"), ("scripts/tests", "script tests")]


def load_criteria(path=CRITERIA):
    if not path.exists():
        return None, f"missing {path.as_posix()}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"invalid JSON in criteria file: {e}"
    return data.get("phases", {}), None


def plan_rows_problems(rows, wanted):
    by = {r["ID"]: r for r in rows}
    out = []
    for pid in wanted:
        r = by.get(pid)
        if not r:
            out.append(f"plan row {pid} does not exist")
        elif r["Status"] != "done":
            out.append(f"plan row {pid} is {r['Status']}, must be done")
    return out


def find_exit_log(phase, logs):
    """Return the newest log whose header says `Phase exit: <phase>`."""
    pat = re.compile(rf"^Phase exit:\s*{re.escape(phase)}\s*$", re.M | re.I)
    for f in logs:  # newest first
        if pat.search(f.read_text(encoding="utf-8")):
            return f
    return None


def evidence_problems(text, evidence_ids):
    out = []
    for eid in evidence_ids:
        if not re.search(rf"^- {re.escape(eid)}:\s*PASS\b", text, re.M):
            out.append(f"evidence {eid} not recorded as PASS in the exit log")
    if not re.search(r"^Reviewed by:\s*\S+.*\(.+\)\s*$", text, re.M):
        out.append("missing line 'Reviewed by: <name> (<model>)' (a different model than the author)")
    return out


def run_checks():
    problems = []
    for label, cmd in CHECKS:
        p = ROOT / cmd[0]
        if not p.exists():
            print(f"SKIP  {label} (not present)")
            continue
        r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0
        print(("PASS  " if ok else "FAIL  ") + label)
        if not ok:
            problems.append(f"{label} failed: {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
    for path, label in SUITES:
        if not (ROOT / path).is_dir():
            print(f"SKIP  {label} (no {path})")
            continue
        r = subprocess.run([sys.executable, "-m", "pytest", path, "-q"], cwd=ROOT, capture_output=True, text=True)
        if "No module named pytest" in (r.stdout + r.stderr):
            print(f"FAIL  {label} (pytest not installed)")
            problems.append(f"{label}: install pytest and the suite's requirements")
            continue
        ok = r.returncode == 0
        print(("PASS  " if ok else "FAIL  ") + label)
        if not ok:
            problems.append(f"{label} failed")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--skip-run", action="store_true", help="do not run the repo checks and test suites")
    a = ap.parse_args()
    phases, err = load_criteria()
    if err:
        print("FAIL  " + err)
        return 1
    if a.list or not a.phase:
        for k, v in phases.items():
            print(f"{k}: {v.get('title', '')}")
        return 0
    spec = phases.get(a.phase)
    if not spec:
        print(f"FAIL  unknown phase '{a.phase}' (see --list)")
        return 1
    problems = [] if a.skip_run else run_checks()
    rows, perrs = parse_plan()
    problems += perrs
    problems += plan_rows_problems(rows, spec.get("plan_rows", []))
    ids = [e["id"] for e in spec.get("evidence", [])]
    log = find_exit_log(a.phase, log_files())
    if not log:
        problems.append(f"no session log with the line 'Phase exit: {a.phase}'")
    else:
        problems += evidence_problems(log.read_text(encoding="utf-8"), ids)
        print(f"exit log: docs/log/{log.name}")
    if problems:
        print(f"\nPHASE {a.phase} NOT CLOSED. Fix:")
        for p in problems:
            print("  - " + str(p))
        print("\nEvidence required:")
        for e in spec.get("evidence", []):
            print(f"  - {e['id']}: {e['text']}")
        return 1
    print(f"\nPHASE {a.phase} CLOSED. Tell the founders; the other founder reviews the exit log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
