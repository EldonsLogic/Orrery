import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # services/control-plane

from identity import (AuditLog, Channel, IdentityService, InMemoryRepository,  # noqa: E402
                      InviteService, Membership, Person, Realm, RealmConfig, RoleInfo,
                      StaffIdentity, SupportGrantService, TenantState,
                      TestOnlyHmacSha256Signer)

T0 = 1_900_000_000
OWNER = RoleInfo("owner", is_admin=True, functions=frozenset({"owner"}))
SALES = RoleInfo("sales", functions=frozenset({"sales"}))
FINANCE = RoleInfo("finance", functions=frozenset({"finance"}))
ADMIN = RoleInfo("it_admin", is_admin=True)


class FakeClock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class DictResolver:
    """Stands in for the tenant's assignment store."""

    def __init__(self):
        self.roles = {}

    def roles_for(self, tenant_id, person_id):
        value = self.roles.get((tenant_id, person_id), ())
        if isinstance(value, Exception):
            raise value
        return value


def email(addr):
    return Channel("email", addr)


class World:
    def __init__(self):
        self.clock = FakeClock()
        self.repo = InMemoryRepository()
        self.audit = AuditLog()
        self.resolver = DictResolver()
        self.customer_cfg = RealmConfig(Realm.CUSTOMER, "https://id.example.test",
                                        "platform-app",
                                        TestOnlyHmacSha256Signer(b"c" * 32, "cust-1"))
        self.staff_cfg = RealmConfig(Realm.STAFF, "https://staff-id.example.test",
                                     "platform-staff",
                                     TestOnlyHmacSha256Signer(b"s" * 32, "staff-1"))
        self.idn = IdentityService(repo=self.repo, customer=self.customer_cfg,
                                   staff=self.staff_cfg, roles=self.resolver,
                                   audit=self.audit, clock=self.clock)
        self.invites = InviteService(self.idn)
        self.support = SupportGrantService(self.idn)
        for t in ("t-a", "t-b"):
            self.repo.put_tenant(TenantState(t))
        self.add_person("p-owner", "owner@example.test", mfa=True)
        self.add_person("p-clerk", "clerk@example.test", mfa=False)
        self.add_person("p-acct", "acct@example.test", mfa=True)
        self.add_person("p-new", "new@example.test", mfa=False, member_of=())
        self.resolver.roles[("t-a", "p-owner")] = (OWNER,)
        self.resolver.roles[("t-a", "p-clerk")] = (SALES,)
        self.resolver.roles[("t-a", "p-acct")] = (FINANCE,)
        self.resolver.roles[("t-b", "p-acct")] = (FINANCE,)
        self.repo.put_staff(StaffIdentity("s-1", "Support One", mfa_enrolled=True,
                                          verified_channels=frozenset({email("s1@example.test")})))

    def add_person(self, pid, addr, mfa, member_of=("t-a",)):
        self.repo.put_person(Person(pid, pid, frozenset({email(addr)}), mfa_enrolled=mfa))
        for t in member_of:
            self.repo.put_membership(Membership(pid, t))
        if pid == "p-acct":
            self.repo.put_membership(Membership(pid, "t-b"))

    def login(self, pid, tenant="t-a", mfa=True):
        return self.idn.issue_customer_token(pid, tenant, mfa_satisfied=mfa,
                                             auth_time=self.clock())

    def claims(self, pid, tenant="t-a", mfa=True):
        return self.idn.verify_customer_token(self.login(pid, tenant, mfa).access_token, tenant)

    def staff_claims(self, sid="s-1"):
        token = self.idn.issue_staff_token(sid, mfa_satisfied=True, auth_time=self.clock())
        return self.idn.verify_staff_token(token.access_token)


@pytest.fixture
def w():
    return World()
