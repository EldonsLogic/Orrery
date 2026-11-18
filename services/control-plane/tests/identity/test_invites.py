import pytest

from identity import Channel, IdentityError
NEW = Channel("email", "New@Example.test")


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def test_invite_accept_creates_membership(w):
    owner = w.claims("p-owner")
    secret = w.invites.create(owner, "t-a", NEW)
    m = w.invites.accept(secret, "p-new")
    assert (m.tenant_id, m.invited_by) == ("t-a", "p-owner")
    w.resolver.roles[("t-a", "p-new")] = ()
    w.login("p-new", mfa=False)


def test_replayed_invite_rejected(w):
    secret = w.invites.create(w.claims("p-owner"), "t-a", NEW)
    w.invites.accept(secret, "p-new")
    w.repo.delete_membership("p-new", "t-a")
    assert code(lambda: w.invites.accept(secret, "p-new")) == "IDN-031"


def test_missing_invite_permission(w):
    clerk = w.claims("p-clerk", mfa=False)
    assert code(lambda: w.invites.create(clerk, "t-a", NEW)) == "IDN-030"
    w.resolver.permissions[("t-a", "p-clerk")] = frozenset({"other.permission"})
    assert code(lambda: w.invites.create(clerk, "t-a", NEW)) == "IDN-030"


def test_invite_for_other_tenant_denied(w):
    owner = w.claims("p-owner")
    assert code(lambda: w.invites.create(owner, "t-b", NEW)) == "IDN-006"


def test_invite_expires(w):
    secret = w.invites.create(w.claims("p-owner"), "t-a", NEW, ttl=3600)
    w.clock.advance(3600)
    assert code(lambda: w.invites.accept(secret, "p-new")) == "IDN-032"


def test_invite_bound_to_verified_channel(w):
    secret = w.invites.create(w.claims("p-owner"), "t-a", NEW)
    assert code(lambda: w.invites.accept(secret, "p-clerk")) == "IDN-033"
    w.invites.accept(secret, "p-new")  # still usable by the right person


def test_invite_bad_requests(w):
    owner = w.claims("p-owner")
    for ch, ttl in ((Channel("fax", "1"), 60), (Channel("email", " "), 60), (NEW, 0),
                    (NEW, 30 * 24 * 3600), ("new@example.test", 60), (NEW, True)):
        assert code(lambda: w.invites.create(owner, "t-a", ch, ttl)) == "IDN-034"
    assert code(lambda: w.invites.accept("nope", "p-new")) == "IDN-031"
    assert code(lambda: w.invites.accept(None, "p-new")) == "IDN-031"


def test_existing_member_cannot_reuse_invite(w):
    w.repo.put_person(w.repo.get_person("p-clerk").__class__(
        "p-clerk", "p-clerk", frozenset({Channel("email", "new@example.test")})))
    secret = w.invites.create(w.claims("p-owner"), "t-a", NEW)
    assert code(lambda: w.invites.accept(secret, "p-clerk")) == "IDN-034"


def test_revoked_caller_cannot_invite(w):
    owner = w.claims("p-owner")
    w.idn.revoke_sessions("p-owner", "t-a", "compromise")
    assert code(lambda: w.invites.create(owner, "t-a", NEW)) == "IDN-009"


def test_secret_and_address_not_in_audit(w):
    secret = w.invites.create(w.claims("p-owner"), "t-a", NEW)
    text = repr(w.audit.events())
    assert secret not in text and "example.test" not in text.lower().replace(
        "https://id.example.test", "")
