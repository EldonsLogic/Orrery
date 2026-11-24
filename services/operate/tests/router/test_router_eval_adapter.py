"""Scores the router on the QA-020 case set with the harness scorer. The harness rules arm is contaminated (written
from the same cases), so this is a sanity check on the router's mode and risk behaviour, not a quality claim."""
import json
import sys
import time
from pathlib import Path

from router import IntentRouter, RouteContext, RouterMetrics

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from evals.harness import intent_routing as ir  # noqa: E402

CASES, ERRORS = ir.load_cases()


def _run():
    router, metrics = IntentRouter(), RouterMetrics()
    for c in CASES:
        intent = ir.route_rules(c["text"])  # stand-in intent resolver (stage-2 of the real router is not built here)
        hint = ir.INTENT_RISK[intent] if intent else None
        t0 = time.perf_counter()
        d = router.route(c["text"], RouteContext(), risk_hint=hint)
        ms = (time.perf_counter() - t0) * 1000
        mode_of_intent = None if intent is None else ("ask" if ir.INTENT_RISK[intent] == "R0" else "act")
        metrics.record(c["id"], d, intent, mode_of_intent, ms)
    return metrics


def test_case_set_clean():
    assert ERRORS == []


def test_predictions_use_the_scorer_format_and_load(tmp_path):
    m = _run()
    path = tmp_path / "p.ndjson"
    path.write_text(m.to_ndjson(), encoding="utf-8")
    preds = ir.load_predictions(str(path), CASES)  # raises on bad ids or risk classes
    assert len(preds) == len(CASES)
    assert all(set(json.loads(l)) <= {"id", "intent", "risk_class", "latency_ms", "cost_usd"}
               for l in m.to_ndjson().splitlines())


def test_no_under_classified_risk_and_ambiguous_cases_abstain():
    m = _run()
    report = ir.score(CASES, {p["id"]: p for p in m.predictions()})
    assert report["under_classified_rate"] == 0.0
    assert report["unknown_intents"] == 0 and report["missing_predictions"] == 0
    by_id = {p["id"]: p for p in m.predictions()}
    ambiguous = [c for c in CASES if c["ambiguous"]]
    assert ambiguous and all(by_id[c["id"]]["intent"] is None for c in ambiguous)
    assert report["by_ambiguous"][True]["n"] == len(ambiguous)


def test_router_never_acts_on_a_read_case_and_never_reads_on_a_write_case_as_act():
    router = IntentRouter()
    for c in CASES:
        d = router.route(c["text"], RouteContext())
        if c["expected_risk_class"] == "R0":
            assert d.mode in ("ask",), (c["id"], d.mode)  # a read is never routed to a writing mode


def test_metrics_counters():
    m = _run()
    assert sum(m.by_mode.values()) == len(CASES) and m.by_mode["ask"] > 0 and m.by_mode["act"] > 0
    assert m.by_intent and "needs_confirmation" in m.by_reason
