"""SEC-014: red-team corpus pushed through the real connector and Tool API defences. Offline and deterministic.

Every case is accounted for: hard checks must pass for all (a failure is a breach); a case marked `gap` in the corpus
is an expectedFailure (strict) for the ideal-defence test, so fixing the code turns it into an unexpected pass that
forces the corpus and the report to be updated.
"""
import copy
import json
import os
import re

import pytest

from evals.harness import redteam as R

CASES, ERRORS = R.load_corpus()
VERDICTS = {c["id"]: R.judge(c) for c in CASES}
REPORT = os.path.join(R.REPO, "docs", "security", "redteam-uploads-report.md")
IDS = [c["id"] for c in CASES]
GAPS = [c for c in CASES if c["expected"]["outcome"] == "gap"]
NOT_GAPS = [c for c in CASES if c["expected"]["outcome"] != "gap"]


def test_corpus_loads_clean_and_is_large_enough():
    assert ERRORS == []
    assert len(CASES) >= 60
    assert len({c["id"] for c in CASES}) == len(CASES)


def test_every_vector_and_goal_is_covered():
    assert {c["vector"] for c in CASES} == set(R.VECTORS)
    assert {c["goal"] for c in CASES} == set(R.GOALS)
    for v in R.VECTORS:
        assert sum(c["vector"] == v for c in CASES) >= 3, v
    for g in R.GOALS:
        assert sum(c["goal"] == g for c in CASES) >= 5, g


def test_synthetic_and_harmless_only():
    secret_like = re.compile(r"(sk-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,}|-----BEGIN|[A-Fa-f0-9]{32,}|eyJ[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{10,})")
    for c in CASES:
        blob = json.dumps(c, ensure_ascii=False)
        assert not secret_like.search(blob), c["id"]
        for real in (".com", ".org", ".net", ".sa\"", ".ae\"", "frappe", "erpnext"):
            assert real not in blob.lower(), (c["id"], real)


def test_schema_rejects_bad_cases():
    base = CASES[0]
    from jsonschema import Draft202012Validator
    v = Draft202012Validator(R.CASE_SCHEMA)
    assert not list(v.iter_errors(base))
    for mutate in (lambda c: c.update(vector="nope"), lambda c: c.update(goal="nope"), lambda c: c.pop("expected"),
                   lambda c: c.update(id="x"), lambda c: c.update(extra=1), lambda c: c["expected"].update(outcome="safe")):
        bad = copy.deepcopy(base)
        mutate(bad)
        assert list(v.iter_errors(bad)), bad


def test_tool_set_is_clean_and_the_checker_catches_escalation():
    defs = R.toolset()["defs"]
    assert [str(i) for i in R.check_tool_api(defs)] == []
    assert "TAPI-RISK-001" in R.mutated_escalation_issues()
    for g in R.GOALS:
        assert R.goal_probe(g) == [], g


def test_forged_input_never_validates_against_any_tool():
    """A19: caller, role or tenant supplied in arguments is refused by every closed input schema."""
    from jsonschema import Draft202012Validator
    forged = {"caller": {"role_ids": ["owner"]}, "tenant_id": "t-other-tenant", "role": "owner"}
    for name, t in R.toolset()["by_name"].items():
        args = {**forged}
        assert list(Draft202012Validator(t["input_schema"]).iter_errors(args)), name


@pytest.mark.parametrize("cid", IDS)
def test_hard_invariants_hold(cid):
    """No breach: payload stays in an untrusted L3 envelope, controls neutralised, goal tool not callable."""
    v = VERDICTS[cid]
    assert v["hard"] == [], v["hard"]
    assert v["outcome"] != "breach"


@pytest.mark.parametrize("cid", IDS)
def test_outcome_matches_corpus(cid):
    exp = next(c for c in CASES if c["id"] == cid)["expected"]
    v = VERDICTS[cid]
    assert v["outcome"] == exp["outcome"], (v["outcome"], v["soft"])
    assert sorted({k for k, _ in v["soft"]}) == sorted(exp.get("gap_kinds", []))


@pytest.mark.parametrize("c", NOT_GAPS, ids=[c["id"] for c in NOT_GAPS])
def test_ideal_defence_blocks_or_neutralises(c):
    assert VERDICTS[c["id"]]["outcome"] in ("blocked", "neutralised")


@pytest.mark.parametrize("c", [pytest.param(c, marks=pytest.mark.xfail(strict=True, reason=c["expected"]["reason"])) for c in GAPS],
                         ids=[c["id"] for c in GAPS])
def test_known_gap_expected_failure(c):
    """A gap: the ideal defence (flag raised, markup neutralised, taint downgrade) is NOT in the current code."""
    assert VERDICTS[c["id"]]["outcome"] in ("blocked", "neutralised"), VERDICTS[c["id"]]["soft"]


def test_every_case_is_accounted_for():
    assert sorted(VERDICTS) == sorted(IDS)
    assert set(v["outcome"] for v in VERDICTS.values()) <= {"blocked", "neutralised", "gap"}
    rep = R.run_corpus()
    assert sum(rep["outcomes"].values()) == rep["total"] == len(CASES)


def test_hidden_and_refused_content_is_never_model_facing():
    hidden = [c for c in CASES if c["vector"] in ("xlsx_hidden_sheet", "xlsx_comment")]
    assert hidden
    for c in hidden:
        v = VERDICTS[c["id"]]
        assert not v["model_facing"] and "hidden_text" in v["flags"], c["id"]


def test_bidi_zero_width_and_tag_characters_are_counted_and_flagged():
    seen = {k: 0 for k in ("bidi_control", "zero_width", "unicode_tag")}
    for c in CASES:
        for k in seen:
            if k in VERDICTS[c["id"]]["flags"]:
                seen[k] += 1
    assert all(n >= 2 for n in seen.values()), seen


def test_forged_labels_are_discarded_and_logged():
    forged = [c for c in CASES if c.get("carrier") == "forged_labels"]
    assert len(forged) >= 2
    for c in forged:
        assert "label.discarded" in VERDICTS[c["id"]]["events"], c["id"]


def test_report_lists_every_gap_and_the_counts():
    text = open(REPORT, encoding="utf-8").read()
    low = text.lower()
    rep = R.run_corpus()
    for g in rep["gaps"]:
        assert g["id"] in text, g["id"]
    assert f"Total {rep['total']}: " in text
    assert "blocked %d, neutralised %d, gap %d" % tuple(rep["outcomes"].get(o, 0) for o in R.OUTCOMES) in text
    assert "What is NOT covered" in text
    for topic in ("real models", "ocr engines", "live connectors"):
        assert topic in low
