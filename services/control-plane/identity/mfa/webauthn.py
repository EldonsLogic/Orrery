"""WebAuthn / passkey extension point (interface only; see the open question
added by SEC-005). ADR-0007 item 1 names passkeys; the identity-provider spike
decides whether they live here or behind the provider. Nothing implements this
yet: a factor kind other than TOTP is refused until an implementation is
registered and reviewed."""

from typing import Optional, Protocol


class WebAuthnVerifier(Protocol):
    def begin_registration(self, realm: str, subject_id: str) -> dict:
        """Return an opaque challenge for the browser; store it server side, single use."""

    def finish_registration(self, realm: str, subject_id: str, response: dict) -> Optional[bytes]:
        """Return the sealed credential record to store, or None when invalid."""

    def begin_assertion(self, realm: str, subject_id: str) -> dict:
        """Return an opaque challenge for sign-in."""

    def finish_assertion(self, realm: str, subject_id: str, response: dict,
                         last_sign_count: int) -> Optional[int]:
        """Return the new signature counter on success (must exceed last_sign_count), else None."""
