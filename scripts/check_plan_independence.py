#!/usr/bin/env python3
"""Plan independence check: the two founders' work never blocks each other (ADR-0025).

Rules over docs/PLAN.md, for every row that is not done:
1. It has an owner (eldon or partner), never "unassigned".
2. If it depends on a row owned by the other founder that is not done, that row must be in an EARLIER gate.
   Inside one gate the two lanes are therefore independent; cross-lane needs are met by interface rows
   (contracts, fakes, fixtures) scheduled a gate earlier.
Dependencies are listed in the Depends column. Exit 1 with one line per violation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import parse_plan, GATES


def check(rows):
    by = {r["ID"]: r for r in rows}
    errors = []
    for r in rows:
        if r["Status"] == "done":
            continue
        if r["Owner"] == "unassigned":
            errors.append(f"PLAN.md:{r['line']}: {r['ID']} has no owner (assign eldon or partner)")
            continue
        for d in [x.strip() for x in r["Depends"].replace(" ", ",").split(",") if x.strip() and x.strip() != "-"]:
            dep = by.get(d)
            if not dep or dep["Status"] == "done":
                continue
            if dep["Owner"] != r["Owner"] and GATES.index(dep["Gate"]) >= GATES.index(r["Gate"]):
                errors.append(
                    f"PLAN.md:{r['line']}: {r['ID']} ({r['Owner']}, {r['Gate']}) depends on {d} "
                    f"({dep['Owner']}, {dep['Gate']}); the other founder's row must be in an earlier gate "
                    f"or replaced by an interface row (contract, fake or fixture)")
    return errors


def main():
    rows, perrs = parse_plan()
    errs = perrs + check(rows)
    for e in errs:
        print(e)
    print("Plan independence OK" if not errs else f"Plan independence FAILED ({len(errs)})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
