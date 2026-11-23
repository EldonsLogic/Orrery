"""OPR-013 first slice: scheduled agents with budgets (ADR-0064). Fake clock, fake model-call port (PLT-026)."""
import copy
import json
import math
import threading
from pathlib import Path

import pytest

from runtime import schedule as S
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


W = {"kind": "write", "entity_class": "plain"}
DEFS = [tool("sales_order.list", kind="read"), tool("customer_note.create", "R1", **W),
        tool("sales_invoice.create", "R1", kind="write", entity_class="ledger"), tool("payroll_run.get", roles=("hr",)),
        tool("purchase_order.cancel", "R2"), tool("customer_note.delete", "R1", **W),
        tool("customer_note.update", "R2", **W), tool("gl_posting.create", "R1"),
        tool("customer.export", "R1", **W), tool("einvoice.create", "R1", **W), tool("wps_file.create", "R1", **W),
        tool("customer_note.transition", "R1", **W), tool("lead.create", "R1", transitions=[], **W)]


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def call(ctx, thread_tainted=True):
    r = copy.deepcopy(REQ)
    n = len(ctx.run_id) + id(r) % 997
    r.update(caller=ctx.caller(), call_id=f"{ctx.run_id}_c{n}", idempotency_key=f"{ctx.run_id}:c{n}",
             blocks=[{"content_id": "p_rules", "trust": "platform", "data_class": "C0"}], tools=[],
             max_output_tokens=100, min_output_tokens=50, thread_tainted=thread_tainted)
    return ctx.complete(r)


def digest_agent(ctx):
    call(ctx)
    ctx.draft("customer_note.create", {"text": "follow up"})


def fake_port(principal, budgets, cls=FakeModelCallPort, **kw):
    b = {"tenant": 1_000_000, **budgets}
    return cls(principal=principal, registry=copy.deepcopy(REG), budgets=b, layers=tuple(b), **kw)


def make(port_kw=None, factory=None, roles=None, emit=None, defs=None):
    clock, events, ports = Clock(0), [], []

    def default_factory(principal, budgets):
        ports.append(fake_port(principal, budgets, **(port_kw or {})))
        return ports[-1]
    s = Scheduler(tool_defs=lambda t: defs if defs is not None else DEFS,
                  roles_of=roles or (lambda t, u: ("sales",)),
                  port_factory=factory or default_factory, clock=clock, emit=emit or events.append)
    return s, clock, events, ports


SPEC = dict(agent_role="sales", tools=("sales_order.list", "customer_note.create"), cadence_s=DAY, start_at=1000,
            run_cap=2_000, period_s=7 * DAY, period_cap=2_500)


def refused(code, fn, *a, **kw):
    with pytest.raises(ScheduleRefused) as ei:
        fn(*a, **kw)
    assert ei.value.code == code and code in CODES


def first_run(s, clock, agent=digest_agent):
    clock.t = 1000
    return s.tick(agent)[0]


def test_run_drafts_only_reserves_and_settles_through_the_port():
    s, clock, events, ports = make()
    sch = s.create(OWNER, **SPEC)
    rec = first_run(s, clock)
    assert rec.outcome == "completed" and rec.tainted
    assert rec.drafts == ({"tool": "customer_note.create", "args": {"text": "follow up"}, "tainted": True},)
    p = ports[0]
    assert p.budgets == {"tenant": 1_000_000, "run": 2_000} and p.principal["on_behalf_of"] == "u_1"
    assert p.principal["role_ids"] == ["sales"] and p.principal["tool_grant"] == list(sch.tools)
    assert p._tainted_threads, "a scheduled run is tainted from the start (ALP-019)"
    assert 0 < rec.cost == sum(e["data"]["cost_micro_usd"] for e in p.events) <= 2_000
    assert s.period_spent(OWNER, sch.id) == rec.cost and s.period_held(OWNER, sch.id) == 0
    types = [e["type"] for e in events]
    assert types == ["schedule.created", "agent.run_started", "agent.tool_proposed", "agent.run_completed"]
    assert all(e["tenant_id"] == "t_acme" and e["data"]["owner_id"] == "u_1" and e["data"]["on_behalf_of"] == "u_1"
               for e in events)
    assert all(e["data"]["slot"] == 0 and e["data"]["at"] == 1000 for e in events[1:])
    assert "follow up" not in json.dumps(events)


def test_period_budget_exhaustion_refuses_and_meters_then_frees_up():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    outcomes = []
    for day in range(4):
        clock.t = 1000 + day * DAY
        outcomes += [r.code or r.outcome for r in s.tick(digest_agent)]
    assert outcomes == ["completed", "completed", "budget_exhausted", "budget_exhausted"]
    assert [e for e in events if e["type"] == "agent.budget_exceeded"][0]["data"]["scope"] == "period"
    clock.t = 1000 + 7 * DAY                                        # the first run leaves the trailing window
    assert s.tick(digest_agent)[0].outcome == "completed" and s.period_spent(OWNER, sch.id) > 0


def test_cap_boundary_is_allowed():
    s, clock, _, _ = make()
    s.create(OWNER, **(SPEC | {"run_cap": 2_500}))
    assert first_run(s, clock, lambda ctx: None).outcome == "completed"   # 0 + 2500 == cap


@pytest.mark.parametrize("port_kw,spec", [({"meter_up": False}, {}), ({}, {"run_cap": 10})])
def test_reservation_failing_at_the_port_fails_closed_and_discards_drafts(port_kw, spec):
    s, clock, events, _ = make(port_kw=port_kw)
    sch = s.create(OWNER, **(SPEC | spec))
    rec = first_run(s, clock)
    assert (rec.outcome, rec.code, rec.detail, rec.drafts) == ("failed", "port_refused", "budget_refused", ())
    assert s.period_spent(OWNER, sch.id) == 0 and s.period_held(OWNER, sch.id) == 0
    assert events[-1]["type"] == "agent.run_failed" and not any(e["type"] == "agent.tool_proposed" for e in events)


class BadMeter(FakeModelCallPort):
    bad = math.nan

    def complete(self, request):
        out = super().complete(request)
        self.events[-1] = copy.deepcopy(self.events[-1])
        self.events[-1]["data"]["cost_micro_usd"] = self.bad
        return out


@pytest.mark.parametrize("bad", [math.nan, -500, True, 12.5, "100", None, 10**15])
def test_invalid_metered_cost_settles_at_the_hold(bad):
    cls = type("B", (BadMeter,), {"bad": bad})
    s, clock, _, _ = make(factory=lambda p, b: fake_port(p, b, cls=cls))
    sch = s.create(OWNER, **SPEC)
    assert first_run(s, clock).cost == 2_000 and s.period_spent(OWNER, sch.id) == 2_000
    clock.t = 1000 + DAY
    assert s.tick(digest_agent)[0].code == "budget_exhausted"


class Noisy(FakeModelCallPort):
    def complete(self, request):
        out = super().complete(request)
        for other in ({"correlation_id": "other", "tenant_id": "t_acme"}, {"tenant_id": "t_other"},
                      {"type": "meter.other"}):
            self.events.append(copy.deepcopy(self.events[-1]) | other)
        return out


def test_only_this_runs_events_count_and_no_feed_means_the_hold():
    s, clock, _, _ = make(factory=lambda p, b: fake_port(p, b, cls=Noisy))
    s.create(OWNER, **SPEC)
    plain, pclock, _, _ = make()
    plain.create(OWNER, **SPEC)
    assert first_run(s, clock).cost == first_run(plain, pclock).cost > 0   # one event, not four

    class NoFeed:
        layers = ("tenant", "run")

        def __init__(self, principal):
            self.principal = principal

        def complete(self, request):
            return {"kind": "reply", "text": "x"}
    class Silent(NoFeed):
        events = ()                                                 # a feed, but no event for a charged reply
    for cls in (NoFeed, Silent):
        s2, clock2, _, _ = make(factory=lambda p, b: cls(p))
        s2.create(OWNER, **SPEC)
        assert first_run(s2, clock2, lambda ctx: call(ctx)).cost == 2_000


def test_context_exposes_no_port_drafts_or_schedule_and_forces_taint():
    s, clock, _, ports = make()
    s.create(OWNER, **SPEC)
    seen = {}

    def nosy(ctx):
        for attr in ("port", "drafts", "schedule", "_port"):
            with pytest.raises(AttributeError):
                getattr(ctx, attr)
        with pytest.raises(AttributeError):
            ctx.extra = 1
        call(ctx, thread_tainted=False)
        args = {"text": "a"}
        ctx.draft("customer_note.create", args)
        args["text"] = "changed"
        seen["ok"] = True
    rec = first_run(s, clock, nosy)
    assert seen and rec.outcome == "completed" and ports[0]._tainted_threads
    assert rec.drafts[0]["args"] == {"text": "a"}


def test_tenant_mismatch_on_create_update_and_port():
    s, clock, events, _ = make()
    refused("tenant_mismatch", s.create, OWNER, tenant_id="t_other", **SPEC)
    refused("owner_mismatch", s.create, OWNER, owner_id="u_2", **SPEC)
    assert [e["data"]["code"] for e in events] == ["tenant_mismatch", "owner_mismatch"]
    sch = s.create(OWNER, **SPEC)
    refused("not_found", s.update, Principal("t_other", "u_1", ("sales",)), sch.id, cadence_s=2 * DAY)
    refused("owner_mismatch", s.update, Principal("t_acme", "u_2", ("sales",)), sch.id, cadence_s=2 * DAY)
    refused("not_found", s.period_spent, Principal("t_other", "u_1", ("sales",)), sch.id)
    s2, clock2, _, _ = make(factory=lambda p, b: fake_port(p | {"tenant_id": "t_other"}, b))
    s2.create(OWNER, **SPEC)
    rec = first_run(s2, clock2)
    assert (rec.outcome, rec.code) == ("failed", "tenant_mismatch")


def test_port_without_a_tenant_layer_is_refused():
    s, clock, _, _ = make(factory=lambda p, b: FakeModelCallPort(principal=p, registry=REG, budgets=b,
                                                                 layers=tuple(b)))
    s.create(OWNER, **SPEC)
    assert first_run(s, clock).code == "tenant_budget_missing"


def test_role_escalation_and_malformed_principal():
    s, _, _, _ = make()
    refused("role_escalation", s.create, OWNER, **(SPEC | {"agent_role": "hr"}))
    sch = s.create(OWNER, **SPEC)
    refused("role_escalation", s.update, OWNER, sch.id, agent_role="owner")
    refused("invalid_schedule", s.update, OWNER, sch.id, role_ids=("owner",))
    with pytest.raises(ScheduleRefused):
        Principal("t_acme", "u_1", "presales_viewer")              # a string would be a substring test


@pytest.mark.parametrize("name,code", [
    ("payroll_run.get", "tool_not_allowed"), ("sales_invoice.create", "draft_only"),
    ("purchase_order.cancel", "draft_only"), ("customer_note.delete", "draft_only"),
    ("customer_note.update", "draft_only"), ("gl_posting.create", "draft_only"), ("customer.export", "draft_only"),
    ("einvoice.create", "draft_only"), ("wps_file.create", "draft_only"),
    ("customer_note.transition", "draft_only"), ("lead.create", "draft_only")])
def test_draft_only_tool_rules(name, code):
    s, _, _, _ = make()
    refused(code, s.create, OWNER, **(SPEC | {"tools": (name,)}))


def test_run_time_tool_recheck_and_drafts_outside_the_schedule():
    defs = list(DEFS)
    s, clock, _, _ = make(defs=defs)
    s.create(OWNER, **SPEC)

    def sneaky(ctx):
        ctx.draft("sales_invoice.create", {})
    assert (first_run(s, clock, sneaky).code) == "tool_not_allowed"
    defs[1] = tool("customer_note.create", "R1", kind="write", entity_class="ledger")
    clock.t = 1000 + DAY
    rec = s.tick(digest_agent)[0]
    assert (rec.outcome, rec.code, rec.drafts, rec.cost) == ("failed", "draft_only", (), 0)   # checked before any call


def test_owner_losing_the_role_suspends_the_schedule_with_an_audit():
    roles = {"now": ("sales",)}
    s, clock, events, _ = make(roles=lambda t, u: roles["now"])
    sch = s.create(OWNER, **SPEC)
    roles["now"] = ("viewer",)
    assert first_run(s, clock).code == "owner_permission_lost"
    assert not s.get(OWNER, sch.id).active
    assert [e["type"] for e in events[-2:]] == ["schedule.suspended", "agent.run_refused"]
    clock.t = 1000 + DAY
    assert s.tick(digest_agent) == []


def test_suspension_holds_even_if_its_audit_fails_and_other_tenants_still_run():
    state = {"down": False, "acme_roles": ("sales",)}

    def emit(e):
        if state["down"] and e["tenant_id"] == "t_acme":
            raise OSError("down")
    s, clock, _, _ = make(roles=lambda t, u: state["acme_roles"] if t == "t_acme" else ("sales",), emit=emit)
    a = s.create(OWNER, **SPEC)
    b = s.create(Principal("t_beta", "u_9", ("sales",)), **SPEC)
    state.update(down=True, acme_roles=("viewer",))
    clock.t = 1000
    recs = {r.schedule_id: r for r in s.tick(digest_agent)}
    assert recs[a.id].code == "audit_unavailable" and not s.get(OWNER, a.id).active
    assert recs[b.id].outcome == "completed"


def test_roles_store_failure_is_recorded():
    def boom(t, u):
        raise OSError("x")
    s, clock, events, _ = make(roles=boom)
    s.create(OWNER, **SPEC)
    assert first_run(s, clock).code == "roles_unavailable"
    assert events[-1]["type"] == "agent.run_refused" and events[-1]["data"]["code"] == "roles_unavailable"


def test_overlapping_run_is_refused_and_audited():
    s, clock, events, _ = make()
    s.create(OWNER, **SPEC)
    inner = []

    def reenter(ctx):
        clock.t = 1000 + DAY
        inner.extend(s.tick(digest_agent))
        clock.t = 1000                                             # back inside this run's deadline
    assert first_run(s, clock, reenter).outcome == "completed" and [r.code for r in inner] == ["overlap"]
    assert any(e["data"].get("code") == "overlap" for e in events)
    clock.t = 1000 + DAY
    assert [r.slot for r in s.tick(digest_agent)] == [1]           # deferred, not dropped


def test_two_threads_run_a_slot_once_and_a_late_disable_holds():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **SPEC)
    clock.t = 1000
    gate, runs, results = threading.Barrier(2), [], []

    def slow(ctx):
        runs.append(ctx.run_id)
        digest_agent(ctx)

    def worker():
        gate.wait()
        results.extend(s.tick(slow))
    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert runs == [f"srun_{sch.id}_0"] and len(results) == 1
    s.disable(OWNER, sch.id)
    clock.t = 1000 + DAY
    assert s.tick(digest_agent) == []


def test_clock_edges():
    s, clock, events, _ = make()
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
    for bad in (1000 + DAY, math.nan, math.inf, None, True, 1000 + 5 * DAY + S.MAX_STEP_S + 1, S.MAX_EPOCH_S + 1):
        clock.t = bad
        refused("clock_fault", s.tick, digest_agent)
    assert events[-1]["type"] == "scheduler.clock_fault"
    clock.t = 1000 + 6 * DAY                                       # rejected readings were not stored
    assert len(s.tick(digest_agent)) == 1
    s2, clock2, _, _ = make()
    for bad in (True, S.MAX_EPOCH_S + 1):                          # a fresh scheduler too
        clock2.t = bad
        refused("clock_fault", s2.tick, digest_agent)


def test_wall_clock_limit_per_run():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)

    def slow(ctx):
        clock.t += S.MAX_RUN_S + 1
        ctx.draft("customer_note.create", {})
    rec = first_run(s, clock, slow)
    assert (rec.outcome, rec.code, rec.drafts) == ("failed", "run_timeout", ())


def test_agent_errors_keep_spend_and_repeated_failures_suspend():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))

    def boom(ctx):
        call(ctx)
        raise RuntimeError("x")
    codes = []
    for day in range(S.MAX_FAILURES):
        clock.t = 1000 + day * DAY
        rec = s.tick(boom)[0]
        codes.append(rec.code)
        assert rec.cost > 0 and rec.drafts == ()
    assert codes == ["run_failed"] * S.MAX_FAILURES and not s.get(OWNER, sch.id).active
    assert events[-1]["type"] == "schedule.suspended" and events[-1]["data"]["reason"] == "repeated_failures"


def test_keyboard_interrupt_still_settles_spend():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **SPEC)

    def stop(ctx):
        call(ctx)
        raise KeyboardInterrupt
    clock.t = 1000
    with pytest.raises(KeyboardInterrupt):
        s.tick(stop)
    assert s.period_spent(OWNER, sch.id) > 0 and s.period_held(OWNER, sch.id) == 0


def test_audit_failures():
    def broken(e):
        raise OSError("audit down")
    s, _, _, _ = make(emit=broken)
    refused("audit_unavailable", s.create, OWNER, **SPEC)
    state = {"fail": set()}

    def emit(e):
        if e["type"] in state["fail"]:
            raise OSError("down")
    s2, clock2, _, _ = make(emit=emit)
    sch = s2.create(OWNER, **SPEC)
    state["fail"] = {"agent.run_completed", "agent.run_failed"}
    rec = first_run(s2, clock2)
    assert (rec.outcome, rec.code, rec.drafts) == ("failed", "audit_unavailable", ()) and rec.cost > 0
    assert s2.period_spent(OWNER, sch.id) == rec.cost


def test_limits_and_budget_window_cannot_be_reset_by_update():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **SPEC)
    first_run(s, clock)
    spent = s.period_spent(OWNER, sch.id)
    s.update(OWNER, sch.id, period_s=DAY, start_at=2000)
    clock.t = 1000 + 2 * DAY
    assert s.tick(lambda ctx: None)[0].cost == 0
    assert s.period_spent(OWNER, sch.id) == spent                  # the window keeps the longest period
    for _ in range(S.MAX_SCHEDULES_PER_OWNER - 1):
        s.create(OWNER, **SPEC)
    refused("schedule_limit", s.create, OWNER, **SPEC)
    refused("invalid_schedule", s.update, OWNER, sch.id, period_cap=S.MAX_CAP + 1)


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
    assert events[-1]["type"] == "schedule.change_refused"
