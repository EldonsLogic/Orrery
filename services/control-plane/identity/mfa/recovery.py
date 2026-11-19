"""Single-use recovery codes. Generated at runtime from an injected random
source, shown once, stored only as salted PBKDF2-HMAC-SHA256 hashes (a fresh
salt per code). Verification checks every unused code with no early exit."""

import hashlib
import hmac
from typing import Callable, Optional

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
GROUPS, GROUP_LEN = 2, 5  # 10 symbols, 50 bits


def new_code(rng: Callable[[int], bytes]) -> str:
    raw = rng(GROUPS * GROUP_LEN)
    chars = [ALPHABET[b % len(ALPHABET)] for b in raw]  # 32 symbols: no modulo bias
    return "-".join("".join(chars[i:i + GROUP_LEN]) for i in range(0, len(chars), GROUP_LEN))


def normalise(code) -> Optional[str]:
    if not isinstance(code, str) or len(code) > 32:
        return None
    flat = code.replace("-", "").replace(" ", "").upper()
    if len(flat) != GROUPS * GROUP_LEN or any(ch not in ALPHABET for ch in flat):
        return None
    return flat


def hash_code(code: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt, iterations)


def matches(code: str, salt: bytes, digest: bytes, iterations: int) -> bool:
    return hmac.compare_digest(hash_code(code, salt, iterations), digest)
