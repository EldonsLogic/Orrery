"""OPR-013 first slice: scheduled agents with budgets (ADR-0064). Fake clock, fake model-call port (PLT-026)."""
import copy
import json
import math
from pathlib import Path

import pytest

from runtime.model_call_fake import FakeModelCallPort
from runtime.schedule import CODES, Principal, ScheduleRefused, Scheduler

REQ = json.loads((Path(__file__).resolve().parents[4] / "contracts/examples/model-call-request-agent.json")
                 .read_text(encoding="utf-8"))
REG = {"platform": {(REQ["prompt_version"], "p_rules"): {"text": "Scheduled sales digest.", "data_class": "C0"}},
       "tenant_config": {}, "tools": {}, "applied_revision": {},
       "active_releases": {"operate": {REQ["prompt_version"]}}}
OWNER = Principal("t_acme", "u_1", ("sales",))
DAY = 86400


def tool(name, risk="R0", roles=("sales",), **kw):
    return {"name": name, "risk_class": risk, "agent_creatable": True, "requires": {"roles": list(roles)},
            "input_schema": {"type": "object"}, **kw}


DEFS = [tool("sales_order.list", kind="read"), tool("customer_note.create", "R1", entity_class="plain"),
        tool("sales_invoice.create", "R1", entity_class="ledger"), tool("payroll_run.get", roles=("hr",)),
        tool("purchase_order.cancel", "R2")]


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def call(ctx):
    r = copy.deepcopy(REQ)
    r.update(caller=ctx.caller(), call_id=f"{ctx.run_id}_c{ctx.calls}", idempotency_key=f"{ctx.run_id}:c{ctx.calls}",
             blocks=[{"content_id": "p_rules", "trust": "platform", "data_class": "C0"}], tools=[],
             max_output_tokens=100, min_output_tokens=50)
    return ctx.complete(r)


def digest_agent(ctx):
    call(ctx)
    ctx.draft("customer_note.create", {"text": "follow up"})


def make(port_kw=None, factory=None, roles=None, emit=None):
    clock, events, ports = Clock(0), [], []

    def default_factory(principal, budgets):
        p = FakeModelCallPort(principal=principal, registry=copy.deepcopy(REG), budgets=budgets,
                              layers=tuple(budgets), **(port_kw or {}))
        ports.append(p)
        return p
    s = Scheduler(tool_defs=lambda t: DEFS, roles_of=roles or (lambda t, u: ("sales",)),
                  port_factory=factory or default_factory, clock=clock, emit=emit or events.append)
    return s, clock, events, ports


SPEC = dict(agent_role="sales", tools=("sales_order.list", "customer_note.create"), cadence_s=DAY, start_at=1000,
            run_cap=2_000, period_s=7 * DAY, period_cap=2_500)


def refused(code, fn, *a, **kw):
    with pytest.raises(ScheduleRefused) as ei:
        fn(*a, **kw)
    assert ei.value.code == code and code in CODES


def test_run_drafts_only_reserves_and_settles_through_the_port():
    s, clock, events, ports = make()
    sch = s.create(OWNER, **SPEC)
    clock.t = 1000
    [rec] = s.tick(digest_agent)
    assert rec.outcome == "completed" and rec.drafts == (("customer_note.create", {"text": "follow up"}),)
    p = ports[0]
    assert p.budgets == {"run": 2_000} and p.principal["on_behalf_of"] == "u_1" and p.principal["role_ids"] == ["sales"]
    assert p.principal["tenant_id"] == "t_acme" and p.principal["tool_grant"] == list(sch.tools)
    assert p._tainted_threads, "a scheduled run is tainted from the start (ALP-019)"
    assert 0 < rec.cost == sum(e["data"]["cost_micro_usd"] for e in p.events) <= 2_000
    assert s.period_spent(sch.id) == rec.cost
    types = [e["type"] for e in events]
    assert types == ["schedule.created", "agent.run_started", "agent.tool_proposed", "agent.run_completed"]
    assert all(e["tenant_id"] == "t_acme" for e in events) and "follow up" not in json.dumps(events)


def test_period_budget_exhaustion_refuses_and_meters_then_resets_next_period():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    outcomes = []
    for day in range(4):
        clock.t = 1000 + day * DAY
        outcomes += [r.code or r.outcome for r in s.tick(digest_agent)]
    assert outcomes[:2] == ["completed", "completed"] and outcomes[2:] == ["budget_exhausted"] * 2
    assert [e for e in events if e["type"] == "agent.budget_exceeded"][0]["data"]["scope"] == "period"
    clock.t = 1000 + 7 * DAY                                        # new period
    assert s.tick(digest_agent)[0].outcome == "completed" and s.period_spent(sch.id) > 0


@pytest.mark.parametrize("port_kw,spec", [({"meter_up": False}, {}), ({}, {"run_cap": 10})])
def test_reservation_failing_at_the_port_fails_closed_and_discards_drafts(port_kw, spec):
    s, clock, events, _ = make(port_kw=port_kw)
    sch = s.create(OWNER, **(SPEC | spec))
    clock.t = 1000
    [rec] = s.tick(digest_agent)
    assert (rec.outcome, rec.code, rec.detail, rec.drafts) == ("failed", "port_refused", "budget_refused", ())
    assert s.period_spent(sch.id) == 0 and s.period_held(sch.id) == 0
    assert events[-1]["type"] == "agent.run_failed" and not any(e["type"] == "agent.tool_proposed" for e in events)


def test_tenant_mismatch_on_create_update_and_port():
    s, clock, _, _ = make()
    refused("tenant_mismatch", s.create, OWNER, tenant_id="t_other", **SPEC)
    refused("owner_mismatch", s.create, OWNER, owner_id="u_2", **SPEC)
    sch = s.create(OWNER, **SPEC)
    refused("not_found", s.update, Principal("t_other", "u_1", ("sales",)), sch.id, cadence_s=2 * DAY)
    refused("owner_mismatch", s.update, Principal("t_acme", "u_2", ("sales",)), sch.id, cadence_s=2 * DAY)

    def foreign(principal, budgets):
        return FakeModelCallPort(principal=principal | {"tenant_id": "t_other"}, registry=REG, budgets=budgets,
                                 layers=tuple(budgets))
    s2, clock2, _, _ = make(factory=foreign)
    s2.create(OWNER, **SPEC)
    clock2.t = 1000
    rec = s2.tick(digest_agent)[0]
    assert (rec.outcome, rec.code) == ("failed", "tenant_mismatch")


def test_role_escalation_and_tool_rules():
    s, clock, _, _ = make()
    refused("role_escalation", s.create, OWNER, **(SPEC | {"agent_role": "hr"}))
    refused("tool_not_allowed", s.create, OWNER, **(SPEC | {"tools": ("payroll_run.get",)}))
    refused("draft_only", s.create, OWNER, **(SPEC | {"tools": ("sales_invoice.create",)}))
    refused("draft_only", s.create, OWNER, **(SPEC | {"tools": ("purchase_order.cancel",)}))
    sch = s.create(OWNER, **SPEC)
    refused("role_escalation", s.update, OWNER, sch.id, agent_role="owner")
    refused("invalid_schedule", s.update, OWNER, sch.id, role_ids=("owner",))

    def sneaky(ctx):                                               # a draft outside the schedule's tools
        ctx.draft("sales_invoice.create", {})
    clock.t = 1000
    rec = s.tick(sneaky)[0]
    assert (rec.outcome, rec.code, rec.drafts) == ("failed", "tool_not_allowed", ())


def test_owner_losing_the_role_suspends_the_schedule():
    roles = {"now": ("sales",)}
    s, clock, events, _ = make(roles=lambda t, u: roles["now"])
    sch = s.create(OWNER, **SPEC)
    roles["now"] = ("viewer",)
    clock.t = 1000
    assert s.tick(digest_agent)[0].code == "owner_permission_lost"
    assert not s.get(OWNER, sch.id).active and events[-1]["type"] == "schedule.suspended"
    clock.t = 1000 + DAY
    assert s.tick(digest_agent) == []


def test_overlapping_run_is_refused():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)
    inner = []

    def reenter(ctx):                                              # next slot comes due while this run is open
        clock.t = 1000 + DAY
        inner.extend(s.tick(digest_agent))
    clock.t = 1000
    assert s.tick(reenter)[0].outcome == "completed" and [r.code for r in inner] == ["overlap"]
    assert [r.slot for r in s.tick(digest_agent)] == [1]           # deferred, not dropped


def test_clock_edges():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)
    clock.t = 999.999
    assert s.tick(digest_agent) == []                              # before start
    clock.t = 1000
    assert len(s.tick(digest_agent)) == 1                          # exactly on the boundary
    assert s.tick(digest_agent) == []                              # same slot again
    clock.t = 1000 + DAY - 0.001
    assert s.tick(digest_agent) == []
    clock.t = 1000 + 5 * DAY                                       # missed slots collapse into one run
    assert len(s.tick(digest_agent)) == 1
    for bad in (1000 + DAY, math.nan, math.inf, None, True):       # backwards step or a broken clock
        clock.t = bad
        refused("clock_fault", s.tick, digest_agent)


def test_agent_error_or_audit_failure_fails_closed():
    s, clock, events, _ = make()
    s.create(OWNER, **SPEC)

    def boom(ctx):
        call(ctx)
        ctx.draft("customer_note.create", {})
        raise RuntimeError("x")
    clock.t = 1000
    rec = s.tick(boom)[0]
    assert (rec.outcome, rec.code, rec.drafts) == ("failed", "run_failed", ()) and rec.cost > 0  # spend is real

    def broken(e):
        raise OSError("audit down")
    s2, clock2, _, ports = make(emit=broken)
    refused("audit_unavailable", s2.create, OWNER, **SPEC)


def test_every_schedule_change_is_logged_and_invalid_specs_refuse():
    s, _, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    sch2 = s.update(OWNER, sch.id, cadence_s=2 * DAY)
    s.disable(OWNER, sch.id)
    assert sch2.version == 2 and not s.get(OWNER, sch.id).active
    log = [(e["type"], e["data"].get("changed")) for e in events]
    assert log == [("schedule.created", None), ("schedule.updated", ["cadence_s"]), ("schedule.disabled", None)]
    assert all(e["data"]["actor_id"] == "u_1" for e in events)
    for bad in ({"cadence_s": 60}, {"run_cap": 0}, {"run_cap": 6_000}, {"period_s": 3600}, {"tools": ()},
                {"cadence_s": True}, {"tools": ("sales_order.list", "sales_order.list")}):
        refused("invalid_schedule", s.create, OWNER, **(SPEC | bad))
