"""End to end on the synthetic month: schema-valid, deterministic, neutral, sign-off empty."""
import json
import re

import sim_helpers as h
from simulator import validate_report


def test_report_valid_and_deterministic():
    a, _ = h.run()
    b, _ = h.run()
    assert validate_report(a) == []
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["status"] == "completed"


def test_month_results_with_ledger_posting_held():
    report, _ = h.run()
    assert h.metric(report, "sales_net")["status"] == "match"
    assert h.metric(report, "vat_output")["status"] == "within_tolerance"  # line versus document rounding
    assert h.metric(report, "vat_output")["differenceMinor"] == 1
    assert h.metric(report, "stock_value")["status"] == "match"  # stock posting is R2 and runs
    assert h.metric(report, "receivables_0_30")["status"] == "blocked_by_approval"
    assert h.metric(report, "payroll_net")["status"] == "match"
    assert report["summary"]["held"] == 5 and report["summary"]["mismatched"] == 0


def test_month_results_when_posting_is_allowed():
    """With a tool set whose posting is R2 (a sandbox policy, not today's generator) aging is compared too."""
    report, _ = h.run(ts=h.tool_set(ledger_post="R2"))
    assert h.metric(report, "receivables_0_30")["status"] == "within_tolerance"
    assert h.metric(report, "payables_not_due")["status"] == "match"
    assert report["summary"]["held"] == 0


def test_sign_off_empty_and_no_free_text():
    report, _ = h.run()
    assert report["signOff"] == {k: {"userId": None, "decision": None, "decidedAt": None, "note": None}
                                 for k in ("owner", "accountant")}
    blob = json.dumps(report)
    assert not re.search(r"frappe|erpnext", blob, re.I)
    assert all(a["messageKey"].startswith("sim.") for a in report["anomalies"])


def test_no_floats_in_report():
    report, _ = h.run()

    def walk(x):
        if isinstance(x, float):
            raise AssertionError(x)
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        if isinstance(x, list):
            for v in x:
                walk(v)
    walk(report)


def test_aborted_report_is_schema_valid():
    report, _ = h.run(p=h.port(fail_on={"tool": "purchase_receipt.create", "nth": 1, "mode": "error"}))
    assert validate_report(report) == [] and report["status"] == "aborted"
