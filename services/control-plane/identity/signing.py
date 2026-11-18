"""Signer interface. Production signing keys, algorithm and the identity provider
come from the identity-provider spike (ADR-0007 item 5); nothing here is a
production signer. The HMAC signer exists for tests only."""

import hashlib
import hmac
from typing import Protocol

from .errors import IdentityError

FORBIDDEN_ALGS = frozenset({"", "none", "None", "NONE"})


class Signer(Protocol):
    alg: str  # pinned algorithm name written to and required in the header
    key_id: str

    def sign(self, data: bytes) -> bytes: ...

    def verify(self, data: bytes, signature: bytes) -> bool: ...


class TestOnlyHmacSha256Signer:
    """TEST ONLY. Symmetric HMAC-SHA256 from the standard library. Not for
    production: a shared key lets any verifier mint tokens."""

    alg = "HS256"
    __test__ = False  # not a pytest test class

    def __init__(self, key: bytes, key_id: str):
        if not isinstance(key, bytes) or len(key) < 32 or not key_id:
            raise IdentityError("IDN-051")
        self._key = key
        self.key_id = key_id

    def sign(self, data: bytes) -> bytes:
        return hmac.new(self._key, data, hashlib.sha256).digest()

    def verify(self, data: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(data), signature)

    def __repr__(self) -> str:  # never print the key
        return f"TestOnlyHmacSha256Signer(key_id={self.key_id!r})"


def check_signer(signer) -> None:
    alg = getattr(signer, "alg", "")
    if not isinstance(alg, str) or alg in FORBIDDEN_ALGS or not getattr(signer, "key_id", ""):
        raise IdentityError("IDN-051")
