"""TOTP (RFC 6238 over RFC 4226 HOTP, HMAC-SHA1, 6 digits, 30 s) from the
standard library only. Verification evaluates every counter in the window with
no early exit and compares in constant time. Replay protection is the caller's
job: accept only a counter greater than the factor's stored last-used counter
and advance it with a compare-and-set (see store.FactorRepository)."""

import base64
import hashlib
import hmac
import struct
from typing import Optional
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
DRIFT_STEPS = 1  # one step either side of the current one
SECRET_BYTES = 20  # RFC 4226 recommends 160 bits


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def counter_at(now: int, period: int = PERIOD) -> int:
    return now // period


def well_formed(code, digits: int = DIGITS) -> bool:
    return isinstance(code, str) and len(code) == digits and code.isascii() and code.isdigit()


def verify(key: bytes, code, now: int, last_counter: int, *, digits: int = DIGITS,
           period: int = PERIOD, drift: int = DRIFT_STEPS) -> Optional[int]:
    """Return the matched counter, or None. Only a counter above `last_counter`
    counts (a code, or an older one, is never accepted twice)."""
    if not well_formed(code, digits):
        return None
    current = counter_at(now, period)
    matched = None
    for c in range(current - drift, current + drift + 1):
        if c < 0:
            continue
        # no short-circuit: every candidate is computed and compared
        if hmac.compare_digest(hotp(key, c, digits).encode(), code.encode()) and c > last_counter:
            matched = c if matched is None else max(matched, c)
    return matched


def b32(key: bytes) -> str:
    return base64.b32encode(key).decode("ascii").rstrip("=")


def provisioning_uri(key: bytes, account: str, issuer: str) -> str:
    """otpauth URI for authenticator apps. Contains the secret: show once, never log."""
    label = f"{quote(issuer, safe='')}:{quote(account, safe='')}"
    return (f"otpauth://totp/{label}?secret={b32(key)}&issuer={quote(issuer, safe='')}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")
