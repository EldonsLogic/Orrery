"""Ports of the pack publishing workflow. Real implementations (the reviewed trusted_signers.json, WebAuthn
verification, the SEC-008 AuditStore, the versioned pack store and the tenant registry) come later; `fakes.py`
holds in-memory stand-ins for tests."""
from __future__ import annotations

from typing import Optional, Protocol


class TrustedSigners(Protocol):
    def accountant_name(self, market: str, signer_id: str) -> Optional[str]:
        """Name when the signer is on the market's accountant roster (Q-653), else None."""

    def founder_login(self, signer_id: str) -> Optional[str]:
        """GitHub login when the signer is a founder, else None."""


class SignerVerifier(Protocol):
    def verify(self, signer_id: str, statement_digest: str, signature: Optional[dict], key_env: str) -> bool:
        """True only when `signature` is the signer's own assertion over the statement digest. In production a
        missing signature is False (Q-652)."""


class AuditStore(Protocol):
    def write(self, audit_id: str, entry: dict) -> None:
        """Append one record. Raise on any failure: the caller then refuses the change (Q-656)."""


class PackStore(Protocol):
    def latest_index(self, country: str) -> Optional[bytes]: ...
    def get_request(self, request_id: str) -> Optional[tuple]:
        """(fingerprint, result) of an earlier request id, or None."""
    def get_pin(self, tenant_id: str, country: str) -> Optional[dict]: ...
    def commit_publish(self, country: str, expected_seq: int, record: dict, index_bytes: bytes,
                       request_id: str, fingerprint: str, result: dict) -> None:
        """Atomic: raise if the stored index is not at `expected_seq`; else store record and index and the request."""
    def commit_pin(self, tenant_id: str, country: str, expected_pin_seq: int, pin: dict,
                   request_id: str, fingerprint: str, result: dict) -> None:
        """Atomic compare-and-set on the pin sequence."""
