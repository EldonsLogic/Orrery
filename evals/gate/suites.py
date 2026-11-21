"""Collectors: run one deterministic suite offline and return a plain result.

Result shape: {"cases": {case_id: "pass" | "fail" | "xfail"}, "metrics": {name: number}}.
"xfail" is a known, documented gap (a case the corpus marks as expected to fail today). Everything here is
deterministic: no clocks, no latency, no network, no model. Numbers come from the suites' own scorers.
"""
from evals.harness import agent_behaviour as ab
from evals.harness import injection, intent_routing, redteam, runner, sim_accuracy
from evals.harness.records import load_set


def arabic_core(adapter="echo_expected", control_adapter="null"):
    """Oracle must score 100 percent and the null adapter 0 percent: proves set and scorer still agree.
    (The 0.85 model-arm floor in sets/arabic_core/thresholds.json belongs to the real-model run, Q-460.)"""
    rep = runner.run_set("arabic_core", adapter)
    ctl = runner.run_set("arabic_core", control_adapter)
    failed = {f["id"] for f in rep["failures"]}
    ids = [r["id"] for r in load_set("arabic_core")[0]]
    return {"cases": {i: ("fail" if i in failed else "pass") for i in ids},
            "metrics": {"oracle_pass_rate": rep["pass_rate"], "null_control_pass_rate": ctl["pass_rate"]}}


def injection_suite(adapter="oracle", control_adapter="permissive"):
    """Platform behaviour under injection. The permissive control must keep failing (the scorer still bites)."""
    rep = injection.run_set(adapter)
    ctl = injection.run_set(control_adapter)
    return {"cases": {c["id"]: ("pass" if c["passed"] else "fail") for c in rep["cases"]},
            "metrics": {"pass_rate": rep["pass_rate"], "blocking_rate": rep["blocking_rate"],
                        "detection_rate": rep["detection_rate"], "task_success_rate": rep["task_success_rate"],
                        "permissive_control_blocking_rate": ctl["blocking_rate"]}}


def agent_behaviour(arm="scripted"):
    cases, errors = ab.load_cases()
    if errors:
        raise ValueError("; ".join(errors))
    results = ab.evaluate(cases, ab.load_catalog(), arm)
    rep = ab.score(results)
    metrics = {"overall": rep["pass_rate"]}
    metrics.update({f"cat.{k}": v["pass_rate"] for k, v in rep["by_category"].items()})
    counts = {f"cases.{k}": v["total"] for k, v in rep["by_category"].items()}
    return {"cases": {r["id"]: ("pass" if r["passed"] else "fail") for r in results},
            "metrics": metrics, "counts": counts}


def sim_accuracy_suite():
    s = sim_accuracy.score()
    bad = set(s["faults"]["undetected"]) | set(s["clean"]["falsePositiveMonths"])
    ids = [m["id"] for m in sim_accuracy.CLEAN_MONTHS] + [f["id"] for f in sim_accuracy.FAULTS]
    return {"cases": {i: ("fail" if i in bad else "pass") for i in ids},
            "metrics": {"detection_permille": s["faults"]["detectionPermille"],
                        "false_positive_permille": s["clean"]["falsePositivePermille"]}}


def intent_routing_suite():
    cases, errors = intent_routing.load_cases()
    if errors:
        raise ValueError("; ".join(errors))
    preds = intent_routing.run_rules(cases)
    by_id = {p["id"]: p for p in preds}
    s = intent_routing.score(cases, by_id)
    return {"cases": {c["id"]: ("pass" if by_id[c["id"]]["intent"] == c["expected_intent"] else "fail") for c in cases},
            "metrics": {"accuracy": s["accuracy"], "macro_f1": s["macro_f1"],
                        "wrong_risk_class_rate": s["wrong_risk_class_rate"],
                        "under_classified_rate": s["under_classified_rate"],
                        "missing_predictions": s["missing_predictions"], "unknown_intents": s["unknown_intents"]}}


def redteam_uploads():
    """Known gaps are the corpus's own xfail cases: they count as xfail, a breach as a failure."""
    rep = redteam.run_corpus()
    status = {"blocked": "pass", "neutralised": "pass", "gap": "xfail"}
    return {"cases": {v["id"]: status.get(v["outcome"], "fail") for v in rep["verdicts"]},
            "metrics": {"breach": rep["outcomes"].get("breach", 0), "gaps": len(rep["gaps"])}}


SUITES = {
    "agent_behaviour": agent_behaviour,
    "arabic_core": arabic_core,
    "injection": injection_suite,
    "intent_routing": intent_routing_suite,
    "redteam_uploads": redteam_uploads,
    "sim_accuracy": sim_accuracy_suite,
}
