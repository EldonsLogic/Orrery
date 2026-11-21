"""QA-010: the release gate. Pure-logic tests on fabricated results, then the real suites, then broken controls
that must make the gate fail."""
import copy
import json
import os

import pytest

from evals.gate import __main__ as gate_main
from evals.gate import core, suites

TH = {"markers": {"max_skip": 0}, "suites": {"s": {"min_cases": 3, "max_regression": 0.0, "known_gaps": ["c3"],
      "metrics": {"acc": {"min": 0.9}, "bad": {"max": 0}}}}}


def res(cases=None, acc=1.0, bad=0):
    return {"s": {"cases": cases or {"c1": "pass", "c2": "pass", "c3": "xfail"}, "metrics": {"acc": acc, "bad": bad}}}


MK = {"skip": 0, "xfail": 1}
BASE = core.new_baseline(res(), MK)


def verdict(r, base=BASE, mk=MK, th=TH):
    return core.evaluate(core.apply_known_gaps(r, th), th, base, mk)


def test_clean_run_passes():
    v = verdict(res())
    assert v["ok"] and not v["floor_failures"] and not v["regressions"]


def test_category_under_floor_fails():
    assert any("below floor" in x for x in verdict(res(acc=0.8))["floor_failures"])


def test_ceiling_fails():
    assert any("above ceiling" in x for x in verdict(res(bad=1))["floor_failures"])


def test_regression_beyond_limit_fails_even_above_floor():
    base = core.new_baseline(res(acc=1.0), MK)
    v = verdict(res(acc=0.95), base)
    assert not v["ok"] and any("regressed 1.0 -> 0.95" in x for x in v["regressions"])


def test_regression_within_allowed_limit_passes():
    th = copy.deepcopy(TH)
    th["suites"]["s"]["max_regression"] = 0.1
    assert verdict(res(acc=0.95), core.new_baseline(res(acc=1.0), MK), th=th)["ok"]


def test_missing_suite_fails():
    v = core.evaluate({}, TH, BASE, MK)
    assert not v["ok"] and any("suite missing" in x for x in v["floor_failures"])


def test_case_count_below_minimum_fails():
    assert any("needs at least 3" in x for x in verdict(res({"c1": "pass", "c2": "pass"}))["floor_failures"])


def test_vanished_case_is_a_silent_skip_and_fails():
    v = verdict(res({"c1": "pass", "c2": "pass", "c4": "pass"}))
    assert any("c3 was xfail in baseline and is gone" in x for x in v["regressions"])


def test_new_failure_not_in_known_gaps_fails_and_known_gap_does_not():
    assert verdict(res({"c1": "pass", "c2": "fail", "c3": "fail"}))["floor_failures"][0].startswith("s: 1 failing case")


def test_pass_to_xfail_is_a_regression():
    th = copy.deepcopy(TH)
    th["suites"]["s"]["known_gaps"] = ["c2", "c3"]
    assert any("c2 regressed pass -> xfail" in x for x in verdict(res({"c1": "pass", "c2": "fail", "c3": "fail"}), th=th)["regressions"])


def test_xfail_turned_skip_marker_fails():
    assert any("skip marker" in x for x in verdict(res(), mk={"skip": 1, "xfail": 0})["regressions"])
    assert any("xfail markers fell" in x for x in verdict(res(), mk={"skip": 0, "xfail": 0})["regressions"])


def test_fixed_known_gap_is_a_note_not_a_failure():
    v = verdict(res({"c1": "pass", "c2": "pass", "c3": "pass"}))
    assert v["ok"] and any("now passes" in n for n in v["notes"])


def test_missing_baseline_fails():
    assert not core.evaluate(res(), TH, None, MK)["ok"]


def test_condense_is_sorted_and_has_no_clock():
    a = core.condense({"s": {"cases": {"b": "pass", "a": "pass"}, "metrics": {"z": 1, "y": 2}}})
    assert a["s"]["cases"]["pass"] == ["a", "b"] and list(a["s"]["metrics"]) == ["y", "z"]
    assert "20" not in json.dumps(a)  # no dates


def test_table_is_compact_and_marks_failures():
    t = core.table(res(acc=0.5), verdict(res(acc=0.5)))
    assert t.splitlines()[0].startswith("suite") and "FAIL" in t and len(t.splitlines()) == 2


def test_marker_scan_counts_this_repos_xfail_and_no_skip():
    m = core.scan_markers()
    assert m["xfail"] >= 1 and m["skip"] == 0


def test_history_entry_lists_metric_changes():
    h = core.history_entry(BASE, core.new_baseline(res(acc=0.5), MK), "why", "me", "2026-01-01")
    assert h["metric_changes"] == ["s.acc: 1.0 -> 0.5"] and h["reason"] == "why"


# ---- the real thing ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real():
    results, errors = gate_main.collect()
    return results, errors


def run_real(results, errors, *argv):
    args = gate_main.argparse.Namespace(suite=None)
    return gate_main.run(results, errors, args)[0]


def test_real_suites_pass_against_committed_baseline(real):
    v = run_real(*real)
    assert v["ok"], v


def test_every_suite_is_wired_and_has_thresholds_and_baseline():
    th, base = core.load_thresholds(), json.load(open(core.BASELINE))
    assert set(suites.SUITES) == set(th["suites"]) == set(base["suites"])


def test_agent_behaviour_floors_come_from_its_own_file():
    m = core.load_thresholds()["suites"]["agent_behaviour"]["metrics"]
    assert m["overall"] == {"min": 1.0} and m["cat.refusal"] == {"min": 1.0} and m["cases.refusal"] == {"min": 20}


def test_two_runs_are_identical(real):
    again, _ = gate_main.collect()
    assert core.condense(real[0]) == core.condense(again)


def test_committed_baseline_equals_current_run(real):
    """Catches a forgotten baseline update after cases were added or a known gap closed."""
    cur = core.condense(core.apply_known_gaps(real[0], core.load_thresholds()))
    assert cur == json.load(open(core.BASELINE))["suites"]


# ---- deliberately broken controls: the gate must fail ----------------------------------------------------------
def test_control_silent_agent_fails_the_gate():
    results, errors = gate_main.collect(["injection", "arabic_core"])
    results["agent_behaviour"] = suites.agent_behaviour(arm="silent")
    v = gate_main.run(results, errors, gate_main.argparse.Namespace(suite=None))[0]
    assert not v["ok"] and any(x.startswith("agent_behaviour") for x in v["floor_failures"])


def test_control_permissive_injection_defence_fails_the_gate():
    results, _ = gate_main.collect(["agent_behaviour", "arabic_core"])
    results["injection"] = suites.injection_suite(adapter="permissive")
    v = gate_main.run(results, [], gate_main.argparse.Namespace(suite=None))[0]
    assert not v["ok"] and any("injection: blocking_rate" in x for x in v["floor_failures"])


def test_control_dropped_suite_fails(real):
    results = {k: v for k, v in real[0].items() if k != "sim_accuracy"}
    v = gate_main.run(results, [], gate_main.argparse.Namespace(suite=None))[0]
    assert not v["ok"] and any("sim_accuracy: suite missing" in x for x in v["floor_failures"])


def test_control_crashing_suite_fails(real, monkeypatch):
    monkeypatch.setitem(suites.SUITES, "injection", lambda: 1 / 0)
    results, errors = gate_main.collect(["injection"])
    assert errors and "crashed" in errors[0]


def test_cli_exit_codes(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CI", raising=False)
    assert gate_main.main(["--suite", "nope"]) == 2
    assert gate_main.main(["--suite", "sim_accuracy", "--update-baseline", "--reason", "x"]) == 2  # partial run
    assert gate_main.main(["--update-baseline"]) == 2  # no reason
    monkeypatch.setenv("CI", "true")
    assert gate_main.main(["--update-baseline", "--reason", "x"]) == 2  # never in CI
    monkeypatch.delenv("CI")
    assert gate_main.main(["--suite", "sim_accuracy", "--json", str(tmp_path / "r.json")]) == 0
    assert "verdict" in json.loads((tmp_path / "r.json").read_text())


def test_baseline_update_refused_while_a_floor_is_broken(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setitem(suites.SUITES, "injection", lambda: suites.injection_suite(adapter="permissive"))
    before = open(core.BASELINE).read()
    assert gate_main.main(["--update-baseline", "--reason", "try to bless a broken defence"]) == 1
    assert open(core.BASELINE).read() == before
