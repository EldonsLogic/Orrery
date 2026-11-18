import pytest

from identity import IdentityError, TenantStatus


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


@pytest.mark.parametrize("revoke", ["compromise", "suspend", "remove", "tenant"])
def test_revocation_is_immediate(w, revoke):
    tok = w.login("p-clerk", mfa=False).access_token
    w.idn.verify_customer_token(tok, "t-a")
    if revoke == "compromise":
        w.idn.revoke_sessions("p-clerk", "t-a", "compromise")
    elif revoke == "suspend":
        w.idn.suspend_membership("p-clerk", "t-a")
    elif revoke == "remove":
        w.idn.remove_membership("p-clerk", "t-a")
    else:
        w.idn.suspend_tenant("t-a")
    expected = "IDN-011" if revoke == "tenant" else "IDN-009"
    assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) == expected
    if revoke == "compromise":  # a fresh sign-in gets the new session version
        w.idn.verify_customer_token(w.login("p-clerk", mfa=False).access_token, "t-a")
    else:
        assert code(lambda: w.login("p-clerk", mfa=False)) == expected


def test_revoke_reason_must_be_known(w):
    assert code(lambda: w.idn.revoke_sessions("p-clerk", "t-a", "owner@example.test")) == "IDN-034"


def test_non_member_and_unknown_person_denied(w):
    assert code(lambda: w.login("p-new")) == "IDN-009"
    assert code(lambda: w.login("p-ghost")) == "IDN-010"
    assert code(lambda: w.login("p-owner", tenant="t-missing")) == "IDN-011"


def test_suspended_tenant_blocks_issue(w):
    w.idn.suspend_tenant("t-a")
    assert w.repo.get_tenant("t-a").status is TenantStatus.SUSPENDED
    assert code(lambda: w.login("p-owner")) == "IDN-011"


def test_refresh_rotates(w):
    pair = w.login("p-clerk", mfa=False)
    nxt = w.idn.refresh(pair.refresh_token, "t-a")
    assert nxt.refresh_token != pair.refresh_token
    w.idn.verify_customer_token(nxt.access_token, "t-a")
    w.idn.refresh(nxt.refresh_token, "t-a")


def test_refresh_reuse_revokes_family(w):
    pair = w.login("p-clerk", mfa=False)
    second = w.idn.refresh(pair.refresh_token, "t-a")
    assert code(lambda: w.idn.refresh(pair.refresh_token, "t-a")) == "IDN-021"
    # the legitimate newer token in the same family is dead too
    assert code(lambda: w.idn.refresh(second.refresh_token, "t-a")) == "IDN-020"
    # an unrelated session survives
    other = w.login("p-clerk", mfa=False)
    w.idn.refresh(other.refresh_token, "t-a")


def test_refresh_denials(w):
    pair = w.login("p-acct", "t-a")
    assert code(lambda: w.idn.refresh(pair.refresh_token, "t-b")) == "IDN-020"
    assert code(lambda: w.idn.refresh("not-a-token", "t-a")) == "IDN-020"
    assert code(lambda: w.idn.refresh(None, "t-a")) == "IDN-020"
    w.clock.advance(13 * 3600)
    fresh = w.login("p-clerk", mfa=False)
    w.clock.advance(12 * 3600)
    assert code(lambda: w.idn.refresh(fresh.refresh_token, "t-a")) == "IDN-020"


def test_refresh_after_session_bump_denied(w):
    pair = w.login("p-clerk", mfa=False)
    w.idn.revoke_sessions("p-clerk", "t-a", "logout")
    assert code(lambda: w.idn.refresh(pair.refresh_token, "t-a")) == "IDN-009"


def test_role_resolver_unknown_result_denies(w):
    for bad in (None, "owner", {"owner": True}, ("owner",), RuntimeError("down"), 42):
        w.resolver.roles[("t-a", "p-clerk")] = bad
        assert code(lambda: w.login("p-clerk", mfa=False)) == "IDN-012"


def test_member_with_no_roles_may_enter(w):
    w.resolver.roles[("t-a", "p-clerk")] = ()
    w.login("p-clerk", mfa=False)


def test_staff_tokens(w):
    c = w.staff_claims()
    assert c.tenant is None and c.mfa_satisfied
    assert code(lambda: w.idn.issue_staff_token("s-1", mfa_satisfied=False,
                                                auth_time=w.clock())) == "IDN-013"
    tok = w.idn.issue_staff_token("s-1", mfa_satisfied=True, auth_time=w.clock()).access_token
    w.idn.revoke_staff_sessions("s-1")
    assert code(lambda: w.idn.verify_staff_token(tok)) == "IDN-009"
    assert code(lambda: w.idn.issue_staff_token("s-x", mfa_satisfied=True,
                                                auth_time=w.clock())) == "IDN-010"


def test_auth_time_in_future_denied(w):
    assert code(lambda: w.idn.issue_customer_token("p-owner", "t-a", mfa_satisfied=True,
                                                   auth_time=w.clock() + 10)) == "IDN-008"


def test_clock_failure_fails_closed(w):
    w.clock.t = "now"
    with pytest.raises(Exception):
        w.login("p-owner")
