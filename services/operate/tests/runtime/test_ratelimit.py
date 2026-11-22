"""SEC-009 (chat side): per-tenant and per-user rate limits, tool-call limiter, budget guard over the PLT-026 port."""
import threading

import evstream  # noqa: F401  on the path via conftest; a missing package fails, never skips
import pytest

from runtime import (BudgetGuard, BudgetStop, RateLimited, RateLimitedTools, RateLimiter, RateRule, TickClock,
                     ToolRequest, ToolResponse)
from test_model_call_fake import REQ, port, req

RULES = (RateRule("turn", "user", 60, 2), RateRule("turn", "tenant", 60, 3), RateRule("tool", "user", 10, 1))


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def limiter(rules=RULES, **kw):
    clock = TickClock(step=0)
    return RateLimiter(clock, rules, **kw), clock


def reason(lim, *a):
    with pytest.raises(RateLimited) as ei:
        lim.admit(*a)
    return ei.value


def test_per_user_window_and_retry_after():
    lim, clock = limiter()
    lim.admit("turn", "t_a", "u_1")
    clock.advance(15)
    lim.admit("turn", "t_a", "u_1")
    e = reason(lim, "turn", "t_a", "u_1")
    assert (e.code, e.reason, e.retryable, e.retry_after_s) == ("rate_limited", "user_limit", True, 45)
    clock.advance(45)  # the window slides: the oldest hit expires
    lim.admit("turn", "t_a", "u_1")


def test_per_tenant_limit_spans_users_and_tenants_are_isolated():
    lim, _ = limiter()
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_2")
    lim.admit("turn", "t_a", "u_3")
    assert reason(lim, "turn", "t_a", "u_4").reason == "tenant_limit"
    lim.admit("turn", "t_b", "u_1")  # same user id in another tenant: separate counters


def test_refused_event_is_not_recorded():
    lim, clock = limiter()
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_1")
    for _ in range(5):
        reason(lim, "turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_2")  # the tenant counter saw 3 admitted, not 8
    assert reason(lim, "turn", "t_a", "u_3").reason == "tenant_limit"
    clock.advance(60)
    lim.admit("turn", "t_a", "u_1")


@pytest.mark.parametrize("tenant,user", [("", "u_1"), ("t_a", ""), (None, "u_1"), ("t_a", 7), (" ", "u_1")])
def test_missing_identity_fails_closed(tenant, user):
    lim, _ = limiter()
    e = reason(lim, "turn", tenant, user)
    assert (e.reason, e.retryable) == ("identity_missing", False)


@pytest.mark.parametrize("rules", [
    (RateRule("turn", "user", 60, 0),), (RateRule("turn", "user", 60, float("nan")),),
    (RateRule("turn", "user", 60, None),), (RateRule("turn", "user", 60, 1.5),), (RateRule("turn", "user", 60, True),),
    (RateRule("turn", "user", "60", 1),), (RateRule("turn", "user", float("nan"), 1),),
    (RateRule("turn", "user", float("inf"), 1),), (RateRule("turn", "user", -1, 1),), (RateRule("turn", "org", 60, 1),),
    (RateRule("turn", "user", 60, 3), RateRule("turn", "user", 60, 3)), (RateRule("turn", "user", 60, 3), "junk"),
    (), None, 5,
])
def test_invalid_rule_set_fails_closed_as_policy_missing(rules):
    lim = RateLimiter(Clock(1), rules)
    for kind in ("turn", "tool"):  # one bad rule disables the whole set, not just its kind
        e = reason(lim, kind, "t_a", "u_1")
        assert (e.reason, e.retryable) == ("policy_missing", False)


def test_kind_without_rule_fails_closed():
    lim, _ = limiter()
    assert reason(lim, "export", "t_a", "u_1").reason == "policy_missing"
    assert reason(lim, ["turn"], "t_a", "u_1").reason == "policy_missing"


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), 1e300, 2.0 ** 53, -5, "5", None, True])
def test_bad_clock_values_fail_closed_and_recover(bad):
    clock = Clock(bad)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 2),))
    for _ in range(4):
        assert reason(lim, "turn", "t_a", "u_1").reason == "store_error"
    clock.t = 100.0  # the key is not poisoned: normal limits apply once the clock is healthy
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_1")
    assert reason(lim, "turn", "t_a", "u_1").reason == "user_limit"


def test_raising_clock_fails_closed():
    def clock():
        raise OSError("no clock")
    assert reason(RateLimiter(clock, RULES), "turn", "t_a", "u_1").reason == "store_error"


def test_backwards_clock_is_clamped():
    clock = Clock(1000.0)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 1),))
    lim.admit("turn", "t_a", "u_1")
    clock.t = 0.0
    assert reason(lim, "turn", "t_a", "u_1").retry_after_s == 60  # not 1060
    clock.t = 1060.0
    lim.admit("turn", "t_a", "u_1")


def test_small_backwards_step_is_clamped():
    clock = Clock(1000.0)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 1),))
    lim.admit("turn", "t_a", "u_1")
    clock.t = 997.0
    assert reason(lim, "turn", "t_a", "u_1").retry_after_s == 60  # measured from 1000, not 997


def test_one_spurious_high_reading_does_not_freeze_the_limiter():
    clock = Clock(100.0)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 2),))
    lim.admit("turn", "t_a", "u_2")
    clock.t = 9e9  # in range, but wrong
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_1")
    clock.t = 110.0  # back to the real clock: counts are kept, their windows restart at the reset
    e = reason(lim, "turn", "t_a", "u_1")
    assert (e.reason, e.retry_after_s) == ("user_limit", 60)
    lim.admit("turn", "t_a", "u_2")  # not frozen: other keys still admit
    clock.t = 170.0
    lim.admit("turn", "t_a", "u_1")


@pytest.mark.parametrize("bad", [0, -1, None, 1.5, True])
def test_invalid_sweep_every_refuses_and_records_nothing(bad):
    lim = RateLimiter(Clock(1.0), RULES, sweep_every=bad)
    for _ in range(3):
        assert reason(lim, "turn", "t_a", "u_1").reason == "policy_missing"
    assert not any(lim._hits.values())


def test_sweep_keeps_live_counts():
    clock = Clock(0.0)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 2),), sweep_every=2)
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_1")  # second admit triggers a sweep; this key is live
    clock.t = 10.0
    lim.admit("turn", "t_a", "u_2")
    lim.admit("turn", "t_a", "u_3")  # another sweep
    assert reason(lim, "turn", "t_a", "u_1").reason == "user_limit"


def test_refusal_is_logged_once_per_key_until_admitted(caplog):
    clock = Clock(0.0)
    lim = RateLimiter(clock, (RateRule("turn", "user", 60, 1),))
    lim.admit("turn", "t_a", "u_1")
    with caplog.at_level("WARNING", logger="ratelimit"):
        firsts = [reason(lim, "turn", "t_a", "u_1").first for _ in range(5)]
    assert firsts == [True, False, False, False, False]
    lines = [r.getMessage() for r in caplog.records if r.name == "ratelimit"]
    assert lines == ["rate refusal kind=turn tenant=t_a user=u_1 reason=user_limit retry_after_s=60"]
    caplog.clear()
    clock.t = 60.0
    with caplog.at_level("WARNING", logger="ratelimit"):
        lim.admit("turn", "t_a", "u_1")
    assert [r.getMessage() for r in caplog.records] == [
        "rate refusals repeated kind=turn tenant=t_a user=u_1 user_limit=4"]


def test_stale_keys_are_swept():
    clock = Clock(0.0)
    lim = RateLimiter(clock, RULES, sweep_every=100)
    for i in range(1000):
        lim.admit("turn", f"t{i}", f"u{i}")
    clock.t = 1000.0
    for i in range(100):
        lim.admit("tool", "t_x", f"v{i}")
    assert len(lim._hits) <= 100  # only the live tool keys of the last sweep window remain


class RacingRule(RateRule):
    """Reads of `limit` (between the length check and the record) wait for every thread once armed: without the
    lock all threads pass the check together; with it the first waits out the timeout alone."""
    armed, barrier = False, None

    @property
    def limit(self):
        if RacingRule.armed:
            try:
                RacingRule.barrier.wait(timeout=0.3)
            except threading.BrokenBarrierError:
                pass
        return self._limit

    @limit.setter
    def limit(self, v):
        object.__setattr__(self, "_limit", v)


def test_check_and_record_is_atomic_under_threads():
    n = 8
    lim, ok = RateLimiter(Clock(1.0), (RacingRule("turn", "tenant", 60, 2),)), []
    RacingRule.barrier, RacingRule.armed = threading.Barrier(n), True

    def worker(i):
        try:
            lim.admit("turn", "t_a", f"u{i}")
            ok.append(i)
        except RateLimited:
            pass
    try:
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        RacingRule.armed = False
    assert len(ok) == 2


class Tools:
    supports_propose = True

    def __init__(self):
        self.calls = []

    def call(self, request):
        self.calls.append(request)
        return ToolResponse(status="ok", result={})


def treq(user="u_1", tool="sales_order.get", args=None, idem="idem_1", session="s1", run="run_1"):
    return ToolRequest(tool, args or {}, idem, "t_a", user, ("sales",), session, run)


def test_tool_limiter_blocks_before_dispatch_with_retry_after():
    lim, clock = limiter()
    inner = Tools()
    tools = RateLimitedTools(inner, lim)
    assert tools.supports_propose is True
    assert tools.call(treq()).status == "ok"
    clock.advance(4)
    out = tools.call(treq())
    assert (out.status, out.error) == ("error", {"code": "rate_limited", "retryable": True, "retry_after_s": 6})
    assert len(inner.calls) == 1  # the refused call never reached the Tool API
    assert tools.call(treq("u_2")).status == "ok"
    clock.advance(6)
    assert tools.call(treq()).status == "ok"


def test_tool_limiter_keys_on_user_not_call_fields():
    lim, _ = limiter()
    tools = RateLimitedTools(Tools(), lim)
    assert tools.call(treq()).status == "ok"
    other = treq(tool="sales_order.list", args={"id": "SO-9", "user_id": "u_9", "tenant_id": "t_z"}, idem="idem_2",
                 session="s2", run="run_2")
    assert tools.call(other).error["code"] == "rate_limited"  # same user: tool, args, ids do not reset the count


def test_tool_limiter_fault_is_not_retryable():
    tools = RateLimitedTools(Tools(), RateLimiter(Clock(float("nan")), RULES))
    assert tools.call(treq()).error == {"code": "rate_limited", "retryable": False}


def test_tool_limiter_in_agent_loop_stops_the_run():
    from runtime import AgentLoop, Caller, Limits, MemoryTraceStore, ModelReply, SequentialIds, ToolCall, Usage, \
        resolve_allowlist
    caller = Caller("t_acme", "u_1", ("sales",), "s1")
    defs = [{"name": n, "risk_class": "R0", "agent_creatable": True, "requires": {"roles": ["sales"]},
             "description": n, "input_schema": {"type": "object"}} for n in ("sales_order.get", "sales_order.list")]

    class Model:
        def __init__(self):
            self.n = 0

        def complete(self, request):
            self.n += 1
            calls = (ToolCall("a", "sales_order.get", {"id": "SO-1"}), ToolCall("b", "sales_order.list", {}))
            return ModelReply("", calls, Usage(1, 1, 0, 1))

    lim, _ = limiter((RateRule("tool", "user", 60, 1),))
    inner, model = Tools(), Model()
    loop = AgentLoop(model=model, tools=RateLimitedTools(inner, lim),
                     allow=resolve_allowlist(defs, caller.role_ids), limits=Limits(), clock=TickClock(),
                     ids=SequentialIds(), traces=MemoryTraceStore())
    res = loop.run(caller=caller, run_id="run_1", user_text="show orders")
    assert len(inner.calls) == 1 and model.n == 1  # no further model steps after the refusal
    assert (res.status, res.stop_reason, res.error_code) == ("stopped", "rate_limited", "budget_exceeded")
    assert [s.error_code for s in loop.traces.spans("t_acme", "run_1") if s.kind == "tool"][-1] == "rate_limited"


# ---- budget guard over the PLT-026 fake port ---------------------------------------------------------------------
def test_budget_guard_passes_reply():
    p = port()
    out = BudgetGuard(p).complete(req())
    assert out["kind"] == "reply" and p.reservations[-1].state == "committed"


@pytest.mark.parametrize("kw,why", [({"budgets": {"tenant": 1, "session": 1, "run": 1}}, "exceeded"),
                                    ({"meter_up": False}, "meter_unavailable"),
                                    ({"budgets": {"tenant": 1_000_000, "session": 100_000}}, "policy_missing")])
def test_budget_guard_stops_when_reservation_refused(kw, why):
    p = port(**kw)
    with pytest.raises(BudgetStop) as ei:
        BudgetGuard(p).complete(req())
    assert ei.value.kind == why
    assert all(x.state != "reserved" for x in p.reservations) and not p.events  # nothing held, nothing metered


def test_budget_guard_reraises_other_refusals():
    p = port(kill_switch=True)
    with pytest.raises(Exception) as ei:
        BudgetGuard(p).complete(req())
    assert not isinstance(ei.value, BudgetStop) and ei.value.code == "kill_switch_engaged"


class DictPort:
    def __init__(self, out):
        self.out = out

    def complete(self, request):
        return self.out


@pytest.mark.parametrize("why,kind", [("exceeded", "exceeded"), ("policy_missing", "policy_missing"),
                                      ("meter_unavailable", "meter_unavailable"), ("layer_unbound", "layer_unbound"),
                                      ("x" * 60, "unknown"), ({"a": 1}, "unknown"), (None, "unknown")])
def test_budget_guard_dict_refusal_reasons_are_closed(why, kind):
    with pytest.raises(BudgetStop) as ei:
        BudgetGuard(DictPort({"kind": "refusal", "code": "budget_refused", "reason": why})).complete(REQ)
    assert ei.value.kind == kind


def test_budget_guard_raised_reason_is_closed():
    class Refused(Exception):
        code, reason = "budget_refused", "free text from somewhere"

    class Raising:
        def complete(self, request):
            raise Refused()
    with pytest.raises(BudgetStop) as ei:
        BudgetGuard(Raising()).complete(REQ)
    assert ei.value.kind == "unknown"


def test_budget_guard_non_reply_results_fail_closed():
    for out in ({"kind": "refusal", "code": "filter_blocked"}, None, {"text": "hi"}, {"kind": "Reply"}):
        with pytest.raises(RuntimeError):
            BudgetGuard(DictPort(out)).complete(REQ)
