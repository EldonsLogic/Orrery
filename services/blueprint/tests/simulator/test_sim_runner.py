"""Runner: fail closed on every kind of port failure; parked calls; nothing compared after an abort."""
import pytest

import sim_helpers as h


@pytest.mark.parametrize("mode", ["raise", "error", "malformed"])
def test_port_failure_aborts_and_stops(mode):
    port = h.port(fail_on={"tool": "sales_invoice.create", "nth": 1, "mode": mode})
    report, _ = h.run(p=port)
    assert report["status"] == "aborted"
    outcomes = [s["outcome"] for s in report["steps"]]
    first_err = next(i for i, s in enumerate(report["steps"]) if s["tool"] == "sales_invoice.create")
    assert all(o == "not_run" for o in outcomes[first_err + 1:])
    assert outcomes[first_err] == ("in_doubt" if mode == "raise" else "error")
    if mode == "error":
        assert report["steps"][first_err]["errorCode"] == "engine_error"
    assert all(r["status"] == "not_compared" and r["reason"] == "run_aborted" for r in report["comparison"])
    assert "SIM-120" in h.codes(report)
    assert not any(c["tool"] == "sales_invoice.submit" for c in port.calls)


@pytest.mark.parametrize("mode", ["raise", "malformed"])
def test_totals_failure_aborts(mode):
    report, _ = h.run(p=h.port(fail_totals=mode))
    assert report["status"] == "aborted"
    assert all(r["status"] == "not_compared" for r in report["comparison"])
    assert next(a for a in report["anomalies"] if a["code"] == "SIM-120")["params"]["reason"].startswith("totals_")


def test_port_role_refusal_fails_closed():
    """The gateway is the guarantee: if it refuses a role the planner allowed, the run stops."""
    ts = h.tool_set()
    port = h.port(ts=h.tool_set())
    for t in port.tools.values():
        if t["name"] == "purchase_receipt.create":
            t["requires"] = {"roles": ["owner"]}
    report, _ = h.run(ts=ts, p=port)
    assert report["status"] == "aborted"
    assert report["steps"][0]["errorCode"] == "permission_denied"


def test_parked_by_approval_rule_is_not_an_error():
    class ParkingPort:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, call):
            if call.tool == "sales_invoice.create":
                return {"status": "pending_approval", "approval": {"status": "pending"}}
            return self.inner.execute(call)

        def report_totals(self, *a):
            return self.inner.report_totals(*a)

    report, _ = h.run(p=ParkingPort(h.port()))
    assert report["status"] == "completed"
    si = [s for s in report["steps"] if s["kind"] == "sales_invoice"]
    assert [s["outcome"] for s in si if s["stage"] == "create"] == ["parked", "parked"]
    assert "SIM-118" in h.codes(report)
    assert h.metric(report, "sales_net")["status"] == "mismatch"  # the month's sales did not reach the tenant


def test_planner_never_marks_r3_execute_even_if_tool_set_says_r2_for_create():
    """Defence in depth: a step whose recorded risk is above R2 is never sent, even if marked execute."""
    from simulator.plan import plan_replay
    from simulator.runner import run_plan
    from simulator.anomalies import check_records
    from simulator.model import normalise
    import datetime as dt

    recs, _ = check_records(normalise(h.month_rows(), connector_id="intake").records,
                            period_start=dt.date(2026, 3, 1), period_end=dt.date(2026, 3, 31))
    plan = plan_replay(recs, tenant_id=h.TENANT, period=h.PERIOD, tool_set=h.tool_set(), mapping=h.MAPPING,
                       caller=h.CALLER)
    tampered = next(s for s in plan.steps if s.action == "needs_approval")
    tampered.action = "execute"
    port = h.port()
    result = run_plan(plan, port)
    assert result.status == "aborted"
    assert all(c["risk_class"] in ("R0", "R1", "R2") for c in port.calls)
