#!/usr/bin/env python3
"""Print what a session needs first: gate, latest 3 log summaries, doing items."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import parse_plan, current_gate, log_files, log_summary


def main():
    print(f"Current gate: {current_gate()}")
    print("\nLatest logs:")
    logs = log_files()[:3]
    for f in logs:
        print(f"- {f.name}: {log_summary(f)}")
    if not logs:
        print("- none yet")
    rows, _ = parse_plan()
    print("\nDoing:")
    doing = [r for r in rows if r["Status"] == "doing"]
    for r in doing:
        print(f"- {r['ID']} [{r['Owner']}] {r['Item']}")
    if not doing:
        print("- none")
    print("\nNext: read docs/STATUS.md, then pick a todo item whose Depends are all done.")


if __name__ == "__main__":
    main()
