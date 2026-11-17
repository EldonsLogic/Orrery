"""plan_view: the artifact's steps as an ordered plan with the references between them, read only from the artifact.

For each step: `dependsOn` lists earlier steps whose subject this step's definition references (they must be applied
first, and the contract's phase order puts them first); `forwardRefs` lists later steps it references (the adapter
must resolve them after both exist, see open question 5); `unresolved` lists referenced pointers no step creates
(empty for a compiled artifact: the validator already proved every reference resolves). Apply (BPL-007) and the
real adapter (BPL-012) can build and test their ordering against this view and the fixtures.
"""
from __future__ import annotations

from typing import Any


def _esc(seg: Any) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def _p(section: str, key: Any) -> str | None:
    return f"/{section}/{_esc(key)}" if isinstance(key, str) else None


def _list(x: Any) -> list:
    return x if isinstance(x, list) else []


def _dicts(x: Any) -> list[dict]:
    return [v for v in _list(x) if isinstance(v, dict)]


def references(step: dict) -> list[str]:
    """Pointers of other Blueprint elements that this step's definition names (sorted, unique)."""
    d = step["params"].get("definition")
    if not isinstance(d, dict):
        return []
    kind, refs = step["kind"], []
    if kind == "entity.add":
        refs += [_p("components", b.get("component")) for b in _dicts(d.get("components"))]
        refs.append(_p("workflows", d.get("workflow")))
        refs += [_p("entities", r.get("target")) for r in _dicts(d.get("relations"))]
        refs += [_p("entities", f.get("target")) for f in _dicts(d.get("fields")) if f.get("type") == "link"]
    elif kind == "location.upsert":
        refs.append(_p("locations", d.get("parent")))
    elif kind == "role.upsert":
        refs += [_p("entities", p.get("entity")) for p in _dicts(d.get("permissions"))]
        scope = d.get("scope") if isinstance(d.get("scope"), dict) else {}
        refs += [_p("locations", v) for v in _list(scope.get("values"))]
    elif kind == "workflow.upsert":
        refs.append(_p("entities", d.get("entity")))
        for t in _dicts(d.get("transitions")):
            refs += [_p("roles", r) for r in _list(t.get("allowedRoles")) + _list(t.get("notify"))]
            refs.append(_p("approvals", t.get("approval")))
    elif kind == "approval.upsert":
        applies = d.get("appliesTo") if isinstance(d.get("appliesTo"), dict) else {}
        refs.append(_p("entities", applies.get("entity")))
        for s in _dicts(d.get("steps")):
            refs += [_p("roles", s.get("approverRole")), _p("roles", s.get("escalateToRole"))]
    elif kind == "report.upsert":
        refs.append(_p("entities", d.get("entity")))
        refs += [_p("roles", r) for r in _list(d.get("visibleToRoles"))]
    own = step["pointer"]
    return sorted({r for r in refs if r and r != own})


def plan_view(artifact: dict) -> list[dict]:
    """One row per step, in seq order."""
    by_pointer: dict[str, int] = {}
    for s in artifact["steps"]:
        by_pointer.setdefault(s["pointer"], s["seq"])
    rows = []
    for s in sorted(artifact["steps"], key=lambda x: x["seq"]):
        before, after, missing = set(), set(), []
        for ref in references(s):
            seq = by_pointer.get(ref)
            if seq is None:
                missing.append(ref)
            elif seq < s["seq"]:
                before.add(seq)
            else:
                after.add(seq)
        rows.append({"seq": s["seq"], "phase": s["phase"], "kind": s["kind"], "pointer": s["pointer"],
                     "ddlImpact": s["ddlImpact"], "reversible": s["reversible"],
                     "dependsOn": sorted(before), "forwardRefs": sorted(after), "unresolved": missing})
    return rows
