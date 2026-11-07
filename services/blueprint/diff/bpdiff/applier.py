"""apply(diff, a) and invert(diff): pure functions over diffs."""
from __future__ import annotations

import copy
from typing import Any

from .classify import build_op
from .engine import Diff, make_diff
from .errors import BpdError
from .model import KEYED, blueprint_hash, eq, key_of, keys_of, step, validate_input

_KINDS = ("add", "remove", "replace", "reorder")


def _bad(msg: str) -> BpdError:
    return BpdError("BPD-APPLY-001", msg)


def _check_shape(d: Any) -> None:
    ok = (type(d) is dict and type(d.get("ops")) is list and type(d.get("base")) is dict
          and type(d.get("target")) is dict and type(d["base"].get("hash")) is str
          and type(d["target"].get("hash")) is str)
    if not ok:
        raise BpdError("BPD-DIFF-001", "diff needs base.hash, target.hash and ops")
    for op in d["ops"]:
        if (type(op) is not dict or op.get("op") not in _KINDS or type(op.get("path")) is not list
                or not op["path"] or not all(type(s) in (str, int) and type(s) is not bool for s in op["path"])):
            raise BpdError("BPD-DIFF-001", "malformed operation")


def apply(d: Diff, a: dict) -> dict:
    """Return the revision `d` leads to. `a` is not modified. Refuses a foreign base (BPD-BASE-001)."""
    _check_shape(d)
    validate_input(a)
    if blueprint_hash(a) != d["base"]["hash"]:
        raise BpdError("BPD-BASE-001", "the diff was not made against this revision")
    doc = copy.deepcopy(a)
    for op in d["ops"]:
        try:
            _apply_op(doc, op)
        except (LookupError, TypeError, ValueError) as e:
            raise _bad(f"{op.get('pointer', '?')}: {e}") from None
    validate_input(doc)
    if blueprint_hash(doc) != d["target"]["hash"]:
        raise BpdError("BPD-APPLY-002", "result does not match the recorded target hash")
    return doc


def _apply_op(doc: dict, op: dict) -> None:
    kind, path = op["op"], op["path"]
    container: Any = doc
    sp: tuple = ()
    for seg in path[:-1]:
        _, container, sp = step(container, seg, sp)
    last = path[-1]
    if kind == "reorder":
        _, container, sp = step(container, last, sp)
        _reorder(container, sp, op)
    elif kind == "add":
        _add(container, sp, last, op)
    else:
        slot, child, _ = step(container, last, sp)
        if not eq(child, op.get("before")):
            raise _bad("current value differs from the recorded 'before'")
        if kind == "remove":
            del container[slot]
        else:
            if "after" not in op:
                raise _bad("replace without 'after'")
            container[slot] = copy.deepcopy(op["after"])


def _add(container: Any, sp: tuple, last: Any, op: dict) -> None:
    if "after" not in op:
        raise _bad("add without 'after'")
    value = copy.deepcopy(op["after"])
    if type(container) is dict:
        if type(last) is not str or last in container:
            raise _bad("key exists or is not a string")
        container[last] = value
        return
    if type(container) is not list:
        raise _bad("cannot add into a scalar")
    if type(last) is int:
        idx = last
    else:
        spec = KEYED.get(sp)
        if spec is None or key_of(value, spec) != last:
            raise _bad("element key does not match its path")
        if any(key_of(e, spec) == last for e in container):
            raise _bad("an element with this key exists")
        idx = op.get("index", len(container))
    if type(idx) is not int or type(idx) is bool or not 0 <= idx <= len(container):
        raise _bad("index out of range")
    container.insert(idx, value)


def _reorder(arr: Any, sp: tuple, op: dict) -> None:
    if type(arr) is not list:
        raise _bad("reorder target is not an array")
    before, after = op.get("before"), op.get("after")
    cur = keys_of(arr, sp)
    if cur is None or cur != before or type(after) is not list or sorted(after) != sorted(cur) \
            or len(set(after)) != len(after):
        raise _bad("reorder does not match the current keys")
    spec = KEYED[sp]
    by_key = {key_of(e, spec): e for e in arr}
    arr[:] = [by_key[k] for k in after]


def _swap_labels(labels: Any) -> Any:
    return None if labels is None else {"before": labels["after"], "after": labels["before"]}


def invert_op(op: dict) -> dict:
    kind = op["op"]
    path = tuple(op["path"])
    labels = _swap_labels(op.get("labels"))
    index = op.get("index")
    if kind == "add":
        return build_op("remove", path, before=op["after"], index=index, labels=labels)
    if kind == "remove":
        return build_op("add", path, after=op["before"], index=index, labels=labels)
    return build_op(kind, path, before=op["after"], after=op["before"], labels=labels)


def invert(d: Diff) -> Diff:
    """The undo point: `apply(invert(d), b) == a` when `d = diff(a, b)`."""
    _check_shape(d)
    ops = [invert_op(op) for op in reversed(d["ops"])]
    return make_diff(copy.deepcopy(d["target"]), copy.deepcopy(d["base"]), ops)
