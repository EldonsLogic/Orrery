"""From diff ops to neutral steps, post-conditions and risk (contracts/engine-adapter.md section 9).

An initial build (base null) has no base revision, so its source diff is bpdiff's diff from an empty skeleton to the
target (open question 1 in __init__). Every op lands exactly once in a step's sourceOps or in skippedOps; an op no
rule covers refuses the compile.
"""
from __future__ import annotations

import copy
import heapq
import json
from functools import lru_cache
from typing import Any

from ._deps import CONTRACTS
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


@lru_cache(maxsize=1)
def builtin_entities() -> frozenset[str]:
    """Entities that map to a document type the engine ships with (contracts/engine-builtin-entities.json, Q-722): the
    type exists before any step, so a Link into one needs no order."""
    doc = json.loads((CONTRACTS / "engine-builtin-entities.json").read_text(encoding="utf-8"))
    return frozenset(doc["entities"])


def link_targets(definition: Any) -> set[str]:
    """Entity ids an entity definition links to: every field of type `link` and every relation (reference, child table
    and many-to-many all point the engine at the target type). Other field types are excluded even if they carry a
    `target`: the schema allows `target` only for type link, so on any other type it is no Link the engine resolves."""
    if not isinstance(definition, dict):
        return set()
    fields = [f for f in definition.get("fields") or [] if isinstance(f, dict) and f.get("type") == "link"]
    relations = [r for r in definition.get("relations") or [] if isinstance(r, dict)]
    return {el["target"] for el in fields + relations if isinstance(el.get("target"), str)}


def _edges(by_id: dict) -> tuple[list[tuple], list[tuple]]:
    """(hard, soft) edges among the entities of `by_id`, each (pointer, target, entity, element id): the target must
    come before the entity. Hard: a field of type `link`, which the adapter creates with the entity. Soft: a relation, an
    ordering preference only, because the adapter does not create inline relations on entity.add (#391 review). A
    self-link, a link outside the group and a link into a built-in type add no edge."""
    hard, soft = [], []
    for e, s in by_id.items():
        d = s["params"]["definition"]
        if not isinstance(d, dict):
            continue
        into = set(by_id) - builtin_entities() - {e}
        for coll, out in (("fields", hard), ("relations", soft)):
            for el in d.get(coll) or []:
                if isinstance(el, dict) and isinstance(el.get("target"), str) and el["target"] in into \
                        and (coll == "relations" or el.get("type") == "link"):
                    out.append((f"{s['pointer']}/{coll}/{_esc(el.get('id'))}", el["target"], e, el.get("id")))
    return sorted(hard), sorted(soft)


def _reaches(after: dict[str, set[str]], src: str, dst: str) -> bool:
    seen, todo = set(), [src]
    while todo:
        e = todo.pop()
        if e == dst:
            return True
        if e not in seen:
            seen.add(e)
            todo += after[e]
    return False


def _graph(by_id: dict, hard: list[tuple], soft: list[tuple]) -> dict[str, set[str]]:
    """target -> entities that come after it: every hard edge, then each soft edge in pointer order unless it would
    close a cycle (dropped)."""
    after: dict[str, set[str]] = {e: set() for e in by_id}
    for _, t, e, _ in hard:
        after[t].add(e)
    for _, t, e, _ in soft:
        if not _reaches(after, e, t):
            after[t].add(e)
    return after


def _closing_links(by_id: dict) -> list[tuple]:
    """The hard edges to move out of their entity.add so no hard cycle remains: while one does, the edge on a cycle with
    the smallest pointer (deterministic; one per cycle unless cycles share it)."""
    hard, _ = _edges(by_id)
    out = []
    while True:
        after = _graph(by_id, hard, [])
        on_cycle = [edge for edge in hard if _reaches(after, edge[2], edge[1])]
        if not on_cycle:
            return out
        out.append(on_cycle[0])
        hard.remove(on_cycle[0])


def _split(step: dict, links: list[tuple]) -> list[dict]:
    """The entity.add without the closing Link fields, a phase 5 field.add per Link (pointer order) and, when appending
    them leaves the fields out of Blueprint order, a phase 6 field.reorder. The new steps implement the same diff op,
    so they repeat the entity.add's sourceOps (ADR-0075)."""
    e, defn = step["subject"]["id"], copy.deepcopy(step["params"]["definition"])
    moved = {fid for *_, fid in links}
    order = [f.get("id") for f in defn["fields"]]
    fields = {f.get("id"): f for f in defn["fields"]}
    defn["fields"] = [f for f in defn["fields"] if f.get("id") not in moved]
    head = {**step, "subject": copy.deepcopy(step["subject"]), "params": {"definition": defn},
            "sourceOps": list(step["sourceOps"])}
    out = [head]
    for ptr, _, _, fid in sorted(links):
        add = _step("field.add", {"kind": "field", "id": fid, "parents": [{"kind": "entity", "id": e}]}, ptr,
                    step["impact"], {"definition": copy.deepcopy(fields[fid])}, "")
        out.append({**add, "sourceOps": list(step["sourceOps"])})
    previous = [f.get("id") for f in defn["fields"]] + [fid for *_, fid in sorted(links)]
    if previous != order:
        ro = _step("field.reorder", {"kind": "entity", "id": e, "parents": []}, step["pointer"] + "/fields",
                   step["impact"], {"order": order, "previousOrder": previous}, "")
        out.append({**ro, "sourceOps": list(step["sourceOps"])})
    return out


def _topo(group: list[dict], dependants_first: bool) -> list[dict]:
    """Kahn's algorithm over the edges among `group` (_edges, _graph), ties by pointer. A hard cycle left here (a
    quarantine, or a restore) is broken at the smallest remaining pointer."""
    by_id = {s["subject"]["id"]: s for s in group}
    if len(by_id) != len(group):  # a duplicate subject: leave the order alone, CMP-ART-006 refuses it
        return group
    before = _graph(by_id, *_edges(by_id))
    after = before if not dependants_first else {e: {t for t in by_id if e in before[t]} for e in by_id}
    need = {e: sum(e in a for a in after.values()) for e in by_id}
    ptr = {e: by_id[e]["pointer"] for e in by_id}
    ready = [(ptr[e], e) for e in by_id if not need[e]]
    heapq.heapify(ready)
    order, left = [], set(by_id)
    while left:
        if not ready:
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
    return order


def order_by_links(steps: list[dict], *, restores: bool = False) -> tuple[list[dict], list[Issue]]:
    """BPL-051 (Q-691, ADR-0075): reorder the entity.add steps (phase 4) so every Link target is created before the
    entities that link to it, and the entity.quarantine steps (phase 16) so dependants go first. `steps` must already
    be in the 9.4 sort order; every other step keeps its place. A hard Link cycle among new entities is split: its
    closing Link fields (_closing_links) move to a later field.add, so the compile never refuses for a cycle. A
    quarantine cycle is broken by pointer, as quarantine keeps the stored entity; so is an add cycle when `restores`
    (an inverse, whose entity.add steps only re-activate entities the forward quarantined: the stored types still
    exist, so their Links resolve in any order). Returns (steps, issues); no Link graph refuses, so issues is empty."""
    out = list(steps)
    adds = {s["subject"]["id"]: s for s in out if s["kind"] == "entity.add"}
    links = _closing_links(adds) if not restores and len(adds) == sum(s["kind"] == "entity.add" for s in out) else []
    if links:
        by_entity: dict[str, list[tuple]] = {}
        for link in links:
            by_entity.setdefault(link[2], []).append(link)
        split = {e: _split(adds[e], ls) for e, ls in by_entity.items()}
        out = [x for s in out for x in (split[s["subject"]["id"]] if s["kind"] == "entity.add" and
                                         s["subject"]["id"] in split else [s])]
        out.sort(key=lambda s: (s["phase"], s["pointer"], s["kind"]))  # stable: settings.set keep their property order
    for kind, dependants_first in (("entity.add", False), ("entity.quarantine", True)):
        idx = [i for i, s in enumerate(out) if s["kind"] == kind]
        for i, s in zip(idx, _topo([out[i] for i in idx], dependants_first)):
            out[i] = s
    return out, []


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
