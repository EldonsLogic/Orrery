"""Platform Autonomy Rate (BPL-022).

    autonomy_rate(draft, applied, tenant=None, revision=None) -> AutonomyResult

draft = the Blueprint the library produced, applied = the revision after human edits. Pure, deterministic, no I/O;
inputs are never modified. Definition: docs/strategy/autonomy-metrics.md. The elements and the unit of count are in
`elements.py`.

Rules fixed here (conservative readings, see the report of BPL-022):
- Denominator: elements in the APPLIED Blueprint. A removed element is not counted (it no longer exists); it is
  listed in `removed` for the exceptions register but does not lower or raise the rate by itself.
- Numerator: applied elements that exist in the draft (same kind and keyed pointer) with identical content, judged
  by the bpdiff diff of the two revisions. Identical means strict JSON equality; key order is ignored.
- Hand-added elements and hand-edited elements count against the rate, correct or not.
- Edits outside element content (meta, company, branding, compliance, i18n, approvals, locations, components) are
  not elements and change nothing here.
- A reorder of an entity's fields counts as an edit of that entity. Reorders of whole collections do not.
- A renamed id is one removal plus one addition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._deps import BpdError, bpdiff
from .elements import ELEMENT_KINDS
from .errors import MetricsError

Pointer = tuple[str, ...]


def _ptr(segs: Pointer) -> str:
    return "".join("/" + s.replace("~", "~0").replace("/", "~1") for s in segs)


def _percent(num: int, den: int) -> float:
    """Percent rounded half up to two decimals, by integer arithmetic."""
    return ((num * 20000 + den) // (2 * den)) / 100


def _ids(items: Any, where: str) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise MetricsError("MET-INPUT-002", f"{where}: not a list")
    out: list[str] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not isinstance(it.get("id"), str) or not it["id"]:
            raise MetricsError("MET-INPUT-002", f"{where}/{i}: not an object with a non-empty string id")
        out.append(it["id"])
    if len(set(out)) != len(out):
        raise MetricsError("MET-INPUT-003", f"{where}: duplicate id")
    return out


def enumerate_elements(blueprint: Any, label: str = "") -> dict[Pointer, str]:
    """Map keyed pointer segments -> element kind for every element of the Blueprint. Raises MetricsError."""
    if not isinstance(blueprint, dict):
        raise MetricsError("MET-INPUT-001", f"{label or 'blueprint'}: root is not an object")
    found: dict[Pointer, str] = {}
    for kind in ELEMENT_KINDS:
        if not kind.in_schema or kind.parent is not None:
            continue
        for eid in _ids(blueprint.get(kind.collection), f"{label}/{kind.collection}"):
            found[(kind.collection, eid)] = kind.name
    for kind in ELEMENT_KINDS:
        if not kind.in_schema or kind.parent is None:
            continue
        for parent in blueprint.get(kind.parent) or []:
            pid = parent["id"]
            for eid in _ids(parent.get(kind.collection), f"{label}/{kind.parent}/{pid}/{kind.collection}"):
                found[(kind.parent, pid, kind.collection, eid)] = kind.name
    return found


def _element_of(path: list, op: str, elements_depth: dict[str, int], child_arrays: dict[str, str]) -> tuple[Pointer, bool] | None:
    """Element addressed by a bpdiff op path: (pointer, edited). `edited` is False for an element-level add or
    remove (settled by membership). None when the op touches no element."""
    segs = tuple(path)
    if not segs or not all(isinstance(s, str) for s in segs) or segs[0] not in elements_depth:
        return None
    root = segs[0]
    if len(segs) < 2:
        return None
    child = child_arrays.get(root)
    if child and len(segs) >= 3 and segs[2] == child:
        if len(segs) == 3:
            return ((root, segs[1]), True) if op == "reorder" else None
        if len(segs) == 4:
            return (segs, op == "reorder")
        return (segs[:4], True)
    if len(segs) == 2:
        return (segs, False)
    return (segs[:2], True)


def _manual_row(tenant: str | None, revision: Any, ptr: str, change: str) -> dict:
    return {"tenant": tenant, "revision": revision, "pointer": ptr, "change": change, "class": None}


@dataclass(frozen=True)
class AutonomyResult:
    tenant: str | None
    revision: Any
    autonomous: int          # numerator
    total: int               # denominator, elements in the applied Blueprint
    percent: float           # rounded half up, 2 decimals
    by_kind: dict[str, dict[str, int]]   # kind -> {"total", "autonomous"}
    manual: tuple[str, ...]  # applied elements added or edited by hand (pointers, sorted)
    removed: tuple[str, ...]  # draft elements missing from the applied Blueprint (pointers, sorted)
    exceptions_rows: tuple[dict, ...] = field(default=())  # register row skeletons, class unset (None)

    @property
    def rate(self) -> tuple[int, int]:
        """Exact fraction as (numerator, denominator)."""
        return (self.autonomous, self.total)

    def to_dict(self) -> dict:
        return {
            "tenant": self.tenant, "revision": self.revision,
            "rate": {"numerator": self.autonomous, "denominator": self.total}, "percent": self.percent,
            "by_kind": {k: dict(v) for k, v in self.by_kind.items()},
            "manual": list(self.manual), "removed": list(self.removed),
            "exceptions_rows": [dict(r) for r in self.exceptions_rows],
        }


def autonomy_rate(draft: Any, applied: Any, tenant: str | None = None, revision: Any = None) -> AutonomyResult:
    """See the module docstring. tenant defaults to applied meta.id, revision to applied meta.revision."""
    d_el = enumerate_elements(draft, "draft")
    a_el = enumerate_elements(applied, "applied")
    if tenant is not None and not isinstance(tenant, str):
        raise MetricsError("MET-INPUT-001", "tenant is not a string")
    if revision is not None and (isinstance(revision, bool) or not isinstance(revision, (int, str))):
        raise MetricsError("MET-INPUT-001", "revision is not an integer or string")
    if not a_el:
        raise MetricsError("MET-AUTO-001", "applied Blueprint has no entities, fields, workflows, roles, reports, "
                                           "print formats or integrations")
    meta = applied.get("meta") if isinstance(applied.get("meta"), dict) else {}
    if tenant is None and isinstance(meta.get("id"), str):
        tenant = meta["id"]
    if revision is None and isinstance(meta.get("revision"), (int, str)) and not isinstance(meta.get("revision"), bool):
        revision = meta["revision"]

    try:
        d = bpdiff.diff(draft, applied)
    except BpdError as exc:
        raise MetricsError("MET-INPUT-004", exc.message) from None
    depth = {k.collection: 2 for k in ELEMENT_KINDS if k.parent is None and k.in_schema}
    child_arrays = {k.parent: k.collection for k in ELEMENT_KINDS if k.parent is not None}
    edited: set[Pointer] = set()
    for op in d["ops"]:
        hit = _element_of(op["path"], op["op"], depth, child_arrays)
        if hit and hit[1]:
            edited.add(hit[0])

    added = {p for p in a_el if p not in d_el}
    changed = {p for p in a_el if p in d_el and p in edited}
    manual_set = added | changed
    by_kind = {k.name: {"total": 0, "autonomous": 0} for k in ELEMENT_KINDS}
    for p, kind in a_el.items():
        by_kind[kind]["total"] += 1
        if p not in manual_set:
            by_kind[kind]["autonomous"] += 1
    total = len(a_el)
    auto = total - len(manual_set)
    manual = tuple(sorted(_ptr(p) for p in manual_set))
    removed = tuple(sorted(_ptr(p) for p in d_el if p not in a_el))
    rows = tuple(_manual_row(tenant, revision, _ptr(p), "added" if p in added else "edited")
                 for p in sorted(manual_set, key=_ptr))
    return AutonomyResult(tenant, revision, auto, total, _percent(auto, total), by_kind, manual, removed, rows)
