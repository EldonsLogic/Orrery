"""MFA for owners, staff and support access (SEC-005, ADR-0007 items 6 and 12).

Sign-in is password then factor; a successful second factor mints a token with
mfa=true and auth_time=now through the existing IdentityService. Enrolling or
removing a factor, and regenerating recovery codes, need a recent MFA step-up
(except a customer's very first factor, and a staff first factor which needs an
admin-issued bootstrap ticket). Every attempt is counted before it is evaluated
and a locked subject is refused without evaluating anything; every store or
sealing failure denies (IDN-064). Secrets are injected opaque values: a
SecretBox seals TOTP keys, a PasswordVerifier and BootstrapAuthority come from
the identity provider. Nothing secret is audited or put in an error."""

import secrets
from dataclasses import dataclass, field, replace
from typing import Callable, Optional, Protocol

from ..errors import IdentityError
from ..models import Realm, TokenPair
from ..policy import mfa_required, resolve_roles
from ..service import IdentityService
from ..tokens import AccessClaims, check_live
from . import recovery, totp
from .store import FactorRepository, FactorStatus, RecoveryRecord, TotpFactor

MAX_ID = 256
MAX_SECRET_INPUT = 256


class SecretBox(Protocol):
    """Seals and opens TOTP keys (a KMS in production). `context` binds the
    sealed value to its factor id."""

    def seal(self, plaintext: bytes, context: str) -> bytes: ...
    def open(self, sealed: bytes, context: str) -> bytes: ...


class PasswordVerifier(Protocol):
    def verify(self, realm: str, subject_id: str, password: str) -> bool: ...


class BootstrapAuthority(Protocol):
    def consume(self, staff_id: str, ticket: str) -> bool:
        """True once for a valid admin-issued ticket, then never again."""


@dataclass(frozen=True)
class MfaConfig:
    max_attempts: int = 5
    attempt_window: int = 900
    lockout: int = 900
    pending_ttl: int = 600
    max_factors: int = 3
    recovery_codes: int = 10
    kdf_iterations: int = 60_000
    issuer_label: str = "Platform"


@dataclass(frozen=True)
class EnrolmentStart:
    factor_id: str
    secret: str = field(repr=False)  # base32, shown once
    uri: str = field(repr=False)


def _ok_text(v) -> bool:
    return isinstance(v, str) and 0 < len(v) <= MAX_ID


class MfaService:
    def __init__(self, *, idn: IdentityService, factors: FactorRepository, box: SecretBox,
                 passwords: PasswordVerifier, bootstrap: Optional[BootstrapAuthority] = None,
                 rng: Callable[[int], bytes] = secrets.token_bytes,
                 config: MfaConfig = MfaConfig()):
        c = config
        if (min(c.max_attempts, c.attempt_window, c.lockout, c.pending_ttl, c.max_factors,
                c.recovery_codes, c.kdf_iterations) <= 0):
            raise IdentityError("IDN-051")
        self.idn, self.factors, self.box, self.passwords = idn, factors, box, passwords
        self.bootstrap, self.rng, self.cfg = bootstrap, rng, c

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _io(fn, *args):
        """Store, box and provider failures deny (fail closed)."""
        try:
            return fn(*args)
        except IdentityError:
            raise
        except Exception:
            raise IdentityError("IDN-064") from None

    @staticmethod
    def _attempt_key(realm: Realm, subject_id: str) -> str:
        return f"{realm.value}:{subject_id}"

    def _random(self, n: int) -> bytes:
        raw = self._io(self.rng, n)
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != n:
            raise IdentityError("IDN-064")
        return bytes(raw)

    def _caller(self, claims) -> tuple:
        """A live, unrevoked session of this realm; returns (realm, subject)."""
        check_live(claims, self.idn.now())
        repo = self.idn.repo
        if claims.realm is Realm.CUSTOMER:
            m = self.idn.active_membership(claims.subject, claims.tenant)
            if m.session_version != claims.session_version:
                raise IdentityError("IDN-009")
        else:
            staff = repo.get_staff(claims.subject)
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            if staff.session_version != claims.session_version:
                raise IdentityError("IDN-009")
        return claims.realm, claims.subject

    def _mine(self, realm: Realm, subject_id: str) -> tuple:
        return tuple(f for f in self._io(self.factors.factors_for, realm.value, subject_id))

    def _active(self, realm: Realm, subject_id: str) -> tuple:
        return tuple(f for f in self._mine(realm, subject_id) if f.status is FactorStatus.ACTIVE)

    def _set_enrolled(self, realm: Realm, subject_id: str, flag: bool) -> None:
        repo = self.idn.repo
        if realm is Realm.CUSTOMER:
            person = repo.get_person(subject_id)
            if person is None:
                raise IdentityError("IDN-010")
            repo.put_person(replace(person, mfa_enrolled=flag))
        else:
            staff = repo.get_staff(subject_id)
            if staff is None:
                raise IdentityError("IDN-010")
            bump = 0 if flag else 1  # losing the last factor ends staff sessions
            repo.put_staff(replace(staff, mfa_enrolled=flag,
                                   session_version=staff.session_version + bump))

    def _attempt(self, realm: Realm, subject_id: str) -> None:
        a = self._io(self.factors.begin_attempt, self._attempt_key(realm, subject_id),
                     self.idn.now(), self.cfg.attempt_window, self.cfg.max_attempts,
                     self.cfg.lockout)
        if a.allowed is not True:
            raise IdentityError("IDN-061")

    def _clear(self, realm: Realm, subject_id: str) -> None:
        self._io(self.factors.clear_attempts, self._attempt_key(realm, subject_id))

    def _key_of(self, f: TotpFactor) -> bytes:
        key = self._io(self.box.open, f.sealed_secret, f.factor_id)
        if not isinstance(key, (bytes, bytearray)) or not key:
            raise IdentityError("IDN-064")
        return bytes(key)

    # -- second factor check (TOTP or recovery code) -----------------------
    def _check_factor(self, realm: Realm, subject_id: str, code) -> str:
        if not isinstance(code, str) or len(code) > MAX_SECRET_INPUT:
            raise IdentityError("IDN-060")
        if totp.well_formed(code):
            with self.idn.decision("mfa.verify", realm, subject_id, None, "totp"):
                now, winner = self.idn.now(), None
                for f in self._active(realm, subject_id):
                    counter = totp.verify(self._key_of(f), code, now, f.last_counter)
                    if counter is not None and winner is None and self._io(
                            self.factors.advance_counter, f.factor_id, f.last_counter, counter):
                        winner = f  # lost compare-and-set = replay or race: not a win
                if winner is None:
                    raise IdentityError("IDN-060")
            return "totp"
        with self.idn.decision("mfa.recovery_use", realm, subject_id, None) as ctx:
            norm = recovery.normalise(code)
            if norm is None:
                raise IdentityError("IDN-060")
            records = [r for r in self._io(self.factors.recovery_for, realm.value, subject_id)
                       if not r.used]
            found = None
            for r in records:  # every unused code is hashed; no early exit
                if recovery.matches(norm, r.salt, r.digest, self.cfg.kdf_iterations) and found is None:
                    found = r
            if found is None or not self._io(self.factors.consume_recovery, found.code_id):
                raise IdentityError("IDN-060")
            ctx["subject"] = subject_id
        return "recovery"

    # -- sign-in ----------------------------------------------------------
    def sign_in(self, realm: Realm, subject_id, password, code=None, *, tenant_id=None) -> TokenPair:
        """Password, then (when a factor is enrolled) the factor. Every failure
        before the credential is proven is the same IDN-060. A subject whose role
        requires MFA but who has no factor gets IDN-013 from the token service."""
        with self.idn.decision("mfa.signin", realm if isinstance(realm, Realm) else Realm.CUSTOMER,
                               subject_id, tenant_id):
            if (not isinstance(realm, Realm) or not _ok_text(subject_id)
                    or not isinstance(password, str) or not 0 < len(password) <= MAX_SECRET_INPUT
                    or (code is not None and not isinstance(code, str))
                    or (realm is Realm.CUSTOMER and not _ok_text(tenant_id))
                    or (realm is Realm.STAFF and tenant_id is not None)):
                raise IdentityError("IDN-060")
            self._attempt(realm, subject_id)
            try:
                password_ok = self.passwords.verify(realm.value, subject_id, password) is True
            except Exception:
                password_ok = False
            if not password_ok:
                raise IdentityError("IDN-060")
            active = self._active(realm, subject_id)
            if code is None:
                if active:
                    raise IdentityError("IDN-013")
            else:
                if not active:
                    raise IdentityError("IDN-060")
                self._check_factor(realm, subject_id, code)
            self._clear(realm, subject_id)
            return self._issue(realm, subject_id, tenant_id, mfa=code is not None)

    def _issue(self, realm, subject_id, tenant_id, mfa: bool) -> TokenPair:
        now = self.idn.now()
        if realm is Realm.CUSTOMER:
            return self.idn.issue_customer_token(subject_id, tenant_id, mfa_satisfied=mfa,
                                                 auth_time=now)
        return self.idn.issue_staff_token(subject_id, mfa_satisfied=mfa, auth_time=now)

    def step_up(self, claims: AccessClaims, code) -> TokenPair:
        """Fresh factor check on a live session; returns a token with auth_time=now."""
        realm, sid = self._caller_safe(claims)
        with self.idn.decision("mfa.step_up", realm, sid, getattr(claims, "tenant", None)):
            self._caller(claims)
            if not self._active(realm, sid):
                raise IdentityError("IDN-013")
            self._attempt(realm, sid)
            self._check_factor(realm, sid, code)
            self._clear(realm, sid)
            return self._issue(realm, sid, claims.tenant, mfa=True)

    @staticmethod
    def _caller_safe(claims) -> tuple:
        realm = getattr(claims, "realm", None)
        sid = getattr(claims, "subject", None)
        return (realm if isinstance(realm, Realm) else Realm.CUSTOMER), sid

    # -- enrolment --------------------------------------------------------
    def _begin(self, realm: Realm, subject_id: str, bootstrap: bool) -> EnrolmentStart:
        mine = self._mine(realm, subject_id)
        if len([f for f in mine if f.status is FactorStatus.ACTIVE]) >= self.cfg.max_factors:
            raise IdentityError("IDN-062")
        for f in mine:
            if f.status is FactorStatus.PENDING:
                self._io(self.factors.delete_factor, f.factor_id)
        factor_id = self._random(16).hex()
        key = self._random(totp.SECRET_BYTES)
        sealed = self._io(self.box.seal, key, factor_id)
        if not isinstance(sealed, (bytes, bytearray)) or not sealed:
            raise IdentityError("IDN-064")
        self._io(self.factors.put_factor, TotpFactor(
            factor_id, realm.value, subject_id, bytes(sealed), self.idn.now(),
            bootstrap=bootstrap))
        return EnrolmentStart(factor_id, totp.b32(key),
                              totp.provisioning_uri(key, subject_id, self.cfg.issuer_label))

    def begin_totp_enrolment(self, claims: AccessClaims) -> EnrolmentStart:
        """Customer first factor: a live session is enough. Any further factor, or
        a staff factor, needs a recent MFA step-up."""
        realm, sid = self._caller_safe(claims)
        with self.idn.decision("mfa.enrol_begin", realm, sid, getattr(claims, "tenant", None)):
            realm, sid = self._caller(claims)
            if self._active(realm, sid) or realm is Realm.STAFF:
                self.idn.require_step_up(claims)
            return self._begin(realm, sid, bootstrap=False)

    def begin_staff_bootstrap(self, staff_id, ticket) -> EnrolmentStart:
        """First staff factor, before any staff token can exist: an admin-issued
        one-time ticket proves the enrolment is authorised."""
        with self.idn.decision("mfa.enrol_begin", Realm.STAFF, staff_id, None, "bootstrap"):
            staff = self.idn.repo.get_staff(staff_id) if _ok_text(staff_id) else None
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            if self._active(Realm.STAFF, staff_id):
                raise IdentityError("IDN-062")
            if (self.bootstrap is None or not _ok_text(ticket)
                    or self._io(self.bootstrap.consume, staff_id, ticket) is not True):
                raise IdentityError("IDN-013")
            return self._begin(Realm.STAFF, staff_id, bootstrap=True)

    def confirm_totp_enrolment(self, realm: Realm, subject_id, factor_id, code, *,
                               claims: Optional[AccessClaims] = None) -> tuple:
        """Prove the authenticator works. Returns the recovery codes (shown once)
        when this is the subject's first active factor, else an empty tuple."""
        with self.idn.decision("mfa.enrol_confirm", realm, subject_id, None):
            f = self._io(self.factors.get_factor, factor_id) if _ok_text(factor_id) else None
            if (f is None or f.realm != realm.value or f.subject_id != subject_id
                    or f.status is not FactorStatus.PENDING):
                raise IdentityError("IDN-062")
            if self.idn.now() - f.created_at >= self.cfg.pending_ttl:
                self._io(self.factors.delete_factor, factor_id)
                raise IdentityError("IDN-062")
            others = [x for x in self._active(realm, subject_id) if x.factor_id != factor_id]
            if not f.bootstrap:
                if claims is None or self._caller(claims) != (realm, subject_id):
                    raise IdentityError("IDN-013")
                if others:
                    self.idn.require_step_up(claims)
            self._attempt(realm, subject_id)
            counter = totp.verify(self._key_of(f), code, self.idn.now(), -1)
            if counter is None:
                raise IdentityError("IDN-060")
            if not self._io(self.factors.activate_factor, factor_id, counter):
                raise IdentityError("IDN-062")
            self._clear(realm, subject_id)
            if others:
                return ()
            self._set_enrolled(realm, subject_id, True)
            return self._new_recovery(realm, subject_id)

    # -- recovery codes ---------------------------------------------------
    def _new_recovery(self, realm: Realm, subject_id: str) -> tuple:
        codes = [recovery.new_code(self._random) for _ in range(self.cfg.recovery_codes)]
        records = []
        for c in codes:
            salt = self._random(16)
            records.append(RecoveryRecord(self._random(8).hex(), realm.value, subject_id, salt,
                                          recovery.hash_code(recovery.normalise(c), salt, self.cfg.kdf_iterations)))
        records = tuple(records)
        self._io(self.factors.replace_recovery, realm.value, subject_id, records)
        return tuple(codes)

    def regenerate_recovery_codes(self, claims: AccessClaims) -> tuple:
        realm, sid = self._caller_safe(claims)
        with self.idn.decision("mfa.recovery_regenerate", realm, sid, getattr(claims, "tenant", None)):
            realm, sid = self._caller(claims)
            self.idn.require_step_up(claims)
            if not self._active(realm, sid):
                raise IdentityError("IDN-062")
            return self._new_recovery(realm, sid)

    # -- removal ----------------------------------------------------------
    def remove_factor(self, claims: AccessClaims, factor_id) -> None:
        realm, sid = self._caller_safe(claims)
        with self.idn.decision("mfa.remove", realm, sid, getattr(claims, "tenant", None)):
            realm, sid = self._caller(claims)
            self.idn.require_step_up(claims)
            f = self._io(self.factors.get_factor, factor_id) if _ok_text(factor_id) else None
            if f is None or f.realm != realm.value or f.subject_id != sid:
                raise IdentityError("IDN-063")
            active = self._active(realm, sid)
            last = f.status is FactorStatus.ACTIVE and len(active) == 1
            if last and self._must_keep(claims, realm):
                raise IdentityError("IDN-062")
            self._io(self.factors.delete_factor, factor_id)
            if last:
                self._io(self.factors.replace_recovery, realm.value, sid, ())
                self._set_enrolled(realm, sid, False)

    def _must_keep(self, claims, realm: Realm) -> bool:
        """The last factor stays when policy demands MFA: always for staff, and for
        a customer when the tenant of this session demands it (Q on other tenants)."""
        if realm is Realm.STAFF:
            return True
        m = self.idn.active_membership(claims.subject, claims.tenant)
        roles = resolve_roles(self.idn.roles, claims.tenant, claims.subject)
        tenant = self.idn.repo.get_tenant(claims.tenant)
        return mfa_required(roles, tenant_mfa_for_all=tenant.mfa_for_all,
                            membership_flag=m.mfa_required)
