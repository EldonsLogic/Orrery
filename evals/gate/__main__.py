"""python3 -m evals.gate [--json PATH] [--suite NAME ...] [--update-baseline --reason TEXT]

Runs every deterministic eval suite offline, applies evals/gate/thresholds.json and compares with the committed
evals/gate/baseline.json. Exit 0 pass, 1 gate failed, 2 usage or setup error. The baseline changes only with
--update-baseline and a reason, which is appended to evals/gate/baseline-history.json; never in CI.
"""
import argparse
import datetime
import json
import os
import sys

from . import core, suites


def collect(names=None):
    results, errors = {}, []
    for name, fn in sorted(suites.SUITES.items()):
        if names and name not in names:
            continue
        try:
            results[name] = fn()
        except Exception as e:  # a suite that crashes is a failed suite, never a skipped one
            errors.append(f"{name}: suite crashed: {type(e).__name__}: {e}")
    return results, errors


def run(results, errors, args, thresholds=None, baseline=None, markers=None):
    thresholds = thresholds or core.load_thresholds()
    if baseline is None and os.path.exists(core.BASELINE):
        baseline = core._load(core.BASELINE)
    markers = markers or core.scan_markers()
    results = core.apply_known_gaps(results, thresholds)
    if args.suite:  # a partial run cannot be compared as a whole
        thresholds = dict(thresholds, suites={k: v for k, v in thresholds["suites"].items() if k in args.suite})
        baseline = baseline and dict(baseline, suites={k: v for k, v in baseline["suites"].items() if k in args.suite})
    verdict = core.evaluate(results, thresholds, baseline, markers)
    verdict["floor_failures"] = errors + verdict["floor_failures"]
    verdict["ok"] = verdict["ok"] and not errors
    return verdict, thresholds, baseline, markers, results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evals.gate")
    ap.add_argument("--suite", action="append", help="run only this suite (repeatable); not for release")
    ap.add_argument("--json", help="write the compared report (sorted, no timestamps) to this path")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--reason", help="required with --update-baseline; recorded in baseline-history.json")
    args = ap.parse_args(argv)
    unknown = set(args.suite or []) - set(suites.SUITES)
    if unknown:
        print(f"ERROR unknown suite(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    results, errors = collect(args.suite)
    verdict, thresholds, baseline, markers, results = run(results, errors, args)
    print(core.table(results, verdict))
    for k, label in (("floor_failures", "FAIL"), ("regressions", "REGRESSION"), ("notes", "note")):
        for line in verdict[k]:
            print(f"{label}: {line}", file=sys.stderr if k != "notes" else sys.stdout)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"verdict": verdict, "report": core.condense(results), "markers": markers}, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    if args.update_baseline:
        if args.suite:
            print("ERROR baseline update needs a full run (no --suite)", file=sys.stderr)
            return 2
        if os.environ.get("CI"):
            print("ERROR the baseline is never updated in CI", file=sys.stderr)
            return 2
        if not (args.reason or "").strip():
            print("ERROR --update-baseline needs --reason", file=sys.stderr)
            return 2
        if verdict["floor_failures"]:
            print("ERROR refusing to record a baseline that violates a floor, ceiling, case minimum or has failing cases", file=sys.stderr)
            return 1
        new = core.new_baseline(results, markers)
        hist = core._load(core.HISTORY) if os.path.exists(core.HISTORY) else []
        hist.append(core.history_entry(baseline, new, args.reason.strip(), core.git_user(), datetime.date.today().isoformat()))
        for path, data in ((core.BASELINE, new), (core.HISTORY, hist)):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
        print("baseline updated; record it in your session log and commit baseline.json and baseline-history.json")
        return 0
    if verdict["ok"]:
        print("GATE PASSED")
        return 0
    print("GATE FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
