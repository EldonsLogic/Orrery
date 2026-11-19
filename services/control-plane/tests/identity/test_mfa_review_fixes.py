"""PR #186 Tier 3 review fixes (H1, M1-M5, LOWs)."""

from dataclasses import replace

import pytest

from identity import IdentityError, MembershipStatus, Realm, StaffIdentity
from identity.mfa import recovery, totp
from identity.mfa import service as mfa_service
from mfa_helpers import Hooked, MfaWorld


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


@pytest.fixture
def m(w):
    return MfaWorld(w)


def enrolled(m, pid="p-clerk"):
    fid, codes = m.enrol_customer(pid)
    m.w.clock.advance(totp.PERIOD)
    return fid, codes, m.passwords.set("customer", pid)


def enrol_mfa_person(m, pid):
    """First factor for a fixture person whose role already demands MFA."""
    claims = m.w.claims(pid, mfa=True)
    s = m.svc.begin_totp_enrolment(claims)
    m.svc.confirm_totp_enrolment(Realm.CUSTOMER, pid, s.factor_id, m.code(s.factor_id), claims=claims)
    return s.factor_id


def add_factor(m, pid="p-clerk"):
    claims = m.w.claims(pid, mfa=True)
    s = m.svc.begin_totp_enrolment(claims)
    m.svc.confirm_totp_enrolment(Realm.CUSTOMER, pid, s.factor_id, m.code(s.factor_id), claims=claims)
    m.w.clock.advance(totp.PERIOD)
    return s.factor_id


# -- H1: first factor needs the password proven now ---------------------------
def test_stale_session_cannot_begin_first_enrolment(m):
    claims = m.w.claims("p-clerk", mfa=False)
    m.w.clock.advance(301)
    assert code(lambda: m.svc.begin_totp_enrolment(claims)) == "IDN-013"


def test_refreshed_session_keeps_old_auth_time_and_cannot_enrol(m):
    pair = m.w.login("p-clerk", mfa=False)
    m.w.clock.advance(400)
    fresh_pair = m.w.idn.refresh(pair.refresh_token, "t-a")
    claims = m.w.idn.verify_customer_token(fresh_pair.access_token, "t-a")
    assert code(lambda: m.svc.begin_totp_enrolment(claims)) == "IDN-013"


def test_stale_session_may_enrol_by_re_entering_the_password(m):
    pw = m.passwords.set("customer", "p-clerk")
    claims = m.w.claims("p-clerk", mfa=False)
    m.w.clock.advance(400)
    assert code(lambda: m.svc.begin_totp_enrolment(claims, password="wrong")) == "IDN-060"
    start = m.svc.begin_totp_enrolment(claims, password=pw)
    codes = m.svc.confirm_totp_enrolment(Realm.CUSTOMER, "p-clerk", start.factor_id,
                                         m.code(start.factor_id), claims=claims)
    assert len(codes) == 10


def test_enrolment_password_guesses_are_counted(m):
    claims = m.w.claims("p-clerk", mfa=False)
    m.w.clock.advance(400)
    for _ in range(5):
        code(lambda: m.svc.begin_totp_enrolment(claims, password="wrong"))
    pw = m.passwords.set("customer", "p-clerk")
    assert code(lambda: m.svc.begin_totp_enrolment(claims, password=pw)) == "IDN-061"


# -- M1: no password oracle -----------------------------------------------------
def test_uniform_error_for_password_and_code_shapes(m):
    fid, codes, pw = enrolled(m)
    for p, c in ((pw, None), ("nope", None), (pw, "AAAAA-AAAAA"), ("nope", "AAAAA-AAAAA"),
                 (pw, "000000"), ("nope", m.code(fid)), ("nope", codes[0])):
        m.svc._clear_key(m.svc._source_key(Realm.CUSTOMER, "p-clerk", "unknown"))
        m.svc._clear(Realm.CUSTOMER, "p-clerk")
        assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", p, c, tenant_id="t-a")) == "IDN-060"


def test_uniform_work_whatever_the_password_and_codes_left(m, monkeypatch):
    fid, codes, pw = enrolled(m)
    calls = []
    real_matches, real_verify = recovery.matches, totp.verify
    monkeypatch.setattr(recovery, "matches", lambda *a: calls.append("kdf") or real_matches(*a))
    monkeypatch.setattr(totp, "verify", lambda *a, **k: calls.append("totp") or real_verify(*a, **k))

    def work(password, c):
        calls.clear()
        m.svc._clear_key(m.svc._source_key(Realm.CUSTOMER, "p-clerk", "unknown"))
        m.svc._clear(Realm.CUSTOMER, "p-clerk")
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", password, c, tenant_id="t-a"))
        return list(calls)

    assert work("nope", "AAAAA-AAAAA") == work(pw, "AAAAA-AAAAA") == ["kdf"] * 10
    assert work("nope", "000000") == work(pw, "000000") == ["totp"] * m.svc.cfg.max_factors
    assert work("ghost-pw", "AAAAA-AAAAA") == ["kdf"] * 10
    for c in codes[:3]:  # L3: used codes do not shorten the work
        m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")
    assert work(pw, "AAAAA-AAAAA") == ["kdf"] * 10


def test_unknown_subject_does_the_same_recovery_work(m, monkeypatch):
    calls = []
    real = recovery.matches
    monkeypatch.setattr(recovery, "matches", lambda *a: calls.append(1) or real(*a))
    code(lambda: m.svc.sign_in(Realm.CUSTOMER, "ghost", "pw", "AAAAA-AAAAA", tenant_id="t-a"))
    assert len(calls) == 10


# -- M2: lockout -------------------------------------------------------------
def test_lockout_not_extended_while_locked(m):
    fid, _, pw = enrolled(m)
    for _ in range(5):
        code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "000000", tenant_id="t-a"))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-061"
    m.w.clock.advance(600)
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")) == "IDN-061"
    m.w.clock.advance(301)  # 901 s after the lock: not pushed back by the attempt at 600 s
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")


# -- M3: atomic last-factor removal --------------------------------------------
class RaceRemove(Hooked):
    before_remove = None

    def remove_factor(self, *args):
        hook, self.before_remove = self.before_remove, None
        if hook:
            hook()
        return super().remove_factor(*args)


def two_factor_world(w):
    repo = RaceRemove()
    m = MfaWorld(w, repo)
    a, _, _ = enrolled(m)
    b = add_factor(m)
    return m, repo, a, b


def test_concurrent_removes_never_leave_zero_factors_when_mfa_is_required(w):
    m, repo, a, b = two_factor_world(w)
    w.repo.put_tenant(type(w.repo.get_tenant("t-a"))("t-a", mfa_for_all=True))
    c1, c2 = w.claims("p-clerk"), w.claims("p-clerk")
    repo.before_remove = lambda: m.svc.remove_factor(c2, b)  # the other remove commits first
    assert code(lambda: m.svc.remove_factor(c1, a)) == "IDN-062"
    assert [f.factor_id for f in m.svc._active(Realm.CUSTOMER, "p-clerk")] == [a]
    assert w.repo.get_person("p-clerk").mfa_enrolled is True
    assert len(repo.recovery_for("customer", "p-clerk")) == 10


def test_concurrent_removes_when_optional_end_consistent(w):
    m, repo, a, b = two_factor_world(w)
    c1, c2 = w.claims("p-clerk"), w.claims("p-clerk")
    repo.before_remove = lambda: m.svc.remove_factor(c2, b)
    m.svc.remove_factor(c1, a)
    assert m.svc._active(Realm.CUSTOMER, "p-clerk") == ()
    assert w.repo.get_person("p-clerk").mfa_enrolled is False
    assert repo.recovery_for("customer", "p-clerk") == ()


def test_recovery_kept_when_a_factor_is_active(m):
    enrolled(m)
    assert m.factors.clear_recovery_if_no_active("customer", "p-clerk") is False
    assert len(m.factors.recovery_for("customer", "p-clerk")) == 10


# -- M4: staff bootstrap -----------------------------------------------------
def test_bootstrap_ticket_expires(m):
    m.w.repo.put_staff(StaffIdentity("s-9", "S", mfa_enrolled=False))
    t = m.bootstrap.issue("s-9")
    m.w.clock.advance(m.svc.cfg.bootstrap_ttl)
    assert code(lambda: m.svc.begin_staff_bootstrap("s-9", t)) == "IDN-060"


def test_bootstrap_uniform_error(m):
    m.w.repo.put_staff(StaffIdentity("s-off", "S", active=False))
    t_unknown = m.bootstrap.issue("s-none")
    t_off = m.bootstrap.issue("s-off")
    assert code(lambda: m.svc.begin_staff_bootstrap("s-none", t_unknown)) == "IDN-060"
    assert code(lambda: m.svc.begin_staff_bootstrap("s-off", t_off)) == "IDN-060"
    m.w.repo.put_staff(StaffIdentity("s-9", "S", mfa_enrolled=False))
    s = m.svc.begin_staff_bootstrap("s-9", m.bootstrap.issue("s-9"))
    m.svc.confirm_totp_enrolment(Realm.STAFF, "s-9", s.factor_id, m.code(s.factor_id))
    assert code(lambda: m.svc.begin_staff_bootstrap("s-9", m.bootstrap.issue("s-9"))) == "IDN-060"


def test_bootstrap_attempts_are_limited(m):
    m.w.repo.put_staff(StaffIdentity("s-9", "S", mfa_enrolled=False))
    for _ in range(5):
        assert code(lambda: m.svc.begin_staff_bootstrap("s-9", "guess")) == "IDN-060"
    assert code(lambda: m.svc.begin_staff_bootstrap("s-9", m.bootstrap.issue("s-9"))) == "IDN-061"


# -- M5: factor changes end sessions ----------------------------------------------
def test_refresh_after_factor_removal_is_refused(m):
    fid, _, pw = enrolled(m)
    pair = m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, m.code(fid), tenant_id="t-a")
    m.svc.remove_factor(m.w.claims("p-clerk"), fid)
    assert code(lambda: m.w.idn.refresh(pair.refresh_token, "t-a")) in {"IDN-009", "IDN-020"}
    assert code(lambda: m.w.idn.verify_customer_token(pair.access_token, "t-a")) == "IDN-009"


def test_first_factor_ends_pre_mfa_sessions_in_every_tenant(m):
    old_a = m.w.login("p-acct", "t-a")
    old_b = m.w.login("p-acct", "t-b")
    enrol_mfa_person(m, "p-acct")
    for pair, t in ((old_a, "t-a"), (old_b, "t-b")):
        assert code(lambda: m.w.idn.verify_customer_token(pair.access_token, t)) == "IDN-009"
        assert code(lambda: m.w.idn.refresh(pair.refresh_token, t)) in {"IDN-009", "IDN-020"}


def test_staff_factor_removal_ends_staff_sessions(m):
    m.w.repo.put_staff(StaffIdentity("s-9", "S", mfa_enrolled=False))
    s = m.svc.begin_staff_bootstrap("s-9", m.bootstrap.issue("s-9"))
    m.svc.confirm_totp_enrolment(Realm.STAFF, "s-9", s.factor_id, m.code(s.factor_id))
    m.w.clock.advance(totp.PERIOD)
    c = m.w.staff_claims("s-9")
    s2 = m.svc.begin_totp_enrolment(c)
    m.svc.confirm_totp_enrolment(Realm.STAFF, "s-9", s2.factor_id, m.code(s2.factor_id), claims=c)
    m.w.clock.advance(totp.PERIOD)
    c = m.w.staff_claims("s-9")
    token = m.w.idn.issue_staff_token("s-9", mfa_satisfied=True, auth_time=m.w.clock()).access_token
    m.svc.remove_factor(c, s.factor_id)
    assert code(lambda: m.w.idn.verify_staff_token(token)) == "IDN-009"
    assert m.w.repo.get_staff("s-9").mfa_enrolled is True


# -- LOWs --------------------------------------------------------------------------
def test_sealed_secret_bound_to_subject_and_factor(m):
    fa, _, pw = enrolled(m)
    fb = enrol_mfa_person(m, "p-acct")
    m.w.clock.advance(totp.PERIOD)
    other = m.factors.get_factor(fb).sealed_secret
    m.factors.put_factor(replace(m.factors.get_factor(fa), sealed_secret=other))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "123456", tenant_id="t-a")) == "IDN-064"


def test_factor_stores_algorithm_digits_and_period(m):
    fid, _, pw = enrolled(m)
    f = m.factors.get_factor(fid)
    assert (f.algorithm, f.digits, f.period) == ("SHA1", 6, 30)
    m.factors.put_factor(replace(f, algorithm="SHA256", digits=8))
    c = totp.hotp(m.key(fid), totp.counter_at(m.w.clock()), 8, "SHA256")
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")
    m.factors.put_factor(replace(m.factors.get_factor(fid), algorithm="MD5"))
    m.w.clock.advance(totp.PERIOD)
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, "12345678", tenant_id="t-a")) == "IDN-064"


def test_repo_errors_become_idn_064(m):
    m.w.repo.put_staff(StaffIdentity("s-9", "S", mfa_enrolled=False))
    t = m.bootstrap.issue("s-9")
    m.w.repo.get_staff = lambda *_: 1 / 0
    assert code(lambda: m.svc.begin_staff_bootstrap("s-9", t)) == "IDN-064"


def test_invalid_subject_not_written_to_audit(m):
    junk = "x" * 5000
    code(lambda: m.svc.sign_in(Realm.CUSTOMER, junk, "pw", None, tenant_id="t-a"))
    assert junk not in repr(m.w.audit.events())


def test_factor_not_consumed_before_membership_check(m):
    fid, _, pw = enrolled(m)
    c = m.code(fid)
    mem = m.w.repo.get_membership("p-clerk", "t-a")
    m.w.repo.put_membership(replace(mem, status=MembershipStatus.SUSPENDED))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")) == "IDN-009"
    m.w.repo.put_membership(mem)
    m.svc.sign_in(Realm.CUSTOMER, "p-clerk", pw, c, tenant_id="t-a")  # same code still unused


def test_membership_state_hidden_until_password_proven(m):
    fid, _, pw = enrolled(m)
    mem = m.w.repo.get_membership("p-clerk", "t-a")
    m.w.repo.put_membership(replace(mem, status=MembershipStatus.SUSPENDED))
    assert code(lambda: m.svc.sign_in(Realm.CUSTOMER, "p-clerk", "nope", m.code(fid), tenant_id="t-a")) == "IDN-060"
    assert mfa_service.UNKNOWN_SOURCE == "unknown"
