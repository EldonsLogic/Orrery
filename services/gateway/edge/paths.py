"""Path policy: deny by default. Only registered routes under our own /v1/ namespace are routable."""
from __future__ import annotations

import re
from urllib.parse import unquote

OWN_PREFIX = "/v1/"
ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


def normalise_path(raw_path: str) -> str | None:
    """Return a canonical path, or None when the path is malformed or an evasion attempt.

    Rejects: query/fragment in the path, backslashes, control characters, double encoding, empty
    segments, dot segments, path parameters (`;`) and anything outside a conservative segment alphabet.
    """
    if not isinstance(raw_path, str) or not raw_path.startswith("/") or len(raw_path) > 2048:
        return None
    if any(c in raw_path for c in "?#\;") or any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw_path):
        return None
    try:
        decoded = unquote(raw_path, errors="strict") if "%" in raw_path else raw_path
    except UnicodeDecodeError:
        return None
    if "%" in decoded or any(c in decoded for c in "?#\;") or any(ord(c) < 0x20 or ord(c) == 0x7F for c in decoded):
        return None  # double encoding or a control character hidden behind encoding
    segments = decoded[1:].split("/")
    if segments and segments[-1] == "":
        segments.pop()  # one trailing slash is tolerated
    for seg in segments:
        if seg in ("", ".", "..") or not _SEGMENT_RE.match(seg):
            return None
    return "/" + "/".join(segments)


def is_own_path(path: str | None) -> bool:
    return path is not None and (path + "/").startswith(OWN_PREFIX) and path != OWN_PREFIX.rstrip("/")
