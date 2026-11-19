"""CLI: python3 -m exceptions append|summary|reconcile REGISTER ...

From services/blueprint, or from the repo root with PYTHONPATH=services/blueprint. REGISTER is a path outside the
repo (the private tenant record); this tool never picks or creates a default location.

  append REGISTER --date D --tenant T --rev R --pointer P --edit TEXT --reason TEXT --class C --automation TEXT
         --owner O [--follow-up TEXT] [--corrects ID]     (or --json FILE|- with a whole row as a JSON object)
  summary REGISTER                                         counts by class and tenant, as JSON
  reconcile REGISTER --metrics FILE [--tenant T] [--revision R]
         FILE is the JSON printed by `python3 -m metrics autonomy`; its `manual` and `removed` are the human edits.

Exit 0 ok, 1 findings (reconcile mismatch, unreadable or corrupt register), 2 refusal (row or input refused).
`ERROR <code> <message>` goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "exceptions"

from .errors import ExceptionsError  # noqa: E402
from .report import reconcile, summary  # noqa: E402
from .store import append  # noqa: E402

MAX_IN = 1024 * 1024


def _json(src: str):
    try:
        raw = sys.stdin.read(MAX_IN + 1) if src == "-" else Path(src).read_text(encoding="utf-8")
        if len(raw) > MAX_IN:
            raise ExceptionsError("EXC-IN-001", "input over 1 MiB")
        return json.loads(raw)
    except (OSError, ValueError, RecursionError):
        raise ExceptionsError("EXC-IN-001", "input unreadable or not valid JSON") from None


def _row(a) -> dict:
    if a.json:
        return _json(a.json)
    row = {"date": a.date, "tenant": a.tenant, "blueprint_rev": a.rev, "element_pointer": a.pointer,
           "edited_by_hand": a.edit, "reason": a.reason, "class": a.cls, "proposed_automation": a.automation,
           "owner": a.owner}
    if a.follow_up is not None:
        row["follow_up"] = a.follow_up
    if a.corrects is not None:
        row["corrects"] = a.corrects
    return {k: v for k, v in row.items() if v is not None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="exceptions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("append")
    p.add_argument("register")
    p.add_argument("--json")
    for flag, dest in (("date", "date"), ("tenant", "tenant"), ("rev", "rev"), ("pointer", "pointer"),
                       ("edit", "edit"), ("reason", "reason"), ("class", "cls"), ("automation", "automation"),
                       ("owner", "owner"), ("follow-up", "follow_up")):
        p.add_argument("--" + flag, dest=dest)
    p.add_argument("--corrects", type=int)
    sub.add_parser("summary").add_argument("register")
    r = sub.add_parser("reconcile")
    r.add_argument("register")
    r.add_argument("--metrics", required=True)
    r.add_argument("--tenant")
    r.add_argument("--revision")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "append":
            out = append(args.register, _row(args))
        elif args.cmd == "summary":
            out = summary(args.register)
        else:
            m = _json(args.metrics)
            if not isinstance(m, dict):
                raise ExceptionsError("EXC-IN-001", "metrics: expected the JSON object of `metrics autonomy`")
            edits = [*(m.get("manual") or []), *(m.get("removed") or [])]
            out = reconcile(args.register, edits, args.tenant or m.get("tenant"),
                            args.revision if args.revision is not None else m.get("revision"))
    except ExceptionsError as e:
        print(f"ERROR {e.code} {e.message}", file=sys.stderr)
        return 1 if e.code.startswith("EXC-FILE-002") or e.code == "EXC-FILE-001" else 2
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
