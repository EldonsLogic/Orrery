"""QA-005: agent behaviour evals. Offline: real runtime, chat and change code with fake ports, no model call."""
import copy
import json
from collections import Counter

import pytest

from evals.harness import agent_behaviour as ab

CASES, ERRORS = ab.load_cases()
CATALOG = ab.load_catalog()
NAMES = {d["name"] for d in CATALOG}


def row(cid, cat, loc, passed, failed=()):
    return {"id": cid, "category": cat, "locale": loc, "kind": "run", "passed": passed, "failed": list(failed)}


# ---- scorer and gate (pure) ----
def test_score_reports_pass_rate_per_category_and_locale():
    rows = [row("tc-en-001", "tool_choice", "en", True), row("tc-ar-001", "tool_choice", "ar", False, ["dispatched"]),
            row("rf-en-001", "refusal", "en", True)]
    rep = ab.score(rows)
    assert (rep["total"], rep["passed"], rep["pass_rate"]) == (3, 2, 0.6667)
    assert rep["by_category"]["tool_choice"] == {"total": 2, "passed": 1, "pass_rate": 0.5}
    assert rep["by_category"]["injection"] == {"total": 0, "passed": 0, "pass_rate": 0.0}
    assert rep["by_locale"]["ar"]["pass_rate"] == 0.0
    assert rep["failures"] == [{"id": "tc-ar-001", "category": "tool_choice", "failed": ["dispatched"]}]


def _rep(rates):
    rows = []
    for cat, (n, p) in rates.items():
        rows += [row(f"x-{cat}-{i}", cat, "en", i < p) for i in range(n)]
    return ab.score(rows)


def test_gate_fails_below_category_floor_and_names_the_category():
    ok, why = ab.gate(_rep({"tool_choice": (4, 4), "refusal": (4, 3)}), {"category_min": {"refusal": 1.0}})
    assert not ok and any("refusal" in r for r in why)


def test_gate_passes_at_the_floor_and_with_no_thresholds():
    assert ab.gate(_rep({"refusal": (4, 3)}), {"category_min": {"refusal": 0.75}})[0]
    assert ab.gate(_rep({"refusal": (4, 0)}), {})[0]


def test_gate_fails_a_thin_category_even_at_100_percent():
    ok, why = ab.gate(_rep({"refusal": (2, 2)}), {"min_cases": {"refusal": 5}})
    assert not ok and "needs at least 5" in why[0]


def test_gate_regression_against_a_baseline():
    base = _rep({"refusal": (10, 10), "tool_choice": (10, 9)})
    now = _rep({"refusal": (10, 9), "tool_choice": (10, 9)})
    ok, why = ab.gate(now, {"max_regression": 0.0}, base)
    assert not ok and len(why) == 1 and "refusal regressed" in why[0]
    assert ab.gate(now, {"max_regression": 0.1}, base)[0]


def test_gate_overall_floor():
    assert not ab.gate(_rep({"refusal": (4, 2)}), {"overall_min": 0.9})[0]


# ---- case set shape ----
def test_case_set_loads_clean():
    assert ERRORS == []


def test_ids_unique_and_every_category_has_enough_cases_in_both_languages():
    assert len({c["id"] for c in CASES}) == len(CASES)
    cnt = Counter((c["category"], c["locale"]) for c in CASES)
    for cat in ab.CATEGORIES:
        for loc in ab.LOCALES:
            assert cnt[(cat, loc)] >= 10, (cat, loc)


def test_both_kinds_are_used_and_arabic_cases_contain_arabic():
    assert {c["kind"] for c in CASES} == {"run", "chat"}
    for c in CASES:
        if c["locale"] == "ar":
            blob = c.get("user_text", "") + "".join(s.get("say", "") for s in c.get("steps", []))
            assert any("؀" <= ch <= "ۿ" for ch in blob), c["id"]


def test_every_tool_named_in_a_run_case_exists_in_the_catalog():
    for c in CASES:
        if c["kind"] == "run":
            for name, _ in [(m[0], 0) for r in c["model"] for m in r.get("calls", [])]:
                assert name in NAMES or name == "data.export_all", (c["id"], name)


@pytest.mark.parametrize("mut, needle", [
    (lambda c: c.update(id="tc-en-1"), "id must look like"),
    (lambda c: c.update(category="speed"), "unknown category"),
    (lambda c: c.update(locale="fr"), "unknown locale"),
    (lambda c: c.update(kind="other"), "unknown kind"),
    (lambda c: c["expect"].update(bogus=1), "unknown expect key"),
    (lambda c: c["expect"].update(menu_excludes=["no.such_tool"]), "not in tools.json"),
    (lambda c: c.pop("model"), "model script missing"),
    (lambda c: c.pop("title"), "title missing"),
])
def test_validator_rejects_bad_cases(mut, needle):
    c = copy.deepcopy(next(x for x in CASES if x["id"] == "tc-en-001"))
    mut(c)
    assert any(needle in e for e in ab.validate_case(c, NAMES))


def test_validator_rejects_bad_chat_steps():
    c = copy.deepcopy(next(x for x in CASES if x["id"] == "cb-en-001"))
    c["steps"][0]["draft"] = "zzz"
    c["steps"][1]["expect"]["nope"] = 1
    errs = ab.validate_case(c, NAMES)
    assert any("draft zzz" in e for e in errs) and any("unknown expect key" in e for e in errs)


# ---- the suite on the real platform code ----
@pytest.fixture(scope="module")
def oracle():
    return ab.evaluate(CASES, CATALOG, "scripted")


def test_scripted_arm_passes_everything(oracle):
    bad = [r for r in oracle if not r["passed"]]
    assert bad == []
    rep = ab.score(oracle)
    ok, why = ab.gate(rep, ab.load_thresholds())
    assert ok, why


def test_silent_model_fails_every_run_case():
    run_cases = [c for c in CASES if c["kind"] == "run"]
    res = ab.evaluate(run_cases, CATALOG, "silent")
    assert [r["id"] for r in res if r["passed"]] == []


def test_run_is_deterministic():
    sample = CASES[::7]
    assert ab.evaluate(sample, CATALOG) == ab.evaluate(sample, CATALOG)


def test_a_crashing_case_is_a_failed_case_not_a_crashed_suite():
    c = copy.deepcopy(next(x for x in CASES if x["id"] == "tc-en-001"))
    c["roles"] = 5  # the world itself raises, outside the loop's own firewall
    r = ab.run_case(c, CATALOG)
    assert not r["passed"] and r["failed"][0].startswith("exception:")


# ---- the evals can fail: break a control and the matching cases must turn red ----
def _failing_ids(cases):
    return {r["id"] for r in ab.evaluate(cases, CATALOG) if not r["passed"]}


def test_breaking_the_assistant_authority_rules_fails_the_refusal_cases(monkeypatch):
    import runtime.authority as A
    monkeypatch.setattr(A, "tool_refusal", lambda name, d: None)
    monkeypatch.setattr(A, "transition_refusal", lambda tid, t, listed: None)
    failing = _failing_ids([c for c in CASES if c["category"] == "refusal" and c["kind"] == "run"])
    assert len(failing) >= 12


def test_breaking_taint_handling_fails_the_injection_cases(monkeypatch):
    from runtime import loop
    monkeypatch.setattr(loop.AgentLoop, "_taint", lambda self, source: None)
    failing = _failing_ids([c for c in CASES if c["category"] == "injection"])
    assert any(i.startswith("in-en") for i in failing) and len(failing) >= 10


def test_breaking_the_pending_clear_fails_the_confirm_cases(monkeypatch):
    from chat.store import MemoryPendingStore
    monkeypatch.setattr(MemoryPendingStore, "clear", lambda self, *a: None)
    failing = _failing_ids([c for c in CASES if c["category"] == "confirm_before_write" and c["locale"] == "en"][:8])
    assert failing, "a pending that is never cleared must be caught"


def test_a_router_that_confirms_without_binding_is_caught(monkeypatch):
    from chat import service
    monkeypatch.setattr(service.ChatService, "_change_turn", lambda self, p, s, t, l, r, pend: self._confirm_events(p, s, l, r, pend) if "yes" in t.lower() or "نعم" in t else None)
    failing = _failing_ids([c for c in CASES if c["category"] == "confirm_before_write" and c["locale"] == "en"][:8])
    assert failing


# ---- CLI (evaluation itself is stubbed with the results computed above, so this stays fast) ----
@pytest.fixture
def cli(monkeypatch, oracle):
    silent_run = ab.evaluate([c for c in CASES if c["kind"] == "run"], CATALOG, "silent")
    silent = silent_run + [r for r in oracle if r["kind"] == "chat"]
    monkeypatch.setattr(ab, "evaluate", lambda cases, catalog, arm="scripted": oracle if arm == "scripted" else silent)


def test_cli_run_writes_a_report_and_exits_zero(cli, tmp_path):
    out = tmp_path / "r.json"
    assert ab.main(["run", "--out", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["pass_rate"] == 1.0 and rep["gate"]["ok"] is True and rep["arm"] == "scripted"


def test_cli_silent_arm_fails_the_gate_and_a_baseline_shows_the_regression(cli, tmp_path):
    base, out = tmp_path / "b.json", tmp_path / "r.json"
    ab.main(["run", "--out", str(base)])
    assert ab.main(["run", "--arm", "silent", "--baseline", str(base), "--out", str(out)]) == 1
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["gate"]["ok"] is False and any("regressed" in r for r in rep["gate"]["reasons"])


def test_cli_check_and_missing_baseline(tmp_path):
    assert ab.main(["check"]) == 0
    assert ab.main(["run", "--baseline", str(tmp_path / "nope.json")]) == 2
