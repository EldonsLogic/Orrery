import pytest

from featureflags import FlagError

K = "ui.new_viewer"


def code(fn):
    with pytest.raises(FlagError) as e:
        fn()
    return e.value.code


def on_everywhere(w):
    s = w.staff()
    w.admin.set_global(s, K, True, "global on")
    w.admin.set_tenant(s, K, "t-a", True, "tenant on")
    w.admin.set_user(s, K, "t-a", "u-1", True, "user on")
    w.admin.set_percent(s, K, 10000, "everyone")
    w.clock.advance(100)
    assert w.ev.is_enabled(w.ctx(), K)
    return s


@pytest.mark.parametrize("level,kw,reason", [
    ("flag", {"key": K}, "kill.flag"),
    ("tenant", {"tenant_id": "t-a"}, "kill.tenant"),
    ("platform", {}, "kill.platform"),
])
def test_kill_overrides_every_rule_at_once(w, level, kw, reason):
    s = on_everywhere(w)
    w.ev.is_enabled(w.ctx(), K)  # warm the cache with ON
    w.admin.engage_kill(s, level, "incident", **kw)
    d = w.ev.evaluate(w.ctx(), K)  # no ttl wait: kill is never cached
    assert d.enabled is False and d.reason == reason


def test_kill_overrides_default_true_flag(w):
    w.admin.engage_kill(w.staff(), "platform", "incident")
    assert w.ev.is_enabled(w.ctx(), "ui.dark_default") is False


def test_tenant_kill_leaves_other_tenants(w):
    s = on_everywhere(w)
    w.admin.engage_kill(s, "tenant", "tenant incident", tenant_id="t-b")
    assert w.ev.is_enabled(w.ctx("u-1", "t-a"), K)
    assert not w.ev.is_enabled(w.ctx("u-b", "t-b"), K)


def test_engage_needs_staff_but_no_step_up(w):
    w.clock.advance(1000)
    old = w.staff(auth_time=w.clock() - 900)
    assert w.admin.engage_kill(old, "platform", "incident").new is True


def test_release_needs_step_up(w):
    s = w.staff()
    w.admin.engage_kill(s, "flag", "incident", key=K)
    w.clock.advance(1000)
    old = w.staff(auth_time=w.clock() - 900)
    assert code(lambda: w.admin.release_kill(old, "flag", "all clear", key=K)) == "FLG-011"
    assert w.admin.release_kill(w.staff(), "flag", "all clear", key=K).new is False


def test_platform_release_needs_second_distinct_staff(w):
    w.admin.engage_kill(w.staff(), "platform", "incident")
    a, b = w.staff("s-1"), w.staff("s-2")
    assert code(lambda: w.admin.release_kill(a, "platform", "clear")) == "FLG-012"
    assert code(lambda: w.admin.release_kill(a, "platform", "clear", second=a)) == "FLG-012"
    assert code(lambda: w.admin.release_kill(a, "platform", "clear", second="s-2")) == "FLG-010"
    assert code(lambda: w.admin.release_kill(a, "platform", "clear", second=w.customer())) == "FLG-010"
    assert w.store.kill_state().platform is True
    w.admin.release_kill(a, "platform", "reviewed", second=b)
    assert w.store.kill_state().platform is False


def test_kill_audited_and_idempotent(w):
    s = w.staff()
    w.admin.engage_kill(s, "flag", "incident", key=K)
    assert w.admin.engage_kill(s, "flag", "again", key=K) is None
    r = w.store.audit()[0]
    assert (r.action, r.flag_key, r.old, r.new, r.staff_id) == ("kill.engage.flag", K, False, True, "s-1")


@pytest.mark.parametrize("kw", [
    {"level": "flag"}, {"level": "flag", "key": "nope"}, {"level": "tenant"},
    {"level": "tenant", "tenant_id": "a b"}, {"level": "other"}, {"level": "platform", "key": K},
    {"level": None},
])
def test_kill_args_validated(w, kw):
    level = kw.pop("level")
    assert code(lambda: w.admin.engage_kill(w.staff(), level, "incident", **kw)) == "FLG-003"


def test_kill_by_agent_refused(w):
    assert code(lambda: w.admin.engage_kill("agent:x", "platform", "incident")) == "FLG-010"
    assert code(lambda: w.admin.release_kill(w.customer(), "flag", "clear", key=K)) == "FLG-010"
