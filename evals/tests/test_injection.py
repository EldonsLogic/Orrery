import copy
import json

import pytest

from evals.harness import __main__ as cli
from evals.harness import injection as inj
from evals.harness.records import SETS_DIR

CASES, ERRORS = inj.load_cases(SETS_DIR)
ATTACKS = [c for c in CASES if c["kind"] == "attack"]


def test_set_loads_clean():
    assert ERRORS == []
    assert len(CASES) == 34
    assert len({c["id"] for c in CASES}) == 34
    assert sorted(c["attack"] for c in CASES) == [f"A{i:02d}" for i in range(1, 35)]


def test_controls_are_a33_a34():
    assert {c["attack"] for c in CASES if c["kind"] == "control"} == {"A33", "A34"}
    assert len(ATTACKS) == 32


def test_arabic_cases_have_arabic_text_and_unreviewed():
    ar = [c for c in CASES if c["language"] in ("ar", "mixed")]
    assert ar
    for c in ar:
        assert any("؀" <= ch <= "ۿ" for ch in c["fixture"]["text"] + c["task"]), c["id"]
        assert c["review"]["nativeSpeaker"] is False
    assert {c["language"] for c in CASES} == {"ar", "en", "mixed"}


def test_synthetic_only():
    for c in CASES:
        blob = json.dumps(c).lower()
        for real in (".com", ".org", ".net", ".sa\"", ".ae\""):
            assert real not in blob, (c["id"], real)
        for word in ("frappe", "erpnext"):
            assert word not in json.dumps(c).lower()


def test_schema_rejects():
    base = ATTACKS[0]
    for mutate in (lambda c: c.pop("assertions"), lambda c: c.update(id="bad"), lambda c: c.update(kind="x"),
                   lambda c: c["assertions"].update(must_emit_events=["nope.event"]),
                   lambda c: c["assertions"].clear(), lambda c: c.update(extra=1)):
        c = copy.deepcopy(base)
        mutate(c)
        assert inj.validate_case(c), c
    assert inj.validate_case(base) == []


def test_oracle_scores_100():
    r = inj.run_set("oracle")
    assert r["pass_rate"] == 1.0 and r["blocking_rate"] == 1.0 and r["task_success_rate"] == 1.0
    assert r["failures"] == []


def test_permissive_fails_every_attack_blocking():
    r = inj.run_set("permissive")
    for c in r["cases"]:
        if c["kind"] == "attack":
            assert c["blocking_ok"] is False and c["passed"] is False, c["id"]
    assert r["blocking_rate"] == 0.0


def test_null_behaves():
    r = inj.run_set("null")
    controls = [c for c in r["cases"] if c["kind"] == "control"]
    assert r["task_success_rate"] == 0.0 and all(not c["passed"] for c in controls)
    assert r["blocking_rate"] > 0.9  # does nothing, so side effects are stopped; detection is not
    assert r["detection_rate"] < 0.1 and r["pass_rate"] < 0.2


def test_report_per_language_and_case():
    r = inj.run_set("oracle")
    assert set(r["by_language"]) == {"ar", "en", "mixed"}
    assert sum(v["total"] for v in r["by_language"].values()) == 34
    assert len(r["cases"]) == 34 and r["by_language"]["ar"]["blocking_rate"] == 1.0
    assert r["detector_hit_rate"] == 1.0


def test_detector_miss_is_not_a_pass_condition():
    c = next(c for c in CASES if c["attack"] == "A13")
    obs = inj.OracleAdapter().run(c)
    obs.detector_hit = False
    assert inj.score_case(c, obs)["passed"] is True


def test_false_positive_on_control_fails():
    c = next(c for c in CASES if c["attack"] == "A33")
    obs = inj.OracleAdapter().run(c)
    obs.flags = ["hidden_text"]
    assert inj.score_case(c, obs)["passed"] is False


def test_deterministic():
    assert json.dumps(inj.run_set("permissive"), sort_keys=True) == json.dumps(inj.run_set("permissive"), sort_keys=True)


def test_cli(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert cli.main(["injection", "--adapter", "oracle", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["pass_rate"] == 1.0
    assert cli.main(["injection", "--adapter", "nope"]) == 2
    assert cli.main(["check"]) == 0
    assert "injection cases: 34" in capsys.readouterr().out


def test_check_reports_bad_injection_set(tmp_path, capsys):
    d = tmp_path / "injection"
    d.mkdir()
    (d / "cases.jsonl").write_text("{}\n", encoding="utf-8")
    assert cli.main(["--sets-dir", str(tmp_path), "check"]) == 1
    assert "injection/cases.jsonl:1" in capsys.readouterr().err
