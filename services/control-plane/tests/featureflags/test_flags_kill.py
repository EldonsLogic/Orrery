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
    d = w.ev.evaluate(w.ctx(), K)
    assert d.enabled is False and d.reason == reason


def test_kill_overrides_default_true_flag(w):
    w.admin.engage_kill(w.staff(), "platform", "incident")
    assert w.ev.is_enabled(w.ctx(), "ui.dark_default") is False


def test_kill_overrides_a_restricted_flag_enabled_by_two_people(w):
    w.enable("agents.draft_inbox")
    assert w.ev.is_enabled(w.ctx(), "agents.draft_inbox")
    w.admin.engage_kill(w.staff(), "flag", "incident", key="agents.draft_inbox")
    assert not w.ev.is_enabled(w.ctx(), "agents.draft_inbox")


def test_tenant_kill_leaves_other_tenants(w):
    s = on_everywhere(w)
    w.admin.engage_kill(s, "tenant", "tenant incident", tenant_id="t-b")
    assert w.ev.is_enabled(w.ctx("u-1", "t-a"), K)
    assert not w.ev.is_enabled(w.ctx("u-b", "t-b"), K)


def test_engage_needs_staff_but_no_step_up_or_role(w):
    w.clock.advance(1000)
    old = w.staff("s-3", auth_time=w.clock() - 900)
    assert w.admin.engage_kill(old, "platform", "incident").new is True


def test_release_needs_a_fresh_step_up_spent_once(w):
    s = w.staff()
    w.admin.engage_kill(s, "flag", "incident", key=K)
    w.admin.engage_kill(s, "tenant", "incident", tenant_id="t-a")
    w.clock.advance(1000)
    old = w.staff(auth_time=w.clock() - 900)
    assert code(lambda: w.admin.release_kill(old, "flag", "all clear", key=K)) == "FLG-011"
    fresh = w.fresh()
    assert w.admin.release_kill(fresh, "flag", "all clear", key=K).new is False
    assert code(lambda: w.admin.release_kill(fresh, "tenant", "clear", tenant_id="t-a")) == "FLG-011"


def test_platform_release_is_propose_approve_bound_and_single_use(w):
    w.admin.engage_kill(w.staff(), "platform", "incident")
    assert code(lambda: w.admin.release_kill(w.fresh(), "platform", "clear")) == "FLG-014"
    assert w.store.kill_state().platform is True
    p = w.admin.propose(w.fresh("s-1"), "release_platform_kill", "reviewed, clear")
    assert code(lambda: w.admin.approve(w.fresh("s-1"), p.proposal_id)) == "FLG-015"  # self
    rec = w.admin.approve(w.fresh("s-2"), p.proposal_id)
    assert (rec.staff_id, rec.approved_by, rec.new) == ("s-1", "s-2", False)
    assert w.store.kill_state().platform is False
    # the approval does not carry over to the next incident
    w.admin.engage_kill(w.staff(), "platform", "incident again")
    assert code(lambda: w.admin.approve(w.fresh("s-2"), p.proposal_id)) == "FLG-015"
    assert w.store.kill_state().platform is True
    # one approver session cannot release three times
    s2 = w.fresh("s-2")
    p2 = w.admin.propose(w.fresh("s-1"), "release_platform_kill", "second clear")
    w.admin.approve(s2, p2.proposal_id)
    w.admin.engage_kill(w.staff(), "platform", "incident 3")
    p3 = w.admin.propose(w.fresh("s-1"), "release_platform_kill", "third clear")
    assert code(lambda: w.admin.approve(s2, p3.proposal_id)) == "FLG-011"


def test_platform_release_needs_the_role_and_nothing_to_release_is_refused(w):
    assert code(lambda: w.admin.propose(w.fresh("s-1"), "release_platform_kill", "clear")) == "FLG-003"
    w.admin.engage_kill(w.staff(), "platform", "incident")
    assert code(lambda: w.admin.propose(w.fresh("s-3"), "release_platform_kill", "clear")) == "FLG-013"


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
