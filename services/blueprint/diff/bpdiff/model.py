"""Shared tables and helpers: keyed-array table, JSON-data checks, strict equality, hashing, paths.

The table below is derived from contracts/blueprint.schema.json: every array of objects in the
contract, with the property (or properties) that identify an element. tests/diff checks the table
against the schema so a new collection in the contract cannot be missed silently.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import BpdError

MAX_DEPTH = 64
SCHEMA_ID = "bpdiff/0.1.0"

# (array schema path, key properties, noun of one element). "*" stands for one array element.
_ROWS: list[tuple[str, tuple[str, ...], str]] = [
    ("locations", ("id",), "location"),
    ("components", ("id",), "component"),
    ("entities", ("id",), "entity"),
    ("entities/*/fields", ("id",), "field"),
    ("entities/*/fields/*/options", ("value",), "option"),
    ("entities/*/relations", ("id",), "relation"),
    ("entities/*/components", ("component",), "binding"),
    ("workflows", ("id",), "workflow"),
    ("workflows/*/states", ("id",), "state"),
    ("workflows/*/transitions", ("id",), "transition"),
    ("workflows/*/transitions/*/guards", ("field", "op"), "guard"),
    ("roles", ("id",), "role"),
    ("roles/*/permissions", ("entity",), "permission"),
    ("approvals", ("id",), "approval"),
    ("approvals/*/conditions", ("field", "op"), "condition"),
    ("approvals/*/steps", ("approverRole",), "step"),
    ("reports", ("id",), "report"),
    ("reports/*/metrics", ("ref",), "metric"),
    ("reports/*/filters", ("field",), "filter"),
    ("integrations", ("id",), "integration"),
    ("integrations/*/mappings", ("target",), "mapping"),
    ("i18n/glossary", ("term",), "glossary_term"),
    ("company/locale/workingTime/reducedPeriods", ("id",), "reduced_period"),
    ("company/locale/holidays/overrides", ("date", "action"), "holiday_override"),
]

SPath = tuple  # tuple of str; "*" marks an array element


def spath(text: str) -> SPath:
    return tuple(text.split("/"))


KEYED: dict[SPath, tuple[str, ...]] = {spath(p): k for p, k, _ in _ROWS}
NOUN: dict[SPath, str] = {spath(p) + ("*",): n for p, _, n in _ROWS}

# Arrays whose physical order means something (a reorder there is not cosmetic).
ORDER_SIGNIFICANT: set[SPath] = {
    spath("approvals/*/steps"),
    spath("entities/*/fields"),
    spath("entities/*/fields/*/options"),
    spath("workflows/*/states"),
    spath("reports/*/metrics"),
}

_JSON_SCALARS = (str, int, float, bool, type(None))


def validate_input(value: Any) -> None:
    """Fail closed unless `value` is a plain-JSON object nested at most MAX_DEPTH levels."""
    if type(value) is not dict:
        raise BpdError("BPD-INPUT-003", "a Blueprint must be a JSON object")
    _check(value, 1)


def _check(v: Any, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise BpdError("BPD-INPUT-001", f"nesting deeper than {MAX_DEPTH}")
    t = type(v)
    if t is dict:
        for k, x in v.items():
            if type(k) is not str:
                raise BpdError("BPD-INPUT-002", "object key is not a string")
            _check(x, depth + 1)
    elif t is list:
        for x in v:
            _check(x, depth + 1)
    elif t is float:
        if v != v or v in (float("inf"), float("-inf")):
            raise BpdError("BPD-INPUT-002", "non-finite number")
    elif t not in _JSON_SCALARS:
        raise BpdError("BPD-INPUT-002", f"value of type {t.__name__} is not JSON data")


def eq(a: Any, b: Any) -> bool:
    """Strict JSON equality: True != 1, 1 != 1.0, order of object keys ignored, array order kept."""
    ta = type(a)
    if ta is not type(b):
        return False
    if ta is dict:
        return a.keys() == b.keys() and all(eq(a[k], b[k]) for k in a)
    if ta is list:
        return len(a) == len(b) and all(eq(x, y) for x, y in zip(a, b))
    return a == b


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def blueprint_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def key_of(elem: Any, spec: tuple[str, ...]) -> str | None:
    if type(elem) is not dict:
        return None
    parts = []
    for k in spec:
        v = elem.get(k)
        if type(v) is not str:
            return None
        parts.append(v)
    return "|".join(parts)


def keys_of(arr: list, sp: SPath) -> list[str] | None:
    """Keys of an array at schema path `sp`, or None when it is not a valid keyed array."""
    spec = KEYED.get(sp)
    if spec is None:
        return None
    keys = [key_of(e, spec) for e in arr]
    if any(k is None for k in keys) or len(set(keys)) != len(keys):
        return None
    return keys  # type: ignore[return-value]


def child_spath(sp: SPath, seg: Any) -> SPath:
    return sp + ("*",) if sp in KEYED else sp + (str(seg),)


def path_info(path: tuple | list) -> tuple[SPath, list[tuple[int, str, Any]]]:
    """Schema path of `path` and its array elements as (position, noun, key-or-index)."""
    sp: SPath = ()
    elems: list[tuple[int, str, Any]] = []
    for i, seg in enumerate(path):
        if sp in KEYED:
            sp = sp + ("*",)
            elems.append((i, NOUN[sp], seg))
        else:
            sp = sp + (str(seg),)
    return sp, elems


def esc(seg: Any) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def pointer(path: tuple | list) -> str:
    return "".join("/" + esc(s) for s in path)


def step(container: Any, seg: Any, sp: SPath) -> tuple[Any, Any, SPath]:
    """One move down: returns (slot, child, child schema path). Raises LookupError when absent.

    slot is the dict key or list index of the child. A str segment on an array means "the element
    whose key is seg" (keyed array); an int segment is a plain index.
    """
    nsp = child_spath(sp, seg)
    if type(container) is dict:
        if type(seg) is not str or seg not in container:
            raise LookupError(f"no key {seg!r}")
        return seg, container[seg], nsp
    if type(container) is list:
        if type(seg) is int:
            if not 0 <= seg < len(container):
                raise LookupError(f"index {seg} out of range")
            return seg, container[seg], nsp
        spec = KEYED.get(sp)
        if type(seg) is str and spec is not None:
            hits = [i for i, e in enumerate(container) if key_of(e, spec) == seg]
            if len(hits) != 1:
                raise LookupError(f"key {seg!r} matches {len(hits)} elements")
            return hits[0], container[hits[0]], nsp
    raise LookupError(f"cannot step into {type(container).__name__} with {seg!r}")


def node_at(doc: Any, path: tuple | list) -> Any:
    """The value at `path` or None when absent (used for labels only)."""
    cur, sp = doc, ()
    try:
        for seg in path:
            _, cur, sp = step(cur, seg, sp)
    except LookupError:
        return None
    return cur
