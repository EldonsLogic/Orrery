"""Gate logic: pure functions over suite results, thresholds and a committed baseline. No I/O except load helpers."""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
THRESHOLDS = os.path.join(HERE, "thresholds.json")
BASELINE = os.path.join(HERE, "baseline.json")
HISTORY = os.path.join(HERE, "baseline-history.json")
TESTS_DIR = os.path.join(REPO, "evals", "tests")
STATUSES = ("pass", "fail", "xfail")
MARKER_PATTERNS = {
    "skip": r"mark\.skip\b|mark\.skipif\b|pytest\.skip\(|importorskip\(|unittest\.skip",
    "xfail": r"mark\.xfail\b|pytest\.xfail\(",
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_thresholds(path=THRESHOLDS, repo=REPO):
    """Central thresholds, with agent_behaviour's own file folded in (single source for its floors)."""
    th = _load(path)
    for name, block in list(th["suites"].items()):
        src = block.get("from_suite_file")
        if not src:
            continue
        own = _load(os.path.join(repo, src))
        m = dict(block.get("metrics", {}))
        if "overall_min" in own:
            m["overall"] = {"min": own["overall_min"]}
        for cat, floor in own.get("category_min", {}).items():
            m[f"cat.{cat}"] = {"min": floor}
        for cat, n in own.get("min_cases", {}).items():
            m[f"cases.{cat}"] = {"min": n}
        th["suites"][name] = dict(block, metrics=m, max_regression=own.get("max_regression", block.get("max_regression", 0.0)))
    return th


def scan_markers(tests_dir=TESTS_DIR):
    """Static count of skip and xfail markers in the eval tests, so a silent xfail-to-skip swap shows up."""
    counts = {k: 0 for k in MARKER_PATTERNS}
    for fn in sorted(os.listdir(tests_dir)):
        if fn.endswith(".py"):
            with open(os.path.join(tests_dir, fn), encoding="utf-8") as f:
                text = f.read()
            for k, pat in MARKER_PATTERNS.items():
                counts[k] += len(re.findall(pat, text))
    return counts


def condense(results):
    """Compare-ready, deterministic form: per suite sorted ids by status, plus metrics."""
    out = {}
    for name in sorted(results):
        r = results[name]
        cases = {s: sorted(i for i, v in r["cases"].items() if v == s) for s in STATUSES}
        out[name] = {"cases": {s: ids for s, ids in cases.items() if ids},
                     "metrics": dict(sorted(r["metrics"].items())), "counts": dict(sorted(r.get("counts", {}).items()))}
    return out


def apply_known_gaps(results, thresholds):
    """A failing case listed in the suite's committed `known_gaps` is an xfail, not a failure. Anything else that
    fails stays a failure, so a new miss cannot hide. A listed gap that passes is reported as a note by the baseline."""
    out = {}
    for name, r in results.items():
        gaps = set(thresholds["suites"].get(name, {}).get("known_gaps", []))
        cases = {i: ("xfail" if v == "fail" and i in gaps else v) for i, v in r["cases"].items()}
        out[name] = dict(r, cases=cases)
    return out


def _status_map(entry):
    return {i: s for s, ids in entry.get("cases", {}).items() for i in ids}


def floor_findings(results, thresholds):
    """Hard failures that do not depend on the baseline: missing suite, floors, ceilings, case counts, failed cases."""
    f = []
    for name, block in sorted(thresholds["suites"].items()):
        r = results.get(name)
        if r is None:
            f.append(f"{name}: suite missing from run (a suite that does not run is a failure, not a skip)")
            continue
        n = len(r["cases"])
        if n < block.get("min_cases", 0):
            f.append(f"{name}: {n} cases, needs at least {block['min_cases']}")
        have = {**r["metrics"], **r.get("counts", {})}
        for metric, bound in sorted(block.get("metrics", {}).items()):
            if metric not in have:
                f.append(f"{name}: metric {metric} missing")
                continue
            v = have[metric]
            if "min" in bound and v < bound["min"]:
                f.append(f"{name}: {metric} {v} below floor {bound['min']}")
            if "max" in bound and v > bound["max"]:
                f.append(f"{name}: {metric} {v} above ceiling {bound['max']}")
        bad = sorted(i for i, s in r["cases"].items() if s == "fail")
        if bad:
            f.append(f"{name}: {len(bad)} failing case(s): {', '.join(bad[:5])}{' ...' if len(bad) > 5 else ''}")
    for name in sorted(set(results) - set(thresholds["suites"])):
        f.append(f"{name}: suite has no thresholds block")
    return f


def baseline_findings(results, thresholds, baseline, markers):
    """Regressions against the committed baseline. Returns (failures, notes)."""
    f, notes = [], []
    if baseline is None:
        return ["baseline.json missing: run once with --update-baseline --reason ... and commit it"], notes
    for name in sorted(baseline["suites"]):
        base = baseline["suites"][name]
        cur = results.get(name)
        if cur is None:
            f.append(f"{name}: in baseline but not run")
            continue
        block = thresholds["suites"].get(name, {})
        tol, bounds = block.get("max_regression", 0.0), block.get("metrics", {})
        have = {**cur["metrics"], **cur.get("counts", {})}
        for metric, bv in sorted({**base.get("metrics", {}), **base.get("counts", {})}.items()):
            cv = have.get(metric)
            if cv is None:
                f.append(f"{name}: metric {metric} disappeared")
                continue
            bound = bounds.get(metric)
            if bound is None:
                continue
            worse = (cv - bv) if ("max" in bound and "min" not in bound) else (bv - cv)
            if worse > tol:
                f.append(f"{name}: {metric} regressed {bv} -> {cv} (allowed {tol})")
        bmap, cmap = _status_map(base), cur["cases"]
        for cid in sorted(bmap):
            now, was = cmap.get(cid), bmap[cid]
            if now is None:
                f.append(f"{name}: case {cid} was {was} in baseline and is gone (silently skipped or deleted)")
            elif was == "pass" and now != "pass":
                f.append(f"{name}: case {cid} regressed pass -> {now}")
            elif was == "xfail" and now == "fail":
                f.append(f"{name}: case {cid} was a known gap and now fails")
            elif was == "xfail" and now == "pass":
                notes.append(f"{name}: known gap {cid} now passes; update the baseline")
        new = sorted(set(cmap) - set(bmap))
        if new:
            notes.append(f"{name}: {len(new)} new case(s) not in baseline; update the baseline")
    bm = baseline.get("markers") or {}
    allowed_skip = max(bm.get("skip", 0), thresholds.get("markers", {}).get("max_skip", 0))
    if markers["skip"] > allowed_skip:
        f.append(f"pytest: {markers['skip']} skip marker(s), allowed {allowed_skip} (an xfail must not become a skip)")
    if markers["xfail"] < bm.get("xfail", 0):
        f.append(f"pytest: xfail markers fell {bm.get('xfail')} -> {markers['xfail']}; removing one needs a baseline update with a reason")
    return f, notes


def evaluate(results, thresholds, baseline, markers):
    hard = floor_findings(results, thresholds)
    reg, notes = baseline_findings(results, thresholds, baseline, markers)
    return {"ok": not hard and not reg, "floor_failures": hard, "regressions": reg, "notes": notes}


def table(results, verdict):
    """Compact fixed-width table, sorted by suite name."""
    failing = {f.split(":", 1)[0] for f in verdict["floor_failures"] + verdict["regressions"]}
    rows = [("suite", "cases", "pass", "xfail", "fail", "status")]
    for name in sorted(results):
        c = results[name]["cases"]
        cnt = lambda s: sum(1 for v in c.values() if v == s)
        rows.append((name, str(len(c)), str(cnt("pass")), str(cnt("xfail")), str(cnt("fail")),
                     "FAIL" if name in failing else "ok"))
    for name in sorted(failing - set(results)):
        rows.append((name, "-", "-", "-", "-", "FAIL"))
    w = [max(len(r[i]) for r in rows) for i in range(6)]
    return "\n".join("  ".join(x.ljust(w[i]) if i in (0, 5) else x.rjust(w[i]) for i, x in enumerate(r)) for r in rows)


def new_baseline(results, markers):
    return {"version": 1, "markers": markers, "suites": condense(results)}


def git_user():
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, cwd=REPO).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def history_entry(old, new, reason, author, date):
    def ms(b):
        return {n: s["metrics"] for n, s in (b or {"suites": {}})["suites"].items()}
    o, n = ms(old), ms(new)
    changed = sorted(f"{s}.{m}: {o.get(s, {}).get(m)} -> {v}" for s, d in n.items() for m, v in d.items()
                     if o.get(s, {}).get(m) != v)
    return {"date": date, "author": author, "reason": reason, "metric_changes": changed}
