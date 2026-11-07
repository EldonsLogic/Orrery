"""ULID generate and validate. Standard library only.

26 characters of Crockford base32: 48-bit millisecond time, 80 random bits. Within one
millisecond the random part is incremented, so ids from one generator strictly increase
(also when the clock stands still or steps back). Uppercase only; the first character is 0-7.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Callable

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
_MAX_MS = (1 << 48) - 1
_RAND_BITS = 80


def encode(value: int) -> str:
    out = []
    for _ in range(26):
        out.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def is_valid_ulid(value: object) -> bool:
    return isinstance(value, str) and ULID_RE.fullmatch(value) is not None


def ulid_time_ms(value: str) -> int:
    if not is_valid_ulid(value):
        raise ValueError("not a ULID")
    n = 0
    for ch in value:
        n = (n << 5) | ALPHABET.index(ch)
    return n >> _RAND_BITS


class UlidGenerator:
    def __init__(self, clock_ms: Callable[[], int] | None = None,
                 randbytes: Callable[[int], bytes] | None = None):
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._rand = randbytes or os.urandom
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand = 0

    def _fresh(self) -> int:
        return int.from_bytes(self._rand(10), "big")

    def generate(self) -> str:
        with self._lock:
            ms = max(int(self._clock_ms()), self._last_ms)
            if ms == self._last_ms:
                r = self._last_rand + 1
                if r >> _RAND_BITS:  # overflow: move to the next millisecond
                    ms += 1
                    r = self._fresh()
            else:
                r = self._fresh()
            if ms > _MAX_MS:
                raise ValueError("ULID time out of range")
            self._last_ms, self._last_rand = ms, r
            return encode((ms << _RAND_BITS) | r)


_default = UlidGenerator()


def new_ulid() -> str:
    return _default.generate()
