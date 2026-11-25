"""Incremental compile (BPL-039): diff ops of any kind -> neutral steps (contracts/engine-adapter.md 9.3 to 9.6).

The forward artifact is compiled from diff(base, target), its embedded inverse from invert(diff) by the same rules
with base and target swapped, so rollback restores the base revision. Values are copied verbatim from the two
revisions; nothing here computes a ledger, tax or posting figure (ADR-0030).

Rules beyond the initial build (open points, conservative reading; see the BPL-039 log):
- A property stops at the first array, so an array is always set whole. No two steps share (kind, pointer) (schema
  x-validator-rules): changes under one property of one subject coalesce into one step whose `property` is their
  common prefix (the labels of an entity: one /labels step); changes to two different properties of one subject
  cannot be carried by one step (one `property` per step) and refuse with CMP-ART-001. settings.set keeps one step
  per property until BPL-037 settles it in the contract.
- Field and option order (9.4): quarantine runs in phase 15, after the reorder in phase 6, so a reorder `order` lists
  exactly the keys active when it runs (target order, then the removed keys). An added or restored element carries no
  position in the step schema; with no reorder op in the diff, the compiler predicts the adapter's order (a new
  element is appended, a single restored one returns to its former index) and refuses with CMP-ART-001 when that
  misses the target, in either direction (prepend, rename, several removals whose rollback cannot restore order).
- A precision change is refused (CMP-ART-001) until the engine adapter supports it (BPL-039 review, partner).
- Only the declared Blueprint provenance paths are skipped (`provenance` of a component, entity, workflow, role,
  approval, report, integration or assistant); a `provenance` key inside ordinary data (a JSON default) is compiled.
- Changes inside a location become one location.upsert of the whole node (9.3 names no location.set_property).
- Not compiled, refused (CMP-ART-001): a component version range change, a change inside an option, a reorder of
  an unordered collection (9.3 has no step kind and skippedOps no reason for it), whole sections added or removed.
- `reversible: false` (9.5) is decided by `irreversible_reason`, a pure function of the step, so a reader (Studio)
  can show why an artifact cannot be rolled back. The adapter refuses its rollback (`irreversible_step`).
"""
from __future__ import annotations

import copy
from typing import Any

from ._deps import bpdiff
from .components import touches_ledger_or_tax
from .result import Issue
from .steps import ADD_KIND, ADDITIVE, I18N_SETTINGS, PHASE, SETTINGS_SECTIONS, SKIP, _esc

MISSING = object()
OP_KINDS = ("add", "remove", "replace", "reorder")
_SEVERITY = list(reversed(bpdiff.classify._SEVERITY))  # bpdiff impact severity, lowest first
REMOVE_KIND = {"locations": "location.disable", "components": "component.disable", "entities": "entity.quarantine",
               "roles": "role.disable", "workflows": "workflow.disable", "approvals": "approval.disable",
               "reports": "report.disable"}
COALESCED = {"workflows": "workflow.upsert", "roles": "role.upsert", "approvals": "approval.upsert",
             "reports": "report.upsert", "locations": "location.upsert"}
CHILD = {"fields": ("field.add", "field.quarantine", "field.set_property"),
         "relations": ("relation.add", "relation.quarantine", "relation.set_property"),
         "components": ("binding.add", "binding.disable", "binding.set_property")}
PROVENANCE_OF = {"components", "entities", "workflows", "roles", "approvals", "reports", "integrations", "assistants"}
ORDERED = (("fields", "field.reorder"), ("options", "option.reorder"))  # order-significant collections with a step kind
UNCOALESCED = {"settings.set"}  # BPL-037 owns the settings.set contract change
SEMANTIC = {"field.set_property": {"/type", "/unique", "/precision", "/maxLength", "/required", "/target"},
            "relation.set_property": {"/target", "/required"}}


def irreversible_reason(step: dict) -> str | None:
    """Stable reason code when the inverse of `step` cannot restore the exact prior state, data included (9.5)."""
    kind, params = step["kind"], step["params"]
    prop, before, after = params.get("property"), params.get("before", MISSING), params.get("after", MISSING)
    if kind == "field.set_property" and prop == "/type":
        return "type_change"
    if kind in ("field.set_property", "relation.set_property") and prop == "/target":
        return "link_target_change"
    widened = type(before) is int and type(after) is int and after >= before
    if kind == "field.set_property" and prop == "/precision" and not widened:
        return "precision_reduction"  # an absent precision is the engine default, unknown here: fail closed
    if kind == "field.set_property" and prop == "/maxLength" and after is not MISSING and not widened:
        return "length_reduction"  # absent before means unlimited
    return None


def _get(doc: Any, path: list) -> Any:
    cur, sp = doc, ()
    try:
        for seg in path:
            _, cur, sp = bpdiff.model.step(cur, seg, sp)
    except LookupError:
        return MISSING
    return cur


def _prop(base: dict, target: dict, path: list, start: int) -> list:
    """path[start:] cut after the first segment whose value is an array in either revision."""
    for i in range(start, len(path)):
        if isinstance(_get(base, path[:i + 1]), list) or isinstance(_get(target, path[:i + 1]), list):
            return path[start:i + 1]
    return path[start:]


def _subject(kind: str, ident: Any, parents: list) -> dict:
    return {"kind": kind, "id": ident, "parents": [{"kind": k, "id": i} for k, i in parents]}


def _classify(op: dict, base: dict, target: dict) -> tuple | str:
    """(kind, subject, pointer, params) for one op, "skip:<reason>", or "" when no rule covers it."""
    path, kind = op["path"], op["op"]
    if kind not in OP_KINDS:  # fail closed: an unknown kind must never fall through to a property change
        return ""
    head, n = (path[0] if path else None), len(path)
    if head in SKIP or (n >= 3 and head in PROVENANCE_OF and path[2] == "provenance"):
        return "skip:" + SKIP.get(head, "provenance")
    if head == "i18n" and n >= 2 and path[1] == "glossary":
        return "skip:i18n_glossary"
    if (head in SETTINGS_SECTIONS and n >= 2) or (head == "i18n" and n >= 2 and path[1] in I18N_SETTINGS):
        return "settings.set", _subject(head, None, []), "/" + head, ("settings", 1)
    if head not in ADD_KIND or n < 2:
        return ""
    top = (head, path[1])
    if n == 2 and kind in ("add", "remove"):
        sk = ADD_KIND[head] if kind == "add" else REMOVE_KIND[head]
        return sk, op["subject"], op["pointer"], ("definition", target if kind == "add" else base, path)
    if head in COALESCED:
        return COALESCED[head], _subject(head[:-1], path[1], []), "/" + "/".join(map(_esc, top)), \
            ("definition", target, path[:2])
    if head == "components":
        return ("component.configure", _subject("component", path[1], []), "/components/" + _esc(path[1]),
                ("property", 2)) if path[2] == "parameters" else ""
    ent = [("entity", path[1])]
    eptr = "/entities/" + _esc(path[1])
    if path[2] in CHILD and n >= 4:
        add, rem, setp = CHILD[path[2]]
        noun = {"fields": "field", "relations": "relation", "components": "binding"}[path[2]]
        cptr = f"{eptr}/{path[2]}/{_esc(path[3])}"
        subj = _subject(noun, path[3], ent)
        if n == 4 and kind in ("add", "remove"):
            return (add if kind == "add" else rem), subj, cptr, ("definition", target if kind == "add" else base, path)
        if path[2] == "fields" and n >= 5 and path[4] == "options":
            osubj = _subject("option", path[5] if n >= 6 else None, ent + [("field", path[3])])
            if n == 5 and kind == "reorder":
                return "option.reorder", _subject("field", path[3], ent), cptr + "/options", ("order", path)
            if n == 6 and kind in ("add", "remove"):
                return ("option.add" if kind == "add" else "option.quarantine"), osubj, op["pointer"], \
                    ("definition", target if kind == "add" else base, path)
            return ""
        return setp, subj, cptr, ("property", 4)
    if path[2] == "fields" and n == 3 and kind == "reorder":
        return "field.reorder", _subject("entity", path[1], []), eptr + "/fields", ("order", path)
    if path[2] in CHILD:
        return ""
    return "entity.set_property", _subject("entity", path[1], []), eptr, ("property", 2)


def _keys(doc: dict, path: list) -> list | None:
    arr = _get(doc, path)
    return bpdiff.model.keys_of(arr, bpdiff.model.path_info(path)[0]) if isinstance(arr, list) else None


def _params(spec: tuple, path: list, base: dict, target: dict) -> dict:
    if spec[0] == "definition":
        return {"definition": copy.deepcopy(_get(spec[1], spec[2]))}
    if spec[0] == "order":  # finished by _reconcile_order, which knows every membership change
        return {"order": _keys(target, path), "previousOrder": _keys(base, path)}
    return _prop_params(path[:spec[1]], _prop(base, target, path, spec[1]), base, target)


def _prop_params(head: list, prop: list, base: dict, target: dict) -> dict:
    out = {"property": "".join("/" + _esc(s) for s in prop)}
    for name, doc in (("before", base), ("after", target)):
        value = _get(doc, head + prop)
        if value is not MISSING:
            out[name] = copy.deepcopy(value)
    return out


def _collections(frm: dict, to: dict):
    """(path, kind) of every ordered collection (entity fields, field options) present in both revisions."""
    for e in to.get("entities", []):
        eid = e.get("id")
        if _get(frm, ["entities", eid]) is MISSING:
            continue
        yield ["entities", eid, "fields"], "field.reorder"
        for f in e.get("fields", []):
            path = ["entities", eid, "fields", f.get("id"), "options"]
            if isinstance(_get(frm, path), list) and isinstance(_get(to, path), list):
                yield path, "option.reorder"


def _reconcile_order(by_key: dict, frm: dict, to: dict, restores: bool) -> list[Issue]:
    """Finish reorder steps and refuse membership changes whose order the adapter cannot reach (module notes)."""
    issues = []
    for path, kind in _collections(frm, to):
        before, after = _keys(frm, path), _keys(to, path)
        if before is None or after is None or before == after:
            continue
        pointer = bpdiff.model.pointer(path)
        removed = [k for k in before if k not in after]
        added = sorted((k for k in after if k not in before), key=_esc)  # phase 5 runs them in pointer order
        step = by_key.get((kind, pointer))
        if step is not None:
            step["params"] = {"order": after + removed, "previousOrder": before + added}
            continue
        active = list(before)
        if restores and len(added) > 1:
            active = None  # several restores: each returns to an index taken after the others left
        for k in added if active is not None else ():
            if restores:
                active.insert(min(after.index(k), len(active)), k)
            else:
                active.append(k)
        if active is None or [k for k in active if k not in removed] != after:
            noun = "field" if kind == "field.reorder" else "option"
            issues.append(Issue("CMP-ART-001", pointer, f"{noun} position change: an added or restored {noun} has "
                                "no position in the step schema and no reorder follows it"))
    return issues


def _coalesce(step: dict, path: list, spec: tuple, base: dict, target: dict, prop_of: dict) -> bool:
    """Widen a property step to the common prefix of its properties; False when they share none."""
    head, old = prop_of[(step["kind"], step["pointer"])]
    new = _prop(base, target, path, spec[1])
    common = []
    for a, b in zip(old, new):
        if a != b:
            break
        common.append(a)
    if not common:
        return False
    prop_of[(step["kind"], step["pointer"])] = (head, common)
    step["params"] = _prop_params(head, common, base, target)
    return True


def steps_from_diff(d: dict, base: dict, target: dict, *, restores: bool = False) -> tuple[list[dict], list[dict],
                                                                                         list[Issue]]:
    """(steps sorted and numbered, skippedOps sorted, issues). Ops with the same (kind, pointer) coalesce into one step
    whose sourceOps lists them all (settings.set: same property). `restores` is true for an inverse, whose adds bring
    back what the forward quarantined."""
    by_key: dict[tuple, dict] = {}
    prop_of: dict[tuple, tuple] = {}
    skipped, issues, refused = [], [], set()
    for op in d["ops"]:
        c = _classify(op, base, target)
        if isinstance(c, str):
            if c.startswith("skip:"):
                skipped.append({"pointer": op["pointer"], "reason": c[5:]})
            else:
                issues.append(Issue("CMP-ART-001", op["pointer"], "no compile rule covers this Blueprint operation"))
            continue
        kind, subject, pointer, spec = c
        params = _params(spec, op["path"], base, target)
        key = (kind, pointer, params["property"]) if kind in UNCOALESCED else (kind, pointer)
        if key in by_key:
            s = by_key[key]
            if spec[0] == "property" and kind not in UNCOALESCED and s["params"]["property"] != params["property"] \
                    and not _coalesce(s, op["path"], spec, base, target, prop_of) and key not in refused:
                refused.add(key)
                issues.append(Issue("CMP-ART-001", pointer, "several properties of one subject change: one step "
                                    "carries one property; change them in separate revisions"))
            s["sourceOps"].append(op["pointer"])
            s["impact"] = max(s["impact"], op["impact"], key=_SEVERITY.index)
            continue
        if spec[0] == "property":
            prop_of[key] = (op["path"][:spec[1]], _prop(base, target, op["path"], spec[1]))
        by_key[key] = {"seq": 0, "phase": PHASE[kind], "kind": kind, "subject": copy.deepcopy(subject),
                       "pointer": pointer, "impact": op["impact"], "ddlImpact": "none", "reversible": True,
                       "params": params, "sourceOps": [op["pointer"]]}
    issues += _reconcile_order(by_key, base, target, restores)
    for s in by_key.values():
        kind, prop = s["kind"], s["params"].get("property")
        if kind == "field.set_property" and prop == "/precision":
            issues.append(Issue("CMP-ART-001", s["pointer"] + prop, "precision change not yet supported by the adapter"))
        s["ddlImpact"] = "additive" if kind in ADDITIVE else "semantic" if prop in SEMANTIC.get(kind, ()) else "none"
        s["reversible"] = irreversible_reason(s) is None
    steps = sorted(by_key.values(), key=lambda s: (s["phase"], s["pointer"], s["kind"], s["params"].get("property", "")))
    for i, s in enumerate(steps, 1):
        s["seq"] = i
        s["sourceOps"].sort()
    skipped.sort(key=lambda s: s["pointer"])
    return steps, skipped, issues


def ledger_or_tax(steps: list[dict], resolved: dict[str, dict], *docs: dict) -> bool:
    """risk.touchesLedgerOrTax for any step kind: the subject is a ledger or tax component, or is (or sits under) an
    entity bound to one in either revision. Wider than the initial-build rule, so it errs toward team review."""
    hot = {cid for cid, m in resolved.items() if touches_ledger_or_tax(m)}
    bound = {e.get("id") for doc in docs for e in doc.get("entities", []) if isinstance(e, dict)
             and {b.get("component") for b in e.get("components", []) if isinstance(b, dict)} & hot}
    for s in steps:
        subj = s["subject"]
        if subj["kind"] == "component" and subj["id"] in hot:
            return True
        ents = {subj["id"]} if subj["kind"] == "entity" else {p["id"] for p in subj["parents"] if p["kind"] == "entity"}
        if ents & bound:
            return True
    return False
