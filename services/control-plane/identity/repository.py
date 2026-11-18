"""Persistence interface and an in-memory implementation for tests only.

No real users may be stored until Q-14 (where the identity store lives) is
answered; the real store arrives with the identity-provider spike. A real
implementation must make `mark_invite_used` and `mark_refresh_used` atomic
compare-and-set operations, or single use and reuse detection break. Family
revocation is a durable tombstone: `put_refresh` must check it and store in one
atomic step, so a rotation racing reuse detection cannot mint a live token in a
revoked family. `transition_grant` must be one atomic compare-and-set (a
conditional UPDATE or single transaction) that sets only the named fields on the
current row; support grant approve and revoke rely on it. `put_grant_if_under_cap`
must count the live pending requests and insert in one atomic step (a single
transaction or conditional insert), or concurrent requests bypass the cap. A real
store should take `now` from the database clock for these. The session high-water mark per person and tenant must survive
membership removal and never go down."""

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Optional

from .models import (GrantStatus, Invite, Membership, Person, RefreshRecord,
                     StaffIdentity, SupportGrant, TenantState)


class Repository(ABC):
    @abstractmethod
    def get_person(self, person_id: str) -> Optional[Person]: ...
    @abstractmethod
    def put_person(self, person: Person) -> None: ...
    @abstractmethod
    def get_staff(self, staff_id: str) -> Optional[StaffIdentity]: ...
    @abstractmethod
    def put_staff(self, staff: StaffIdentity) -> None: ...
    @abstractmethod
    def get_tenant(self, tenant_id: str) -> Optional[TenantState]: ...
    @abstractmethod
    def put_tenant(self, tenant: TenantState) -> None: ...
    @abstractmethod
    def get_membership(self, person_id: str, tenant_id: str) -> Optional[Membership]: ...
    @abstractmethod
    def put_membership(self, membership: Membership) -> None: ...
    @abstractmethod
    def delete_membership(self, person_id: str, tenant_id: str) -> None: ...
    @abstractmethod
    def memberships_for_tenant(self, tenant_id: str) -> tuple: ...
    @abstractmethod
    def put_invite(self, invite: Invite) -> None: ...
    @abstractmethod
    def get_invite(self, invite_hash: str) -> Optional[Invite]: ...
    @abstractmethod
    def mark_invite_used(self, invite_hash: str, at: int) -> bool:
        """Atomically set used_at if unset; False if it was already used or unknown."""
    @abstractmethod
    def put_refresh(self, record: RefreshRecord) -> bool:
        """Atomically store unless the record's family is revoked; False if revoked."""
    @abstractmethod
    def get_refresh(self, token_hash: str) -> Optional[RefreshRecord]: ...
    @abstractmethod
    def mark_refresh_used(self, token_hash: str) -> bool:
        """Atomically mark used; False if it was already used or unknown."""
    @abstractmethod
    def revoke_family(self, family_id: str) -> None:
        """Tombstone the family (permanent) and flag its existing records."""
    @abstractmethod
    def is_family_revoked(self, family_id: str) -> bool: ...
    @abstractmethod
    def families_for(self, person_id: str, tenant_id: str) -> frozenset: ...
    @abstractmethod
    def get_session_high_water(self, person_id: str, tenant_id: str) -> int:
        """Highest session version ever used for this person and tenant; 0 if none."""
    @abstractmethod
    def raise_session_high_water(self, person_id: str, tenant_id: str, version: int) -> None:
        """Set the mark to max(current, version); it never goes down."""
    @abstractmethod
    def put_grant(self, grant: SupportGrant) -> None: ...
    @abstractmethod
    def get_grant(self, grant_id: str) -> Optional[SupportGrant]: ...
    @abstractmethod
    def transition_grant(self, grant_id: str, from_statuses: frozenset,
                         changes: dict) -> Optional[SupportGrant]:
        """Atomically apply `changes` (which must include `status`) to the current
        row only if its status is in `from_statuses`; only status, approved_by,
        approved_at and expires_at may change, other fields keep their stored
        values. Return the new row, or None if unknown or already moved on."""
    @abstractmethod
    def put_grant_if_under_cap(self, grant: SupportGrant, max_pending: int, now: int,
                               pending_ttl: int) -> bool:
        """Atomically insert `grant` only if fewer than `max_pending` PENDING grants
        with `requested_at + pending_ttl > now` exist for its staff member and tenant;
        False if the cap is reached."""


_MUTABLE_GRANT_FIELDS = frozenset({"status", "approved_by", "approved_at", "expires_at"})


class InMemoryRepository(Repository):
    """Tests only. Synthetic data only."""

    def __init__(self):
        self._persons, self._staff, self._tenants = {}, {}, {}
        self._members, self._invites, self._refresh, self._grants = {}, {}, {}, {}
        self._revoked_families, self._high_water = set(), {}

    def get_person(self, person_id):
        return self._persons.get(person_id)

    def put_person(self, person):
        self._persons[person.person_id] = person

    def get_staff(self, staff_id):
        return self._staff.get(staff_id)

    def put_staff(self, staff):
        self._staff[staff.staff_id] = staff

    def get_tenant(self, tenant_id):
        return self._tenants.get(tenant_id)

    def put_tenant(self, tenant):
        self._tenants[tenant.tenant_id] = tenant

    def get_membership(self, person_id, tenant_id):
        return self._members.get((person_id, tenant_id))

    def put_membership(self, membership):
        self._members[(membership.person_id, membership.tenant_id)] = membership

    def delete_membership(self, person_id, tenant_id):
        self._members.pop((person_id, tenant_id), None)

    def memberships_for_tenant(self, tenant_id):
        return tuple(m for (_, t), m in self._members.items() if t == tenant_id)

    def put_invite(self, invite):
        self._invites[invite.invite_hash] = invite

    def get_invite(self, invite_hash):
        return self._invites.get(invite_hash)

    def mark_invite_used(self, invite_hash, at):
        inv = self._invites.get(invite_hash)
        if inv is None or inv.used_at is not None:
            return False
        self._invites[invite_hash] = replace(inv, used_at=at)
        return True

    def put_refresh(self, record):
        if record.family_id in self._revoked_families:
            return False
        self._refresh[record.token_hash] = record
        return True

    def get_refresh(self, token_hash):
        return self._refresh.get(token_hash)

    def mark_refresh_used(self, token_hash):
        rec = self._refresh.get(token_hash)
        if rec is None or rec.used:
            return False
        self._refresh[token_hash] = replace(rec, used=True)
        return True

    def revoke_family(self, family_id):
        self._revoked_families.add(family_id)
        for key, rec in list(self._refresh.items()):
            if rec.family_id == family_id:
                self._refresh[key] = replace(rec, revoked=True)

    def is_family_revoked(self, family_id):
        return family_id in self._revoked_families

    def families_for(self, person_id, tenant_id):
        return frozenset(r.family_id for r in self._refresh.values()
                         if (r.person_id, r.tenant_id) == (person_id, tenant_id))

    def get_session_high_water(self, person_id, tenant_id):
        return self._high_water.get((person_id, tenant_id), 0)

    def raise_session_high_water(self, person_id, tenant_id, version):
        key = (person_id, tenant_id)
        self._high_water[key] = max(self._high_water.get(key, 0), version)

    def put_grant(self, grant):
        self._grants[grant.grant_id] = grant

    def get_grant(self, grant_id):
        return self._grants.get(grant_id)

    def transition_grant(self, grant_id, from_statuses, changes):
        cur = self._grants.get(grant_id)
        if (cur is None or cur.status not in from_statuses or "status" not in changes
                or not set(changes) <= _MUTABLE_GRANT_FIELDS):
            return None
        new = replace(cur, **changes)
        self._grants[grant_id] = new
        return new

    def put_grant_if_under_cap(self, grant, max_pending, now, pending_ttl):
        live = sum(1 for g in self._grants.values()
                   if g.staff_id == grant.staff_id and g.tenant_id == grant.tenant_id
                   and g.status is GrantStatus.PENDING and g.requested_at + pending_ttl > now)
        if live >= max_pending or grant.grant_id in self._grants:
            return False
        self._grants[grant.grant_id] = grant
        return True
