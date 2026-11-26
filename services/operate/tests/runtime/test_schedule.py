"""OPR-013 first slice: scheduled agents with budgets (ADR-0064). Fake clock, fake model-call port (PLT-026)."""
import copy
import json
import math
import threading
from datetime import datetime, timezone
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
        tool("customer_note.transition", "R1", **W), tool("lead.create", "R1", transitions=[], **W),
        tool("memo.create", "R1", kind="write"), tool("memo_two.create", "R1", entity_class="plain")] + [
        tool(n, "R1", **W) for n in ("glPosting.create", "generalledger.create", "zakat_return.create",
                                     "gosi_contribution.create", "withholding.create", "bank_account.update",
                                     "GLPosting.create", "ZATCAInvoice.create", "salesinvoice.create",
                                     "payrollrun.create", "journalentry.create", "salaryslip.create",
                                     "wpsfile.create", "iban_change.create", "vatReturn.create",
                                     "glNote.create")] + [
        tool(n, "R1", **W) for n in ("task.create", "visit_report.create", "meeting.update")]


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
    assert types == ["agent_schedule.created", "agent.run_started", "agent.tool_proposed", "agent.run_completed"]
    assert all(e["tenant_id"] == "t_acme" and e["data"]["owner_id"] == "u_1" and e["data"]["on_behalf_of"] == "u_1"
               for e in events)
    assert all(e["data"]["slot"] == 0 and e["data"]["at"] == 1000 for e in events[1:])
    assert "follow up" not in json.dumps(events)


def test_budget_exhaustion_pauses_until_the_owner_resumes():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    outcomes = []
    for day in range(4):
        clock.t = 1000 + day * DAY
        outcomes += [r.code or r.outcome for r in s.tick(digest_agent)]
    assert outcomes == ["completed", "completed", "budget_exhausted"]  # then paused: no further run (Q-598)
    assert [e for e in events if e["type"] == "agent.budget_exceeded"][0]["data"]["scope"] == "period"
    paused = [e for e in events if e["type"] == "agent_schedule.suspended"]
    assert [e["data"]["reason"] for e in paused] == ["budget_exhausted"] and not s.get(OWNER, sch.id).active
    refused("budget_exhausted", s.resume, OWNER, sch.id)               # still exhausted: stays paused
    assert not s.get(OWNER, sch.id).active
    clock.t = 1000 + 8 * DAY                                         # the window has freed up, yet no auto-restart
    assert s.tick(digest_agent) == []
    spent = s.period_spent(OWNER, sch.id)
    assert s.resume(OWNER, sch.id).active and s.period_spent(OWNER, sch.id) == spent   # ledger kept
    clock.t = 1000 + 9 * DAY
    assert s.tick(digest_agent)[0].outcome == "completed"


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
        genuine = self.events[-1]
        for other in ({"correlation_id": "other"}, {"tenant_id": "t_other"}, {"type": "meter.other"}):
            self.events.append(copy.deepcopy(genuine) | other)              # each differs in one field only
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
    ("customer_note.transition", "draft_only"), ("lead.create", "draft_only"), ("memo.create", "draft_only"),
    ("memo_two.create", "draft_only"), ("glPosting.create", "draft_only"), ("generalledger.create", "draft_only"),
    ("zakat_return.create", "draft_only"), ("gosi_contribution.create", "draft_only"),
    ("withholding.create", "draft_only"), ("bank_account.update", "draft_only"),
    *[(n, "draft_only") for n in ("GLPosting.create", "ZATCAInvoice.create", "salesinvoice.create", "payrollrun.create",
                                  "journalentry.create", "salaryslip.create", "wpsfile.create", "iban_change.create",
                                  "vatReturn.create", "glNote.create")]])
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
    assert [e["type"] for e in events[-2:]] == ["agent_schedule.suspended", "agent.run_refused"]
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
    assert runs == [f"srun_{sch.id}_v1_0"] and len(results) == 1
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
    for bad in (1000 + DAY, math.nan, math.inf, None, True, S.MAX_EPOCH_S + 1):
        clock.t = bad
        refused("clock_fault", s.tick, digest_agent)
    assert events[-1]["type"] == "platform_scheduler.clock_fault"
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
    assert events[-1]["type"] == "agent_schedule.suspended" and events[-1]["data"]["reason"] == "repeated_failures"


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
    assert S.MAX_CAP == 50_000_000 and S.MIN_PERIOD_S == DAY       # platform defaults pinned (ADR-0064 item 6)
    assert s.update(OWNER, sch.id, period_cap=S.MAX_CAP, run_cap=S.MAX_CAP).run_cap == S.MAX_CAP
    refused("invalid_schedule", s.update, OWNER, sch.id, period_s=DAY - 1)
    other = Principal("t_beta", "u_1", ("sales",))                 # the limit is per tenant and owner
    assert s.create(other, **SPEC).tenant_id == "t_beta"


def test_every_schedule_change_is_logged_and_invalid_specs_refuse():
    s, _, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    sch2 = s.update(OWNER, sch.id, cadence_s=2 * DAY)
    s.disable(OWNER, sch.id)
    assert sch2.version == 2 and not s.get(OWNER, sch.id).active
    log = [(e["type"], e["data"].get("changed_fields")) for e in events]
    assert log == [("agent_schedule.created", None), ("agent_schedule.updated", ["cadence_s"]), ("agent_schedule.disabled", None)]
    assert all(e["data"]["actor_id"] == "u_1" for e in events)
    for bad in ({"cadence_s": 60}, {"run_cap": 0}, {"run_cap": 6_000}, {"period_s": 3600}, {"tools": ()},
                {"cadence_s": True}, {"tools": ("sales_order.list", "sales_order.list")},
                {"cadence_s": 300, "period_s": 3600}):                    # window at least a day
        refused("invalid_schedule", s.create, OWNER, **(SPEC | bad))
    assert events[-1]["type"] == "agent_schedule.change_refused"


def test_deadline_counts_from_the_claim_not_the_tick():
    s, clock, _, _ = make(roles=lambda t, u: ("sales",))
    a = [s.create(OWNER, **(SPEC | {"period_cap": 50_000})) for _ in range(2)]
    b = s.create(Principal("t_beta", "u_9", ("sales",)), **(SPEC | {"period_cap": 50_000}))

    def agent(ctx):
        if ctx.caller()["tenant_id"] == "t_acme":
            clock.t += 301                                           # each A run is slow but inside its own limit
        digest_agent(ctx)
    for day in range(S.MAX_FAILURES + 1):
        clock.t = 1000 + day * DAY
        recs = {r.schedule_id: r for r in s.tick(agent)}
        assert recs[b.id].outcome == "completed", recs[b.id]
        assert all(recs[x.id].code != "run_timeout" for x in a if x.id in recs)
    assert s._s[b.id].active


@pytest.mark.parametrize("port_kw", [{"meter_up": False}, {"kill_switch": True}])
def test_platform_failures_do_not_count_toward_suspension(port_kw):
    s, clock, _, _ = make(port_kw=port_kw)
    sch = s.create(OWNER, **SPEC)
    for day in range(S.MAX_FAILURES + 1):
        clock.t = 1000 + day * DAY
        assert s.tick(digest_agent)[0].code == "port_refused"
    assert s.get(OWNER, sch.id).active


def test_timeouts_and_audit_outages_do_not_count_toward_suspension():
    state = {"fail": set()}

    def emit(e):
        if e["type"] in state["fail"]:
            raise OSError("down")
    s, clock, _, _ = make(emit=emit)
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))
    state["fail"] = {"agent.run_completed", "agent.run_failed"}
    for day in range(S.MAX_FAILURES + 1):
        clock.t = 1000 + day * DAY
        assert s.tick(digest_agent)[0].code == "audit_unavailable"
    state["fail"] = set()

    def slow(ctx):
        clock.t += S.MAX_RUN_S + 1
    for day in range(S.MAX_FAILURES + 1):
        clock.t = 1000 + (10 + day) * DAY
        assert s.tick(slow)[0].code == "run_timeout"
    assert s.get(OWNER, sch.id).active


def test_a_success_resets_the_failure_count():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))

    def boom(ctx):
        raise RuntimeError("x")
    plan = [boom, boom, digest_agent, boom, boom]
    for day, agent in enumerate(plan):
        clock.t = 1000 + day * DAY
        s.tick(agent)
    assert s.get(OWNER, sch.id).active                              # fail, fail, pass, fail, fail: not suspended


def test_owner_resume_keeps_the_ledger_and_is_audited():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))

    def boom(ctx):
        call(ctx)
        raise RuntimeError("x")
    for day in range(S.MAX_FAILURES):
        clock.t = 1000 + day * DAY
        s.tick(boom)
    spent = s.period_spent(OWNER, sch.id)
    assert not s.get(OWNER, sch.id).active and spent > 0
    refused("owner_mismatch", s.resume, Principal("t_acme", "u_2", ("sales",)), sch.id)
    refused("role_escalation", s.resume, Principal("t_acme", "u_1", ("viewer",)), sch.id)
    resumed = s.resume(OWNER, sch.id)
    assert resumed.active and events[-1]["type"] == "agent_schedule.resumed"
    assert s.period_spent(OWNER, sch.id) == spent
    clock.t = 1000 + S.MAX_FAILURES * DAY
    assert s.tick(boom)[0].code == "run_failed" and s.get(OWNER, sch.id).active   # resume resets the count


def test_recreating_schedules_does_not_reset_the_owner_budget():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **SPEC)
    first_run(s, clock)
    clock.t = 1000 + DAY
    assert s.tick(digest_agent)[0].outcome == "completed"
    s.disable(OWNER, sch.id)
    again = s.create(OWNER, **(SPEC | {"start_at": 1000 + 2 * DAY}))
    clock.t = 1000 + 2 * DAY
    assert s.tick(digest_agent)[0].code == "budget_exhausted"
    assert s.period_spent(OWNER, again.id) == s.period_spent(OWNER, sch.id) > 0


def test_context_functions_carry_no_meter_or_drafts():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)
    seen = {}

    def nosy(ctx):
        for fn in (ctx.complete, ctx.draft, ctx.caller):
            assert not hasattr(fn, "__self__")
            cells = [c.cell_contents for c in (fn.__closure__ or ())]
            assert all(isinstance(c, str) for c in cells), cells
        seen["ok"] = True
        digest_agent(ctx)
    rec = first_run(s, clock, nosy)
    assert seen and rec.drafts[0]["tainted"] is True


def test_end_of_run_tool_recheck():
    defs = list(DEFS)
    s, clock, _, _ = make(defs=defs)
    s.create(OWNER, **SPEC)

    def agent(ctx):
        digest_agent(ctx)
        defs[1] = tool("customer_note.create", "R1", kind="write", entity_class="ledger")
    rec = first_run(s, clock, agent)
    assert (rec.outcome, rec.code, rec.drafts) == ("failed", "draft_only", ())


def test_role_store_must_return_a_tuple():
    s, clock, _, _ = make(roles=lambda t, u: ["sales"])
    s.create(OWNER, **SPEC)
    assert first_run(s, clock).code == "roles_unavailable"


def test_long_gap_is_a_fresh_start_that_keeps_the_ledger():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    first_run(s, clock)
    spent = s.period_spent(OWNER, sch.id)
    clock.t = 1000 + S.MAX_STEP_S + 2 * DAY
    assert len(s.tick(digest_agent)) == 1 and any(e["type"] == "platform_scheduler.clock_gap" for e in events)
    assert s.period_spent(OWNER, sch.id) > spent                    # the earlier run still counts after the gap


def test_far_future_first_reading_recovers_ticking_without_replay():
    s, clock, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    clock.t = 3_900_000_000                                          # implausible but in range
    s.tick(digest_agent)
    outs = []
    for i in range(S.REBASE_AFTER):
        clock.t = 1000 + i
        try:
            outs.append(len(s.tick(digest_agent)))
        except ScheduleRefused as exc:
            outs.append(exc.code)
    assert outs[:-1] == ["clock_fault"] * (S.REBASE_AFTER - 1) and outs[-1] == 0
    assert any(e["type"] == "platform_scheduler.clock_rebase" for e in events)
    clock.t = 1000 + DAY
    assert s.tick(digest_agent) == []                                # ticks again; no slot below the mark runs
    assert s.period_spent(OWNER, sch.id) > 0                         # the later row keeps counting (fail closed)


def test_rebase_keeps_the_cap_and_never_replays_a_slot():
    s, clock, events, _ = make(factory=lambda p, b: fake_port(p, b, cls=BadMeter))  # runs settle at the 2,000 hold
    spec = SPEC | {"cadence_s": 3600, "period_s": DAY, "period_cap": 2_500, "run_cap": 2_000}
    s.create(OWNER, **spec)
    t0 = 1000 + 5 * DAY + 10 * 3600
    recs = []
    clock.t = t0
    recs += s.tick(digest_agent)
    clock.t = t0 + 3600
    recs += s.tick(digest_agent)
    assert [r.outcome for r in recs] == ["completed", "refused"]
    for i in range(S.REBASE_AFTER):                                  # back two days, then rebase
        clock.t = t0 - 2 * DAY + i
        try:
            recs += s.tick(digest_agent)
        except ScheduleRefused:
            pass
    assert any(e["type"] == "platform_scheduler.clock_rebase" for e in events)
    clock.t = t0 - 2 * DAY + 2.1 * DAY                               # forward again, under the gap rule
    recs += s.tick(digest_agent)
    assert [r.outcome for r in recs if r.outcome == "completed"] == ["completed"]   # the cap still binds
    refused("budget_exhausted", s.resume, OWNER, "sch_1")            # the row from before the rebase still counts
    ids = [r.run_id for r in recs]
    assert len(ids) == len(set(ids)), ids


def test_platform_errors_are_not_counted_as_the_schedules_fault():
    state = {"defs": True, "factory": True, "port": True}

    def defs(t):
        if not state["defs"]:
            raise OSError("store down")
        return DEFS

    class Flaky(FakeModelCallPort):
        def complete(self, request):
            if not state["port"]:
                raise ConnectionError("gateway down")
            return super().complete(request)

    def factory(p, b):
        if not state["factory"]:
            raise OSError("factory down")
        return fake_port(p, b, cls=Flaky)
    s = Scheduler(tool_defs=defs, roles_of=lambda t, u: ("sales",), port_factory=factory, clock=Clock(0),
                  emit=lambda e: None)
    clock = s._clock
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))
    day = 0
    for key in ("defs", "factory", "port"):
        state[key] = False
        for _ in range(S.MAX_FAILURES):
            clock.t = 1000 + day * DAY
            day += 1
            assert s.tick(digest_agent)[0].code == "platform_unavailable"
        state[key] = True
    assert s.get(OWNER, sch.id).active

    def boom(ctx):
        raise RuntimeError("agent bug")
    clock.t = 1000 + day * DAY
    assert s.tick(boom)[0].code == "run_failed"                       # a genuine agent error still counts


def test_resume_refuses_an_active_schedule_and_keeps_the_count():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | {"period_cap": 50_000}))

    def boom(ctx):
        raise RuntimeError("x")
    for day in range(S.MAX_FAILURES - 1):
        clock.t = 1000 + day * DAY
        s.tick(boom)
    refused("already_active", s.resume, OWNER, sch.id)
    clock.t = 1000 + (S.MAX_FAILURES - 1) * DAY
    s.tick(boom)
    assert not s.get(OWNER, sch.id).active                            # the count was not reset


def test_ordinary_tool_names_stay_schedulable():
    s, _, _, _ = make()
    tools = ("sales_order.list", "customer_note.create", "task.create", "visit_report.create", "meeting.update")
    assert s.create(OWNER, **(SPEC | {"tools": tools})).tools == tools


def test_concurrent_holds_of_one_owner_count_against_the_cap():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)
    s.create(OWNER, **SPEC)
    inner = []

    def first(ctx):
        inner.extend(s.tick(digest_agent))                             # the other schedule is claimed meanwhile
    assert first_run(s, clock, first).outcome == "completed"
    assert [r.code for r in inner] == ["budget_exhausted"]            # 0 spent + 2000 held + 2000 > 2500


def test_drafts_are_rebuilt_tainted_when_recorded():
    s, clock, _, _ = make()
    s.create(OWNER, **SPEC)

    def tamper(ctx):
        digest_agent(ctx)
        state = next(iter(S._RUNS.values()))                           # in-process reach, not a sandbox
        lists = [c.cell_contents for c in state["draft"].__closure__ if isinstance(c.cell_contents, list)]
        lists[0].append({"tool": "customer_note.create", "args": {"x": 1}, "tainted": False, "extra": 1})
    rec = first_run(s, clock, tamper)
    assert [d["tainted"] for d in rec.drafts] == [True, True] and all(set(d) == {"tool", "args", "tainted"}
                                                                       for d in rec.drafts)


def test_emitted_types_are_in_the_event_contract():
    contract = (Path(__file__).resolve().parents[4] / "contracts/events.md").read_text(encoding="utf-8")
    import re
    src = Path(S.__file__).read_text(encoding="utf-8")
    emitted = set(re.findall(r'"((?:agent_schedule|platform_scheduler|agent)\.[a-z_]+)"', src))
    assert {"agent_schedule.created", "agent_schedule.resumed", "platform_scheduler.clock_rebase", "agent.run_refused"} <= emitted
    missing = sorted(t for t in emitted if f"`{t}`" not in contract)
    assert not missing, missing


def test_clock_events_are_platform_events():
    s, clock, events, _ = make()
    clock.t = math.nan
    refused("clock_fault", s.tick, digest_agent)
    assert events[-1]["type"] == "platform_scheduler.clock_fault" and events[-1]["tenant_id"] == "platform"


# -- PR #286 review round (partner, Fable 5.2): fixes, each written as a failing test first ---------------------------
def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BIG = dict(period_cap=50_000, run_cap=2_000)


def test_cadence_edit_after_a_run_rekeys_the_slot_mark():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | BIG | {"cadence_s": 300}))
    clock.t = 1000 + 30 * DAY
    assert len(s.tick(digest_agent)) == 1
    s.update(OWNER, sch.id, cadence_s=DAY)
    assert s.tick(digest_agent) == []                              # same instant: the run is not repeated
    clock.t += DAY
    recs = s.tick(digest_agent)
    assert [r.outcome for r in recs] == ["completed"] and recs[0].run_id.startswith(f"srun_{sch.id}_v2_")


def test_start_at_edit_after_a_run_rekeys_the_slot_mark():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | BIG | {"cadence_s": 300}))
    clock.t = 1000 + 30 * DAY
    assert len(s.tick(digest_agent)) == 1
    s.update(OWNER, sch.id, start_at=int(clock.t) + 2 * DAY)       # later: slot 0 of the new start must run
    clock.t += 2 * DAY
    assert [r.outcome for r in s.tick(digest_agent)] == ["completed"]
    s.update(OWNER, sch.id, start_at=1000)                         # earlier: no immediate repeat of the same moment
    assert s.tick(digest_agent) == []
    clock.t += 300
    assert len(s.tick(digest_agent)) == 1


def test_run_ids_carry_the_schedule_version():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | BIG))
    assert first_run(s, clock).run_id == f"srun_{sch.id}_v1_0"


def test_forward_step_past_the_owner_window_is_a_clock_gap_event():
    s, clock, events, _ = make()
    s.create(OWNER, **(SPEC | BIG))                                # period_s is 7 days
    first_run(s, clock)
    clock.t = 1000 + 6 * DAY
    s.tick(digest_agent)
    assert not [e for e in events if e["type"] == "platform_scheduler.clock_gap"]
    clock.t += 8 * DAY                                             # more than the window, less than MAX_STEP_S
    s.tick(digest_agent)
    gaps = [e for e in events if e["type"] == "platform_scheduler.clock_gap"]
    assert len(gaps) == 1 and gaps[0]["tenant_id"] == "platform" and gaps[0]["data"]["last_accepted"] == iso(1000 + 6 * DAY)


def test_spend_rows_carry_the_slot_time_not_the_tick_time():
    s, clock, _, _ = make()
    sch = s.create(OWNER, **(SPEC | {"period_s": DAY, "period_cap": 2_000, "run_cap": 2_000}))
    clock.t = 1025                                                 # 25 s of jitter after the slot
    assert s.tick(digest_agent)[0].outcome == "completed"
    clock.t = 1000 + DAY                                           # the next slot, on time
    assert [r.outcome for r in s.tick(digest_agent)] == ["completed"], s.get(OWNER, sch.id)


def test_a_refused_disable_is_audited():
    s, _, events, _ = make()
    sch = s.create(OWNER, **SPEC)
    other = Principal("t_acme", "u_2", ("sales",))
    refused("owner_mismatch", s.disable, other, sch.id)
    refused("not_found", s.disable, Principal("t_beta", "u_1", ("sales",)), sch.id)
    refused("not_found", s.disable, OWNER, "sch_99")
    refused_ev = [e for e in events if e["type"] == "agent_schedule.change_refused"]
    assert [e["data"]["code"] for e in refused_ev] == ["owner_mismatch", "not_found", "not_found"]
    assert s.get(OWNER, sch.id).active


def test_rigid_words_are_checked_in_every_dotted_segment():
    names = ("sales.invoice.create", "crm.gl.create", "hr.payroll_run.update", "a.b.wps_file.create")
    defs = DEFS + [tool(n, "R1", **W) for n in names]
    s, _, _, _ = make(defs=defs)
    for n in names:
        refused("draft_only", s.create, OWNER, **(SPEC | {"tools": (n,)}))
    defs2 = DEFS + [tool("crm.visit.create", "R1", **W)]
    s2, _, _, _ = make(defs=defs2)
    assert s2.create(OWNER, **(SPEC | {"tools": ("crm.visit.create",)}))


def _all_events():
    """Drive every producer path once and return the audit records."""
    sink, roles = [], {"r": ("sales",)}
    s, clock, _, _ = make(emit=sink.append, roles=lambda t, u: roles["r"])
    a = s.create(OWNER, **(SPEC | BIG))
    s.update(OWNER, a.id, cadence_s=2 * DAY)
    first_run(s, clock)
    s.disable(OWNER, a.id)
    s.resume(OWNER, a.id)
    refused("invalid_schedule", s.update, OWNER, a.id, run_cap=0)
    s.update(OWNER, a.id, cadence_s=DAY)
    clock.t = 1000 + 2 * DAY
    s.tick(lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))        # run_failed
    roles["r"] = ()
    clock.t += 2 * DAY
    s.tick(digest_agent)                                                   # run_refused + schedule.suspended
    clock.t = math.nan
    refused("clock_fault", s.tick, digest_agent)
    clock.t = 1000 + 3 * DAY
    clock.t = 1000 + 3 * DAY + S.MAX_STEP_S + 1
    s.tick(digest_agent)                                                   # clock_gap
    clock.t -= 10
    for i in range(3):                                                     # clock_rebase
        clock.t -= 1 if i == 0 else 0
        try:
            s.tick(digest_agent)
        except ScheduleRefused:
            pass
    s2, c2, _, _ = make(emit=sink.append)
    s2.create(OWNER, **(SPEC | {"period_cap": 2_000, "run_cap": 2_000}))
    first_run(s2, c2)
    c2.t = 1000 + DAY
    s2.tick(digest_agent)                                                  # budget_exceeded + suspended
    return sink


def test_producer_records_match_the_event_registry_values():
    import jsonschema
    root = Path(__file__).resolve().parents[4] / "services/blueprint/events/schemas"
    reg = json.loads((root / "types.json").read_text(encoding="utf-8"))["types"]
    events = _all_events()
    seen = {e["type"] for e in events}
    assert {"agent_schedule.created", "agent_schedule.updated", "agent_schedule.disabled", "agent_schedule.resumed",
            "agent_schedule.suspended", "agent_schedule.change_refused", "agent.run_started", "agent.run_failed",
            "agent.run_refused", "agent.run_completed", "agent.tool_proposed", "agent.budget_exceeded",
            "platform_scheduler.clock_fault", "platform_scheduler.clock_gap", "platform_scheduler.clock_rebase"} <= seen
    for e in events:
        info = reg[e["type"]]                                              # an unregistered type is a KeyError
        file, ref = info["data_schema"].split("#")
        doc = json.loads((root / file).read_text(encoding="utf-8"))
        schema = {**doc["$defs"][ref.rsplit("/", 1)[1]], "$defs": doc["$defs"]}
        jsonschema.Draft202012Validator(schema).validate(e["data"])
        assert (e["tenant_id"] == "platform") == (info["scope"] == "platform"), e["type"]
        if info["requires_trace"]:
            assert e.get("trace"), e["type"]                               # an AI took part: trace is required
    upd = [e for e in events if e["type"] == "agent_schedule.updated"]
    assert upd[0]["data"]["changed_fields"] == ["cadence_s"] and "changed" not in upd[0]["data"]
    clocks = [e for e in events if e["type"].startswith("platform_scheduler.")]
    assert all("last" not in e["data"] for e in clocks)
    assert next(e for e in clocks if e["type"].endswith("clock_gap"))["data"]["last_accepted"] == iso(1000 + 4 * DAY)
    for e in events:
        if e["type"] == "agent_schedule.suspended":
            assert e["data"]["reason"] in ("owner_permission_lost", "budget_exhausted", "repeated_failures")
