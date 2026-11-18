"""Invites (ADR-0007 item 12): single-use, expiring, bound to an email or phone
that the accepting person has verified, creatable only by a caller holding the
invite permission. Permissions are passed in as data the caller resolved from
the tenant; they are never read from the request. Only the secret's hash is
stored, and audit records the channel kind, never the address."""

import secrets

from .errors import IdentityError
from .models import OPEN_TENANT, Channel, Invite, Membership, Realm
from .policy import has_invite_permission
from .service import IdentityService, secret_hash
from .tokens import AccessClaims

DEFAULT_INVITE_TTL = 72 * 3600
MAX_INVITE_TTL = 7 * 24 * 3600
CHANNEL_KINDS = frozenset({"email", "phone"})


class InviteService:
    def __init__(self, identity: IdentityService):
        self.idn = identity

    def create(self, caller: AccessClaims, tenant_id: str, caller_permissions: frozenset,
               channel: Channel, ttl: int = DEFAULT_INVITE_TTL) -> str:
        """Return the invite secret (send it over `channel`; never log it)."""
        subject = getattr(caller, "subject", None)
        kind = getattr(channel, "kind", "")
        with self.idn.decision("invite.create", Realm.CUSTOMER, subject, tenant_id,
                               kind if kind in CHANNEL_KINDS else ""):
            self.idn.caller_roles(caller, tenant_id)  # verified, active, current session
            if not has_invite_permission(caller_permissions):
                raise IdentityError("IDN-030")
            if (not isinstance(channel, Channel) or channel.kind not in CHANNEL_KINDS
                    or not isinstance(channel.address, str) or not channel.address.strip()
                    or isinstance(ttl, bool) or not isinstance(ttl, int)
                    or not 0 < ttl <= MAX_INVITE_TTL):
                raise IdentityError("IDN-034")
            now = self.idn.now()
            secret = secrets.token_urlsafe(32)
            self.idn.repo.put_invite(Invite(secret_hash(secret), tenant_id, channel.normalised(),
                                            caller.subject, now, now + ttl))
            return secret

    def accept(self, secret, person_id: str) -> Membership:
        """`person_id` is the signed-in person accepting; their verified channels
        must include the channel the invite is bound to."""
        with self.idn.decision("invite.accept", Realm.CUSTOMER, person_id, None):
            if not isinstance(secret, str) or not 0 < len(secret) <= 256:
                raise IdentityError("IDN-031")
            h = secret_hash(secret)
            invite = self.idn.repo.get_invite(h)
            if invite is None or invite.used_at is not None:
                raise IdentityError("IDN-031")
            now = self.idn.now()
            if invite.expires_at <= now:
                raise IdentityError("IDN-032")
            person = self.idn.repo.get_person(person_id)
            if person is None or not person.active:
                raise IdentityError("IDN-010")
            if invite.channel not in person.verified_channels:
                raise IdentityError("IDN-033")
            tenant = self.idn.repo.get_tenant(invite.tenant_id)
            if tenant is None or tenant.status not in OPEN_TENANT:
                raise IdentityError("IDN-011")
            if self.idn.repo.get_membership(person_id, invite.tenant_id) is not None:
                raise IdentityError("IDN-034")
            if not self.idn.repo.mark_invite_used(h, now):  # atomic single use
                raise IdentityError("IDN-031")
            membership = Membership(person_id, invite.tenant_id, invited_by=invite.created_by,
                                    created_at=now)
            self.idn.repo.put_membership(membership)
            self.idn.audit.record(at=now, action="membership.create", decision="allow",
                                  code="OK", realm=Realm.CUSTOMER.value, subject=person_id,
                                  tenant=invite.tenant_id)
            return membership
