"""Canonical content digest and input checks. Plain data only: dict, list, tuple, str, int, bool, None. Floats,
sets, generators and other iterables, non-string keys, NaN, deep or huge values are refused, so one content has one
digest and no input is consumed twice."""
from __future__ import annotations

import hashlib
import json
import re

from .errors import ReviewError

MAX_DEPTH, MAX_NODES, MAX_STR, MAX_TOTAL = 12, 20000, 20000, 1_000_000  # MAX_TOTAL: characters over all strings and keys
ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
TENANT_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(s, budget):
    budget[1] -= len(s)
    try:
        s.encode("utf-8")  # a lone surrogate is a coded refusal, not a crash
    except UnicodeEncodeError:
        raise ReviewError("RQ-001", "content_text") from None
    if budget[1] < 0:
        raise ReviewError("RQ-001", "content_size")
    return s


def _walk(v, depth, budget):
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        raise ReviewError("RQ-001", "content_size")
    t = type(v)
    if v is None or t is bool:
        return v
    if t is int:
        return v
    if t is str:
        if len(v) > MAX_STR:
            raise ReviewError("RQ-001", "content_size")
        return _text(v, budget)
    if t in (list, tuple):
        return [_walk(x, depth + 1, budget) for x in v]
    if t is dict:
        out = {}
        for k, x in v.items():
            if type(k) is not str:
                raise ReviewError("RQ-001", "content_key")
            out[_text(k, budget)] = _walk(x, depth + 1, budget)
        return out
    raise ReviewError("RQ-001", "content_type")


def content_digest(content) -> str:
    """sha256 over a domain tag and the canonical JSON. A content digest, not an integrity seal (the seal is HMAC)."""
    if type(content) not in (dict, list, tuple):
        raise ReviewError("RQ-001", "content_type")
    body = json.dumps(_walk(content, 0, [MAX_NODES, MAX_TOTAL]), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(b"orrery.review.content.v1\n" + body.encode("utf-8")).hexdigest()


def ident(v, what="id") -> str:
    if type(v) is not str or not ID_RE.fullmatch(v):
        raise ReviewError("RQ-001", what)
    return v


def tenant(v) -> str:
    if type(v) is not str or not TENANT_RE.fullmatch(v):
        raise ReviewError("RQ-001", "tenant")
    return v


def id_list(v, what) -> tuple:
    """A list or tuple (never a generator, set or string) of distinct ids; duplicates are refused."""
    if type(v) not in (list, tuple):
        raise ReviewError("RQ-001", what)
    out = tuple(ident(x, what) for x in v)
    if len(set(out)) != len(out) or len(out) > 50:
        raise ReviewError("RQ-001", what)
    return tuple(sorted(out))


def note_text(v) -> str:
    if type(v) is not str:
        raise ReviewError("RQ-014", "type")
    s = v.strip()
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise ReviewError("RQ-014", "chars") from None
    if len(s) > 2000 or any(ord(c) < 32 and c not in "\n\t" or 0x7F <= ord(c) < 0xA0 or c in "‪‫‬‭‮⁦⁧⁨⁩​‎‏" for c in s):
        raise ReviewError("RQ-014", "chars")
    return s
