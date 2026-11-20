import dataclasses

import pytest

from featureflags import FlagError

K = "ui.new_viewer"
R = "agents.draft_inbox"


def code(fn):
    with pytest.raises(FlagError) as e:
        fn()
    return e.value.code


def test_change_is_audited_with_who_when_old_new(w):
    s = w.staff()
    rec = w.admin.set_tenant(s, K, "t-a", True, "pilot tenant")
    assert (rec.staff_id, rec.at, rec.flag_key, rec.tenant_id, rec.old, rec.new, rec.reason) == \
        ("s-1", w.clock(), K, "t-a", False, True, "pilot tenant")
    w.admin.set_tenant(s, K, "t-a", False, "pilot over")
    log = w.store.audit()
    assert [(r.old, r.new) for r in log] == [(False, True), (True, False)]
    assert [r.seq for r in log] == [1, 2] and w.store.verify_chain()


def test_no_op_writes_nothing(w):
    s = w.staff()
    w.admin.set_global(s, K, True, "roll out")
    assert w.admin.set_global(s, K, True, "again") is None
    assert len(w.store.audit()) == 1


def test_audit_is_tamper_evident_and_immutable(w):
    s = w.staff()
    w.admin.set_global(s, K, True, "roll out")
    w.admin.set_percent(s, "ui.user_beta", 100, "tiny")
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.store.audit()[0].new = False
    w.store.audit().clear()  # a copy
    assert len(w.store.audit()) == 2
    w.store._audit[0] = dataclasses.replace(w.store._audit[0], new=False)
    assert not w.store.verify_chain()


def test_tenant_sees_only_own_changes(w):
    s = w.staff()
    w.admin.set_tenant(s, K, "t-a", True, "pilot a")
    w.admin.set_tenant(s, K, "t-b", True, "pilot b")
    assert [r.tenant_id for r in w.store.audit_for_tenant("t-a")] == ["t-a"]
    assert w.store.audit_for_tenant("t-zzz") == []


@pytest.mark.parametrize("make", [
    lambda w: "s-1", lambda w: None, lambda w: {"subject": "s-1"}, lambda w: object(),
    lambda w: "agent:inbox-drafter", lambda w: w.customer(),  # customer realm, even an owner
])
def test_non_staff_actors_cannot_change_anything(w, make):
    actor = make(w)
    assert code(lambda: w.admin.set_global(actor, K, True, "go")) == "FLG-010"
    assert code(lambda: w.admin.set_tenant(actor, R, "t-a", True, "go")) == "FLG-010"
    assert code(lambda: w.admin.engage_kill(actor, "platform", "stop")) == "FLG-010"
    assert w.store.audit() == [] and w.store.denials()


def test_agent_cannot_enable_restricted_flag_even_with_a_staff_id_string(w):
    for fn in (lambda: w.admin.set_global("s-1", R, True, "agent says ok"),
               lambda: w.admin.set_percent("s-1", R, 10000, "agent says ok")):
        assert code(fn) == "FLG-010"
    assert w.ev.is_enabled(w.ctx(), R) is False


def test_staff_without_mfa_or_inactive_or_revoked_refused(w):
    s = w.staff()
    w.idn.revoke_staff_sessions("s-1")
    assert code(lambda: w.admin.set_global(s, K, True, "go")) == "FLG-010"
    s2 = w.staff("s-2")
    w.repo.put_staff(dataclasses.replace(w.repo.get_staff("s-2"), active=False))
    assert code(lambda: w.admin.set_global(s2, K, True, "go")) == "FLG-010"


def test_expired_staff_token_refused(w):
    s = w.staff()
    w.clock.advance(24 * 3600)
    assert code(lambda: w.admin.set_global(s, K, True, "go")) == "FLG-010"


@pytest.mark.parametrize("key", ["agents.draft_inbox", "pay.run_batching", "tax.new_pack_path"])
def test_restricted_enable_needs_fresh_step_up(w, key):
    stale = w.staff()
    w.clock.advance(301)
    stale = w.staff(auth_time=w.clock() - 301)
    assert code(lambda: w.admin.set_global(stale, key, True, "go")) == "FLG-011"
    assert code(lambda: w.admin.set_tenant(stale, key, "t-a", True, "go")) == "FLG-011"
    assert code(lambda: w.admin.set_user(stale, key, "t-a", "u-1", True, "go")) == "FLG-011"
    assert code(lambda: w.admin.set_percent(stale, key, 1, "go")) == "FLG-011"
    assert w.store.audit() == []
    fresh = w.staff()
    assert w.admin.set_global(fresh, key, True, "approved rollout").new is True
    # disabling needs no step-up (safe direction), still a staff human
    w.clock.advance(1000)
    assert w.admin.set_global(w.staff(auth_time=w.clock() - 900), key, False, "roll back").new is False


def test_percent_decrease_on_restricted_flag_needs_no_step_up(w):
    w.admin.set_percent(w.staff(), R, 5000, "half")
    w.clock.advance(1000)
    old = w.staff(auth_time=w.clock() - 900)
    assert code(lambda: w.admin.set_percent(old, R, 6000, "more")) == "FLG-011"
    assert w.admin.set_percent(old, R, 1000, "less").new == 1000


def test_standard_flag_needs_no_step_up(w):
    w.clock.advance(1000)
    s = w.staff(auth_time=w.clock() - 900)
    assert w.admin.set_global(s, K, True, "roll out").new is True


def test_restricted_flag_cannot_default_on_or_be_enabled_by_default(w):
    assert w.ev.evaluate(w.ctx(), R).reason == "default"
    assert not w.ev.is_enabled(w.ctx(), R)


@pytest.mark.parametrize("bad", [None, "", "ab", "x" * 201, "bad\nreason", 5, b"reason"])
def test_reason_required_and_bounded(w, bad):
    assert code(lambda: w.admin.set_global(w.staff(), K, True, bad)) == "FLG-003"


@pytest.mark.parametrize("bad", [1, None, "true", float("nan")])
def test_value_must_be_a_real_bool(w, bad):
    assert code(lambda: w.admin.set_global(w.staff(), K, bad, "reason ok")) == "FLG-003"


@pytest.mark.parametrize("bp", [-1, 10001, True, 1.5, float("nan"), "5", None])
def test_percent_validated(w, bp):
    assert code(lambda: w.admin.set_percent(w.staff(), K, bp, "reason ok")) == "FLG-003"


@pytest.mark.parametrize("tid", ["", " ", "t a", "t-a\n", "../t", "x" * 129, None, 5, "t\x00a"])
def test_ids_validated(w, tid):
    assert code(lambda: w.admin.set_tenant(w.staff(), K, tid, True, "reason ok")) == "FLG-003"
    assert code(lambda: w.admin.set_user(w.staff(), K, "t-a", tid, True, "reason ok")) == "FLG-003"


def test_unknown_flag_cannot_be_created_by_admin(w):
    assert code(lambda: w.admin.set_global(w.staff(), "made.up", True, "reason ok")) == "FLG-002"
    assert w.store.audit() == []


def test_failed_store_write_changes_nothing(w):
    s = w.staff()
    w.store.fail = True
    assert code(lambda: w.admin.set_global(s, K, True, "reason ok")) == "FLG-050"
    w.store.fail = False
    assert w.store.audit() == [] and not w.ev.is_enabled(w.ctx(), K)


def test_concurrent_change_is_refused_not_lost(w):
    s = w.staff()
    version = w.store.version()
    w.admin.set_global(s, K, True, "first")
    with pytest.raises(FlagError) as e:
        w.store.commit(version, flag_key=K, flag_state=w.store.get_flag(K),
                       entry=dict(at=1, staff_id="s-1", action="x", flag_key=K, tenant_id=None,
                                  user_id=None, old=0, new=1, reason="late"))
    assert e.value.code == "FLG-040" and len(w.store.audit()) == 1
