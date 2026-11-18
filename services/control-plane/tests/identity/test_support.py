import pytest

from identity import Channel, GrantStatus, IdentityError, Person, RoleInfo

SCOPE = frozenset({"read:invoices"})


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def request(w, duration=3600):
    return w.support.request(w.staff_claims(), "t-a", "Customer ticket 12", SCOPE, duration)


def test_grant_lifecycle(w):
    gid = request(w)
    staff = w.staff_claims()
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-042"
    g = w.support.approve(w.claims("p-owner"), gid)
    assert g.status is GrantStatus.APPROVED and g.approved_by == "p-owner"
    w.support.check_access(staff, gid, "t-a", "read:invoices")
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "write:invoices")) == "IDN-044"
    assert code(lambda: w.support.check_access(staff, gid, "t-b", "read:invoices")) == "IDN-042"
    w.clock.advance(3600)
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-004"
    staff = w.staff_claims()  # the old token is dead; a fresh one meets the expired grant
    assert code(lambda: w.support.check_access(staff, gid, "t-a", "read:invoices")) == "IDN-042"
    tenant_view = w.audit.for_tenant("t-a")
    assert any(e.action == "support.granted" for e in tenant_view)
    assert any(e.action == "support.access" and e.decision == "deny" for e in tenant_view)


def test_staff_self_approval_denied(w):
    gid = request(w)
    # the staff member's own token is never an approver
    assert code(lambda: w.support.approve(w.staff_claims(), gid)) == "IDN-041"
    # nor a customer account of the same human (linked id or shared verified channel)
    w.repo.put_person(Person("p-s1", "s1", frozenset({Channel("email", "s1@example.test")}),
                             mfa_enrolled=True))
    w.repo.put_membership(w.repo.get_membership("p-owner", "t-a").__class__("p-s1", "t-a"))
    w.resolver.roles[("t-a", "p-s1")] = (RoleInfo("owner", True, frozenset({"owner"})),)
    assert code(lambda: w.support.approve(w.claims("p-s1"), gid)) == "IDN-041"


def test_approver_must_be_owner_or_admin(w):
    gid = request(w)
    assert code(lambda: w.support.approve(w.claims("p-clerk", mfa=False), gid)) == "IDN-040"
    assert code(lambda: w.support.approve(w.claims("p-acct", "t-a"), gid)) == "IDN-040"


def test_approver_of_other_tenant_denied(w):
    gid = request(w)
    w.resolver.roles[("t-b", "p-acct")] = (RoleInfo("adm", True),)
    assert code(lambda: w.support.approve(w.claims("p-acct", "t-b"), gid)) == "IDN-006"


def test_approval_needs_fresh_step_up(w):
    gid = request(w)
    owner = w.claims("p-owner")
    w.clock.advance(301)
    assert code(lambda: w.support.approve(owner, gid)) == "IDN-013"


def test_grant_requests_validated(w):
    s = w.staff_claims()
    for reason, scope, dur in (("", SCOPE, 60), ("x", frozenset(), 60), ("x", SCOPE, 0),
                               ("x", SCOPE, 5 * 3600), ("x", {"a"}, 60), ("x" * 501, SCOPE, 60)):
        assert code(lambda: w.support.request(s, "t-a", reason, scope, dur)) == "IDN-043"
    assert code(lambda: w.support.request(w.claims("p-owner"), "t-a", "x", SCOPE, 60)) == "IDN-006"


def test_no_access_without_grant_or_for_other_staff(w):
    from identity import StaffIdentity
    w.repo.put_staff(StaffIdentity("s-2", "Two", mfa_enrolled=True))
    gid = request(w)
    w.support.approve(w.claims("p-owner"), gid)
    assert code(lambda: w.support.check_access(w.staff_claims("s-2"), gid, "t-a",
                                               "read:invoices")) == "IDN-042"
    assert code(lambda: w.support.check_access(w.staff_claims(), "missing", "t-a",
                                               "read:invoices")) == "IDN-042"


def test_revoke_and_double_approve(w):
    gid = request(w)
    owner = w.claims("p-owner")
    w.support.approve(owner, gid)
    assert code(lambda: w.support.approve(owner, gid)) == "IDN-042"
    assert code(lambda: w.support.revoke(w.claims("p-clerk", mfa=False), gid)) == "IDN-040"
    w.support.revoke(owner, gid)
    assert code(lambda: w.support.check_access(w.staff_claims(), gid, "t-a",
                                               "read:invoices")) == "IDN-042"
