import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # services/control-plane

from featureflags import (AuditSealer, EvalContext, FlagAdmin, FlagDef,  # noqa: E402
                          FlagEvaluator, InMemoryAnchor, InMemoryFlagStore, Registry)
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


class Roles:
    def __init__(self):
        self.held = {("s-1", "platform_admin"), ("s-2", "platform_admin")}

    def has_role(self, staff_id, role):
        return (staff_id, role) in self.held


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
        for s in ("s-1", "s-2", "s-3"):
            self.repo.put_staff(StaffIdentity(s, s, mfa_enrolled=True))
        self.registry = Registry(DEFS)
        self.roles = Roles()
        self.anchor = InMemoryAnchor()
        self.store = InMemoryFlagStore(AuditSealer({"k1": b"k" * 32}, "k1"), self.anchor)
        self.admin = FlagAdmin(self.idn, self.registry, self.store,
                               restricted_role="platform_admin", staff_roles=self.roles)
        self.ev = FlagEvaluator(self.registry, self.store, self.clock)

    def staff(self, sid="s-1", mfa=True, auth_time=None):
        tok = self.idn.issue_staff_token(sid, mfa_satisfied=mfa,
                                         auth_time=self.clock() if auth_time is None else auth_time)
        return self.idn.verify_staff_token(tok.access_token) if mfa else tok

    def fresh(self, sid="s-1"):
        """A new sign-in (new step-up): the clock moves one second."""
        self.clock.advance(1)
        return self.staff(sid)

    def enable(self, key, **scope):
        """Two-person enable of a restricted flag (kind from the scope given)."""
        kind = "tenant" if "tenant_id" in scope and "user_id" not in scope else (
            "user" if "user_id" in scope else "global")
        p = self.admin.propose(self.fresh("s-1"), kind, "approved rollout", key=key, **scope)
        return self.admin.approve(self.fresh("s-2"), p.proposal_id)

    def customer(self, pid="u-1", tenant="t-a"):
        tok = self.idn.issue_customer_token(pid, tenant, mfa_satisfied=True, auth_time=self.clock())
        return self.idn.verify_customer_token(tok.access_token, tenant)

    def ctx(self, pid="u-1", tenant="t-a"):
        return EvalContext.from_claims(self.customer(pid, tenant), self.clock())


@pytest.fixture
def w():
    return World()
