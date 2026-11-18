"""Staff just-in-time support grants (ADR-0007 item 7; PLT-019 and SEC-008 build
the screens). A staff member requests access to one tenant with a reason, scope
and duration; an owner or admin of that tenant approves with a fresh MFA
step-up; the grant expires on its own. Staff never approve, and nobody approves
a grant for themselves. Every step lands in the tenant-visible audit."""

import secrets
from dataclasses import replace

from .errors import IdentityError
from .models import GrantStatus, Realm, SupportGrant
from .policy import is_owner_or_admin
from .service import IdentityService
from .tokens import AccessClaims

MAX_SUPPORT_SECONDS = 4 * 3600
STEP_UP_MAX_AGE = 300  # approver must have authenticated with MFA this recently
MAX_REASON_LEN = 500


def _staff_claims(claims) -> AccessClaims:
    if not isinstance(claims, AccessClaims) or claims.realm is not Realm.STAFF:
        raise IdentityError("IDN-006")
    return claims


class SupportGrantService:
    def __init__(self, identity: IdentityService):
        self.idn = identity

    def _tenant(self, grant_id):
        """Tenant of a grant, for the tenant-visible audit; None if unknown."""
        grant = self.idn.repo.get_grant(grant_id) if isinstance(grant_id, str) else None
        return grant.tenant_id if grant else None

    def request(self, staff: AccessClaims, tenant_id: str, reason: str, scope: frozenset,
                duration: int) -> str:
        with self.idn.decision("support.request", Realm.STAFF,
                               getattr(staff, "subject", None), tenant_id):
            staff = _staff_claims(staff)
            if (not isinstance(reason, str) or not reason.strip()
                    or len(reason) > MAX_REASON_LEN
                    or not isinstance(scope, frozenset) or not scope
                    or not all(isinstance(s, str) and s for s in scope)
                    or isinstance(duration, bool) or not isinstance(duration, int)
                    or not 0 < duration <= MAX_SUPPORT_SECONDS):
                raise IdentityError("IDN-043")
            if self.idn.repo.get_tenant(tenant_id) is None:
                raise IdentityError("IDN-011")
            grant_id = secrets.token_urlsafe(16)
            self.idn.repo.put_grant(SupportGrant(grant_id, staff.subject, tenant_id,
                                                 reason.strip(), scope, self.idn.now(), duration))
            return grant_id

    def approve(self, approver: AccessClaims, grant_id: str) -> SupportGrant:
        """`approver` is a verified customer token for the grant's tenant."""
        with self.idn.decision("support.approve", Realm.CUSTOMER,
                               getattr(approver, "subject", None), self._tenant(grant_id),
                               grant_id):
            if not isinstance(approver, AccessClaims) or approver.realm is not Realm.CUSTOMER:
                raise IdentityError("IDN-041" if isinstance(approver, AccessClaims)
                                    else "IDN-006")
            grant = self.idn.repo.get_grant(grant_id)
            if grant is None or grant.status is not GrantStatus.PENDING:
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
            now = self.idn.now()
            if not approver.mfa_satisfied or now - approver.auth_time > STEP_UP_MAX_AGE:
                raise IdentityError("IDN-013")
            approved = replace(grant, status=GrantStatus.APPROVED, approved_by=approver.subject,
                               approved_at=now, expires_at=now + grant.duration)
            self.idn.repo.put_grant(approved)
            self.idn.audit.record(at=now, action="support.granted", decision="allow", code="OK",
                                  realm=Realm.STAFF.value, subject=grant.staff_id,
                                  tenant=grant.tenant_id, detail=grant_id)
            return approved

    def revoke(self, caller: AccessClaims, grant_id: str) -> None:
        """A tenant owner or admin ends a grant early."""
        with self.idn.decision("support.revoke", Realm.CUSTOMER,
                               getattr(caller, "subject", None), self._tenant(grant_id),
                               grant_id):
            grant = self.idn.repo.get_grant(grant_id)
            if grant is None or grant.status is GrantStatus.REVOKED:
                raise IdentityError("IDN-042")
            if not is_owner_or_admin(self.idn.caller_roles(caller, grant.tenant_id)):
                raise IdentityError("IDN-040")
            self.idn.repo.put_grant(replace(grant, status=GrantStatus.REVOKED))

    def check_access(self, staff: AccessClaims, grant_id: str, tenant_id: str,
                     scope_item: str) -> SupportGrant:
        """Call on every staff request to tenant data, after verify_staff_token."""
        with self.idn.decision("support.access", Realm.STAFF,
                               getattr(staff, "subject", None), tenant_id, grant_id):
            staff = _staff_claims(staff)
            grant = self.idn.repo.get_grant(grant_id)
            now = self.idn.now()
            if (grant is None or grant.status is not GrantStatus.APPROVED
                    or grant.staff_id != staff.subject or grant.tenant_id != tenant_id
                    or grant.expires_at is None or grant.expires_at <= now):
                raise IdentityError("IDN-042")
            if scope_item not in grant.scope:
                raise IdentityError("IDN-044")
            return grant
