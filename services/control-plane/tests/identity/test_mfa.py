import pytest

from identity import IdentityError, RoleInfo

ADMIN = RoleInfo("it_admin", is_admin=True)
ACCOUNTING = RoleInfo("accounting", functions=frozenset({"accounting"}))
SALES = RoleInfo("sales", functions=frozenset({"sales"}))


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def test_mfa_not_satisfied_for_admin_role(w):
    assert code(lambda: w.login("p-owner", mfa=False)) == "IDN-013"
    w.login("p-owner", mfa=True)


def test_mfa_required_for_finance_and_accounting(w):
    assert code(lambda: w.login("p-acct", "t-b", mfa=False)) == "IDN-013"
    w.resolver.roles[("t-a", "p-clerk")] = (ACCOUNTING,)
    assert code(lambda: w.login("p-clerk", mfa=False)) == "IDN-013"


def test_mfa_claimed_but_not_enrolled_denied(w):
    w.resolver.roles[("t-a", "p-clerk")] = (ADMIN,)
    assert code(lambda: w.login("p-clerk", mfa=True)) == "IDN-013"


def test_mfa_optional_for_plain_roles(w):
    c = w.claims("p-clerk", mfa=False)
    assert c.mfa_satisfied is False


def test_mfa_truthy_non_bool_is_not_satisfied(w):
    assert code(lambda: w.login("p-owner", mfa=1)) == "IDN-013"


def test_role_grant_requires_enrolment(w):
    assert code(lambda: w.idn.check_role_grant("p-clerk", "t-a", ADMIN)) == "IDN-014"
    w.idn.check_role_grant("p-clerk", "t-a", SALES)  # plain role: fine
    assert code(lambda: w.idn.check_role_grant("p-clerk", "t-a", "it_admin")) == "IDN-012"


def test_role_grant_kills_non_mfa_sessions(w):
    pair = w.login("p-acct", "t-a")  # enrolled, but say a sales-only session
    w.resolver.roles[("t-a", "p-acct")] = (SALES,)
    weak = w.login("p-acct", "t-a", mfa=False)
    w.idn.check_role_grant("p-acct", "t-a", ADMIN)
    assert w.repo.get_membership("p-acct", "t-a").mfa_required is True
    for tok in (weak.access_token, pair.access_token):
        assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) == "IDN-009"
    assert code(lambda: w.login("p-acct", "t-a", mfa=False)) == "IDN-013"


def test_owner_may_require_mfa_for_all(w):
    clerk = w.login("p-clerk", mfa=False).access_token
    owner = w.claims("p-owner")
    w.idn.set_tenant_mfa_for_all(owner, "t-a", True)
    assert code(lambda: w.idn.verify_customer_token(clerk, "t-a")) == "IDN-009"
    assert code(lambda: w.login("p-clerk", mfa=False)) == "IDN-013"


def test_only_owner_sets_mfa_for_all(w):
    w.resolver.roles[("t-a", "p-acct")] = (ADMIN,)
    admin = w.claims("p-acct")
    assert code(lambda: w.idn.set_tenant_mfa_for_all(admin, "t-a", True)) == "IDN-015"
    owner_b = w.claims("p-owner")
    assert code(lambda: w.idn.set_tenant_mfa_for_all(owner_b, "t-b", True)) == "IDN-006"
