"""Deterministic integer source from SHA-256 (independent of the `random` module's version-specific behaviour)."""
from __future__ import annotations

import hashlib


class Rng:
    def __init__(self, seed: int, label: str):
        self._key = f"{seed}|{label}"
        self._n = 0

    def int(self, lo: int, hi: int) -> int:
        self._n += 1
        digest = hashlib.sha256(f"{self._key}|{self._n}".encode()).digest()
        return lo + int.from_bytes(digest[:8], "big") % (hi - lo + 1)


def ranked(seed: int, label: str, pool: list) -> list:
    """The pool in a seed-dependent, stable order."""
    return sorted(pool, key=lambda x: hashlib.sha256(f"{seed}|{label}|{x}".encode()).hexdigest())
