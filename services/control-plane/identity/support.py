"""Staff just-in-time support grants (ADR-0007 item 7; PLT-019 and SEC-008 build
the screens). A staff member requests access to one tenant with a reason, scope
and duration; an owner or admin of that tenant approves with a fresh MFA
step-up; the grant expires on its own. Staff never approve, and nobody approves
a grant for themselves. Every step lands in the tenant-visible audit."""

import secrets

from .errors import IdentityError
from .models import OPEN_TENANT, GrantStatus, Realm, SupportGrant
from .policy import is_owner_or_admin
from .service import STEP_UP_MAX_AGE, IdentityService  # noqa: F401 (re-exported)
from .tokens import AccessClaims, check_live

MAX_SUPPORT_SECONDS = 4 * 3600
MAX_REASON_LEN = 500
PENDING_TTL = 24 * 3600  # a request not approved within this is dead (Q-154)
MAX_PENDING = 5  # unexpired pending requests per staff member and tenant (IDN-045)


def _pending_live(grant, now) -> bool:
    return grant.requested_at + PENDING_TTL > now


def _staff_claims(claims, now) -> AccessClaims:
    check_live(claims, now)
    if claims.realm is not Realm.STAFF:
        raise IdentityError("IDN-006")
    return claims


class SupportGrantService:
    def __init__(self, identity: IdentityService):
        self.idn = identity

    def _live_staff(self, claims) -> AccessClaims:
        """Re-check the staff identity on every call, even after verify_staff_token:
        active, current session version, MFA."""
        claims = _staff_claims(claims, self.idn.now())
        staff = self.idn.repo.get_staff(claims.subject)
        if staff is None or not staff.active:
            raise IdentityError("IDN-010")
        if staff.session_version != claims.session_version or claims.mfa_satisfied is not True:
            raise IdentityError("IDN-009")
        return claims

    def _open_tenant(self, tenant_id) -> None:
        tenant = self.idn.repo.get_tenant(tenant_id) if isinstance(tenant_id, str) else None
        if tenant is None or tenant.status not in OPEN_TENANT:
            raise IdentityError("IDN-011")

    def _tenant(self, grant_id):
        """Tenant of a grant, for the tenant-visible audit; None if unknown."""
        grant = self.idn.repo.get_grant(grant_id) if isinstance(grant_id, str) else None
        return grant.tenant_id if grant else None

    def request(self, staff: AccessClaims, tenant_id: str, reason: str, scope: frozenset,
                duration: int) -> str:
        with self.idn.decision("support.request", Realm.STAFF, None, tenant_id) as ctx:
            staff = self._live_staff(staff)
            ctx["subject"] = staff.subject
            if (not isinstance(reason, str) or not reason.strip()
                    or len(reason) > MAX_REASON_LEN
                    or not isinstance(scope, frozenset) or not scope
                    or not all(isinstance(s, str) and s for s in scope)
                    or isinstance(duration, bool) or not isinstance(duration, int)
                    or not 0 < duration <= MAX_SUPPORT_SECONDS):
                raise IdentityError("IDN-043")
            self._open_tenant(tenant_id)
            now = self.idn.now()
            grant_id = secrets.token_urlsafe(16)
            # count and insert in one atomic repository step, so concurrent requests
            # cannot each see room under the cap
            if not self.idn.repo.put_grant_if_under_cap(
                    SupportGrant(grant_id, staff.subject, tenant_id, reason.strip(), scope,
                                 now, duration), MAX_PENDING, now, PENDING_TTL):
                raise IdentityError("IDN-045")
            return grant_id

    def approve(self, approver: AccessClaims, grant_id: str) -> SupportGrant:
        """`approver` is a verified customer token for the grant's tenant."""
        with self.idn.decision("support.approve", Realm.CUSTOMER, None,
                               self._tenant(grant_id), grant_id) as ctx:
            now = self.idn.now()  # one clock read for the TTL check and the approval
            check_live(approver, now)
            ctx["subject"] = approver.subject
            if approver.realm is not Realm.CUSTOMER:
                raise IdentityError("IDN-041")
            grant = self.idn.repo.get_grant(grant_id)
            if (grant is None or grant.status is not GrantStatus.PENDING
                    or not _pending_live(grant, now)):
                raise IdentityError("IDN-042")
            staff = self.idn.repo.get_staff(grant.staff_id)
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            person = self.idn.repo.get_person(approver.subject)
            channels = person.verified_channels if person else frozenset()
            if (approver.subject in staff.linked_person_ids
                    or channels & staff.verified_channels):
                raise IdentityError("IDN-041")
            if not is_owner_or_admin(self.idn.caller_roles(approver, grant.tenant_id)):
                raise IdentityError("IDN-040")
            self.idn.require_step_up(approver)
            # compare-and-set: only a still-PENDING grant can be approved, so a
            # concurrent revoke or approval wins and nothing is extended (Q-153)
            approved = self.idn.repo.transition_grant(
                grant_id, frozenset({GrantStatus.PENDING}),
                {"status": GrantStatus.APPROVED, "approved_by": approver.subject,
                 "approved_at": now, "expires_at": now + grant.duration})
            if approved is None:
                raise IdentityError("IDN-042")
            self.idn.audit.record(at=now, action="support.granted", decision="allow", code="OK",
                                  realm=Realm.STAFF.value, subject=grant.staff_id,
                                  tenant=grant.tenant_id, detail=grant_id)
            return approved

    def revoke(self, caller: AccessClaims, grant_id: str) -> None:
        """A tenant owner or admin ends a grant early."""
        with self.idn.decision("support.revoke", Realm.CUSTOMER, None,
                               self._tenant(grant_id), grant_id) as ctx:
            check_live(caller, self.idn.now())  # authenticate before reading the grant
            ctx["subject"] = caller.subject
            grant = self.idn.repo.get_grant(grant_id)
            if grant is None or grant.status is GrantStatus.REVOKED:
                raise IdentityError("IDN-042")
            if not is_owner_or_admin(self.idn.caller_roles(caller, grant.tenant_id)):
                raise IdentityError("IDN-040")
            self.idn.require_step_up(caller)
            # revoke is terminal and wins any race: from PENDING or APPROVED only.
            # Only the status changes, so a racing approval's fields are kept.
            if self.idn.repo.transition_grant(
                    grant_id, frozenset({GrantStatus.PENDING, GrantStatus.APPROVED}),
                    {"status": GrantStatus.REVOKED}) is None:
                raise IdentityError("IDN-042")

    def check_access(self, staff: AccessClaims, grant_id: str, tenant_id: str,
                     scope_item: str) -> SupportGrant:
        """Call on every staff request to tenant data, after verify_staff_token."""
        with self.idn.decision("support.access", Realm.STAFF, None, tenant_id,
                               grant_id) as ctx:
            staff = self._live_staff(staff)
            ctx["subject"] = staff.subject
            self._open_tenant(tenant_id)
            grant = self.idn.repo.get_grant(grant_id)
            now = self.idn.now()
            if (grant is None or grant.status is not GrantStatus.APPROVED
                    or grant.staff_id != staff.subject or grant.tenant_id != tenant_id
                    or grant.expires_at is None or grant.expires_at <= now
                    or grant.approved_at is None
                    or grant.approved_at >= grant.requested_at + PENDING_TTL
                    or grant.expires_at > grant.approved_at + min(grant.duration,
                                                                  MAX_SUPPORT_SECONDS)):
                raise IdentityError("IDN-042")
            if scope_item not in grant.scope:
                raise IdentityError("IDN-044")
            return grant
