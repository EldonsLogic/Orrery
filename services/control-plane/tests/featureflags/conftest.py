import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # services/control-plane

from featureflags import (EvalContext, FlagAdmin, FlagDef, FlagEvaluator,  # noqa: E402
                          InMemoryFlagStore, Registry)
from identity import (AuditLog, Channel, IdentityService, InMemoryRepository,  # noqa: E402
                      Membership, Person, Realm, RealmConfig, StaffIdentity, TenantState,
                      TestOnlyHmacSha256Signer)

T0 = 1_900_000_000
DEFS = [
    FlagDef("ui.new_viewer", "rollout"),
    FlagDef("ui.dark_default", "rollout", default=True),
    FlagDef("ui.user_beta", "rollout", percent_by="user"),
    FlagDef("agents.draft_inbox", "agent_authority"),
    FlagDef("pay.run_batching", "money"),
    FlagDef("tax.new_pack_path", "compliance"),
]


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class Resolver:
    def roles_for(self, tenant_id, person_id):
        return ()

    def permissions_for(self, tenant_id, person_id):
        return frozenset()


class World:
    def __init__(self):
        self.clock = Clock()
        self.repo = InMemoryRepository()
        self.idn = IdentityService(
            repo=self.repo, roles=Resolver(), audit=AuditLog(), clock=self.clock,
            customer=RealmConfig(Realm.CUSTOMER, "https://id.example.test", "platform-app",
                                 TestOnlyHmacSha256Signer(b"c" * 32, "c1")),
            staff=RealmConfig(Realm.STAFF, "https://staff-id.example.test", "platform-staff",
                              TestOnlyHmacSha256Signer(b"s" * 32, "s1")))
        for t in ("t-a", "t-b"):
            self.repo.put_tenant(TenantState(t))
        for p in ("u-1", "u-2"):
            self.repo.put_person(Person(p, p, frozenset({Channel("email", f"{p}@example.test")})))
            self.repo.put_membership(Membership(p, "t-a"))
        self.repo.put_person(Person("u-b", "u-b", frozenset({Channel("email", "b@example.test")})))
        self.repo.put_membership(Membership("u-b", "t-b"))
        for s in ("s-1", "s-2"):
            self.repo.put_staff(StaffIdentity(s, s, mfa_enrolled=True))
        self.registry = Registry(DEFS)
        self.store = InMemoryFlagStore()
        self.admin = FlagAdmin(self.idn, self.registry, self.store, self.clock)
        self.ev = FlagEvaluator(self.registry, self.store, self.clock)

    def staff(self, sid="s-1", mfa=True, auth_time=None):
        tok = self.idn.issue_staff_token(sid, mfa_satisfied=mfa,
                                         auth_time=self.clock() if auth_time is None else auth_time)
        return self.idn.verify_staff_token(tok.access_token) if mfa else tok

    def customer(self, pid="u-1", tenant="t-a"):
        tok = self.idn.issue_customer_token(pid, tenant, mfa_satisfied=True, auth_time=self.clock())
        return self.idn.verify_customer_token(tok.access_token, tenant)

    def ctx(self, pid="u-1", tenant="t-a"):
        return EvalContext.from_claims(self.customer(pid, tenant), self.clock())


@pytest.fixture
def w():
    return World()
