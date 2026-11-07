"""Run a set through an adapter, summarise, apply the optional threshold gate."""
import json
import os
from collections import defaultdict

from .adapters import get_adapter
from .records import SETS_DIR, load_set
from .scorers import score_record


def _rate(p, t):
    return round(p / t, 4) if t else 0.0


def run_set(name: str, adapter_name: str, sets_dir: str = SETS_DIR) -> dict:
    records, errors = load_set(name, sets_dir)
    if errors:
        raise ValueError("set has validation errors; run `check` first:\n" + "\n".join(errors[:20]))
    if not records:
        raise ValueError(f"set '{name}' not found or has no records in {sets_dir}")
    adapter = get_adapter(adapter_name)
    cat, dia = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    failures, passed = [], 0
    for rec in records:
        ok, reasons = score_record(rec, adapter.respond(rec))
        passed += ok
        for table, key in ((cat, rec["category"]), (dia, rec["dialect"])):
            table[key][0] += ok
            table[key][1] += 1
        if not ok:
            failures.append({"id": rec["id"], "reasons": reasons})
    table = lambda t: {k: {"passed": p, "total": n, "pass_rate": _rate(p, n)} for k, (p, n) in sorted(t.items())}
    return {"set": name, "adapter": adapter_name, "total": len(records), "passed": passed,
            "pass_rate": _rate(passed, len(records)), "by_category": table(cat), "by_dialect": table(dia),
            "failures": failures}


def load_threshold(name: str, sets_dir: str = SETS_DIR):
    """min_pass_rate from sets/<name>/thresholds.json, or None when absent (no gate)."""
    path = os.path.join(sets_dir, name, "thresholds.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return float(json.load(f)["min_pass_rate"])


def gate(report: dict, threshold):
    """Attach threshold info to the report; return True when the gate passes."""
    report["min_pass_rate"] = threshold
    report["gate_passed"] = threshold is None or report["pass_rate"] >= threshold
    return report["gate_passed"]
