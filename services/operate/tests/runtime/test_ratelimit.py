"""SEC-009 (chat side): per-tenant and per-user rate limits, tool-call limiter, budget guard over the PLT-026 port."""
import evstream  # noqa: F401  on the path via conftest; a missing package fails, never skips
import pytest

from runtime import (BudgetGuard, BudgetStop, RateLimited, RateLimitedTools, RateLimiter, RateRule, TickClock,
                     ToolRequest, ToolResponse)
from test_model_call_fake import REQ, port, req

RULES = (RateRule("turn", "user", 60, 2), RateRule("turn", "tenant", 60, 3), RateRule("tool", "user", 10, 1))


def limiter(rules=RULES):
    clock = TickClock(step=0)
    return RateLimiter(clock, rules), clock


def reason(lim, *a):
    with pytest.raises(RateLimited) as ei:
        lim.admit(*a)
    return ei.value


def test_per_user_window_and_retry_after():
    lim, clock = limiter()
    lim.admit("turn", "t_a", "u_1")
    lim.admit("turn", "t_a", "u_1")
    e = reason(lim, "turn", "t_a", "u_1")
    assert (e.code, e.reason, e.retryable, e.retry_after_s) == ("rate_limited", "user_limit", True, 60)
    assert set(e.as_dict()) == {"kind", "code", "reason", "retryable", "retry_after_s"}
    clock.advance(60)  # the window slides: old hits expire
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


@pytest.mark.parametrize("tenant,user", [("", "u_1"), ("t_a", ""), (None, "u_1"), ("t_a", 7)])
def test_missing_identity_fails_closed(tenant, user):
    lim, _ = limiter()
    e = reason(lim, "turn", tenant, user)
    assert (e.reason, e.retryable) == ("identity_missing", False)


def test_kind_without_rule_or_bad_rule_fails_closed():
    lim, _ = limiter()
    assert reason(lim, "export", "t_a", "u_1").reason == "policy_missing"
    bad, _ = limiter((RateRule("turn", "user", 60, 0),))
    assert reason(bad, "turn", "t_a", "u_1").reason == "policy_missing"


def test_broken_clock_fails_closed():
    def clock():
        raise OSError("no clock")
    assert reason(RateLimiter(clock, RULES), "turn", "t_a", "u_1").reason == "store_error"


class Tools:
    supports_propose = True

    def __init__(self):
        self.calls = []

    def call(self, request):
        self.calls.append(request)
        return ToolResponse(status="ok", result={})


def treq(user="u_1"):
    return ToolRequest("sales_order.get", {}, "idem_1", "t_a", user, ("sales",), "s1", "run_1")


def test_tool_limiter_blocks_before_dispatch():
    lim, clock = limiter()
    inner = Tools()
    tools = RateLimitedTools(inner, lim)
    assert tools.supports_propose is True
    assert tools.call(treq()).status == "ok"
    out = tools.call(treq())
    assert (out.status, out.error) == ("error", {"code": "rate_limited"})
    assert len(inner.calls) == 1  # the refused call never reached the Tool API
    assert tools.call(treq("u_2")).status == "ok"
    clock.advance(10)
    assert tools.call(treq()).status == "ok"


def test_tool_limiter_in_agent_loop_maps_to_rate_limited():
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
            calls = (ToolCall("a", "sales_order.get", {"id": "SO-1"}), ToolCall("b", "sales_order.list", {})) \
                if self.n == 1 else ()
            return ModelReply("done" if self.n > 1 else "", calls, Usage(1, 1, 0, 1))

    lim, _ = limiter((RateRule("tool", "user", 60, 1),))
    inner = Tools()
    loop = AgentLoop(model=Model(), tools=RateLimitedTools(inner, lim),
                     allow=resolve_allowlist(defs, caller.role_ids), limits=Limits(), clock=TickClock(),
                     ids=SequentialIds(), traces=MemoryTraceStore())
    loop.run(caller=caller, run_id="run_1", user_text="show orders")
    assert len(inner.calls) == 1
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


def test_budget_guard_dict_results_fail_closed():
    with pytest.raises(BudgetStop):
        BudgetGuard(DictPort({"kind": "refusal", "code": "budget_refused", "reason": "exceeded"})).complete(REQ)
    for out in ({"kind": "refusal", "code": "filter_blocked"}, None, {"text": "hi"}):
        with pytest.raises(RuntimeError):
            BudgetGuard(DictPort(out)).complete(REQ)
