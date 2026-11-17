"""Monotonic Crockford Base32 ULID generator (pure Python stdlib).

Matches Contract 4 event_id pattern ``^[0-7][0-9A-HJKMNP-TV-Z]{25}$``.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Callable

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_MAX_RAND = (1 << 80) - 1


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def is_valid_ulid(value: object) -> bool:
    return isinstance(value, str) and bool(ULID_RE.fullmatch(value))


class UlidGenerator:
    """Thread-safe monotonic ULID generator compatible with Contract 4 events."""

    def __init__(self, time_ms: Callable[[], int] | None = None):
        self._time_ms = time_ms or (lambda: int(time.time() * 1000))
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand = 0

    def generate(self) -> str:
        with self._lock:
            now_ms = int(self._time_ms())
            if now_ms < 0:
                raise ValueError("Timestamp must be non-negative")
            if now_ms == self._last_ms:
                rand = self._last_rand + 1
                if rand > _MAX_RAND:
                    now_ms += 1
                    rand = int.from_bytes(os.urandom(10), "big")
            else:
                rand = int.from_bytes(os.urandom(10), "big")
            self._last_ms = now_ms
            self._last_rand = rand
            return _encode(now_ms, 10) + _encode(rand, 16)
