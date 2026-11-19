"""The model's draft: a short list of typed edits, decoded strictly, applied by code to a copy of the Blueprint.

The model never writes the Blueprint. It names pointers and values; this module checks the shape, refuses
forbidden areas (permissions, approvals, compliance, computed or ledger logic) and applies the edits to a deep copy.
This check is only an early exit: the binding decision is `policy.check_diff` on the resulting diff, after the validator."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from .errors import ChangeRefused

MAX_EDITS = 20
MAX_DEPTH = 12
MAX_VALUE_CHARS = 20_000
OPS = ("set", "add", "remove")
# Areas a chat change may touch. Everything else (meta, company, compliance, components, roles, approvals, assistants,
# integrations) is refused here, before any diff: those are reviewed in Studio (ADR-0027, action-policy R3/R4).
ALLOWED_ROOTS = frozenset({"entities", "workflows", "reports", "locations", "i18n", "branding"})
# Any path segment or value key with one of these names is logic or authority, never a chat edit.
FORBIDDEN_KEYS = frozenset({"computed", "guards", "approval", "approvals", "visibleToRoles", "allowedRoles",
                            "hiddenFields", "readOnlyFields", "permissions", "provenance", "readOnly", "locksEditing"})
# A `set` this shallow replaces a whole section or element (every entity, one whole workflow...): never from chat.
WHOLE_SECTIONS = frozenset({"entities", "workflows", "reports", "locations"})


@dataclass(frozen=True)
class Edit:
    op: str
    pointer: tuple      # path segments; a segment inside a list is the element's `id`
    value: Any = None

    def to_json(self) -> dict:
        return {"op": self.op, "path": list(self.pointer), "value": self.value}


def _deep_keys(v, depth=0):
    if depth > MAX_DEPTH + 8:
        raise ChangeRefused("change_draft_invalid")
    if isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from _deep_keys(x, depth + 1)
    elif isinstance(v, list):
        for x in v:
            yield from _deep_keys(x, depth + 1)


def _json_only(v) -> bool:
    return isinstance(v, (str, int, float, bool, type(None), list, dict)) and _json_ok(v, 0)


def _json_ok(v, depth) -> bool:
    if depth > MAX_DEPTH + 8:
        return False
    if isinstance(v, dict):
        return all(type(k) is str and _json_ok(x, depth + 1) for k, x in v.items())
    if isinstance(v, list):
        return all(_json_ok(x, depth + 1) for x in v)
    if isinstance(v, float):
        return v == v and v not in (float("inf"), float("-inf"))
    return isinstance(v, (str, int, bool, type(None)))


def decode_draft(raw) -> tuple:
    """Closed-shape decode of the drafter's output. Anything else is refused; no raw text survives."""
    if isinstance(raw, dict):
        raw = raw.get("edits")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ChangeRefused("change_draft_failed")
    if len(raw) > MAX_EDITS:
        raise ChangeRefused("change_draft_invalid")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not set(item) <= {"op", "path", "value"} or "op" not in item \
                or "path" not in item:
            raise ChangeRefused("change_draft_invalid")
        op, path, value = item["op"], item["path"], item.get("value")
        if op not in OPS or not isinstance(path, (list, tuple)) or not 1 <= len(path) <= MAX_DEPTH \
                or not all(isinstance(s, str) and s and len(s) <= 128 for s in path):
            raise ChangeRefused("change_draft_invalid")
        if (op == "remove") != ("value" not in item):
            raise ChangeRefused("change_draft_invalid")
        if not _json_only(value) or len(json.dumps(value, ensure_ascii=False)) > MAX_VALUE_CHARS:
            raise ChangeRefused("change_draft_invalid")
        out.append(Edit(op, tuple(path), copy.deepcopy(value)))
    return tuple(out)


def check_allowed(edits: tuple) -> None:
    for e in edits:
        if e.pointer[0] not in ALLOWED_ROOTS or len(e.pointer) == 1:
            raise ChangeRefused("change_forbidden_path")
        if e.op == "set" and e.pointer[0] in WHOLE_SECTIONS and len(e.pointer) <= 2:
            raise ChangeRefused("change_forbidden_path")
        if FORBIDDEN_KEYS & set(e.pointer) or (e.value is not None and FORBIDDEN_KEYS & set(_deep_keys(e.value))):
            raise ChangeRefused("change_forbidden_path")


def _find(lst: list, key: str):
    hits = [i for i, x in enumerate(lst) if isinstance(x, dict) and x.get("id") == key]
    if len(hits) != 1:
        raise ChangeRefused("change_draft_invalid")
    return hits[0]


def apply_edits(blueprint: dict, edits: tuple) -> dict:
    """Apply to a deep copy; the input is never modified. Any irregularity refuses the whole draft."""
    bp = copy.deepcopy(blueprint)
    for e in edits:
        node: Any = bp
        for seg in e.pointer[:-1]:
            if isinstance(node, dict) and seg in node:
                node = node[seg]
            elif isinstance(node, list):
                node = node[_find(node, seg)]
            else:
                raise ChangeRefused("change_draft_invalid")
        last = e.pointer[-1]
        if isinstance(node, dict):
            if e.op == "set" and last in node:
                node[last] = copy.deepcopy(e.value)  # a plain-value array is replaced whole
            elif e.op == "add" and last not in node:
                node[last] = copy.deepcopy(e.value)
            elif e.op == "add" and isinstance(node[last], list):
                if not (isinstance(e.value, dict) and isinstance(e.value.get("id"), str)):
                    raise ChangeRefused("change_draft_invalid")
                if any(isinstance(x, dict) and x.get("id") == e.value["id"] for x in node[last]):
                    raise ChangeRefused("change_draft_invalid")
                node[last].append(copy.deepcopy(e.value))
            elif e.op == "remove" and last in node:
                del node[last]
            else:
                raise ChangeRefused("change_draft_invalid")
        elif isinstance(node, list):
            i = _find(node, last)
            if e.op == "set" and isinstance(e.value, dict) and e.value.get("id") == last:
                node[i] = copy.deepcopy(e.value)
            elif e.op == "remove":
                del node[i]
            else:
                raise ChangeRefused("change_draft_invalid")
        else:
            raise ChangeRefused("change_draft_invalid")
    return bp
