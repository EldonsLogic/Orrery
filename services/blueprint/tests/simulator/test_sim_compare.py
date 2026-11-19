"""Comparison: tolerance edges, precision, Decimal-only, blocked and unreported metrics, expected totals."""
import datetime as dt
from decimal import Decimal

import pytest

import sim_helpers as h
from simulator.compare import (ToleranceError, allowed_minor, check_tolerances, compare, expected_totals)
from simulator.model import normalise
from simulator.money import MoneyError, exact_minor, parse_decimal, to_minor

END = dt.date(2026, 3, 31)


def _exp(minor, docs=1, metric="sales_net", ccy="SAR"):
    return {(metric, ccy): {"minor": minor, "sourceIds": {f"s{i}" for i in range(docs)}}}


def _one(expected, actual, rules=None, blocked=frozenset(), aborted=False):
    rows, found = compare(expected, actual, blocked=set(blocked), rules=check_tolerances(rules), aborted=aborted)
    assert len(rows) == 1
    return rows[0], [a.code for a in found]


@pytest.mark.parametrize("actual,status,code", [
    ("100.00", "match", None),
    ("100.03", "within_tolerance", "SIM-102"),   # exactly at the limit: 1 + 1 x 2 documents = 3
    ("99.97", "within_tolerance", "SIM-102"),    # negative difference, same limit
    ("100.04", "mismatch", "SIM-121"),           # one minor unit over
    ("99.96", "mismatch", "SIM-121"),
])
def test_tolerance_edges(actual, status, code):
    row, codes = _one(_exp(10000, docs=2), {"sales_net": {"SAR": actual}},
                      {"sales_net": {"abs_minor": 1, "per_document_minor": 1}})
    assert row["toleranceMinor"] == 3
    assert row["status"] == status
    assert codes == ([code] if code else [])


def test_zero_tolerance_default():
    row, _ = _one(_exp(10000), {"sales_net": {"SAR": "100.01"}})
    assert row["toleranceMinor"] == 0 and row["status"] == "mismatch" and row["differenceMinor"] == 1


def test_three_decimal_currency():
    row, _ = _one(_exp(1234, ccy="KWD"), {"sales_net": {"KWD": "1.235"}}, {"default": {"abs_minor": 1}})
    assert row["actualMinor"] == 1235 and row["status"] == "within_tolerance"


@pytest.mark.parametrize("raw", ["100.001", "1e2", "abc", "", "NaN"])
def test_reported_amount_precision_or_format_fails(raw):
    row, codes = _one(_exp(10000), {"sales_net": {"SAR": raw}}, {"default": {"abs_minor": 100}})
    assert row["status"] == "invalid_actual" and codes == ["SIM-123"]


def test_family_rule_applies_to_aging_buckets():
    rules = check_tolerances({"receivables": {"abs_minor": 5}, "default": {"abs_minor": 1}})
    assert allowed_minor(rules, "receivables_0_30", 3) == 5
    assert allowed_minor(rules, "sales_net", 3) == 1


@pytest.mark.parametrize("rules", [{"default": {"abs_minor": 0.5}}, {"default": {"abs_minor": True}},
                                   {"default": {"abs_minor": -1}}, {"default": {"pct": 1}}, ["x"],
                                   {"default": {"abs_minor": "1"}}])
def test_bad_tolerance_rules_refused(rules):
    with pytest.raises(ToleranceError):
        check_tolerances(rules)


def test_blocked_unreported_aborted_unknown():
    row, codes = _one(_exp(10000), {"sales_net": {"SAR": "100.00"}}, blocked={"sales_net"})
    assert row["status"] == "blocked_by_approval" and codes == ["SIM-122"]
    row, codes = _one(_exp(10000), {})
    assert row["status"] == "not_compared" and row["reason"] == "not_reported"
    row, codes = _one(_exp(10000), None, aborted=True)
    assert row["status"] == "not_compared" and row["reason"] == "run_aborted" and codes == []
    rows, found = compare({}, {"bonus_points": {"SAR": "1.00"}}, blocked=set(), rules={}, aborted=False)
    assert rows == [] and [a.code for a in found] == ["SIM-122"]  # unknown names never reach the report


def test_unexpected_reported_currency_is_compared_against_zero():
    row, codes = _one({}, {"sales_net": {"USD": "5.00"}})
    assert row["expectedMinor"] == 0 and row["status"] == "mismatch" and codes == ["SIM-121"]


def test_money_refuses_floats():
    for bad in (0.1, True, float("nan")):
        with pytest.raises(MoneyError):
            parse_decimal(bad)
    with pytest.raises(MoneyError):
        to_minor(Decimal("1"), "XXX")
    assert to_minor(Decimal("0.045"), "SAR") == 5 and to_minor(Decimal("-0.045"), "SAR") == -5
    assert exact_minor("1.10", "SAR") == 110 and exact_minor("1.105", "SAR") is None


def test_expected_totals_month():
    recs = sorted(normalise(h.month_rows(), connector_id="intake").records,
                  key=lambda r: (r.posting_date, r.kind))
    from simulator.anomalies import replay_order
    exp = expected_totals(replay_order(recs), END)
    get = lambda m: exp[(m, "SAR")]["minor"]
    assert get("sales_net") == 11000 + 30          # SI-1 110.00, SI-2 0.30
    assert get("vat_output") == 1650 + 5           # per-document rounding of 0.045 is 0.05
    assert get("purchases_net") == 20000 and get("vat_input") == 3000
    assert get("receivables_0_30") == 12650 - 5000 + 35
    assert get("payables_not_due") == 23000
    assert get("stock_value") == 14000 and exp[("stock_value", "SAR")]["sourceIds"] == {
        "intake:stock_in:GRN-1", "intake:stock_out:DN-1"}
    assert (get("payroll_gross"), get("payroll_deductions"), get("payroll_net")) == (1400000, 140000, 1260000)


def test_moving_average_stock_value():
    rows = [h.row(row=1, type="stock_in", number="A", date="2026-03-01", item="X", warehouse="W", qty="3",
                  unit_price="10.00"),
            h.row(row=2, type="stock_in", number="B", date="2026-03-02", item="X", warehouse="W", qty="1",
                  unit_price="11.00"),
            h.row(row=3, type="stock_out", number="C", date="2026-03-03", item="X", warehouse="W", qty="1")]
    from simulator.anomalies import replay_order
    exp = expected_totals(replay_order(normalise(rows, connector_id="i").records), END)
    # 41.00 / 4 = 10.25 average; 3 left = 30.75
    assert exp[("stock_value", "SAR")]["minor"] == 3075
