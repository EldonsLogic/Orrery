import pytest

from identity import IdentityError, Membership, Realm, RoleInfo, StaffIdentity
from identity.mfa import FactorStatus, totp
from identity.policy import role_requires_mfa
from mfa_helpers import Hooked, MfaWorld


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def actions(w, name):
    return [e for e in w.audit.events() if e.action == name]


@pytest.fixture
def m(w):
    return MfaWorld(w)


def next_step(w):
    w.clock.advance(totp.PERIOD)


def customer_with_factor(m, pid="p-clerk"):
    fid, codes = m.enrol_customer(pid)
    next_step(m.w)
    return fid, codes, m.passwords.set("customer", pid)


# -- enrolment -------------------------------------------------------------
def test_first_factor_enrols_and_returns_recovery_codes(m):
    fid, codes = m.enrol_customer()
    assert len(codes) == 10 and len(set(codes)) == 10
    assert m.w.repo.get_person("p-clerk").mfa_enrolled is True
    assert m.factors.get_factor(fid).status is FactorStatus.ACTIVE


def test_enrolment_needs_valid_code_and_pending_dies(m):
    claims = m.w.claims("p-clerk", mfa=False)
    start = m.svc.begin_totp_enrolment(claims)
    assert code(lambda: m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                                     "000000", claims=claims)) == "IDN-060"
    m.w.clock.advance(601)
    assert code(lambda: m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                                     m.code(start.factor_id), claims=claims)) == "IDN-062"


def test_confirm_for_another_subject_or_without_session_denied(m):
    claims = m.w.claims("p-clerk", mfa=False)
    start = m.svc.begin_totp_enrolment(claims)
    c = m.code(start.factor_id)
    assert code(lambda: m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-owner", start.factor_id, c,
                                                     claims=claims)) == "IDN-062"
    assert code(lambda: m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                                     c)) == "IDN-013"
    other = m.w.claims("p-owner")
    assert code(lambda: m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id, c,
                                                     claims=other)) == "IDN-013"


def test_second_factor_needs_step_up(m):
    fid, _, pw = customer_with_factor(m)
    stale = m.w.claims("p-clerk", mfa=True)
    m.w.clock.advance(400)
    assert code(lambda: m.svc.begin_totp_enrolment(stale)) == "IDN-013"
    fresh = m.w.claims("p-clerk", mfa=True)
    start = m.svc.begin_totp_enrolment(fresh)
    assert m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                        m.code(start.factor_id), claims=fresh) == ()
    assert len(m.svc._active(Realm.CUSTOMER, "p-clerk")) == 2


def test_non_mfa_session_cannot_add_factor_once_enrolled(m):
    customer_with_factor(m)
    weak = m.w.claims("p-clerk", mfa=False)
    assert code(lambda: m.svc.begin_totp_enrolment(weak)) == "IDN-013"


def test_factor_cap(m):
    customer_with_factor(m)
    for _ in range(2):
        claims = m.w.claims("p-clerk", mfa=True)
        s = m.svc.begin_totp_enrolment(claims)
        next_step(m.w)
        m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", s.factor_id, m.code(s.factor_id), claims=claims)
    claims = m.w.claims("p-clerk", mfa=True)
    assert code(lambda: m.svc.begin_totp_enrolment(claims)) == "IDN-062"


# -- sign-in ---------------------------------------------------------------
def test_sign_in_password_then_factor_gives_mfa_token(m):
    fid, _, pw = customer_with_factor(m)
    pair = m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")
    c = m.w.idn.verify_customer_token(pair.access_token, "t-a")
    assert c.mfa_satisfied is True and c.auth_time == m.w.clock()
    m.w.idn.require_step_up(c)


def test_sign_in_needs_the_factor_when_enrolled(m):
    fid, _, pw = customer_with_factor(m)
    # M1: a missing code with the right password is the same IDN-060 as a wrong password
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, None, tenant_id="t-a")) == "IDN-060"
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", "nope", None, tenant_id="t-a")) == "IDN-060"


def test_wrong_password_and_wrong_code_are_indistinguishable(m):
    fid, _, pw = customer_with_factor(m)
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", "nope", m.code(fid), tenant_id="t-a")) == "IDN-060"
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "000000", tenant_id="t-a")) == "IDN-060"
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "ghost", pw, "000000", tenant_id="t-a")) == "IDN-060"


def test_replayed_code_refused(m):
    fid, _, pw = customer_with_factor(m)
    c = m.code(fid)
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")) == "IDN-060"
    # drift: the previous step's code is also dead once a later counter was used
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid, -1), tenant_id="t-a")) == "IDN-060"
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid, +1), tenant_id="t-a")  # one step of drift


def test_replay_race_only_one_request_wins(w):
    repo = Hooked()
    m = MfaWorld(w, repo)
    fid, _, pw = customer_with_factor(m)
    c = m.code(fid)
    counter = totp.counter_at(w.clock())
    snapshot_last = repo.get_factor(fid).last_counter

    def competitor(_snap):  # a second request with the same code commits first
        assert repo.advance_counter(fid, snapshot_last, counter) is True

    repo.on_factors_for = competitor
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")) == "IDN-060"
    assert repo.get_factor(fid).last_counter == counter


def test_cas_refuses_stale_and_non_increasing(m):
    fid, _, _ = customer_with_factor(m)
    last = m.factors.get_factor(fid).last_counter
    assert m.factors.advance_counter(fid, last + 5, last + 9) is False
    assert m.factors.advance_counter(fid, last, last) is False
    assert m.factors.advance_counter(fid, last, last + 1) is True
    assert m.factors.advance_counter(fid, last, last + 2) is False


def test_lockout_after_n_failures_even_for_right_code(m):
    fid, _, pw = customer_with_factor(m)
    for _ in range(5):
        assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "000000", tenant_id="t-a")) == "IDN-060"
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-061"
    m.w.clock.advance(901)
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")


def test_success_resets_failure_count(m):
    fid, _, pw = customer_with_factor(m)
    for _ in range(4):
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "000000", tenant_id="t-a"))
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")
    next_step(m.w)
    for _ in range(4):
        assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "000000", tenant_id="t-a")) == "IDN-060"


def test_wrong_password_counts_toward_lockout(m):
    fid, _, pw = customer_with_factor(m)
    for _ in range(5):
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", "bad", None, tenant_id="t-a"))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-061"


def test_wrong_passwords_from_one_source_do_not_lock_the_account(m):
    # M2: guesses without the password lock only (subject, source), not the owner
    fid, _, pw = customer_with_factor(m)
    for _ in range(6):
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", "bad", "000000", tenant_id="t-a",
                                   source="attacker"))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a",
                                      source="attacker")) == "IDN-061"
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a", source="owner-device")


def test_source_throttle_is_consulted(m):
    fid, _, pw = customer_with_factor(m)
    m.svc.sources = type("Deny", (), {"allow": lambda self, s, now: s != "blocked"})()
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a",
                                      source="blocked")) == "IDN-061"
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a", source="ok")


def test_store_failure_fails_closed(w):
    repo = Hooked()
    m = MfaWorld(w, repo)
    fid, _, pw = customer_with_factor(m)
    repo.fail = True
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-064"


def test_password_verifier_error_denies(m):
    fid, _, pw = customer_with_factor(m)
    good = m.svc.passwords
    m.svc.passwords = type("Bad", (), {"verify": lambda *a: 1 / 0})()
    for _ in range(8):  # L5: a provider outage is IDN-064 and is not counted as a guess
        assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-064"
    m.svc.passwords = good
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")


# -- recovery codes ----------------------------------------------------------
def test_recovery_code_single_use_and_stored_hashed(m):
    fid, codes, pw = customer_with_factor(m)
    stored = m.factors.recovery_for("customer", "p-clerk")
    flat = [c.replace("-", "") for c in codes]
    assert len({r.salt for r in stored}) == 10
    for r in stored:
        assert all(p.encode() not in r.digest and p.encode() not in r.salt for p in flat)
    pair = m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, codes[0], tenant_id="t-a")
    assert m.w.idn.verify_customer_token(pair.access_token, "t-a").mfa_satisfied is True
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, codes[0], tenant_id="t-a")) == "IDN-060"
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, codes[1].lower(), tenant_id="t-a")  # case-insensitive


def test_recovery_use_is_audited_without_the_code(m):
    fid, codes, pw = customer_with_factor(m)
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, codes[0], tenant_id="t-a")
    assert [e.decision for e in actions(m.w, "mfa.recovery_use")] == ["allow"]
    dump = repr(m.w.audit.events())
    assert codes[0] not in dump and pw not in dump and m.code(fid) not in dump


def test_recovery_consume_is_atomic(m):
    fid, codes, _ = customer_with_factor(m)
    rid = m.factors.recovery_for("customer", "p-clerk")[0].code_id
    assert m.factors.consume_recovery("customer", "p-owner", rid) is False  # keyed by subject
    assert m.factors.consume_recovery("customer", "p-clerk", rid) is True
    assert m.factors.consume_recovery("customer", "p-clerk", rid) is False


def test_regenerate_needs_step_up_and_kills_old_codes(m):
    fid, old, pw = customer_with_factor(m)
    weak = m.w.claims("p-clerk", mfa=False)
    assert code(lambda: m.svc.regenerate_recovery_codes(weak)) == "IDN-013"
    new = m.svc.regenerate_recovery_codes(m.w.claims("p-clerk", mfa=True))
    assert set(new).isdisjoint(old)
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, old[0], tenant_id="t-a")) == "IDN-060"
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, new[0], tenant_id="t-a")


def test_recovery_guessing_is_throttled(m):
    fid, codes, pw = customer_with_factor(m)
    for _ in range(5):
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "AAAAA-AAAAA", tenant_id="t-a"))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, codes[0], tenant_id="t-a")) == "IDN-061"


# -- removal and step-up ----------------------------------------------------
def test_removal_needs_step_up_and_clears_enrolment(m):
    fid, _, pw = customer_with_factor(m)
    m.w.clock.advance(400)
    stale = m.w.claims("p-clerk", mfa=True)
    m.w.clock.advance(400)
    assert code(lambda: m.svc.remove_factor(stale, fid)) == "IDN-013"
    fresh = m.w.claims("p-clerk", mfa=True)
    m.svc.remove_factor(fresh, fid)
    assert m.factors.get_factor(fid) is None
    assert m.factors.recovery_for("customer", "p-clerk") == ()
    assert m.w.repo.get_person("p-clerk").mfa_enrolled is False
    assert code(lambda: m.svc.remove_factor(fresh, fid)) == "IDN-009"  # M5: that session ended
    assert code(lambda: m.svc.remove_factor(m.w.claims("p-clerk", mfa=True), fid)) == "IDN-063"


def test_cannot_remove_someone_elses_factor(m):
    fid, _, _ = customer_with_factor(m)
    owner = m.w.claims("p-owner")
    assert code(lambda: m.svc.remove_factor(owner, fid)) == "IDN-063"


def test_last_factor_stays_when_tenant_demands_mfa(m):
    # p-clerk's role (sales) does not demand MFA: only the tenant flag does (L10)
    fid, _, _ = customer_with_factor(m)
    m.w.repo.put_tenant(type(m.w.repo.get_tenant("t-a"))("t-a", mfa_for_all=True))
    assert code(lambda: m.svc.remove_factor(m.w.claims("p-clerk"), fid)) == "IDN-062"
    m.w.repo.put_tenant(type(m.w.repo.get_tenant("t-a"))("t-a", mfa_for_all=False))
    m.svc.remove_factor(m.w.claims("p-clerk"), fid)


def test_last_factor_stays_when_another_tenant_demands_mfa(m):
    fid, _, _ = customer_with_factor(m)
    m.w.repo.put_membership(Membership("p-clerk", "t-b"))
    m.w.repo.put_tenant(type(m.w.repo.get_tenant("t-b"))("t-b", mfa_for_all=True))
    assert code(lambda: m.svc.remove_factor(m.w.claims("p-clerk"), fid)) == "IDN-062"


def test_step_up_returns_fresh_auth_time(m):
    fid, _, pw = customer_with_factor(m)
    c = m.w.idn.verify_customer_token(
        m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a").access_token, "t-a")
    m.w.clock.advance(400)
    assert code(lambda: m.w.idn.require_step_up(c)) == "IDN-013"
    pair = m.svc.step_up(c, m.code(fid))
    assert m.w.idn.verify_customer_token(pair.access_token, "t-a").auth_time == m.w.clock()


# -- policy: owners, staff, support ------------------------------------------
def test_owner_requires_mfa_by_policy_and_signs_in_with_factor(m):
    owner_only = RoleInfo("owner", functions=frozenset({"owner"}))
    assert role_requires_mfa(owner_only)
    claims = m.w.claims("p-owner")
    s = m.svc.begin_totp_enrolment(claims)
    m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-owner", s.factor_id, m.code(s.factor_id), claims=claims)
    next_step(m.w)
    pw = m.passwords.set("customer", "p-owner")
    # password alone is not enough for an owner
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-owner", pw, None, tenant_id="t-a")) == "IDN-060"
    next_step(m.w)
    pair = m.svc.sign_in(Realm.CUSTOMER, "p-owner", pw, m.code(s.factor_id), tenant_id="t-a")
    assert m.w.idn.verify_customer_token(pair.access_token, "t-a").mfa_satisfied is True


def test_owner_without_factor_cannot_get_a_token(m):
    m.w.repo.put_person(type(m.w.repo.get_person("p-owner"))("p-owner", "o", mfa_enrolled=False))
    pw = m.passwords.set("customer", "p-owner")
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-owner", pw, None, tenant_id="t-a")) == "IDN-013"


def test_support_function_role_requires_mfa(m):
    assert role_requires_mfa(RoleInfo("support_agent", functions=frozenset({"support"})))
    m.w.resolver.roles[("t-a", "p-clerk")] = (RoleInfo("support_agent", functions=frozenset({"support"})),)
    pw = m.passwords.set("customer", "p-clerk")
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, None, tenant_id="t-a")) == "IDN-013"


def staff_enrol(m, sid="s-1"):
    m.w.repo.put_staff(StaffIdentity(sid, "S", mfa_enrolled=False))
    start = m.svc.begin_staff_bootstrap(sid, m.bootstrap.issue(sid))
    codes = m.svc.confirm_totp_enrolment(Realm.STAFF, sid, start.factor_id, m.code(start.factor_id))
    next_step(m.w)
    return start.factor_id, codes, m.passwords.set("staff", sid)


def test_staff_bootstrap_needs_a_ticket_and_it_is_single_use(m):
    m.w.repo.put_staff(StaffIdentity("s-2", "S", mfa_enrolled=False))
    assert code(lambda: m.svc.begin_staff_bootstrap("s-2", "guess")) == "IDN-060"
    t = m.bootstrap.issue("s-2")
    m.svc.begin_staff_bootstrap("s-2", t)
    assert code(lambda: m.svc.begin_staff_bootstrap("s-2", t)) == "IDN-060"


def test_staff_sign_in_always_needs_the_factor(m):
    fid, codes, pw = staff_enrol(m)
    assert code(lambda: m.svc.sign_in(Realm.STAFF, "s-1", pw, None)) == "IDN-060"
    pair = m.svc.sign_in(Realm.STAFF, "s-1", pw, m.code(fid))
    c = m.w.idn.verify_staff_token(pair.access_token)
    assert c.mfa_satisfied is True and c.tenant is None


def test_staff_without_factor_cannot_sign_in_and_cannot_drop_last_factor(m):
    m.w.repo.put_staff(StaffIdentity("s-3", "S", mfa_enrolled=False))
    pw = m.passwords.set("staff", "s-3")
    assert code(lambda: m.svc.sign_in(Realm.STAFF, "s-3", pw, None)) == "IDN-013"
    fid, _, pw1 = staff_enrol(m)
    claims = m.w.idn.verify_staff_token(m.svc.sign_in(Realm.STAFF, "s-1", pw1, m.code(fid)).access_token)
    assert code(lambda: m.svc.remove_factor(claims, fid)) == "IDN-062"


def test_staff_support_access_needs_mfa_end_to_end(m):
    fid, _, pw = staff_enrol(m)
    claims = m.w.idn.verify_staff_token(m.svc.sign_in(Realm.STAFF, "s-1", pw, m.code(fid)).access_token)
    gid = m.w.support.request(claims, "t-a", "ticket 1", frozenset({"read"}), 600)
    assert gid
    # a staff token minted without MFA is never accepted
    assert code(lambda: m.w.idn.issue_staff_token("s-1", mfa_satisfied=False, auth_time=m.w.clock())) == "IDN-013"


def test_staff_enrolling_another_factor_needs_step_up(m):
    fid, _, pw = staff_enrol(m)
    m.svc.sign_in(Realm.STAFF, "s-1", pw, m.code(fid))
    m.w.clock.advance(400)
    c2 = m.w.idn.verify_staff_token(m.w.idn.issue_staff_token(
        "s-1", mfa_satisfied=True, auth_time=m.w.clock() - 400).access_token)
    assert code(lambda: m.svc.begin_totp_enrolment(c2)) == "IDN-013"


def test_enrolment_audited_without_secrets(m):
    claims = m.w.claims("p-clerk", mfa=False)
    start = m.svc.begin_totp_enrolment(claims)
    m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                 m.code(start.factor_id), claims=claims)
    names = {e.action for e in m.w.audit.events()}
    assert {"mfa.enrol_begin", "mfa.enrol_confirm"} <= names
    dump = repr(m.w.audit.events())
    assert start.secret not in dump and m.code(start.factor_id) not in dump
    assert start.secret not in repr(start)


def test_sealed_secret_is_not_plain(m):
    claims = m.w.claims("p-clerk", mfa=False)
    start = m.svc.begin_totp_enrolment(claims)
    f = m.factors.get_factor(start.factor_id)
    assert f.sealed_secret != m.key(start.factor_id) and "sealed_secret" not in repr(f)
