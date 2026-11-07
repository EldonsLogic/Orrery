"""CLI: python3 -m evals.harness check | run --set NAME --adapter NAME [--out PATH]"""
import argparse
import json
import sys

from .records import SETS_DIR, counts, list_sets, load_set
from .runner import gate, load_threshold, run_set


def cmd_check(args) -> int:
    all_records, all_errors = [], []
    for name in list_sets(args.sets_dir):
        recs, errs = load_set(name, args.sets_dir)
        all_records += recs
        all_errors += errs
    summary = counts(all_records)
    print(f"records: {summary['total']}")
    for label, key in (("category", "by_category"), ("dialect", "by_dialect")):
        for k, v in summary[key].items():
            print(f"  {label} {k}: {v}")
    for e in all_errors:
        print(f"ERROR {e}", file=sys.stderr)
    if all_errors:
        print(f"{len(all_errors)} error(s)", file=sys.stderr)
        return 1
    print("ok")
    return 0


def cmd_run(args) -> int:
    try:
        report = run_set(args.set, args.adapter, args.sets_dir)
    except (ValueError, KeyError) as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    ok = gate(report, load_threshold(args.set, args.sets_dir))
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    if not ok:
        print(f"GATE FAILED: pass_rate {report['pass_rate']} < min_pass_rate {report['min_pass_rate']}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m evals.harness")
    p.add_argument("--sets-dir", default=SETS_DIR, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate all sets").set_defaults(fn=cmd_check)
    r = sub.add_parser("run", help="run a set through an adapter")
    r.add_argument("--set", required=True)
    r.add_argument("--adapter", required=True)
    r.add_argument("--out")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
