"""Test doubles for SEC-005. Every secret is built at run time; none is a literal."""

import hashlib
import hmac
import secrets

from identity import Realm
from identity.mfa import InMemoryFactorRepository, MfaConfig, MfaService
from identity.mfa import totp


class FakeBox:
    """Stand-in for a KMS: keystream from a per-run key, bound to the context."""

    def __init__(self):
        self.k = secrets.token_bytes(32)

    def _stream(self, context, n):
        return hmac.new(self.k, context.encode(), hashlib.sha256).digest()[:n]

    def seal(self, plaintext, context):
        return bytes(a ^ b for a, b in zip(plaintext, self._stream(context, len(plaintext))))

    open = seal


class FakePasswords:
    def __init__(self):
        self.good = {}

    def set(self, realm, sid):
        pw = secrets.token_urlsafe(12)
        self.good[(realm, sid)] = pw
        return pw

    def verify(self, realm, subject_id, password):
        return hmac.compare_digest(self.good.get((realm, subject_id), "x" * 99).encode(),
                                   password.encode())


class FakeBootstrap:
    def __init__(self):
        self.tickets = {}

    def issue(self, staff_id):
        t = secrets.token_urlsafe(12)
        self.tickets[staff_id] = t
        return t

    def consume(self, staff_id, ticket):
        return self.tickets.pop(staff_id, None) == ticket


class Hooked(InMemoryFactorRepository):
    """Runs `on_factors_for` right after a snapshot is returned (interleaving tests)."""

    on_factors_for = None
    fail = False

    def factors_for(self, realm, subject_id):
        if self.fail:
            raise RuntimeError("store down")
        snap = super().factors_for(realm, subject_id)
        hook, self.on_factors_for = self.on_factors_for, None
        if hook:
            hook(snap)
        return snap


FAST = MfaConfig(kdf_iterations=1000)


class MfaWorld:
    def __init__(self, w, repo=None):
        self.w = w
        self.factors = repo or Hooked()
        self.passwords, self.bootstrap, self.box = FakePasswords(), FakeBootstrap(), FakeBox()
        self.svc = MfaService(idn=w.idn, factors=self.factors, box=self.box,
                              passwords=self.passwords, bootstrap=self.bootstrap, config=FAST)

    def key(self, factor_id):
        f = self.factors.get_factor(factor_id)
        return self.box.open(f.sealed_secret, f.factor_id)

    def code(self, factor_id, offset=0):
        return totp.hotp(self.key(factor_id), totp.counter_at(self.w.clock()) + offset)

    def enrol_customer(self, pid="p-clerk", tenant="t-a"):
        """First factor via a live non-MFA session; returns (factor_id, recovery codes)."""
        claims = self.w.claims(pid, tenant, mfa=False)
        start = self.svc.begin_totp_enrolment(claims)
        codes = self.svc.confirm_totp_enrolment(
            Realm.CUSTOMER, pid, start.factor_id, self.code(start.factor_id), claims=claims)
        return start.factor_id, codes
