"""Regression tests for the PR 156 security review (HIGH-1, HIGH-2, MEDIUM-3,
MEDIUM-5, MEDIUM-8). Each was written failing before the fix."""

from dataclasses import replace

import pytest

from identity import Channel, IdentityError, InMemoryRepository, TenantStatus
from identity.policy import INVITE_PERMISSION
from identity.service import secret_hash

NEW = Channel("email", "new@example.test")
SCOPE = frozenset({"read:invoices"})


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def readmit(w, pid="p-clerk", addr="clerk@example.test"):
    w.resolver.permissions[("t-a", "p-owner")] = frozenset({INVITE_PERMISSION})
    secret = w.invites.create(w.claims("p-owner"), "t-a", Channel("email", addr))
    return w.invites.accept(secret, pid)


# -- HIGH-1: a re-added member must not revive old sessions ---------------
def test_readded_member_old_tokens_stay_dead(w):
    old = w.login("p-clerk", mfa=False)
    w.idn.remove_membership("p-clerk", "t-a")
    m = readmit(w)
    assert m.session_version > 1
    assert code(lambda: w.idn.verify_customer_token(old.access_token, "t-a")) == "IDN-009"
    assert code(lambda: w.idn.refresh(old.refresh_token, "t-a")) in ("IDN-020", "IDN-009")
    # a fresh sign-in after re-admission works
    w.idn.verify_customer_token(w.login("p-clerk", mfa=False).access_token, "t-a")


def test_readd_continues_after_bumps(w):
    old = w.login("p-clerk", mfa=False)
    for _ in range(3):
        w.idn.revoke_sessions("p-clerk", "t-a", "logout")
    w.idn.remove_membership("p-clerk", "t-a")
    assert readmit(w).session_version == 5
    assert code(lambda: w.idn.verify_customer_token(old.access_token, "t-a")) == "IDN-009"


def test_remove_revokes_refresh_families(w):
    pair = w.login("p-clerk", mfa=False)
    w.idn.remove_membership("p-clerk", "t-a")
    rec = w.repo.get_refresh(secret_hash(pair.refresh_token))
    assert w.repo.is_family_revoked(rec.family_id)


# -- HIGH-2: revoke is a family tombstone that a racing rotation cannot beat --
class RacingRepo(InMemoryRepository):
    """Reuse detection revokes the family right after this rotation passed
    mark_refresh_used, as a concurrent replay would."""

    def mark_refresh_used(self, token_hash):
        ok = super().mark_refresh_used(token_hash)
        if ok:
            self.revoke_family(self.get_refresh(token_hash).family_id)
        return ok


def test_rotation_racing_reuse_detection_mints_nothing(w):
    racing = RacingRepo()
    racing.__dict__.update({k: v for k, v in w.repo.__dict__.items()})
    w.idn.repo = racing
    pair = w.login("p-clerk", mfa=False)
    before = set(racing._refresh)
    assert code(lambda: w.idn.refresh(pair.refresh_token, "t-a")) == "IDN-021"
    assert set(racing._refresh) == before  # no live record in the revoked family


def test_put_refresh_refused_in_revoked_family(w):
    pair = w.login("p-clerk", mfa=False)
    rec = w.repo.get_refresh(secret_hash(pair.refresh_token))
    w.repo.revoke_family(rec.family_id)
    assert w.repo.put_refresh(replace(rec, token_hash="x" * 64, used=False)) is False
    assert w.repo.get_refresh("x" * 64) is None


# -- MEDIUM-3: invite permission comes from the resolver for the inviter ----
def test_invite_permission_from_resolver(w):
    owner = w.claims("p-owner")
    del w.resolver.permissions[("t-a", "p-owner")]  # owner role alone is not the permission
    assert code(lambda: w.invites.create(owner, "t-a", NEW)) == "IDN-030"
    w.resolver.permissions[("t-a", "p-owner")] = frozenset({INVITE_PERMISSION})
    w.invites.create(owner, "t-a", NEW)
    clerk = w.claims("p-clerk", mfa=False)
    assert code(lambda: w.invites.create(clerk, "t-a", NEW)) == "IDN-030"


def test_invite_permission_resolver_failure_denies(w):
    owner = w.claims("p-owner")
    for bad in (RuntimeError("down"), {INVITE_PERMISSION}, [INVITE_PERMISSION], None,
                frozenset({1})):
        w.resolver.permissions[("t-a", "p-owner")] = bad
        assert code(lambda: w.invites.create(owner, "t-a", NEW)) == "IDN-012"


def test_invite_create_takes_no_caller_permissions(w):
    clerk = w.claims("p-clerk", mfa=False)
    with pytest.raises(TypeError):
        w.invites.create(clerk, "t-a", caller_permissions=frozenset({INVITE_PERMISSION}),
                         channel=NEW)
    # a permission set in the channel slot is just a bad channel
    assert code(lambda: w.invites.create(clerk, "t-a", frozenset({INVITE_PERMISSION}))) \
        == "IDN-030"


# -- MEDIUM-5: staff side re-checks the staff identity and tenant ----------
def _approved(w):
    gid = w.support.request(w.staff_claims(), "t-a", "Ticket 7", SCOPE, 3600)
    w.support.approve(w.claims("p-owner"), gid)
    return gid


def test_check_access_after_staff_sessions_revoked(w):
    gid = _approved(w)
    staff = w.staff_claims()
    w.idn.revoke_staff_sessions("s-1")
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-009"
    assert code(lambda: w.support.request(staff, "t-a", "x", SCOPE, 60)) == "IDN-009"


def test_check_access_after_staff_deactivated(w):
    gid = _approved(w)
    staff = w.staff_claims()
    w.repo.put_staff(replace(w.repo.get_staff("s-1"), active=False))
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-010"
    assert code(lambda: w.support.request(staff, "t-a", "x", SCOPE, 60)) == "IDN-010"


def test_check_access_tenant_not_open(w):
    gid = _approved(w)
    staff = w.staff_claims()
    w.idn.suspend_tenant("t-a")
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-011"
    assert code(lambda: w.support.request(staff, "t-a", "x", SCOPE, 60)) == "IDN-011"
    w.repo.put_tenant(replace(w.repo.get_tenant("t-b"), status=TenantStatus.DELETED))
    assert code(lambda: w.support.request(staff, "t-b", "x", SCOPE, 60)) == "IDN-011"


# -- MEDIUM-8: tenant-wide MFA changes need a fresh step-up ----------------
def test_mfa_for_all_needs_fresh_step_up(w):
    w.idn.set_tenant_mfa_for_all(w.claims("p-owner"), "t-a", True)
    stale = w.claims("p-owner")
    w.clock.advance(301)
    assert code(lambda: w.idn.set_tenant_mfa_for_all(stale, "t-a", False)) == "IDN-013"
    assert code(lambda: w.idn.set_tenant_mfa_for_all(stale, "t-a", True)) == "IDN-013"
    assert w.repo.get_tenant("t-a").mfa_for_all is True


def test_mfa_for_all_refresh_keeps_old_auth_time(w):
    pair = w.login("p-owner")
    w.clock.advance(3600)
    fresh_token = w.idn.refresh(pair.refresh_token, "t-a")  # mfa claim, old auth_time
    claims = w.idn.verify_customer_token(fresh_token.access_token, "t-a")
    assert code(lambda: w.idn.set_tenant_mfa_for_all(claims, "t-a", False)) == "IDN-013"
