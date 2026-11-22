"""SEC-009 (chat side): chat turns and new sessions are rate limited per tenant and user at the chat entry point."""
from chat_helpers import ALICE, BOB, OTHER, Audit, Factory, collect, last
from agui.ports import Principal
from chat import ChatFailure, ChatService, MemoryChatStore, Session, loop_runtime_factory, render_error
from runtime import MemoryTraceStore, RateLimitedTools, RateLimiter, RateRule, SequentialIds, TickClock

RULES = (RateRule("turn", "user", 60, 2), RateRule("turn", "tenant", 60, 3), RateRule("session", "user", 60, 3),
         RateRule("tool", "user", 60, 5))


def make_limited(rules=RULES, limiter=None):
    clock, audit = TickClock(step=0), Audit()
    f = Factory()
    svc = ChatService(store=MemoryChatStore(), runtime_factory=f, ids=SequentialIds(), clock=clock, audit=audit,
                      limiter=RateLimiter(clock, rules) if limiter is None else limiter)
    return svc, f, clock, audit


def send(svc, p, n, session_id=None):
    sid = session_id or svc.open_session(p).session_id
    return collect(svc.send(p, sid, f"msg-{p.subject}-{n:04d}", f"hello {n}"))


def refusals(audit):
    return [i[3] for i in audit.items if i[2] == "chat.rate_limited"]


def test_user_over_limit_gets_stable_code_wait_time_and_audit():
    svc, f, clock, audit = make_limited()
    assert last(send(svc, ALICE, 1))["type"] == "RUN_FINISHED"
    clock.advance(30)
    assert last(send(svc, ALICE, 2))["type"] == "RUN_FINISHED"
    out = send(svc, ALICE, 3)
    assert out == [out[-1]] and out[-1]["type"] == "RUN_ERROR" and out[-1]["code"] == "chat_rate_limited"
    assert out[-1]["message"] == render_error("chat_rate_limited", "en", {"minutes": 1})["message"]
    assert "1 min" in out[-1]["message"]
    assert len(f.setups) == 2  # the refused turn started no run and no model call
    assert refusals(audit) == [{"kind": "turn", "reason": "user_limit", "retry_after_s": 30}]
    s = svc.open_session(ALICE)
    assert all(e.text != "hello 3" for e in svc.history(ALICE, s.session_id))  # not stored
    clock.advance(30)
    assert last(send(svc, ALICE, 4))["type"] == "RUN_FINISHED"


def test_repeat_refusals_audited_once_and_outside_the_chat_lock():
    svc, _, _, audit = make_limited()
    held = []
    emit = audit.emit
    audit.emit = lambda *a: (held.append(svc._lock.locked()), emit(*a))
    send(svc, ALICE, 1)
    send(svc, ALICE, 2)
    for n in range(3, 8):
        assert last(send(svc, ALICE, n))["code"] == "chat_rate_limited"
    assert len(refusals(audit)) == 1
    assert not any(held)  # no audit write ever ran under the chat lock


def test_hourly_wait_is_shown_in_minutes_both_languages():
    en = render_error("chat_rate_limited", "en", {"minutes": 42})
    ar = render_error("chat_rate_limited", "ar", {"minutes": 42})
    assert "42" in en["message"] and "42" in ar["message"] and en["retryable"] and "{" not in ar["message"]
    assert en["message_key"] == "errors.chat_rate_limited"
    assert render_error("chat_rate_limited", "en")["code"] == "internal_error"  # never a raw template


def test_limiter_fault_is_not_shown_as_too_quick():
    class Broken:
        def admit(self, *a):
            from runtime import RateLimited
            raise RateLimited("store_error")
    svc, f, _, audit = make_limited(limiter=Broken())
    s = svc.store.create_session(Session("t_acme", "u_1", "ses_x", "thr_x", "en", 0.0, 0.0))  # no session check
    out = collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello"))
    err = last(out)
    unavailable = render_error("chat_limit_unavailable")
    assert err["code"] == "chat_limit_unavailable" and err["message"] == unavailable["message"]
    assert unavailable["retryable"] is False and render_error("chat_limit_unavailable", "ar")["message"]
    assert refusals(audit) == [{"kind": "turn", "reason": "store_error", "retry_after_s": 0}] and not f.setups


def test_empty_rule_set_refuses_as_unavailable():
    svc, _, _, _ = make_limited(rules=())
    try:
        svc.open_session(ALICE)
        raise AssertionError("expected a refusal")
    except ChatFailure as e:
        assert e.code == "chat_limit_unavailable"


def test_tenant_limit_spans_users_other_tenant_unaffected():
    svc, _, _, _ = make_limited()
    send(svc, ALICE, 1)
    send(svc, ALICE, 2)
    send(svc, BOB, 1)
    assert last(send(svc, BOB, 2))["code"] == "chat_rate_limited"  # tenant t_acme used its 3 turns
    assert last(send(svc, OTHER, 1))["type"] == "RUN_FINISHED"


def test_new_sessions_and_logins_do_not_reset_the_user_quota():
    alice2 = Principal(ALICE.tenant_id, ALICE.subject, ALICE.role_ids, "tok-other-login")
    svc, _, _, _ = make_limited()
    s1 = svc.open_session(ALICE, new=True)
    s2 = svc.open_session(alice2, new=True)
    send(svc, ALICE, 1, s1.session_id)
    send(svc, alice2, 2, s2.session_id)
    s3 = svc.open_session(ALICE, new=True)
    assert last(send(svc, ALICE, 3, s3.session_id))["code"] == "chat_rate_limited"  # keyed on the user, not session


def test_new_sessions_are_metered_per_user():
    svc, _, _, audit = make_limited()
    for _ in range(3):
        svc.open_session(ALICE, new=True)
    try:
        svc.open_session(ALICE, new=True)
        raise AssertionError("expected a refusal")
    except ChatFailure as e:
        assert e.code == "chat_rate_limited"
    assert refusals(audit)[-1]["kind"] == "session"
    svc.open_session(ALICE)  # resuming the latest session creates nothing and is free
    svc.open_session(BOB, new=True)


def test_replayed_message_does_not_count():
    svc, f, _, _ = make_limited()
    s = svc.open_session(ALICE)
    collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello"))
    for _ in range(4):  # client retries of a finished message replay for free
        assert last(collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello")))["type"] == "RUN_FINISHED"
    assert last(send(svc, ALICE, 9))["type"] == "RUN_FINISHED"
    assert len(f.setups) == 2


def test_send_refused_by_run_in_progress_costs_nothing():
    svc, f, _, _ = make_limited()
    s = svc.open_session(ALICE)
    running = svc.send(ALICE, s.session_id, "msg-0000001", "hello")
    next(running)  # the first run is active
    for i in range(3):
        out = collect(svc.send(ALICE, s.session_id, f"msg-000001{i}", "again"))
        assert last(out)["code"] == "chat_run_in_progress"
    collect(running)
    assert last(collect(svc.send(ALICE, s.session_id, "msg-0000002", "next")))["type"] == "RUN_FINISHED"


def test_refused_turn_releases_the_run_slot():
    svc, _, _, _ = make_limited(rules=(RateRule("turn", "user", 60, 1), RateRule("session", "user", 60, 3)))
    s = svc.open_session(ALICE)
    send(svc, ALICE, 1, s.session_id)
    assert last(send(svc, ALICE, 2, s.session_id))["code"] == "chat_rate_limited"
    assert svc.store.begin_run(s, "run_probe", 0.0, 300.0)  # the refused turn left no active-run mark


def test_falsy_limiter_is_used_not_replaced():
    class Falsy(RateLimiter):
        def __len__(self):
            return 0
    clock = TickClock(step=0)
    lim = Falsy(clock, RULES)
    svc = ChatService(store=MemoryChatStore(), runtime_factory=Factory(), ids=SequentialIds(), clock=clock,
                      limiter=lim)
    assert svc.limiter is lim


def test_default_limiter_is_on():
    svc = ChatService(store=MemoryChatStore(), runtime_factory=Factory(), ids=SequentialIds(), clock=TickClock(step=0))
    sid = svc.open_session(ALICE).session_id
    outs = [last(send(svc, ALICE, n, sid)) for n in range(21)]
    assert [o["type"] for o in outs[:20]] == ["RUN_FINISHED"] * 20 and outs[20]["code"] == "chat_rate_limited"


def _setup():
    from chat.models import RunSetup, Window
    from runtime import CancelToken
    return RunSetup(Window("frame", ()), "ask", "en", CancelToken())


def test_runtime_factory_wraps_tools_with_the_shared_limiter():
    clock, lim = TickClock(), RateLimiter(TickClock(), RULES)
    factory = loop_runtime_factory(model=None, tools=object(), tool_defs=lambda t: [], clock=clock,
                                   ids=SequentialIds(), traces=MemoryTraceStore(), limiter=lim)
    rt = factory(_setup())
    assert isinstance(rt.tools, RateLimitedTools) and rt.tools.limiter is lim


def test_runtime_factory_limits_tools_by_default():
    factory = loop_runtime_factory(model=None, tools=object(), tool_defs=lambda t: [], clock=TickClock(),
                                   ids=SequentialIds(), traces=MemoryTraceStore())
    rt = factory(_setup())
    assert isinstance(rt.tools, RateLimitedTools) and isinstance(rt.tools.limiter, RateLimiter)
