"""SEC-009 (chat side): chat turns are rate limited per tenant and user at the chat entry point."""
from chat_helpers import ALICE, BOB, OTHER, Factory, collect, last
from chat import ChatService, MemoryChatStore, loop_runtime_factory, render_error
from runtime import MemoryTraceStore, RateLimitedTools, RateLimiter, RateRule, SequentialIds, TickClock

RULES = (RateRule("turn", "user", 60, 2), RateRule("turn", "tenant", 60, 3), RateRule("tool", "user", 60, 5))


def make_limited(rules=RULES):
    clock = TickClock(step=0)
    f = Factory()
    svc = ChatService(store=MemoryChatStore(), runtime_factory=f, ids=SequentialIds(), clock=clock,
                      limiter=RateLimiter(clock, rules))
    return svc, f, clock


def send(svc, p, n):
    s = svc.open_session(p)
    return collect(svc.send(p, s.session_id, f"msg-{p.subject}-{n:04d}", f"hello {n}"))


def test_user_over_limit_gets_stable_code_and_bilingual_text():
    svc, f, clock = make_limited()
    assert last(send(svc, ALICE, 1))["type"] == "RUN_FINISHED"
    assert last(send(svc, ALICE, 2))["type"] == "RUN_FINISHED"
    out = send(svc, ALICE, 3)
    assert out == [out[-1]] and out[-1]["type"] == "RUN_ERROR" and out[-1]["code"] == "chat_rate_limited"
    assert len(f.setups) == 2  # the refused turn started no run and no model call
    assert out[-1]["message"] == render_error("chat_rate_limited", "en")["message"]
    ar = render_error("chat_rate_limited", "ar")
    assert ar["message_key"] == "errors.chat_rate_limited" and ar["retryable"] and "انتظر" in ar["message"]
    s = svc.open_session(ALICE)
    assert all(e.text != "hello 3" for e in svc.history(ALICE, s.session_id))  # not stored
    clock.advance(60)
    assert last(send(svc, ALICE, 4))["type"] == "RUN_FINISHED"


def test_tenant_limit_spans_users_other_tenant_unaffected():
    svc, _, _ = make_limited()
    send(svc, ALICE, 1)
    send(svc, ALICE, 2)
    send(svc, BOB, 1)
    assert last(send(svc, BOB, 2))["code"] == "chat_rate_limited"  # tenant t_acme used its 3 turns
    assert last(send(svc, OTHER, 1))["type"] == "RUN_FINISHED"


def test_replayed_message_does_not_count():
    svc, f, _ = make_limited()
    s = svc.open_session(ALICE)
    collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello"))
    for _ in range(4):  # client retries of a finished message replay for free
        assert last(collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello")))["type"] == "RUN_FINISHED"
    assert last(send(svc, ALICE, 9))["type"] == "RUN_FINISHED"
    assert len(f.setups) == 2


def test_default_limiter_is_on():
    svc = ChatService(store=MemoryChatStore(), runtime_factory=Factory(), ids=SequentialIds(), clock=TickClock(step=0))
    outs = [last(send(svc, ALICE, n)) for n in range(21)]
    assert [o["type"] for o in outs[:20]] == ["RUN_FINISHED"] * 20 and outs[20]["code"] == "chat_rate_limited"


def test_runtime_factory_wraps_tools_with_the_shared_limiter():
    clock, lim = TickClock(), RateLimiter(TickClock(), RULES)
    factory = loop_runtime_factory(model=None, tools=object(), tool_defs=lambda t: [], clock=clock,
                                   ids=SequentialIds(), traces=MemoryTraceStore(), limiter=lim)
    from chat.models import RunSetup, Window
    from runtime import CancelToken
    rt = factory(RunSetup(Window("frame", ()), "ask", "en", CancelToken()))
    assert isinstance(rt.tools, RateLimitedTools) and rt.tools.limiter is lim
