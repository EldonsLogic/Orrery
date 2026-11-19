"""MFA for owners, staff and support access (SEC-005, ADR-0007 items 6 and 12).

Sign-in is password then factor; a successful second factor mints a token with
mfa=true and auth_time=now through the existing IdentityService. Rules:

- Sign-in: every failure is the same IDN-060 (wrong password, missing code,
  wrong TOTP, wrong recovery code), and the factor work (TOTP over every slot,
  PBKDF2 over a fixed number of recovery slots) runs whether or not the
  password was right, so neither the answer nor its timing confirms a password.
  Membership state (IDN-009/010/011) is revealed only after password and
  factor both match, and before the factor is consumed.
- Throttling: failed password guesses count per (subject, source) and the
  optional SourceThrottle limits each source; the account key (which locks the
  subject everywhere) counts only attempts whose password verified, so an
  attacker without the password cannot lock the owner out (residual: Q-224).
- First customer factor (H1): needs proof of the password now, either a
  session whose auth_time is within STEP_UP_MAX_AGE (refresh keeps the old
  auth_time, so a refreshed or stale session fails) or the password re-entered
  in `begin_totp_enrolment`. Any further factor, removal, recovery
  regeneration and every staff factor need a recent MFA step-up. A staff
  first factor needs an admin-issued, single-use, expiring bootstrap ticket.
- Any change of a subject's active factors ends every session of that person
  (all tenants) or staff member, and `mfa_enrolled` is re-derived from the
  active factors. The last factor is removed only by an atomic store write
  that refuses when policy in any of the person's tenants demands MFA.
- Every store, sealing or provider failure denies (IDN-064) and is not counted
  as a guess. Secrets are injected opaque values: a SecretBox (AEAD bound to
  realm, subject and factor) seals TOTP keys; a PasswordVerifier,
  BootstrapAuthority and SourceThrottle come from the identity provider and
  gateway. Nothing secret is audited or put in an error."""

import secrets
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from ..errors import IdentityError
from ..models import Realm, TokenPair
from ..policy import mfa_required, resolve_roles
from ..service import STEP_UP_MAX_AGE, IdentityService
from ..tokens import AccessClaims, check_live
from . import recovery, totp
from .ports import BootstrapAuthority, PasswordVerifier, SecretBox, SourceThrottle
from .store import FactorRepository, FactorStatus, RecoveryRecord, TotpFactor

MAX_ID = 256
MAX_SECRET_INPUT = 256
UNKNOWN_SOURCE = "unknown"

# Padding material for equal work; random per process, never a secret of anyone.
_PAD_KEY = secrets.token_bytes(totp.SECRET_BYTES)
_PAD_SALT = secrets.token_bytes(16)
_PAD_DIGEST = bytes(32)


@dataclass(frozen=True)
class MfaConfig:
    max_attempts: int = 5
    attempt_window: int = 900
    lockout: int = 900
    pending_ttl: int = 600
    max_factors: int = 3
    recovery_codes: int = 10
    kdf_iterations: int = 60_000
    bootstrap_ttl: int = 3600
    issuer_label: str = "Platform"


@dataclass(frozen=True)
class EnrolmentStart:
    factor_id: str
    secret: str = field(repr=False)  # base32, shown once
    uri: str = field(repr=False)


def _ok_text(v) -> bool:
    return isinstance(v, str) and 0 < len(v) <= MAX_ID


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _context(f: TotpFactor) -> str:
    return f"{f.realm}:{f.subject_id}:{f.factor_id}"


class MfaService:
    def __init__(self, *, idn: IdentityService, factors: FactorRepository, box: SecretBox,
                 passwords: PasswordVerifier, bootstrap: Optional[BootstrapAuthority] = None,
                 sources: Optional[SourceThrottle] = None,
                 rng: Callable[[int], bytes] = secrets.token_bytes,
                 config: MfaConfig = MfaConfig()):
        c = config
        if (min(c.max_attempts, c.attempt_window, c.lockout, c.pending_ttl, c.max_factors,
                c.recovery_codes, c.kdf_iterations, c.bootstrap_ttl) <= 0):
            raise IdentityError("IDN-051")
        self.idn, self.factors, self.box, self.passwords = idn, factors, box, passwords
        self.bootstrap, self.sources, self.rng, self.cfg = bootstrap, sources, rng, c

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
    def _account_key(realm: Realm, subject_id: str) -> str:
        return f"{realm.value}:{subject_id}"

    @staticmethod
    def _source_key(realm: Realm, subject_id: str, source: str) -> str:
        return f"pw:{realm.value}:{subject_id}:{source}"

    @staticmethod
    def _bootstrap_key(staff_id: str) -> str:
        return f"boot:staff:{staff_id}"

    def _random(self, n: int) -> bytes:
        raw = self._io(self.rng, n)
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != n:
            raise IdentityError("IDN-064")
        return bytes(raw)

    def _caller(self, claims) -> tuple:
        """A live, unrevoked session of this realm; returns (realm, subject)."""
        check_live(claims, self.idn.now())
        if claims.realm is Realm.CUSTOMER:
            m = self._io(self.idn.active_membership, claims.subject, claims.tenant)
            if m.session_version != claims.session_version:
                raise IdentityError("IDN-009")
        else:
            staff = self._io(self.idn.repo.get_staff, claims.subject)
            if staff is None or not staff.active:
                raise IdentityError("IDN-010")
            if staff.session_version != claims.session_version:
                raise IdentityError("IDN-009")
        return claims.realm, claims.subject

    def _mine(self, realm: Realm, subject_id: str) -> tuple:
        return tuple(f for f in self._io(self.factors.factors_for, realm.value, subject_id))

    def _active(self, realm: Realm, subject_id: str) -> tuple:
        return tuple(f for f in self._mine(realm, subject_id) if f.status is FactorStatus.ACTIVE)

    def _after_change(self, realm: Realm, subject_id: str) -> None:
        """The active factor set changed: re-derive mfa_enrolled from it and end
        every session (all tenants of the person, or the staff member's)."""
        enrolled = bool(self._active(realm, subject_id))
        repo = self.idn.repo
        if realm is Realm.CUSTOMER:
            person = self._io(repo.get_person, subject_id)
            if person is None:
                raise IdentityError("IDN-010")
            if person.mfa_enrolled is not enrolled:
                self._io(repo.put_person, replace(person, mfa_enrolled=enrolled))
            self._io(self.idn.end_person_sessions, subject_id)
        else:
            staff = self._io(repo.get_staff, subject_id)
            if staff is None:
                raise IdentityError("IDN-010")
            self._io(repo.put_staff, replace(staff, mfa_enrolled=enrolled,
                                             session_version=staff.session_version + 1))

    def _count(self, key: str) -> None:
        a = self._io(self.factors.begin_attempt, key, self.idn.now(), self.cfg.attempt_window,
                     self.cfg.max_attempts, self.cfg.lockout)
        if a.allowed is not True:
            raise IdentityError("IDN-061")

    def _attempt(self, realm: Realm, subject_id: str) -> None:
        self._count(self._account_key(realm, subject_id))

    def _clear_key(self, key: str) -> None:
        self._io(self.factors.clear_attempts, key)

    def _clear(self, realm: Realm, subject_id: str) -> None:
        self._clear_key(self._account_key(realm, subject_id))

    def _throttle(self, source: str) -> None:
        if self.sources is not None and self._io(
                self.sources.allow, source, self.idn.now()) is not True:
            raise IdentityError("IDN-061")

    def _password_ok(self, realm: Realm, subject_id: str, password: str, counted: str) -> bool:
        """A provider error is not a guess: the counted attempt is released."""
        try:
            ok = self.passwords.verify(realm.value, subject_id, password)
        except Exception:
            try:
                self.factors.release_attempt(counted)
            except Exception:
                pass
            raise IdentityError("IDN-064") from None
        return ok is True

    @staticmethod
    def _params(f: TotpFactor) -> dict:
        if not totp.params_ok(f.algorithm, f.digits, f.period):
            raise IdentityError("IDN-064")
        return {"digits": f.digits, "period": f.period, "algorithm": f.algorithm}

    def _key_of(self, f: TotpFactor) -> bytes:
        key = self._io(self.box.open, f.sealed_secret, _context(f))
        if not isinstance(key, (bytes, bytearray)) or not key:
            raise IdentityError("IDN-064")
        return bytes(key)

    # -- second factor: match (uniform work, no side effect), then consume ----
    def _match(self, realm: Realm, subject_id: str, code, active: tuple):
        """Return ("totp", ((factor, counter), ...)) or ("recovery", record) or
        None. Work does not depend on whether the password matched, on how many
        factors exist (up to max_factors) or on how many recovery codes are left."""
        if not isinstance(code, str) or len(code) > MAX_SECRET_INPUT:
            return None
        now, n = self.idn.now(), self.cfg.kdf_iterations
        if code.isascii() and code.isdigit() and len(code) in totp.ALLOWED_DIGITS:
            hits = []
            for f in active:
                c = totp.verify(self._key_of(f), code, now, f.last_counter, **self._params(f))
                if c is not None:
                    hits.append((f, c))
            for _ in range(max(0, self.cfg.max_factors - len(active))):
                totp.verify(_PAD_KEY, code, now, -1)
            return ("totp", tuple(hits)) if hits else None
        norm = recovery.normalise(code)
        if norm is None:
            return None
        unused = [r for r in self._io(self.factors.recovery_for, realm.value, subject_id)
                  if not r.used]
        found = None
        for i in range(max(self.cfg.recovery_codes, len(unused))):  # no early exit
            if i < len(unused):
                r = unused[i]
                if recovery.matches(norm, r.salt, r.digest, n) and found is None:
                    found = r
            else:
                recovery.matches(norm, _PAD_SALT, _PAD_DIGEST, n)
        return ("recovery", found) if found is not None else None

    def _consume(self, realm: Realm, subject_id: str, match) -> str:
        kind, value = match
        if kind == "totp":
            with self.idn.decision("mfa.verify", realm, subject_id, None, "totp"):
                for f, counter in value:  # lost compare-and-set = replay or race
                    if self._io(self.factors.advance_counter, f.factor_id, f.last_counter, counter):
                        return "totp"
                raise IdentityError("IDN-060")
        with self.idn.decision("mfa.recovery_use", realm, subject_id, None):
            if not self._io(self.factors.consume_recovery, realm.value, subject_id, value.code_id):
                raise IdentityError("IDN-060")
        return "recovery"

    def _precheck(self, realm: Realm, subject_id: str, tenant_id) -> None:
        """Membership and identity state, checked before a factor is consumed."""
        if realm is Realm.CUSTOMER:
            self._io(self.idn.active_membership, subject_id, tenant_id)
            return
        staff = self._io(self.idn.repo.get_staff, subject_id)
        if staff is None or not staff.active:
            raise IdentityError("IDN-010")

    # -- sign-in ----------------------------------------------------------
    def sign_in(self, realm: Realm, subject_id, password, code=None, *, tenant_id=None,
                source=None) -> TokenPair:
        """Password, then (when a factor is enrolled) the factor. `source` is the
        gateway's client identifier (for example a keyed hash of the address);
        without it every caller shares one per-subject password counter."""
        audit_realm = realm if isinstance(realm, Realm) else Realm.CUSTOMER
        with self.idn.decision("mfa.signin", audit_realm,
                               subject_id if _ok_text(subject_id) else None,
                               tenant_id if _ok_text(tenant_id) else None):
            if (not isinstance(realm, Realm) or not _ok_text(subject_id)
                    or not isinstance(password, str) or not 0 < len(password) <= MAX_SECRET_INPUT
                    or (code is not None and not isinstance(code, str))
                    or (source is not None and not _ok_text(source))
                    or (realm is Realm.CUSTOMER and not _ok_text(tenant_id))
                    or (realm is Realm.STAFF and tenant_id is not None)):
                raise IdentityError("IDN-060")
            src = source if source is not None else UNKNOWN_SOURCE
            self._throttle(src)
            pw_key = self._source_key(realm, subject_id, src)
            self._count(pw_key)  # password guesses: per (subject, source), before evaluation
            password_ok = self._password_ok(realm, subject_id, password, pw_key)
            active = self._active(realm, subject_id)
            match = self._match(realm, subject_id, code, active) if code is not None else None
            if not password_ok:
                raise IdentityError("IDN-060")
            self._attempt(realm, subject_id)  # account lock: only password-proven attempts
            if active:
                if match is None:
                    raise IdentityError("IDN-060")
                self._precheck(realm, subject_id, tenant_id)
                self._consume(realm, subject_id, match)
            elif code is not None:
                raise IdentityError("IDN-060")
            self._clear(realm, subject_id)
            self._clear_key(pw_key)
            return self._issue(realm, subject_id, tenant_id, mfa=bool(active))

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
            active = self._active(realm, sid)
            if not active:
                raise IdentityError("IDN-013")
            self._attempt(realm, sid)
            match = self._match(realm, sid, code, active)
            if match is None:
                raise IdentityError("IDN-060")
            self._consume(realm, sid, match)
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
        factor = TotpFactor(self._random(16).hex(), realm.value, subject_id, b"",
                            self.idn.now(), bootstrap=bootstrap)
        key = self._random(totp.SECRET_BYTES)
        sealed = self._io(self.box.seal, key, _context(factor))
        if not isinstance(sealed, (bytes, bytearray)) or not sealed:
            raise IdentityError("IDN-064")
        self._io(self.factors.put_factor, replace(factor, sealed_secret=bytes(sealed)))
        return EnrolmentStart(factor.factor_id, totp.b32(key),
                              totp.provisioning_uri(key, subject_id, self.cfg.issuer_label))

    def _first_factor_proof(self, claims, realm: Realm, subject_id: str, password) -> None:
        """H1: a first customer factor needs the password proven now. Without a
        password the session's auth_time (set at password sign-in, unchanged by
        refresh) must be within STEP_UP_MAX_AGE; otherwise the password is
        re-verified here, counted on the account key, failing as IDN-060."""
        if password is None:
            if self.idn.now() - claims.auth_time > STEP_UP_MAX_AGE:
                raise IdentityError("IDN-013")
            return
        if not isinstance(password, str) or not 0 < len(password) <= MAX_SECRET_INPUT:
            raise IdentityError("IDN-060")
        key = self._account_key(realm, subject_id)
        self._count(key)
        if not self._password_ok(realm, subject_id, password, key):
            raise IdentityError("IDN-060")
        self._clear_key(key)

    def begin_totp_enrolment(self, claims: AccessClaims, password=None) -> EnrolmentStart:
        """Customer first factor: proof of the password now (see
        `_first_factor_proof`). Any further factor, or a staff factor, needs a
        recent MFA step-up."""
        realm, sid = self._caller_safe(claims)
        with self.idn.decision("mfa.enrol_begin", realm, sid, getattr(claims, "tenant", None)):
            realm, sid = self._caller(claims)
            if self._active(realm, sid) or realm is Realm.STAFF:
                self.idn.require_step_up(claims)
            else:
                self._first_factor_proof(claims, realm, sid, password)
            return self._begin(realm, sid, bootstrap=False)

    def begin_staff_bootstrap(self, staff_id, ticket, *, source=None) -> EnrolmentStart:
        """First staff factor, before any staff token can exist: an admin-issued
        single-use ticket, younger than bootstrap_ttl, proves the enrolment is
        authorised. Unknown, inactive or already-enrolled staff and a bad, used
        or expired ticket all give IDN-060; attempts are counted per staff id."""
        with self.idn.decision("mfa.enrol_begin", Realm.STAFF,
                               staff_id if _ok_text(staff_id) else None, None, "bootstrap"):
            if (not _ok_text(staff_id) or not _ok_text(ticket)
                    or (source is not None and not _ok_text(source))):
                raise IdentityError("IDN-060")
            self._throttle(source if source is not None else UNKNOWN_SOURCE)
            key = self._bootstrap_key(staff_id)
            self._count(key)
            now = self.idn.now()
            staff = self._io(self.idn.repo.get_staff, staff_id)
            enrolled = bool(self._active(Realm.STAFF, staff_id))
            issued = (self._io(self.bootstrap.consume, staff_id, ticket, now)
                      if self.bootstrap is not None else None)
            fresh = _is_int(issued) and 0 <= now - issued < self.cfg.bootstrap_ttl
            if staff is None or not staff.active or enrolled or not fresh:
                raise IdentityError("IDN-060")
            self._clear_key(key)
            return self._begin(Realm.STAFF, staff_id, bootstrap=True)

    def confirm_totp_enrolment(self, realm: Realm, subject_id, factor_id, code, *,
                               claims: Optional[AccessClaims] = None) -> tuple:
        """Prove the authenticator works. Returns the recovery codes (shown once)
        when this is the subject's first active factor, else an empty tuple.
        Activation ends every existing session of the subject."""
        audit_realm = realm if isinstance(realm, Realm) else Realm.CUSTOMER
        with self.idn.decision("mfa.enrol_confirm", audit_realm,
                               subject_id if _ok_text(subject_id) else None, None):
            if not isinstance(realm, Realm) or not _ok_text(subject_id):
                raise IdentityError("IDN-062")
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
            counter = totp.verify(self._key_of(f), code, self.idn.now(), -1, **self._params(f))
            if counter is None:
                raise IdentityError("IDN-060")
            count = self._io(self.factors.activate_factor, factor_id, counter)
            if not _is_int(count) or count < 1:
                raise IdentityError("IDN-062")
            self._clear(realm, subject_id)
            codes = self._new_recovery(realm, subject_id) if count == 1 else ()
            self._after_change(realm, subject_id)
            return codes

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
            keep_one = self._must_keep(realm, sid)
            # one atomic write: never leaves zero factors when policy demands one
            left = self._io(self.factors.remove_factor, factor_id, realm.value, sid, keep_one)
            if not _is_int(left) or left < 0:
                raise IdentityError("IDN-062")
            if f.status is FactorStatus.ACTIVE:
                if left == 0:
                    self._io(self.factors.clear_recovery_if_no_active, realm.value, sid)
                self._after_change(realm, sid)

    def _must_keep(self, realm: Realm, subject_id: str) -> bool:
        """The last factor stays when policy demands MFA: always for staff, and
        for a customer when any of the person's memberships (any tenant) does."""
        if realm is Realm.STAFF:
            return True
        repo = self.idn.repo
        for m in self._io(repo.memberships_for_person, subject_id):
            tenant = self._io(repo.get_tenant, m.tenant_id)
            roles = resolve_roles(self.idn.roles, m.tenant_id, subject_id)
            if mfa_required(roles, tenant_mfa_for_all=bool(tenant is not None and tenant.mfa_for_all),
                            membership_flag=m.mfa_required):
                return True
        return False
