#!/usr/bin/env python3
"""Phase and gate exit check (docs/RULES.md rule 48, docs/GATES.md).

A phase or gate closes only after an exit run is recorded. This script:
  1. runs the automated repo checks and the test suites that exist (all required, none skipped);
  2. reads docs/specs/phase-exit-criteria.json for the phase or gate: plan rows that must be `done`
     (for a gate, every plan row in that gate) and the evidence items;
  3. finds a session log whose header (first lines) says `Phase exit: <name>`, records every evidence
     item as `- <evidence-id>: PASS <note or link>`, and has `Reviewed by: <name> (<model>)` where the
     reviewer is the other founder or used a different model than the log's author.
Exit 0 only if every part passes. The log is a record, not proof: the other founder's review of it is the
real control. Never edit the criteria or the log to make a failing run pass.

Usage:
  python3 scripts/phase_exit_check.py --list
  python3 scripts/phase_exit_check.py --phase 1A
  python3 scripts/phase_exit_check.py --phase G0
  python3 scripts/phase_exit_check.py --phase 1A --skip-run   # dry run; never closes a phase (exit 2)
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
FOUNDERS = ("eldon", "partner")
CHECKS = [
    ("docs gate", ["scripts/check_docs.py"]),
    ("repo hygiene", ["scripts/check_repo_hygiene.py"]),
    ("secret scan", ["scripts/scan_secrets.py"]),
    ("plan independence", ["scripts/check_plan_independence.py"]),
]
SUITES = [("services/blueprint/tests", "blueprint tests"), ("evals/tests", "eval tests"),
          ("services/discovery/tests", "discovery tests"), ("scripts/tests", "script tests")]
HEADER_LINES = 14


def load_criteria(path=CRITERIA):
    if not path.exists():
        return None, f"missing {path.as_posix()}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"invalid JSON in criteria file: {e}"
    return data.get("phases", {}), None


def plan_rows_problems(rows, wanted, gate=None):
    by = {r["ID"]: r for r in rows}
    out = []
    for pid in wanted:
        r = by.get(pid)
        if not r:
            out.append(f"plan row {pid} does not exist")
        elif r["Status"] != "done":
            out.append(f"plan row {pid} is {r['Status']}, must be done")
    if gate:
        for r in rows:
            if r["Gate"] == gate and r["Status"] != "done":
                out.append(f"plan row {r['ID']} (gate {gate}) is {r['Status']}, must be done")
    return out


def find_exit_log(phase, logs):
    """Return the newest log whose header lines say `Phase exit: <phase>`."""
    pat = re.compile(rf"^Phase exit:\s*{re.escape(phase)}\s*$", re.I)
    for f in logs:  # newest first
        head = f.read_text(encoding="utf-8").splitlines()[:HEADER_LINES]
        if any(pat.match(line) for line in head):
            return f
    return None


def evidence_problems(text, evidence_ids):
    out = []
    if not evidence_ids:
        out.append("the criteria define no evidence items for this phase")
    for eid in evidence_ids:
        lines = re.findall(rf"^- {re.escape(eid)}:\s*(.*)$", text, re.M)
        if not lines:
            out.append(f"evidence {eid} is not recorded in the exit log")
            continue
        if any(not re.match(r"PASS\b", l) for l in lines):
            out.append(f"evidence {eid} has a line that is not PASS (a FAIL or a malformed entry)")
            continue
        if any(len(l[4:].strip(" -:.")) < 3 for l in lines):
            out.append(f"evidence {eid} needs a note or link after PASS")
    m = re.search(r"^Reviewed by:\s*(.+?)\s*\((.+)\)\s*$", text, re.M)
    if not m:
        out.append("missing line 'Reviewed by: <name> (<model>)'")
        return out
    reviewer, rmodel = m.group(1).strip().lower(), m.group(2).strip().lower()
    author = (re.search(r"^Author:\s*(\S+)", text, re.M) or [None, ""])[1].lower()
    amodel = (re.search(r"^Tool and model:\s*(.+)$", text, re.M) or [None, ""])[1].lower()
    other_founder = reviewer in FOUNDERS and reviewer != author
    other_model = bool(rmodel) and rmodel not in amodel and amodel not in rmodel
    if not (other_founder or other_model):
        out.append("the reviewer must be the other founder or use a different model than the log's author")
    return out


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def run_checks():
    problems = []
    for label, cmd in CHECKS:
        if not (ROOT / cmd[0]).exists():
            print(f"FAIL  {label} (script {cmd[0]} is missing)")
            problems.append(f"{label}: script {cmd[0]} is missing")
            continue
        rc, o = run([sys.executable, *cmd])
        print(("PASS  " if rc == 0 else "FAIL  ") + label)
        if rc != 0:
            problems.append(f"{label} failed: {o.splitlines()[-1] if o else ''}")
    rc, base = run(["git", "merge-base", "origin/main", "HEAD"])
    if rc == 0 and base:
        rc, o = run([sys.executable, "scripts/check_lanes.py", "--base", base, "--head", "HEAD"])
        print(("PASS  " if rc == 0 else "FAIL  ") + "lane guard")
        if rc != 0:
            problems.append(f"lane guard failed: {o.splitlines()[-1] if o else ''}")
    else:
        print("FAIL  lane guard (cannot find origin/main; run git fetch)")
        problems.append("lane guard: cannot compute the merge base with origin/main")
    for path, label in SUITES:
        if not (ROOT / path).is_dir():
            continue  # a suite that does not exist yet is not part of the repo yet
        rc, o = run([sys.executable, "-m", "pytest", path, "-q"])
        if "No module named pytest" in o:
            print(f"FAIL  {label} (pytest not installed)")
            problems.append(f"{label}: install pytest and the suite's requirements")
            continue
        print(("PASS  " if rc == 0 else "FAIL  ") + label)
        if rc != 0:
            problems.append(f"{label} failed")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--skip-run", action="store_true", help="dry run: skip checks and tests; never closes a phase")
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
        print(f"FAIL  unknown phase or gate '{a.phase}' (see --list)")
        return 1
    problems = [] if a.skip_run else run_checks()
    rows, perrs = parse_plan()
    problems += perrs
    problems += plan_rows_problems(rows, spec.get("plan_rows", []), spec.get("gate"))
    ids = [e["id"] for e in spec.get("evidence", [])]
    log = find_exit_log(a.phase, log_files())
    if not log:
        problems.append(f"no session log with 'Phase exit: {a.phase}' in its header")
    else:
        problems += evidence_problems(log.read_text(encoding="utf-8"), ids)
        print(f"exit log: docs/log/{log.name}")
    if problems:
        print(f"\n{a.phase} NOT CLOSED. Fix:")
        for p in problems:
            print("  - " + str(p))
        print("\nEvidence required:")
        for e in spec.get("evidence", []):
            print(f"  - {e['id']}: {e['text']}")
        return 1
    if a.skip_run:
        print(f"\n{a.phase}: criteria and log look complete, but this was a dry run (--skip-run). Run without it to close.")
        return 2
    print(f"\n{a.phase} CLOSED. Tell the founders; the other founder reviews the exit log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
