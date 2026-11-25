"""Canonical digest and input checks. Plain data only (dict, list, tuple, str, int, bool, None); floats, sets,
generators and other iterables, non-string keys, deep or huge values are refused, so one content has one digest and
no input is consumed twice."""
from __future__ import annotations

import hashlib
import json
import re

from .errors import BuildStateError

MAX_DEPTH, MAX_NODES, MAX_STR, MAX_TOTAL = 12, 20000, 20000, 1_000_000
ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
TENANT_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_INT = 10 ** 18


def _walk(v, depth, budget):
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        raise BuildStateError("BS-001", "size")
    t = type(v)
    if v is None or t is bool:
        return v
    if t is int:
        if abs(v) > MAX_INT:
            raise BuildStateError("BS-001", "int")
        return v
    if t is str:
        budget[1] -= len(v)
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise BuildStateError("BS-001", "text") from None
        if len(v) > MAX_STR or budget[1] < 0:
            raise BuildStateError("BS-001", "size")
        return v
    if t in (list, tuple):
        return [_walk(x, depth + 1, budget) for x in v]
    if t is dict:
        out = {}
        for k, x in v.items():
            if type(k) is not str:
                raise BuildStateError("BS-001", "key")
            out[_walk(k, depth + 1, budget)] = _walk(x, depth + 1, budget)
        return out
    raise BuildStateError("BS-001", "type")


def plain(content):
    """A deep copy of plain data (refuses anything else), safe to store and to seal."""
    return _walk(content, 0, [MAX_NODES, MAX_TOTAL])


def canonical(content) -> str:
    return json.dumps(plain(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_digest(content) -> str:
    """sha256 over a domain tag and the canonical JSON of a Blueprint (a content digest, not a seal)."""
    if type(content) is not dict:
        raise BuildStateError("BS-001", "content")
    return hashlib.sha256(b"seshna.buildstate.content.v1\n" + canonical(content).encode("utf-8")).hexdigest()


def ident(v, what="id") -> str:
    if type(v) is not str or not ID_RE.fullmatch(v):
        raise BuildStateError("BS-001", what)
    return v


def tenant(v) -> str:
    if type(v) is not str or not TENANT_RE.fullmatch(v):
        raise BuildStateError("BS-001", "tenant")
    return v


def digest(v, what="digest") -> str:
    if type(v) is not str or not DIGEST_RE.fullmatch(v):
        raise BuildStateError("BS-001", what)
    return v


def id_list(v, what) -> tuple:
    if type(v) not in (list, tuple):
        raise BuildStateError("BS-001", what)
    out = tuple(ident(x, what) for x in v)
    if len(set(out)) != len(out) or len(out) > 50:
        raise BuildStateError("BS-001", what)
    return tuple(sorted(out))
