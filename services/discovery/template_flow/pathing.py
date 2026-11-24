"""Strict JSON-pointer handling for owner edits. ASCII segments only, no escapes, no dunder names."""
from __future__ import annotations

import re
from typing import Any

from .errors import PATH_MISSING, PATH_UNSAFE, FlowError

MAX_POINTER = 200
MAX_SEGMENTS = 8
_SEG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_|.\-]{0,63}\Z", re.ASCII)
_FORBIDDEN = {"proto", "constructor", "prototype", "class", "dict", "init", "globals", "builtins", "hasownproperty"}
LANGS = ("ar", "en")


def parse_pointer(pointer: Any) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > MAX_POINTER:
        raise FlowError(PATH_UNSAFE, "pointer must be a string starting with '/' (200 characters at most)")
    segs = tuple(pointer[1:].split("/"))
    if len(segs) > MAX_SEGMENTS:
        raise FlowError(PATH_UNSAFE, "pointer is too deep")
    for s in segs:
        if not _SEG.match(s):
            raise FlowError(PATH_UNSAFE, "pointer segment is empty or has characters outside A-Z a-z 0-9 _ | . -")
        if s.startswith("__") or s.strip("_").lower() in _FORBIDDEN:
            raise FlowError(PATH_UNSAFE, "pointer segment is reserved")
    return segs


def element_key(el: Any) -> str | None:
    """Arrays are addressed by key, never by index: `id`, or `field|op` for guards."""
    if not isinstance(el, dict):
        return None
    if isinstance(el.get("id"), str):
        return el["id"]
    if isinstance(el.get("field"), str) and isinstance(el.get("op"), str):
        return el["field"] + "|" + el["op"]
    return None


def _step(node: Any, seg: str) -> Any:
    if isinstance(node, dict):
        if seg in node:
            return node[seg]
        raise KeyError(seg)
    if isinstance(node, list):
        hits = [e for e in node if element_key(e) == seg]
        if len(hits) == 1:
            return hits[0]
    raise KeyError(seg)


def resolve(root: dict, segs: tuple[str, ...], create_leaf: bool):
    """Return (parent, leaf_key, exists, ancestors). The parent must exist and be an object.

    ancestors are the objects walked, root first, for provenance."""
    node: Any = root
    ancestors = [root]
    try:
        for s in segs[:-1]:
            node = _step(node, s)
            ancestors.append(node)
    except KeyError:
        raise FlowError(PATH_MISSING, "pointer does not address one element of this draft") from None
    if not isinstance(node, dict):
        raise FlowError(PATH_MISSING, "pointer does not address one element of this draft")
    leaf = segs[-1]
    exists = leaf in node
    if not exists and not create_leaf:
        raise FlowError(PATH_MISSING, "pointer does not address one element of this draft")
    return node, leaf, exists, ancestors


def get(root: dict, segs: tuple[str, ...]):
    node: Any = root
    for s in segs:
        node = _step(node, s)
    return node


def match(pattern: tuple[str, ...], segs: tuple[str, ...]) -> bool:
    if len(pattern) != len(segs):
        return False
    for p, s in zip(pattern, segs):
        if p == "*":
            continue
        if p == "@lang":
            if s not in LANGS:
                return False
        elif p != s:
            return False
    return True


def expand(pattern: tuple[str, ...], root: Any, prefix: tuple[str, ...] = ()):
    """Yield every concrete pointer (segment tuple) in `root` that fits `pattern`."""
    if not pattern:
        yield prefix
        return
    p, rest = pattern[0], pattern[1:]
    node = root if not prefix else _walk(root, prefix)
    if p == "*":
        if isinstance(node, list):
            for e in node:
                k = element_key(e)
                if k is not None and _SEG.match(k):
                    yield from expand(rest, root, prefix + (k,))
    elif p == "@lang":
        for lang in LANGS:
            if isinstance(node, dict) and lang in node:
                yield from expand(rest, root, prefix + (lang,))
    elif isinstance(node, dict) and p in node:
        yield from expand(rest, root, prefix + (p,))


def _walk(root: Any, prefix: tuple[str, ...]):
    return get(root, prefix)
