import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # services/control-plane

from identity import (AuditLog, IdentityService, InMemoryRepository, Realm, RealmConfig,  # noqa: E402
                      StaffIdentity, TenantState, TestOnlyHmacSha256Signer)
from reviewqueue import ReviewError, ReviewQueue, content_digest  # noqa: E402

T0 = 1_900_000_000
KEY = b"k" * 32
BP = {"meta": {"buildState": "owner_approved"}, "entities": ["customer", "invoice"], "n": 3}


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Roles:
    def __init__(self):
        self.map = {}

    def roles_for(self, subject):
        v = self.map.get(subject, ())
        if isinstance(v, Exception):
            raise v
        return v


class CustomerRoles:
    def roles_for(self, tenant_id, person_id):
        return ()

    def permissions_for(self, tenant_id, person_id):
        return frozenset()


class World:
    def __init__(self, **kw):
        self.clock, self.repo, self.audit, self.roles = Clock(), InMemoryRepository(), AuditLog(), Roles()
        self.idn = IdentityService(repo=self.repo, customer=RealmConfig(Realm.CUSTOMER, "https://id.example.test", "app", TestOnlyHmacSha256Signer(b"c" * 32, "c1")),
                                   staff=RealmConfig(Realm.STAFF, "https://staff.example.test", "staff", TestOnlyHmacSha256Signer(b"s" * 32, "s1")),
                                   roles=CustomerRoles(), audit=self.audit, clock=self.clock)
        for t in ("t-a", "t-b"):
            self.repo.put_tenant(TenantState(t))
        for s in ("s-rev1", "s-rev2", "s-norole", "s-author"):
            self.repo.put_staff(StaffIdentity(s, s, mfa_enrolled=True))
        self.repo.put_staff(StaffIdentity("s-linked", "s-linked", mfa_enrolled=True, linked_person_ids=frozenset({"p-owner"})))
        for s in ("s-rev1", "s-rev2", "s-author", "s-linked"):
            self.roles.map[s] = ("team_reviewer",)
        self.q = ReviewQueue(self.idn, self.roles, integrity_key=KEY, **kw)

    def claims(self, sid, auth_age=0):
        self._n = (getattr(self, "_n", 0) + 1) % 100  # a distinct MFA event per call (a step-up is spent by a decision)
        tok = self.idn.issue_staff_token(sid, mfa_satisfied=True, auth_time=self.clock.t - auth_age - self._n)
        return self.idn.verify_staff_token(tok.access_token)

    def submit(self, kind="blueprint_draft", content=BP, tenant="t-a", ref="bp-1", author="agent-1", involved=None, linked_staff=(), **kw):
        if involved is None:
            involved = ('req-1',) if kind != 'blueprint_draft' else ()
        return self.q.submit(tenant_id=tenant, kind=kind, subject_ref=ref, content=content, author=author, involved=involved,
                             linked_staff=linked_staff, **kw)

    def claim(self, iid, sid="s-rev1", tenant="t-a"):
        return self.q.claim(self.claims(sid), tenant_id=tenant, item_id=iid)

    def decide(self, iid, sid="s-rev1", decision="approved", tenant="t-a", content=BP, kind="blueprint_draft", note="ok", checklist=None):
        from reviewqueue import checklist_ids
        cl = checklist if checklist is not None else {i: "pass" for i in checklist_ids(kind)}
        return self.q.decide(self.claims(sid), tenant_id=tenant, item_id=iid, decision=decision, checklist=cl, note=note,
                             current_content=content)


def code(fn):
    try:
        fn()
    except ReviewError as e:
        return e.code
    raise AssertionError("no error raised")
