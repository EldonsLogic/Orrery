"""Injected secrets and limits for MFA (SEC-005): the contracts a KMS, the
identity provider and the gateway must meet. See service.py for the rules."""

from typing import Optional, Protocol


class SecretBox(Protocol):
    """Seals and opens TOTP keys (a KMS in production). MUST be authenticated
    encryption (AEAD) with `context` as associated data: `open` raises when the
    sealed bytes or the context differ from those used to seal. The service
    passes "realm:subject_id:factor_id", so a sealed secret copied to another
    factor row or another subject's row cannot be opened."""

    def seal(self, plaintext: bytes, context: str) -> bytes: ...
    def open(self, sealed: bytes, context: str) -> bytes: ...


class PasswordVerifier(Protocol):
    def verify(self, realm: str, subject_id: str, password: str) -> bool:
        """True only for the right password. For an unknown subject it must do
        the same work as for a known one (a dummy hash). An exception means the
        check could not run (IDN-064, not counted as a guess)."""


class BootstrapAuthority(Protocol):
    def consume(self, staff_id: str, ticket: str, now: int) -> Optional[int]:
        """Single use: the first call with a valid admin-issued ticket for that
        staff id returns the time it was issued; any later call, and any unknown
        or mismatched ticket, returns None. The service refuses a ticket older
        than MfaConfig.bootstrap_ttl; the authority may expire it sooner."""


class SourceThrottle(Protocol):
    def allow(self, source: str, now: int) -> bool:
        """Per-source and global limit for unauthenticated sign-in and staff
        bootstrap (the gateway's limiter). Required before any route exposes
        them (Q-224)."""
