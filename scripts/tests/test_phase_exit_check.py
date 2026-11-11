import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import phase_exit_check as p  # noqa: E402


def rows(**status):
    return [{"ID": k, "Status": v} for k, v in status.items()]


def test_plan_rows_must_exist_and_be_done():
    r = rows(**{"GOV-001": "done", "GOV-002": "doing"})
    assert p.plan_rows_problems(r, ["GOV-001"]) == []
    assert "GOV-002 is doing" in p.plan_rows_problems(r, ["GOV-002"])[0]
    assert "does not exist" in p.plan_rows_problems(r, ["GOV-999"])[0]


def test_evidence_needs_pass_lines_and_a_reviewer():
    good = "Phase exit: 1A\n- E1: PASS ledger matches\n- E2: PASS arabic pdf reviewed\nReviewed by: Partner (codex-5)\n"
    assert p.evidence_problems(good, ["E1", "E2"]) == []
    bad = "Phase exit: 1A\n- E1: FAIL mismatch\nReviewed by: x\n"
    out = p.evidence_problems(bad, ["E1", "E2"])
    assert any("E1" in o for o in out) and any("E2" in o for o in out) and any("Reviewed by" in o for o in out)


def test_find_exit_log_matches_the_phase_exactly(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Phase exit: 1A\n")
    b.write_text("Phase exit: 1B\n")
    assert p.find_exit_log("1B", [a, b]) == b
    assert p.find_exit_log("2", [a, b]) is None


def test_missing_or_bad_criteria_file(tmp_path):
    assert p.load_criteria(tmp_path / "none.json")[0] is None
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert "invalid JSON" in p.load_criteria(bad)[1]
    ok = tmp_path / "ok.json"
    ok.write_text('{"phases": {"0": {"title": "t"}}}')
    assert p.load_criteria(ok)[0] == {"0": {"title": "t"}}
