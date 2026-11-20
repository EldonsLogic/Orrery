import dataclasses

import pytest

from featureflags import FlagAdmin, FlagError, TenantAuditView

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


def test_global_can_be_cleared_to_unset(w):
    s = w.staff()
    w.admin.set_global(s, "ui.dark_default", False, "off for now")
    assert not w.ev.is_enabled(w.ctx(), "ui.dark_default")
    rec = w.admin.set_global(s, "ui.dark_default", None, "back to default")
    assert (rec.old, rec.new) == (False, None)
    assert w.ev.is_enabled(w.ctx(), "ui.dark_default")


def test_rule_changes_apply_on_the_next_evaluation(w):
    s, c = w.staff(), w.ctx()
    w.admin.set_global(s, K, True, "on now")
    assert w.ev.is_enabled(c, K)
    w.admin.set_global(s, K, False, "off now")
    assert not w.ev.is_enabled(c, K)  # no ttl wait: cache is keyed by store version


# --- audit integrity ------------------------------------------------------
def test_audit_records_are_immutable(w):
    w.admin.set_global(w.staff(), K, True, "roll out")
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.store.audit()[0].new = False
    w.store.audit().clear()  # a copy
    assert len(w.store.audit()) == 1


def test_rewritten_record_fails_even_if_rehashed_without_key(w):
    s = w.staff()
    w.admin.set_global(s, K, True, "roll out")
    w.admin.set_percent(s, "ui.user_beta", 100, "tiny")
    w.store._audit[0] = dataclasses.replace(w.store._audit[0], staff_id="s-2")
    assert not w.store.verify_chain()
    assert code(w.store.audit) == "FLG-050"
    assert code(lambda: w.store.audit_for_tenant("t-a")) == "FLG-050"


def test_forged_with_wrong_key_fails(w):
    from featureflags import AuditSealer
    w.admin.set_global(w.staff(), K, True, "roll out")
    r = w.store._audit[0]
    body = {f: getattr(r, f) for f in r.__dataclass_fields__ if f != "seal"}
    body["reason"] = "forged"
    forged = AuditSealer({"k1": b"x" * 32}, "k1").seal("k1", body)
    w.store._audit[0] = dataclasses.replace(r, reason="forged", seal=forged)
    w.anchor.set(1, forged)  # even with the anchor rewritten too
    assert not w.store.verify_chain()


def test_truncation_fails_against_anchor(w):
    s = w.staff()
    w.admin.set_global(s, K, True, "roll out")
    w.admin.set_percent(s, "ui.user_beta", 100, "tiny")
    w.store._audit.pop()
    assert not w.store.verify_chain()
    assert code(w.store.audit) == "FLG-050"
    assert code(lambda: w.admin.set_global(s, K, False, "off now")) == "FLG-050"  # will not extend


def test_unknown_key_id_and_missing_key_fail_closed(w):
    from featureflags import AuditSealer, InMemoryFlagStore
    for bad in (None, "key", {}, {"k": b"short"}, {"k": "x" * 40}):
        with pytest.raises(FlagError):
            InMemoryFlagStore(bad if not isinstance(bad, dict) else AuditSealer(bad, "k"))
    w.admin.set_global(w.staff(), K, True, "roll out")
    w.store._audit[0] = dataclasses.replace(w.store._audit[0], key_id="gone")
    assert not w.store.verify_chain()


def test_audit_time_never_goes_backwards(w):
    w.admin.set_global(w.staff(), K, True, "roll out")
    late = w.store.audit()[0].at
    entry = dict(at=late - 50, staff_id="s-1", action="x", flag_key=K, tenant_id=None,
                 user_id=None, old=0, new=1, reason="clock stepped back")
    rec = w.store.commit(w.store.version(), entry=entry)
    assert rec.at == late


# --- tenant view -----------------------------------------------------------
def test_tenant_sees_only_own_redacted_changes(w):
    s = w.staff()
    w.admin.set_tenant(s, K, "t-a", True, "internal note: customer X churn")
    w.admin.set_tenant(s, K, "t-b", True, "pilot b")
    w.admin.set_global(s, "ui.user_beta", True, "platform wide secret plan")
    view = w.store.audit_for_tenant("t-a")
    assert len(view) == 1 and isinstance(view[0], TenantAuditView)
    assert not hasattr(view[0], "staff_id") and not hasattr(view[0], "reason")
    assert w.store.audit_for_tenant("t-zzz") == []


@pytest.mark.parametrize("bad", [None, "", 5, "t a", object()])
def test_audit_for_tenant_requires_a_valid_tenant(w, bad):
    w.admin.set_global(w.staff(), K, True, "platform note")
    assert code(lambda: w.store.audit_for_tenant(bad)) == "FLG-003"


# --- who may change anything ------------------------------------------------
@pytest.mark.parametrize("make", [
    lambda w: "s-1", lambda w: None, lambda w: {"subject": "s-1"}, lambda w: object(),
    lambda w: "agent:inbox-drafter", lambda w: w.customer(),
])
def test_non_staff_actors_cannot_change_anything(w, make):
    actor = make(w)
    assert code(lambda: w.admin.set_global(actor, K, True, "go ahead")) == "FLG-010"
    assert code(lambda: w.admin.propose(actor, "global", "go ahead", key=R)) == "FLG-010"
    assert code(lambda: w.admin.approve(actor, "x")) == "FLG-010"
    assert code(lambda: w.admin.engage_kill(actor, "platform", "stop")) == "FLG-010"
    assert w.store.audit() == [] and w.store.denials()


def test_agent_looking_staff_subject_refused(w):
    from identity import StaffIdentity
    for sid in ("agent:drafter", "svc-gateway", "bot_x"):
        w.repo.put_staff(StaffIdentity(sid, sid, mfa_enrolled=True))
        w.roles.held.add((sid, "platform_admin"))
        assert code(lambda: w.admin.set_global(w.staff(sid), K, True, "go ahead")) == "FLG-010"
        assert code(lambda: w.admin.propose(w.staff(sid), "global", "go ahead", key=R)) == "FLG-010"


def test_revoked_inactive_expired_staff_refused(w):
    s = w.staff()
    w.idn.revoke_staff_sessions("s-1")
    assert code(lambda: w.admin.set_global(s, K, True, "go ahead")) == "FLG-010"
    s2 = w.staff("s-2")
    w.repo.put_staff(dataclasses.replace(w.repo.get_staff("s-2"), active=False))
    assert code(lambda: w.admin.set_global(s2, K, True, "go ahead")) == "FLG-010"
    s3 = w.staff("s-3")
    w.clock.advance(24 * 3600)
    assert code(lambda: w.admin.set_global(s3, K, True, "go ahead")) == "FLG-010"


# --- restricted flags: two people, role, bound, single use -----------------
def test_restricted_enable_cannot_be_done_directly(w):
    s = w.staff()
    for fn in (lambda: w.admin.set_global(s, R, True, "go ahead"),
               lambda: w.admin.set_tenant(s, R, "t-a", True, "go ahead"),
               lambda: w.admin.set_user(s, R, "t-a", "u-1", True, "go ahead"),
               lambda: w.admin.set_percent(s, R, 1, "go ahead")):
        assert code(fn) == "FLG-014"
    assert w.store.audit() == [] and not w.ev.is_enabled(w.ctx(), R)


@pytest.mark.parametrize("key", ["agents.draft_inbox", "pay.run_batching", "tax.new_pack_path"])
def test_two_person_enable_of_each_restricted_category(w, key):
    rec = w.enable(key)
    assert (rec.staff_id, rec.approved_by, rec.new) == ("s-1", "s-2", True)
    assert w.ev.is_enabled(w.ctx(), key)


def test_approver_must_be_a_different_human(w):
    p = w.admin.propose(w.fresh("s-1"), "global", "go ahead", key=R)
    assert code(lambda: w.admin.approve(w.fresh("s-1"), p.proposal_id)) == "FLG-015"
    # the failed self-approval did not burn the proposal
    assert w.admin.approve(w.fresh("s-2"), p.proposal_id).approved_by == "s-2"


def test_role_required_default_deny(w):
    # s-3 has no role
    assert code(lambda: w.admin.propose(w.fresh("s-3"), "global", "go ahead", key=R)) == "FLG-013"
    p = w.admin.propose(w.fresh("s-1"), "global", "go ahead", key=R)
    assert code(lambda: w.admin.approve(w.fresh("s-3"), p.proposal_id)) == "FLG-013"
    # nothing configured: deny, even for people who would hold the role
    for kw in ({}, {"restricted_role": "platform_admin"}, {"staff_roles": w.roles}):
        adm = FlagAdmin(w.idn, w.registry, w.store, **kw)
        assert code(lambda: adm.propose(w.fresh("s-1"), "global", "go ahead", key=R)) == "FLG-013"
    # a failing role store denies
    class Boom:
        def has_role(self, *a):
            raise RuntimeError
    adm = FlagAdmin(w.idn, w.registry, w.store, restricted_role="platform_admin", staff_roles=Boom())
    assert code(lambda: adm.propose(w.fresh("s-1"), "global", "go ahead", key=R)) == "FLG-013"
    assert w.store.audit() == []


def test_proposal_is_single_use_expiring_and_exactly_bound(w):
    p = w.admin.propose(w.fresh("s-1"), "tenant", "pilot", key=R, tenant_id="t-a")
    assert p.flag_key == R and p.tenant_id == "t-a" and p.value is True
    w.admin.approve(w.fresh("s-2"), p.proposal_id)
    assert code(lambda: w.admin.approve(w.fresh("s-2"), p.proposal_id)) == "FLG-015"
    # only tenant t-a was enabled
    assert w.ev.is_enabled(w.ctx("u-1", "t-a"), R) and not w.ev.is_enabled(w.ctx("u-b", "t-b"), R)
    assert not w.ev.is_enabled(w.ctx("u-1", "t-a"), "pay.run_batching")
    q = w.admin.propose(w.fresh("s-1"), "global", "go ahead", key="pay.run_batching")
    w.clock.advance(901)
    assert code(lambda: w.admin.approve(w.fresh("s-2"), q.proposal_id)) == "FLG-015"
    for bad in (None, "", "nope", 5, b"x"):
        assert code(lambda: w.admin.approve(w.fresh("s-2"), bad)) == "FLG-015"


def test_proposal_cannot_be_used_to_do_something_else(w):
    # the approver supplies only the id: there is nothing to substitute
    p = w.admin.propose(w.fresh("s-1"), "percent", "ramp", key=R, value=100)
    rec = w.admin.approve(w.fresh("s-2"), p.proposal_id)
    assert (rec.action, rec.flag_key, rec.new) == ("set_percent", R, 100)
    assert not w.ev.is_enabled(w.ctx(), "pay.run_batching")


def test_propose_refuses_what_needs_no_approval(w):
    assert code(lambda: w.admin.propose(w.fresh("s-1"), "global", "go ahead", key=K)) == "FLG-003"  # standard
    assert code(lambda: w.admin.propose(w.fresh("s-1"), "global", "go ahead", key=R, value=False)) == "FLG-003"
    assert code(lambda: w.admin.propose(w.fresh("s-1"), "other", "go ahead", key=R)) == "FLG-003"


def test_each_change_spends_its_own_step_up(w):
    a = w.staff("s-1")
    w.admin.propose(a, "global", "first", key=R)
    # the same sign-in cannot pay for a second proposal (the probe: one step-up, three changes)
    assert code(lambda: w.admin.propose(a, "global", "second", key="pay.run_batching")) == "FLG-011"
    assert code(lambda: w.admin.propose(a, "global", "third", key="tax.new_pack_path")) == "FLG-011"
    # a refreshed token keeps auth_time, so it is still the same step-up
    w.clock.advance(5)
    assert code(lambda: w.admin.propose(w.staff("s-1", auth_time=a.auth_time), "percent", "more ramp",
                                        key=R, value=5)) == "FLG-011"


def test_stale_step_up_refused(w):
    stale = w.staff(auth_time=w.clock() - 301)
    assert code(lambda: w.admin.propose(stale, "global", "go ahead", key=R)) == "FLG-011"
    p = w.admin.propose(w.fresh("s-1"), "global", "go ahead", key=R)
    stale2 = w.staff("s-2", auth_time=w.clock() - 301)
    assert code(lambda: w.admin.approve(stale2, p.proposal_id)) == "FLG-011"


def test_disabling_restricted_and_percent_decrease_need_one_staff_only(w):
    w.enable(R)
    w.clock.advance(1000)
    old = w.staff(auth_time=w.clock() - 900)  # no fresh step-up
    assert w.admin.set_global(old, R, False, "roll back").new is False
    w.enable("pay.run_batching")
    assert w.admin.set_global(old, "pay.run_batching", None, "clear").new is None


def test_standard_flag_needs_no_step_up_or_role(w):
    w.clock.advance(1000)
    s = w.staff("s-3", auth_time=w.clock() - 900)
    assert w.admin.set_global(s, K, True, "roll out").new is True


def test_restricted_flag_cannot_default_on(w):
    assert w.ev.evaluate(w.ctx(), R).reason == "default" and not w.ev.is_enabled(w.ctx(), R)


@pytest.mark.parametrize("bad", [None, "", "ab", "x" * 201, "bad\nreason", 5, b"reason",
                                 "ok ‮gnp.exe", "zero​width", "line sep", "tag\U000e0041"])
def test_reason_required_bounded_and_free_of_invisible_controls(w, bad):
    assert code(lambda: w.admin.set_global(w.staff(), K, True, bad)) == "FLG-003"


def test_arabic_reason_accepted(w):
    assert w.admin.set_global(w.staff(), K, True, "تفعيل تجريبي للمستأجر") is not None


@pytest.mark.parametrize("bad", [1, "true", float("nan")])
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
    assert code(lambda: w.admin.propose(w.staff(), "global", "reason ok", key="made.up")) == "FLG-002"


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


def test_one_clock_source_the_identity_clock(w):
    adm = FlagAdmin(w.idn, w.registry, w.store)
    assert adm._now() == w.clock()
