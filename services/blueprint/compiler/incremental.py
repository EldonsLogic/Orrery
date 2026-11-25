"""Incremental compile (BPL-039): diff ops of any kind -> neutral steps (contracts/engine-adapter.md 9.3 to 9.6).

The forward artifact is compiled from diff(base, target), its embedded inverse from invert(diff) by the same rules
with base and target swapped, so rollback restores the base revision. Values are copied verbatim from the two
revisions; nothing here computes a ledger, tax or posting figure (ADR-0030).

Rules beyond the initial build (open points, conservative reading; see the BPL-039 log):
- set_property and settings.set carry one property each; several may share one pointer (as open question 2 in
  __init__). A property stops at the first array, so an array is always set whole.
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
    if head in SKIP or "provenance" in bpdiff.model.path_info(path)[0]:
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


def _params(spec: tuple, path: list, base: dict, target: dict) -> dict:
    if spec[0] == "definition":
        return {"definition": copy.deepcopy(_get(spec[1], spec[2]))}
    if spec[0] == "order":
        key = bpdiff.model.KEYED[bpdiff.model.path_info(path)[0]]
        keys = lambda doc: [bpdiff.model.key_of(e, key) for e in _get(doc, path)]  # noqa: E731
        return {"order": keys(target), "previousOrder": keys(base)}
    start = spec[1]
    prop = _prop(base, target, path, start)
    full = path[:start] + prop
    out = {"property": "".join("/" + _esc(s) for s in prop)}
    for name, doc in (("before", base), ("after", target)):
        value = _get(doc, full)
        if value is not MISSING:
            out[name] = copy.deepcopy(value)
    return out


def steps_from_diff(d: dict, base: dict, target: dict) -> tuple[list[dict], list[dict], list[Issue]]:
    """(steps sorted and numbered, skippedOps sorted, issues). Ops with the same (kind, pointer, property) coalesce
    into one step whose sourceOps lists them all."""
    by_key: dict[tuple, dict] = {}
    skipped, issues = [], []
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
        key = (kind, pointer, params.get("property", ""))
        if key in by_key:
            s = by_key[key]
            s["sourceOps"].append(op["pointer"])
            s["impact"] = max(s["impact"], op["impact"], key=_SEVERITY.index)
            continue
        ddl = "additive" if kind in ADDITIVE else "semantic" if params.get("property") in SEMANTIC.get(kind, ()) else "none"
        step = {"seq": 0, "phase": PHASE[kind], "kind": kind, "subject": copy.deepcopy(subject), "pointer": pointer,
                "impact": op["impact"], "ddlImpact": ddl, "reversible": True, "params": params,
                "sourceOps": [op["pointer"]]}
        step["reversible"] = irreversible_reason(step) is None
        by_key[key] = step
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
