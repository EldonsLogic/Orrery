"""Sessions and tokens for customers and staff (ADR-0007 items 3, 6, 7, 10).

`mfa_satisfied` and `auth_time` are the outcome of authentication, supplied by
the authenticator (the identity provider chosen in the spike), never by the
end user's request. Every decision is audited; every failure denies."""

import hashlib
import secrets
from contextlib import contextmanager
from dataclasses import replace

from .audit import ALLOW, DENY, AuditLog
from .errors import IdentityError
from .models import (OPEN_TENANT, Clock, Membership, MembershipStatus, Realm,
                     RefreshRecord, TenantStatus, TokenPair)
from .policy import RoleInfo, is_owner, mfa_required, resolve_roles, role_requires_mfa
from .repository import Repository
from .tokens import AccessClaims, RealmConfig, check_live, decode, encode

DEFAULT_REFRESH_TTL = 12 * 3600
MAX_SESSION_AGE = 7 * 24 * 3600  # a refresh family never outlives this after sign-in
REVOKE_REASONS = frozenset({"compromise", "logout", "admin"})
STEP_UP_MAX_AGE = 300  # admin-kind changes need an MFA sign-in this recent (ADR-0007 item 6)


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


class IdentityService:
    def __init__(self, *, repo: Repository, customer: RealmConfig, staff: RealmConfig,
                 roles, audit: AuditLog, clock: Clock, refresh_ttl: int = DEFAULT_REFRESH_TTL):
        if (customer.realm is not Realm.CUSTOMER or staff.realm is not Realm.STAFF
                or customer.issuer == staff.issuer or customer.audience == staff.audience
                or not _is_int(refresh_ttl) or not 0 < refresh_ttl <= MAX_SESSION_AGE):
            raise IdentityError("IDN-051")
        self.repo, self.customer, self.staff = repo, customer, staff
        self.roles, self.audit, self.clock = roles, audit, clock
        self.refresh_ttl = refresh_ttl

    # -- shared helpers -------------------------------------------------
    def now(self) -> int:
        t = self.clock()
        if not _is_int(t):
            raise IdentityError("IDN-051")
        return t

    @contextmanager
    def decision(self, action, realm: Realm, subject, tenant, detail: str = ""):
        """Audit allow on success, deny with the reason code on any failure."""
        ctx = {}  # a caller may set "subject" once a token has been verified
        try:
            yield ctx
        except Exception as err:
            subject = ctx.get("subject", subject)
            code = err.code if isinstance(err, IdentityError) else "ERROR"
            self.audit.record(at=self.clock(), action=action, decision=DENY, code=code,
                              realm=realm.value, subject=subject, tenant=tenant, detail=detail)
            raise
        self.audit.record(at=self.clock(), action=action, decision=ALLOW, code="OK",
                          realm=realm.value, subject=ctx.get("subject", subject), tenant=tenant, detail=detail)

    def active_membership(self, person_id, tenant_id) -> Membership:
        person = self.repo.get_person(person_id)
        if person is None or not person.active:
            raise IdentityError("IDN-010")
        tenant = self.repo.get_tenant(tenant_id)
        if tenant is None or tenant.status not in OPEN_TENANT:
            raise IdentityError("IDN-011")
        m = self.repo.get_membership(person_id, tenant_id)
        if m is None or m.status is not MembershipStatus.ACTIVE:
            raise IdentityError("IDN-009")
        return m

    def caller_roles(self, caller: AccessClaims, tenant_id: str) -> tuple:
        """Roles of a verified customer caller in that tenant, from the resolver."""
        check_live(caller, self.now())  # sealed, inside nbf/exp (Q-152)
        if caller.realm is not Realm.CUSTOMER or caller.tenant != tenant_id:
            raise IdentityError("IDN-006")
        m = self.active_membership(caller.subject, tenant_id)
        if m.session_version != caller.session_version:
            raise IdentityError("IDN-009")
        return resolve_roles(self.roles, tenant_id, caller.subject)

    # -- customer tokens ------------------------------------------------
    def _entry_check(self, person_id, tenant_id, mfa_satisfied) -> Membership:
        m = self.active_membership(person_id, tenant_id)
        roles = resolve_roles(self.roles, tenant_id, person_id)
        tenant = self.repo.get_tenant(tenant_id)
        person = self.repo.get_person(person_id)
        if mfa_required(roles, tenant_mfa_for_all=tenant.mfa_for_all,
                        membership_flag=m.mfa_required):
            if not (mfa_satisfied is True and person.mfa_enrolled):
                raise IdentityError("IDN-013")
        return m

    def _mint(self, m: Membership, mfa: bool, auth_time: int, family_id: str, now: int):
        secret = secrets.token_urlsafe(32)
        expires = min(now + self.refresh_ttl, auth_time + MAX_SESSION_AGE)
        # Stored first and atomically refused if the family was revoked meanwhile,
        # so a rotation racing reuse detection never returns a live pair.
        if not self.repo.put_refresh(RefreshRecord(secret_hash(secret), family_id, m.person_id,
                                                   m.tenant_id, m.session_version, mfa,
                                                   auth_time, expires)):
            raise IdentityError("IDN-021")
        token, exp = encode(self.customer, subject=m.person_id, tenant=m.tenant_id,
                            session_version=m.session_version, mfa_satisfied=mfa,
                            auth_time=auth_time, now=now)
        return TokenPair(token, secret, exp)

    def require_step_up(self, claims: AccessClaims) -> None:
        """Fresh MFA sign-in within STEP_UP_MAX_AGE; refresh keeps the old auth_time."""
        check_live(claims, self.now())
        if not claims.mfa_satisfied or self.now() - claims.auth_time > STEP_UP_MAX_AGE:
            raise IdentityError("IDN-013")

    def issue_customer_token(self, person_id, tenant_id, *, mfa_satisfied, auth_time) -> TokenPair:
        """One token for one tenant (workspace). Switching workspace calls this again."""
        with self.decision("token.issue", Realm.CUSTOMER, person_id, tenant_id):
            now = self.now()
            if not _is_int(auth_time) or auth_time > now or now - auth_time > MAX_SESSION_AGE:
                raise IdentityError("IDN-008")
            m = self._entry_check(person_id, tenant_id, mfa_satisfied)
            return self._mint(m, mfa_satisfied is True, auth_time, secrets.token_urlsafe(16), now)

    def verify_customer_token(self, token, tenant_id) -> AccessClaims:
        """`tenant_id` is the tenant this request is for (from the subdomain)."""
        with self.decision("token.verify", Realm.CUSTOMER, None, tenant_id) as ctx:
            claims = decode(token, self.customer, now=self.now(), tenant=tenant_id)
            ctx["subject"] = claims.subject
            m = self.active_membership(claims.subject, tenant_id)
            if m.session_version != claims.session_version:
                raise IdentityError("IDN-009")
            return claims

    def refresh(self, refresh_token, tenant_id) -> TokenPair:
        """Rotate: each refresh token works once. A second use revokes the family."""
        with self.decision("token.refresh", Realm.CUSTOMER, None, tenant_id):
            if not isinstance(refresh_token, str) or not 0 < len(refresh_token) <= 256:
                raise IdentityError("IDN-020")
            h = secret_hash(refresh_token)
            rec = self.repo.get_refresh(h)
            if (rec is None or rec.tenant_id != tenant_id or rec.revoked
                    or self.repo.is_family_revoked(rec.family_id)):
                raise IdentityError("IDN-020")
            if rec.used or not self.repo.mark_refresh_used(h):
                self.repo.revoke_family(rec.family_id)
                raise IdentityError("IDN-021")
            now = self.now()
            if rec.expires_at <= now:
                raise IdentityError("IDN-020")
            m = self._entry_check(rec.person_id, tenant_id, rec.mfa_satisfied)
            if m.session_version != rec.session_version:
                self.repo.revoke_family(rec.family_id)
                raise IdentityError("IDN-009")
            return self._mint(m, rec.mfa_satisfied, rec.auth_time, rec.family_id, now)

    # -- revocation (internal control-plane calls; callers authorise first) --
    def _bump(self, m: Membership, **changes) -> None:
        self.repo.put_membership(replace(m, session_version=m.session_version + 1, **changes))

    def revoke_sessions(self, person_id, tenant_id, reason: str) -> None:
        with self.decision("session.revoke", Realm.CUSTOMER, person_id, tenant_id, reason):
            if reason not in REVOKE_REASONS:
                raise IdentityError("IDN-034")
            m = self.repo.get_membership(person_id, tenant_id)
            if m is None:
                raise IdentityError("IDN-009")
            self._bump(m)

    def end_person_sessions(self, person_id, reason: str = "mfa_change") -> None:
        """Every session of the person in every tenant ends: refresh families are
        tombstoned and each membership's session version is bumped (SEC-005: a
        factor was added or removed, so earlier sessions no longer match)."""
        with self.decision("session.revoke_all", Realm.CUSTOMER, person_id, None, reason):
            for m in self.repo.memberships_for_person(person_id):
                for family_id in self.repo.families_for(person_id, m.tenant_id):
                    self.repo.revoke_family(family_id)
                self._bump(m)

    def suspend_membership(self, person_id, tenant_id) -> None:
        with self.decision("membership.suspend", Realm.CUSTOMER, person_id, tenant_id):
            m = self.repo.get_membership(person_id, tenant_id)
            if m is None:
                raise IdentityError("IDN-009")
            self._bump(m, status=MembershipStatus.SUSPENDED)

    def remove_membership(self, person_id, tenant_id) -> None:
        """Keeps the session high-water mark so a re-admission starts above every
        old token, and tombstones every refresh family of the membership."""
        with self.decision("membership.remove", Realm.CUSTOMER, person_id, tenant_id):
            m = self.repo.get_membership(person_id, tenant_id)
            if m is None:
                raise IdentityError("IDN-009")
            self.repo.raise_session_high_water(person_id, tenant_id, m.session_version)
            for family_id in self.repo.families_for(person_id, tenant_id):
                self.repo.revoke_family(family_id)
            self.repo.delete_membership(person_id, tenant_id)

    def next_session_version(self, person_id, tenant_id) -> int:
        """Session version for a new membership: above any version used before."""
        hw = self.repo.get_session_high_water(person_id, tenant_id)
        if not _is_int(hw) or hw < 0:
            raise IdentityError("IDN-051")
        return hw + 1

    def suspend_tenant(self, tenant_id) -> None:
        """ADR-0007 consequences: suspension blocks issuance and bumps every session."""
        with self.decision("tenant.suspend", Realm.CUSTOMER, None, tenant_id):
            tenant = self.repo.get_tenant(tenant_id)
            if tenant is None:
                raise IdentityError("IDN-011")
            self.repo.put_tenant(replace(tenant, status=TenantStatus.SUSPENDED))
            for m in self.repo.memberships_for_tenant(tenant_id):
                self._bump(m)

    # -- MFA on role grant and tenant-wide MFA ----------------------------
    def check_role_grant(self, person_id, tenant_id, role: RoleInfo) -> None:
        """Call before the tenant assigns `role`. An MFA-mandatory role needs an
        enrolled person; the membership is flagged and sessions are bumped so
        tokens issued without MFA stop working at once."""
        with self.decision("role.grant", Realm.CUSTOMER, person_id, tenant_id):
            if not isinstance(role, RoleInfo):
                raise IdentityError("IDN-012")
            m = self.active_membership(person_id, tenant_id)
            if role_requires_mfa(role):
                if not self.repo.get_person(person_id).mfa_enrolled:
                    raise IdentityError("IDN-014")
                self._bump(m, mfa_required=True)

    def set_tenant_mfa_for_all(self, caller: AccessClaims, tenant_id, enabled: bool) -> None:
        with self.decision("tenant.mfa_for_all", Realm.CUSTOMER,
                           getattr(caller, "subject", None), tenant_id):
            if not isinstance(enabled, bool):
                raise IdentityError("IDN-034")
            if not is_owner(self.caller_roles(caller, tenant_id)):
                raise IdentityError("IDN-015")
            self.require_step_up(caller)
            tenant = self.repo.get_tenant(tenant_id)
            self.repo.put_tenant(replace(tenant, mfa_for_all=enabled))
            if enabled:
                for m in self.repo.memberships_for_tenant(tenant_id):
                    self._bump(m)

    # -- staff realm -----------------------------------------------------
    def issue_staff_token(self, staff_id, *, mfa_satisfied, auth_time) -> TokenPair:
        """Staff tokens carry no tenant; tenant access needs a support grant."""
        with self.decision("token.issue", Realm.STAFF, staff_id, None):
            now = self.now()
            if not _is_int(auth_time) or auth_time > now or now - auth_time > MAX_SESSION_AGE:
                raise IdentityError("IDN-008")
            staff = self.repo.get_staff(staff_id)
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            if not (mfa_satisfied is True and staff.mfa_enrolled):
                raise IdentityError("IDN-013")
            token, exp = encode(self.staff, subject=staff_id, tenant=None,
                                session_version=staff.session_version, mfa_satisfied=True,
                                auth_time=auth_time, now=now)
            return TokenPair(token, None, exp)

    def verify_staff_token(self, token) -> AccessClaims:
        with self.decision("token.verify", Realm.STAFF, None, None) as ctx:
            claims = decode(token, self.staff, now=self.now(), tenant=None)
            ctx["subject"] = claims.subject
            staff = self.repo.get_staff(claims.subject)
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            if staff.session_version != claims.session_version or not claims.mfa_satisfied:
                raise IdentityError("IDN-009")
            return claims

    def revoke_staff_sessions(self, staff_id) -> None:
        with self.decision("session.revoke", Realm.STAFF, staff_id, None):
            staff = self.repo.get_staff(staff_id)
            if staff is None:
                raise IdentityError("IDN-010")
            self.repo.put_staff(replace(staff, session_version=staff.session_version + 1))
