import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import phase_exit_check as p  # noqa: E402

HEAD = "Author: eldon\nTool and model: claude-code / sonnet-5.5\nPhase exit: 1A\n"


def rows(**status):
    return [{"ID": k, "Status": v, "Gate": "G0"} for k, v in status.items()]


def test_plan_rows_must_exist_and_be_done():
    r = rows(**{"GOV-001": "done", "GOV-002": "doing"})
    assert p.plan_rows_problems(r, ["GOV-001"]) == []
    assert "GOV-002 is doing" in p.plan_rows_problems(r, ["GOV-002"])[0]
    assert "does not exist" in p.plan_rows_problems(r, ["GOV-999"])[0]


def test_a_gate_needs_every_row_in_that_gate_done():
    r = rows(**{"GOV-001": "done", "GOV-002": "todo"})
    assert any("GOV-002" in o for o in p.plan_rows_problems(r, [], gate="G0"))
    assert p.plan_rows_problems(rows(**{"GOV-001": "done"}), [], gate="G0") == []


def test_evidence_needs_pass_with_a_note():
    good = HEAD + "- E1: PASS ledger matches\n- E2: PASS arabic pdf reviewed\nReviewed by: partner (codex-5)\n"
    assert p.evidence_problems(good, ["E1", "E2"]) == []
    assert any("E2" in o for o in p.evidence_problems(HEAD + "- E1: PASS ok\nReviewed by: partner (x)\n", ["E1", "E2"]))
    assert any("note" in o for o in p.evidence_problems(HEAD + "- E1: PASS\nReviewed by: partner (x)\n", ["E1"]))


def test_a_fail_line_blocks_even_with_a_pass_line():
    t = HEAD + "- E1: PASS fine\n- E1: FAIL mismatch\nReviewed by: partner (x)\n"
    assert any("not PASS" in o for o in p.evidence_problems(t, ["E1"]))


def test_empty_evidence_list_does_not_pass():
    assert any("no evidence" in o for o in p.evidence_problems(HEAD + "Reviewed by: partner (x)\n", []))


def test_reviewer_must_be_other_founder_or_other_model():
    ev = "- E1: PASS checked ledger\n"
    assert p.evidence_problems(HEAD + ev + "Reviewed by: partner (sonnet-5.5)\n", ["E1"]) == []
    assert p.evidence_problems(HEAD + ev + "Reviewed by: eldon (opus-5.5)\n", ["E1"]) == []
    same = p.evidence_problems(HEAD + ev + "Reviewed by: eldon (sonnet-5.5)\n", ["E1"])
    assert any("reviewer must be" in o for o in same)
    assert any("Reviewed by" in o for o in p.evidence_problems(HEAD + ev, ["E1"]))


def test_exit_header_must_be_in_the_first_lines(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    c = tmp_path / "c.md"
    a.write_text("Phase exit: 1A\n")
    b.write_text("Phase exit: 1B\n")
    c.write_text("x\n" * 40 + "Phase exit: 2\n")
    assert p.find_exit_log("1B", [a, b]) == b
    assert p.find_exit_log("2", [a, b, c]) is None


def test_missing_or_bad_criteria_file(tmp_path):
    assert p.load_criteria(tmp_path / "none.json")[0] is None
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert "invalid JSON" in p.load_criteria(bad)[1]
    ok = tmp_path / "ok.json"
    ok.write_text('{"phases": {"0": {"title": "t"}}}')
    assert p.load_criteria(ok)[0] == {"0": {"title": "t"}}
