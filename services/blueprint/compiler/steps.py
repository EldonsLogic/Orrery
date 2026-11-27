"""From diff ops to neutral steps, post-conditions and risk (contracts/engine-adapter.md section 9).

An initial build (base null) has no base revision, so its source diff is bpdiff's diff from an empty skeleton to the
target (open question 1 in __init__). Every op lands exactly once in a step's sourceOps or in skippedOps; an op no
rule covers refuses the compile.
"""
from __future__ import annotations

import copy
import heapq
from typing import Any

from .components import touches_ledger_or_tax
from .result import Issue

# Contract 9.4 phases.
PHASE = {"settings.set": 1, "component.enable": 2, "component.configure": 2, "location.upsert": 3, "entity.add": 4,
         "field.add": 5, "relation.add": 5, "option.add": 5, "binding.add": 5, "entity.set_property": 6,
         "field.set_property": 6, "relation.set_property": 6, "binding.set_property": 6, "field.reorder": 6,
         "option.reorder": 6, "role.upsert": 7, "workflow.upsert": 8, "approval.upsert": 9, "report.upsert": 10,
         "report.disable": 11, "approval.disable": 12, "workflow.disable": 13, "role.disable": 14,
         "binding.disable": 15, "option.quarantine": 15, "relation.quarantine": 15, "field.quarantine": 15,
         "entity.quarantine": 16, "location.disable": 17, "component.disable": 18}
# Contract 9.3: `add` of a top-level element.
ADD_KIND = {"locations": "location.upsert", "components": "component.enable", "entities": "entity.add",
            "roles": "role.upsert", "workflows": "workflow.upsert", "approvals": "approval.upsert",
            "reports": "report.upsert"}
SETTINGS_SECTIONS = ("company", "compliance")
I18N_SETTINGS = ("defaultLocale", "labelOverrides")  # contract 9.3 (ADR-0057 Q-52)
# Contract 9.3 "Skipped": first pointer segment -> reason.
SKIP = {"meta": "meta", "branding": "branding", "integrations": "integration", "provenance": "provenance"}
KEYED_COLLECTIONS = tuple(ADD_KIND) + ("integrations",)
ADDITIVE = ("entity.add", "field.add", "relation.add")
# Order-significant child collections checked with order_equals; their elements are keyed by `id` (bpdiff model).
ORDER_CHECKS = (("entities", "fields"), ("workflows", "states"))


def skeleton(target: dict) -> dict:
    """The empty revision an initial build starts from: same top-level containers, no content. `$schema` is copied
    (it names the contract file, not tenant configuration); meta and branding are absent, so each is one skipped op."""
    sk: dict[str, Any] = {}
    if "$schema" in target:
        sk["$schema"] = copy.deepcopy(target["$schema"])
    for key in KEYED_COLLECTIONS:
        if key in target:
            sk[key] = []
    for key in SETTINGS_SECTIONS + ("i18n",):
        if key in target:
            sk[key] = {}
    return sk


def _esc(seg: Any) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def _step(kind: str, subject: dict, pointer: str, impact: str, params: dict, source: str) -> dict:
    return {"seq": 0, "phase": PHASE[kind], "kind": kind, "subject": copy.deepcopy(subject), "pointer": pointer,
            "impact": impact, "ddlImpact": "additive" if kind in ADDITIVE else "none", "reversible": True,
            "params": params, "sourceOps": [source]}


def steps_from_ops(ops: list[dict]) -> tuple[list[dict], list[dict], list[Issue]]:
    """(steps sorted and numbered, skippedOps sorted, issues for ops no rule covers)."""
    steps, skipped, issues = [], [], []
    for op in ops:
        path, pointer = op["path"], op["pointer"]
        head = path[0] if path else None
        if op["op"] != "add":
            issues.append(Issue("CMP-ART-001", pointer, f"an initial build cannot contain a '{op['op']}' operation"))
        elif head in SKIP:
            skipped.append({"pointer": pointer, "reason": SKIP[head]})
        elif head == "i18n" and len(path) >= 2 and path[1] == "glossary":
            skipped.append({"pointer": pointer, "reason": "i18n_glossary"})
        elif (head in SETTINGS_SECTIONS and len(path) >= 2) or (head == "i18n" and len(path) >= 2 and path[1] in I18N_SETTINGS):
            prop = "".join("/" + _esc(s) for s in path[1:])
            steps.append(_step("settings.set", op["subject"], "/" + head, op["impact"],
                               {"property": prop, "after": copy.deepcopy(op["after"])}, pointer))
        elif head in ADD_KIND and len(path) == 2:
            steps.append(_step(ADD_KIND[head], op["subject"], pointer, op["impact"],
                               {"definition": copy.deepcopy(op["after"])}, pointer))
        else:
            issues.append(Issue("CMP-ART-001", pointer, "no compile rule covers this Blueprint operation"))
    # Contract 9.4 orders by (phase, pointer, kind); several settings.set steps share one subject pointer, so the
    # property breaks the tie (ADR-0057 Q-51).
    steps.sort(key=lambda s: (s["phase"], s["pointer"], s["kind"],
                              s["params"]["property"] if s["kind"] == "settings.set" else ""))
    steps, cycles = order_by_links(steps)
    issues += cycles
    for i, s in enumerate(steps, 1):
        s["seq"] = i
    skipped.sort(key=lambda s: s["pointer"])
    return steps, skipped, issues


def link_targets(definition: Any) -> set[str]:
    """Entity ids an entity definition links to: every field of type `link` and every relation (reference, child table
    and many-to-many all point the engine at the target type). Other field types are excluded even if they carry a
    `target`: the schema allows `target` only for type link, so on any other type it is no Link the engine resolves."""
    if not isinstance(definition, dict):
        return set()
    fields = [f for f in definition.get("fields") or [] if isinstance(f, dict) and f.get("type") == "link"]
    relations = [r for r in definition.get("relations") or [] if isinstance(r, dict)]
    return {el["target"] for el in fields + relations if isinstance(el.get("target"), str)}


def _topo(group: list[dict], dependants_first: bool) -> tuple[list[dict], list[str]]:
    """Kahn's algorithm over the Links among `group`, ties by pointer. A self-link and a link to an entity outside the
    group add no edge. On a cycle the smallest remaining pointer is taken next; returns (order, cycle member pointers)."""
    by_id = {s["subject"]["id"]: s for s in group}
    if len(by_id) != len(group):  # a duplicate subject: leave the order alone, CMP-ART-006 refuses it
        return group, []
    after: dict[str, set[str]] = {e: set() for e in by_id}  # e -> entities that must come after e
    for e, s in by_id.items():
        for t in link_targets(s["params"]["definition"]) & set(by_id) - {e}:
            after[e if dependants_first else t].add(t if dependants_first else e)
    need = {e: sum(e in a for a in after.values()) for e in by_id}
    ptr = {e: by_id[e]["pointer"] for e in by_id}
    ready = [(ptr[e], e) for e in by_id if not need[e]]
    heapq.heapify(ready)
    order, left, forced = [], set(by_id), False
    while left:
        if not ready:
            forced = True
            heapq.heappush(ready, min((ptr[e], e) for e in left))
        _, e = heapq.heappop(ready)
        if e not in left:
            continue
        order.append(by_id[e])
        left.discard(e)
        for d in sorted(after[e]):
            need[d] -= 1
            if need[d] == 0 and d in left:
                heapq.heappush(ready, (ptr[d], d))
    return order, sorted(ptr[e] for e in _stuck(by_id, after)) if forced else []


def _stuck(by_id: dict, after: dict) -> set[str]:
    """Entities on a Link cycle: the members of every strongly connected component of size > 1 (self-links add no
    edge), found as the entities reachable again from one of their own successors. An entity between two cycles is
    not on one and is not named."""
    def reach(start: set[str]) -> set[str]:
        seen, todo = set(), list(start)
        while todo:
            e = todo.pop()
            if e not in seen:
                seen.add(e)
                todo += after[e]
        return seen
    return {e for e in by_id if e in reach(after[e])}


def order_by_links(steps: list[dict], *, restores: bool = False) -> tuple[list[dict], list[Issue]]:
    """BPL-051 (Q-691): reorder the entity.add steps (phase 4) so every Link target is created before the entities that
    link to it, and the entity.quarantine steps (phase 16) so dependants go first. `steps` must already be in the
    9.4 sort order; every other step keeps its place. A Link cycle among new entities refuses (CMP-ART-007). A
    quarantine cycle is broken by pointer, as quarantine keeps the stored entity; so is an add cycle when `restores`
    (an inverse, whose entity.add steps only re-activate entities the forward quarantined: the stored types still
    exist, so their Links resolve in any order)."""
    out, issues = list(steps), []
    for kind, dependants_first in (("entity.add", False), ("entity.quarantine", True)):
        idx = [i for i, s in enumerate(out) if s["kind"] == kind]
        order, cycle = _topo([out[i] for i in idx], dependants_first)
        for i, s in zip(idx, order):
            out[i] = s
        if cycle and not dependants_first and not restores:
            ids = ", ".join(p.rsplit("/", 1)[-1] for p in cycle)
            issues += [Issue("CMP-ART-007", p, f"Link cycle among new entities ({ids}); add the closing Link as a "
                             "field in a later revision") for p in cycle]
    return out, issues


def post_conditions(steps: list[dict], target: dict) -> list[dict]:
    """At least one check per step subject (9.7), using only ids and counts, never properties the adapter may not
    export (15.2): `exists` per subject (`quarantined` or `disabled` for a removal), `count_equals` per top-level
    collection, `order_equals` for the fields and states of entities and workflows a step touches."""
    rows: dict[tuple, dict] = {}
    for s in steps:
        check = "quarantined" if s["kind"].endswith(".quarantine") else "disabled" if s["kind"].endswith(".disable") \
            else "exists"
        rows[(s["pointer"], check)] = {"check": check, "pointer": s["pointer"]}
    for section in ADD_KIND:
        if any(s["pointer"].startswith("/" + section + "/") for s in steps):
            rows[("/" + section, "count_equals")] = {"check": "count_equals", "pointer": "/" + section,
                                                     "expected": len(target[section])}
    for section, child in ORDER_CHECKS:
        for node in target.get(section, []):
            keys = [c["id"] for c in node.get(child, [])]
            own = f"/{section}/{_esc(node['id'])}"
            if keys and any(s["pointer"] == own or s["pointer"].startswith(own + "/") for s in steps):
                pointer = f"/{section}/{_esc(node['id'])}/{child}"
                rows[(pointer, "order_equals")] = {"check": "order_equals", "pointer": pointer, "expected": keys}
    out = []
    for i, key in enumerate(sorted(rows), 1):
        out.append({"id": f"pc_{i:03d}", **rows[key]})
    return out


def ledger_or_tax_subjects(steps: list[dict], resolved: dict[str, dict]) -> bool:
    """Contract risk.touchesLedgerOrTax: a step's subject is, or is bound to, a ledger or tax component."""
    hot = {cid for cid, m in resolved.items() if touches_ledger_or_tax(m)}
    for s in steps:
        if s["kind"] == "component.enable" and s["subject"]["id"] in hot:
            return True
        if s["kind"] == "entity.add":
            bound = {b.get("component") for b in s["params"]["definition"].get("components", []) if isinstance(b, dict)}
            if bound & hot:
                return True
    return False


def risk(diff_risk: dict, steps: list[dict], ledger_or_tax: bool) -> dict:
    """counts, total, maxImpact, touchesCompliance, touchesAccess are copied from the diff's risk (9.2)."""
    out = {k: copy.deepcopy(diff_risk[k]) for k in ("counts", "total", "maxImpact", "touchesCompliance", "touchesAccess")}
    out["needsDdlPlanGate"] = bool(diff_risk["needsDdlPlanGate"]) or any(s["ddlImpact"] != "none" for s in steps)
    out["touchesLedgerOrTax"] = ledger_or_tax
    out["requiresTeamReview"] = bool(out["touchesCompliance"]) or ledger_or_tax
    out["irreversibleSteps"] = sum(1 for s in steps if not s["reversible"])
    return out


def duplicate_step_keys(steps: list[dict]) -> list[tuple]:
    """Uniqueness keys used by more than one step (contract 9.4): (kind, pointer); settings.set adds params.property."""
    seen, dup = set(), []
    for s in steps:
        key = (s["kind"], s["pointer"]) + ((s["params"].get("property"),) if s["kind"] == "settings.set" else ())
        if key in seen and key not in dup:
            dup.append(key)
        seen.add(key)
    return dup
