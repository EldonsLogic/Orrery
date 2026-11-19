"""Planner: order, idempotency, convergence, risk gating, roles, unmapped tools, real generated tool set."""
import copy
import json
import sys
from pathlib import Path

import pytest

import sim_helpers as h
from simulator import SimulatorError, plan_replay
from simulator.anomalies import check_records
from simulator.model import normalise
from simulator.plan import idempotency_key
from simulator.report import _period

ROOT = Path(__file__).resolve().parents[4]


def _plan(rows=None, ts=None, mapping=None, caller=None, epoch=0, tenant=h.TENANT):
    norm = normalise(rows or h.month_rows(), connector_id="intake")
    start, end = _period(h.PERIOD)
    kept, _ = check_records(norm.records, period_start=start, period_end=end)
    return plan_replay(kept, tenant_id=tenant, period=h.PERIOD, tool_set=ts or h.tool_set(),
                       mapping=mapping or copy.deepcopy(h.MAPPING), caller=caller or dict(h.CALLER), run_epoch=epoch)


def test_order_by_posting_date_then_kind():
    plan = _plan()
    creates = [s for s in plan.steps if s.stage == "create"]
    assert [s.source_id.split(":", 1)[1] for s in creates] == [
        "stock_in:GRN-1", "purchase_invoice:PI-1", "stock_out:DN-1", "sales_invoice:SI-1",
        "sales_invoice:SI-2", "payment_in:RC-1", "payroll_run:PAY-2026-03"]
    assert [s.seq for s in plan.steps] == list(range(1, len(plan.steps) + 1))
    for s in plan.steps:  # post immediately follows its create
        if s.stage == "post":
            assert plan.steps[s.seq - 2].step_id == s.depends_on


def test_order_independent_of_input_order():
    rows = h.month_rows()
    a = _plan(rows)
    b = _plan(list(reversed(rows)))
    assert [(s.step_id, s.idempotency_key, s.args_hash) for s in a.steps] == \
           [(s.step_id, s.idempotency_key, s.args_hash) for s in b.steps]


def test_idempotency_keys_stable_and_scoped():
    a, b = _plan(), _plan()
    assert [s.idempotency_key for s in a.steps] == [s.idempotency_key for s in b.steps]
    assert len({s.idempotency_key for s in a.steps}) == len(a.steps)
    other_epoch = {s.idempotency_key for s in _plan(epoch=1).steps}
    other_tenant = {s.idempotency_key for s in _plan(tenant="t_other").steps}
    assert not other_epoch & {s.idempotency_key for s in a.steps}
    assert not other_tenant & {s.idempotency_key for s in a.steps}
    k = idempotency_key(h.TENANT, h.PERIOD, 0, "intake:sales_invoice:SI-1", "create")
    assert k == idempotency_key(h.TENANT, h.PERIOD, 0, "intake:sales_invoice:SI-1", "create")


def test_rerun_converges_without_second_effect():
    port = h.port()
    first, _ = h.run(p=port)
    docs = dict(port.docs)
    second, _ = h.run(p=port, on_existing="resume")
    assert port.docs == docs  # no new documents
    assert first["summary"]["executed"] > 0 and second["summary"]["executed"] == 0
    assert second["summary"]["replayed"] == first["summary"]["executed"]
    assert [r["status"] for r in second["comparison"]] == [r["status"] for r in first["comparison"]]
    assert second["simulationId"] == first["simulationId"]


def test_changed_source_under_same_key_fails_closed():
    port = h.port()
    h.run(p=port)
    rows = h.month_rows()
    rows[0]["qty"] = "11"  # the owner edited the source after a run: same key, other arguments
    report, _ = h.run(rows=rows, p=port, on_existing="resume")
    assert report["status"] == "aborted"
    assert "SIM-120" in h.codes(report)
    assert next(s for s in report["steps"] if s["outcome"] == "error")["errorCode"] == "idempotency_conflict"


def test_r3_r4_never_sent():
    report, port = h.run()
    assert port.calls and all(c["risk_class"] in ("R0", "R1", "R2") for c in port.calls)
    held = [s for s in report["steps"] if s["action"] == "needs_approval"]
    assert held and all(s["outcome"] == "held" and s["riskClass"] in ("R3", "R4") for s in held)
    assert {c["key"] for c in port.calls}.isdisjoint({s["idempotencyKey"] for s in held})


def test_unknown_risk_is_treated_as_r4():
    ts = h.tool_set()
    for t in ts["tools"]:
        if t["name"] == "delivery_note.submit":
            t["risk_class"] = "R9"
    report, port = h.run(ts=ts)
    step = next(s for s in report["steps"] if s["tool"] == "delivery_note.submit")
    assert step["riskClass"] == "R4" and step["outcome"] == "held"
    assert "delivery_note.submit" not in {c["tool"] for c in port.calls}


def test_caller_without_role_is_denied_and_post_blocked():
    caller = {"user_id": "u_replay", "role_ids": ["accountant"]}
    plan = _plan(caller=caller)
    grn = [s for s in plan.steps if "GRN-1" in s.source_id]
    assert [s.action for s in grn] == ["denied", "blocked"]
    assert {"SIM-110", "SIM-117"} <= {a.code for a in plan.anomalies}


def test_missing_tool_is_unmapped():
    ts = h.tool_set()
    ts["tools"] = [t for t in ts["tools"] if not t["name"].startswith("payroll_entry.")]
    plan = _plan(ts=ts)
    pay = [s for s in plan.steps if s.kind == "payroll_run"]
    assert [s.action for s in pay] == ["unmapped", "blocked"]
    assert any(a.code == "SIM-108" for a in plan.anomalies)


def test_bad_mapping_and_caller_refused():
    bad = copy.deepcopy(h.MAPPING)
    bad["sales_invoice"]["post"] = {"verb": "delete"}
    with pytest.raises(SimulatorError):
        _plan(mapping=bad)
    with pytest.raises(SimulatorError):
        _plan(caller={"user_id": "u", "role_ids": []})
    bad = copy.deepcopy(h.MAPPING)
    bad["sales_invoice"]["header"]["password"] = "x"
    with pytest.raises(SimulatorError):
        _plan(mapping=bad)


def test_generated_trading_tool_set():
    """The real generator's tool set: invoice posting is R3 (held), stock posting R2 (runs), schemas enforced."""
    sys.path.insert(0, str(ROOT / "services" / "operate"))
    try:
        from toolapi.generate import generate_tool_api
    finally:
        sys.path.pop(0)
    bp = json.loads((ROOT / "services/blueprint/fixtures/trading-distribution.blueprint.json").read_text())
    res = generate_tool_api(bp)
    assert res.ok
    ts = res.definition_set()
    mapping = {
        "sales_invoice": {"entity": "sales_invoice", "lines": "lines", "constants": {"branch": "hq_riyadh"},
                          "post": {"transition": "submit_invoice"},
                          "header": {"party": "customer", "date": "invoice_date"},
                          "line": {"item": "item", "qty": "quantity", "unit_price": "unit_price"}},
        "stock_out": {"entity": "delivery_note", "post": {"verb": "submit"}, "header": {}, "line": {}},
    }
    rows = [r for r in h.month_rows() if r["type"] in ("sales_invoice", "stock_out")]
    plan = _plan(rows=rows, ts=ts, mapping=mapping)
    by = {(s.source_id.split(":")[-1], s.stage): s for s in plan.steps}
    assert by[("SI-1", "post")].tool == "sales_invoice.transition"
    assert by[("SI-1", "post")].risk_class == "R3" and by[("SI-1", "post")].action == "needs_approval"
    # 33.33 fits the generated money pattern; 0.10 too: creates are R1 and valid
    assert by[("SI-1", "create")].action == "execute" and by[("SI-2", "create")].action == "execute"
    # The trading delivery note requires a sales order, customer and warehouse header: a bare stock move fails
    # the generated input schema before anything is sent, and its posting is blocked.
    dn = by[("DN-1", "create")]
    assert dn.risk_class == "R1" and dn.action == "invalid_arguments"
    assert by[("DN-1", "post")].action == "blocked"
    assert {a.code for a in plan.anomalies} >= {"SIM-109", "SIM-111", "SIM-117"}
