"""QA-011: simulator accuracy against known outcomes. Offline, deterministic, fake engine adapter only.

Clean months must produce exactly the hand-computed rows, anomaly codes and verdict. Tampered engine outputs
(seeded faults) must all be flagged. The scorer reports detection and false-positive rates.
"""
import json

import pytest

from evals.harness import sim_accuracy as sa

MONTHS = {m["id"]: m for m in sa.CLEAN_MONTHS}
FAULTS = {f["id"]: f for f in sa.FAULTS}


# ---- fixtures are well formed ----

def test_fixture_counts_and_ids_unique():
    assert len(sa.CLEAN_MONTHS) == 4 and len(sa.FAULTS) >= 14
    assert len(MONTHS) == len(sa.CLEAN_MONTHS) and len(FAULTS) == len(sa.FAULTS)


def test_every_fault_targets_a_known_month_and_expects_something():
    for f in sa.FAULTS:
        assert f["month"] in MONTHS, f["id"]
        assert f["expect_rows"] and f["expect_codes"] and f["expect_verdict"] != "pass", f["id"]


def test_fixtures_cover_two_exponents_and_arabic():
    ccys = {c for m in sa.CLEAN_MONTHS for (_, c) in m["expected_rows"]}
    assert {"SAR", "KWD"} <= ccys
    blob = json.dumps([m["rows"] for m in sa.CLEAN_MONTHS], ensure_ascii=False)
    assert any("؀" <= ch <= "ۿ" for ch in blob)


def test_expected_values_are_integers():
    for m in sa.CLEAN_MONTHS:
        assert all(isinstance(v, int) and not isinstance(v, bool) for v in m["expected_rows"].values())


# ---- clean months: exact expected versus actual ----

@pytest.mark.parametrize("month_id", sorted(MONTHS))
def test_clean_month_matches_hand_computed_rows(month_id):
    m = MONTHS[month_id]
    obs = sa.observe(sa.run_month(m))
    assert obs["status"] == "completed"
    got = {k: (v["expectedMinor"], v["actualMinor"], v["status"]) for k, v in obs["rows"].items()}
    assert got == {k: (v, v, "match") for k, v in m["expected_rows"].items()}


@pytest.mark.parametrize("month_id", sorted(MONTHS))
def test_clean_month_codes_and_verdict_exact(month_id):
    m = MONTHS[month_id]
    obs = sa.observe(sa.run_month(m))
    assert obs["codes"] == sorted(m["expected_codes"])
    assert obs["verdict"] == m["expected_verdict"]


def test_hand_computed_anchor_values():
    """A few totals written out here as well, so a mistake in the fixtures is not repeated in the check."""
    a = MONTHS["sar-trading"]["expected_rows"]
    assert a[("sales_net", "SAR")] == 22030 and a[("vat_output", "SAR")] == 3305
    assert a[("stock_value", "SAR")] == 14000 and a[("payroll_net", "SAR")] == 1260000
    b = MONTHS["kwd-three-decimals"]["expected_rows"]
    assert b[("sales_net", "KWD")] == 38036 and b[("stock_value", "KWD")] == 4009
    assert b[("payroll_net", "KWD")] == 1125450


def test_mixed_month_is_union_of_the_single_currency_months():
    c = MONTHS["mixed-sar-kwd"]["expected_rows"]
    union = dict(MONTHS["sar-trading"]["expected_rows"])
    union.update(MONTHS["kwd-three-decimals"]["expected_rows"])
    union[("stock_value", "KWD")] = 5011  # the KWD stock issue is left out of the mixed month (Q-360)
    assert c == union


# ---- seeded faults must be flagged ----

@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_fault_is_flagged_exactly(fault_id):
    f = FAULTS[fault_id]
    obs = sa.observe(sa.run_month(MONTHS[f["month"]], f))
    assert obs["verdict"] == f["expect_verdict"]
    assert obs["codes"] == sorted(f["expect_codes"])
    bad = {k: (v["differenceMinor"] if v["status"] == "mismatch" else v["status"])
           for k, v in obs["rows"].items() if v["status"] not in ("match", "within_tolerance")}
    assert bad == f["expect_rows"]


def test_one_minor_unit_drift_is_caught_at_zero_tolerance_in_both_exponents():
    for fid, key, diff in (("drift-plus1-sales-net", ("sales_net", "SAR"), 1),
                           ("drift-plus1-stock-value-kwd", ("stock_value", "KWD"), 1)):
        obs = sa.observe(sa.run_month(MONTHS[FAULTS[fid]["month"]], FAULTS[fid]))
        assert obs["rows"][key]["differenceMinor"] == diff and obs["rows"][key]["status"] == "mismatch"


def test_drift_inside_configured_tolerance_is_a_warning_not_a_pass():
    f = FAULTS["drift-plus1-sales-net"]
    obs = sa.observe(sa.run_month(MONTHS[f["month"]], f, tolerances={"default": {"abs_minor": 1}}))
    assert obs["rows"][("sales_net", "SAR")]["status"] == "within_tolerance"
    assert obs["codes"] == ["SIM-102", "SIM-134"] and obs["verdict"] == "pass_with_warnings"


def test_drift_of_two_beyond_tolerance_one_is_a_mismatch():
    f = dict(FAULTS["drift-plus1-sales-net"], id="drift-plus2", tamper=("shift", "sales_net", "SAR", 2))
    obs = sa.observe(sa.run_month(MONTHS[f["month"]], f, tolerances={"default": {"abs_minor": 1}}))
    assert obs["rows"][("sales_net", "SAR")]["status"] == "mismatch" and obs["verdict"] == "blocked"


def test_tamper_does_not_touch_the_pre_run_read():
    """The runner pre-reads totals and refuses a non-empty tenant (SIM-129); tampering starts after the replay."""
    f = FAULTS["duplicate-sales-invoice"]
    obs = sa.observe(sa.run_month(MONTHS[f["month"]], f))
    assert "SIM-129" not in obs["codes"] and obs["status"] == "completed"


# ---- scorer ----

def test_scorer_full_detection_and_no_false_positives():
    s = sa.score()
    assert s["faults"]["detected"] == s["faults"]["total"] == len(sa.FAULTS)
    assert s["faults"]["detectionPermille"] == 1000 and s["faults"]["undetected"] == []
    assert s["clean"]["falsePositives"] == 0 and s["clean"]["falsePositivePermille"] == 0
    assert s["clean"]["months"] == len(sa.CLEAN_MONTHS) and s["gate"] == "pass"


def test_scorer_is_deterministic():
    assert json.dumps(sa.score(), sort_keys=True) == json.dumps(sa.score(), sort_keys=True)


def test_scorer_catches_a_blind_check():
    """A scorer that cannot fail is worthless: a no-op tamper must count as undetected."""
    blind = [dict(f, tamper=("noop",)) for f in sa.FAULTS[:3]]
    s = sa.score(faults=blind)
    assert s["faults"]["detected"] == 0 and s["gate"] == "fail" and len(s["faults"]["undetected"]) == 3


def test_scorer_counts_a_false_positive():
    wrong = [dict(sa.CLEAN_MONTHS[0], expected_verdict="blocked")]
    s = sa.score(months=wrong, faults=[])
    assert s["clean"]["falsePositives"] == 1 and s["clean"]["falsePositivePermille"] == 1000 and s["gate"] == "fail"


def test_cli_exit_code_and_json(capsys):
    assert sa.main([]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["gate"] == "pass" and out["faults"]["detectionPermille"] == 1000


def test_report_has_no_floats():
    def walk(x):
        assert not isinstance(x, float)
        for v in (x.values() if isinstance(x, dict) else x if isinstance(x, (list, tuple)) else ()):
            walk(v)
    walk(sa.score())
