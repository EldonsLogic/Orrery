"""PLT-005 hardening: Q-152 (claims only from verification), Q-153 (atomic grant
transitions), Q-154 (pending grant expiry), Q-155 lows."""
import copy
import dataclasses

import pytest

from identity import (AccessClaims, GrantStatus, IdentityError, InMemoryRepository,
                      Realm, VerifiedClaims)
from identity.tokens import AccessClaims as TokenClaims

SCOPE = frozenset({"read:invoices"})


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def request(w, duration=3600):
    return w.support.request(w.staff_claims(), "t-a", "Customer ticket 12", SCOPE, duration)


def forged(c, **changes):
    """Build claims the way a caller might, bypassing verification."""
    obj = object.__new__(AccessClaims)
    for f in dataclasses.fields(c):
        object.__setattr__(obj, f.name, changes.get(f.name, getattr(c, f.name)))
    return obj


# -- Q-152 ---------------------------------------------------------------
def test_verified_claims_alias():
    assert VerifiedClaims is AccessClaims is TokenClaims


def test_claims_cannot_be_constructed_by_callers(w):
    c = w.claims("p-owner")
    args = [getattr(c, f.name) for f in dataclasses.fields(c)]
    assert code(lambda: AccessClaims(*args)) == "IDN-006"
    assert code(lambda: dataclasses.replace(c, subject="p-clerk")) == "IDN-006"
    assert code(lambda: copy.copy(c)) == "IDN-006"
    assert code(lambda: copy.deepcopy(c)) == "IDN-006"


def test_kept_claims_stop_working_after_expiry(w):
    owner = w.claims("p-owner")
    w.support.request(w.staff_claims(), "t-a", "x", SCOPE, 60)
    w.clock.advance(w.customer_cfg.access_ttl + 1)
    assert code(lambda: w.idn.caller_roles(owner, "t-a")) == "IDN-004"
    assert code(lambda: w.invites.create(owner, "t-a", __import__("identity").Channel(
        "email", "x@example.test"))) == "IDN-004"


def test_kept_staff_claims_stop_working_after_expiry(w):
    staff = w.staff_claims()
    w.clock.advance(w.staff_cfg.access_ttl + 1)
    assert code(lambda: w.support.request(staff, "t-a", "x", SCOPE, 60)) == "IDN-004"


def test_forged_claims_refused(w):
    owner = w.claims("p-owner")
    assert code(lambda: w.idn.caller_roles(forged(owner), "t-a")) == "IDN-006"
    staff = w.staff_claims()
    assert code(lambda: w.support.request(forged(staff), "t-a", "x", SCOPE, 60)) == "IDN-006"


def test_verify_allow_audit_records_subject(w):
    w.claims("p-owner")
    allows = [e for e in w.audit.events() if e.action == "token.verify" and e.decision == "allow"]
    assert allows and allows[-1].subject == "p-owner"


# -- Q-153 ---------------------------------------------------------------
class RacingRepo(InMemoryRepository):
    """Runs `hook` once, right after the first get_grant, to interleave a rival."""

    def __init__(self):
        super().__init__()
        self.hook = None

    def get_grant(self, grant_id):
        grant = super().get_grant(grant_id)
        hook, self.hook = self.hook, None
        if hook:
            hook()
        return grant


def test_transition_grant_is_compare_and_set(w):
    gid = request(w)
    g = w.repo.get_grant(gid)
    revoked = dataclasses.replace(g, status=GrantStatus.REVOKED)
    assert w.repo.transition_grant(gid, frozenset({GrantStatus.PENDING}), revoked) is True
    again = dataclasses.replace(g, status=GrantStatus.APPROVED)
    assert w.repo.transition_grant(gid, frozenset({GrantStatus.PENDING}), again) is False
    assert w.repo.get_grant(gid).status is GrantStatus.REVOKED
    assert w.repo.transition_grant("nope", frozenset({GrantStatus.PENDING}), g) is False


def _racing(w):
    from identity import (AuditLog, IdentityService, SupportGrantService)
    repo = RacingRepo()
    for name in ("_persons", "_staff", "_tenants", "_members"):
        getattr(repo, name).update(getattr(w.repo, name))
    idn = IdentityService(repo=repo, customer=w.customer_cfg, staff=w.staff_cfg,
                          roles=w.resolver, audit=AuditLog(), clock=w.clock)
    return repo, SupportGrantService(idn)


def test_revoke_racing_approve_stays_revoked(w):
    repo, support = _racing(w)
    gid = support.request(w.staff_claims(), "t-a", "x", SCOPE, 3600)
    owner = w.claims("p-owner")
    repo.hook = lambda: support.revoke(owner, gid)  # revoke lands between get and write
    assert code(lambda: support.approve(owner, gid)) == "IDN-042"
    assert repo.get_grant(gid).status is GrantStatus.REVOKED


def test_second_approval_cannot_extend_expiry(w):
    repo, support = _racing(w)
    gid = support.request(w.staff_claims(), "t-a", "x", SCOPE, 3600)
    owner = w.claims("p-owner")
    first = {}

    def rival():
        first["g"] = support.approve(owner, gid)
        w.clock.advance(100)

    repo.hook = rival
    assert code(lambda: support.approve(owner, gid)) == "IDN-042"
    assert repo.get_grant(gid).expires_at == first["g"].expires_at


def test_approve_racing_revoke_of_approved_wins_revoke(w):
    repo, support = _racing(w)
    gid = support.request(w.staff_claims(), "t-a", "x", SCOPE, 3600)
    owner = w.claims("p-owner")
    support.approve(owner, gid)
    # revoke reads APPROVED, a rival revoke lands first: second revoke is refused
    repo.hook = lambda: support.revoke(owner, gid)
    assert code(lambda: support.revoke(owner, gid)) == "IDN-042"
    assert repo.get_grant(gid).status is GrantStatus.REVOKED


# -- Q-154 ---------------------------------------------------------------
def test_pending_grant_expires_on_approve(w):
    from identity.support import PENDING_TTL
    gid = request(w)
    owner = w.claims("p-owner")
    w.clock.advance(PENDING_TTL - 1)
    owner = w.claims("p-owner")
    w.support.approve(owner, gid)  # still inside the window
    gid2 = request(w)
    w.clock.advance(PENDING_TTL)
    owner = w.claims("p-owner")
    assert code(lambda: w.support.approve(owner, gid2)) == "IDN-042"
    assert w.repo.get_grant(gid2).status is GrantStatus.PENDING


def test_use_fails_closed_if_approved_after_pending_window(w):
    from identity.support import PENDING_TTL
    gid = request(w)
    g = w.repo.get_grant(gid)
    now = w.clock()
    w.repo.put_grant(dataclasses.replace(
        g, status=GrantStatus.APPROVED, approved_by="p-owner",
        approved_at=g.requested_at + PENDING_TTL + 1, expires_at=now + 3600))
    assert code(lambda: w.support.check_access(w.staff_claims(), gid, "t-a",
                                               "read:invoices")) == "IDN-042"


def test_pending_requests_capped_per_staff_and_tenant(w):
    from identity.support import MAX_PENDING
    for _ in range(MAX_PENDING):
        request(w)
    assert code(lambda: request(w)) == "IDN-043"
    w.clock.advance(25 * 3600)  # expired pendings no longer count
    request(w)


# -- Q-155 ---------------------------------------------------------------
def test_revoke_with_old_auth_time_denied(w):
    gid = request(w)
    owner_pair = w.idn.issue_customer_token("p-owner", "t-a", mfa_satisfied=True,
                                            auth_time=w.clock())
    w.clock.advance(301)
    refreshed = w.idn.refresh(owner_pair.refresh_token, "t-a")  # keeps the old auth_time
    owner = w.idn.verify_customer_token(refreshed.access_token, "t-a")
    assert code(lambda: w.support.revoke(owner, gid)) == "IDN-013"


def test_audit_detail_is_bounded(w):
    ev = w.audit.record(at=1, action="a", decision="allow", code="OK", realm="customer",
                        subject=None, tenant=None, detail="x" * 5000)
    assert len(ev.detail) <= 200
