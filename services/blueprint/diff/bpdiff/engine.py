"""diff(a, b): deterministic structural diff between two Blueprint revisions."""
from __future__ import annotations

from typing import Any

from .classify import build_op, make_labels, risk_of, summary_of
from .model import SCHEMA_ID, SPath, blueprint_hash, child_spath, eq, keys_of, validate_input

Diff = dict  # JSON-serialisable; shape in diff.schema.json


def _ref(bp: dict) -> dict:
    meta = bp.get("meta") if type(bp.get("meta")) is dict else {}
    rev = meta.get("revision")
    ident = meta.get("id")
    return {"hash": blueprint_hash(bp),
            "revision": rev if type(rev) is int else None,
            "id": ident if type(ident) is str else None}


def diff(a: dict, b: dict) -> Diff:
    """Operations that turn revision `a` into revision `b`. Inputs are never modified.

    Arrays of id-keyed objects are matched by key (see model.KEYED), everything else by position
    or as a whole. Operation order is deterministic: objects by sorted key, arrays in order;
    inside a keyed array: nested changes of kept elements, removals (high index first), additions
    (low index first), then one reorder if the kept order still differs.
    """
    validate_input(a)
    validate_input(b)
    raw: list[tuple] = []
    _walk(a, b, (), (), raw)
    ops = [build_op(kind, path, before, after, index, make_labels(path, a, b))
           for kind, path, before, after, index in raw]
    return make_diff(_ref(a), _ref(b), ops)


def make_diff(base: dict, target: dict, ops: list[dict]) -> Diff:
    return {"schema": SCHEMA_ID, "base": base, "target": target, "ops": ops,
            "summary": summary_of(ops), "risk": risk_of(ops)}


def _walk(a: Any, b: Any, path: tuple, sp: SPath, out: list[tuple]) -> None:
    if eq(a, b):
        return
    ta, tb = type(a), type(b)
    if ta is dict and tb is dict:
        for k in sorted(set(a) | set(b)):
            p = path + (k,)
            if k not in b:
                out.append(("remove", p, a[k], None, None))
            elif k not in a:
                out.append(("add", p, None, b[k], None))
            else:
                _walk(a[k], b[k], p, child_spath(sp, k), out)
    elif ta is list and tb is list:
        _walk_list(a, b, path, sp, out)
    else:
        out.append(("replace", path, a, b, None))


def _walk_list(a: list, b: list, path: tuple, sp: SPath, out: list[tuple]) -> None:
    ka, kb = keys_of(a, sp), keys_of(b, sp)
    if ka is not None and kb is not None:
        _walk_keyed(a, b, ka, kb, path, sp, out)
    elif any(type(x) in (dict, list) for x in a + b):
        n = min(len(a), len(b))
        for i in range(n):
            _walk(a[i], b[i], path + (i,), child_spath(sp, i), out)
        for i in range(n, len(b)):
            out.append(("add", path + (i,), None, b[i], i))
        for i in range(len(a) - 1, n - 1, -1):
            out.append(("remove", path + (i,), a[i], None, i))
    else:  # array of scalars: one value
        out.append(("replace", path, a, b, None))


def _walk_keyed(a: list, b: list, ka: list[str], kb: list[str], path: tuple, sp: SPath,
                out: list[tuple]) -> None:
    ia, ib = {k: i for i, k in enumerate(ka)}, {k: i for i, k in enumerate(kb)}
    esp = child_spath(sp, 0)
    for k in ka:
        if k in ib:
            _walk(a[ia[k]], b[ib[k]], path + (k,), esp, out)
    for i in range(len(ka) - 1, -1, -1):
        if ka[i] not in ib:
            out.append(("remove", path + (ka[i],), a[i], None, i))
    cur = [k for k in ka if k in ib]
    for i, k in enumerate(kb):
        if k not in ia:
            out.append(("add", path + (k,), None, b[i], i))
            cur.insert(i, k)
    if cur != kb:
        out.append(("reorder", path, list(cur), list(kb), None))
