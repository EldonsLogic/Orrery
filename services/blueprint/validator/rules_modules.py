"""Module rules (ADR-0079, contracts/blueprint-modules.md): rigid-zone fields on bound entities, view date fields,
the timesheet invoicing component, manufacturing warehouses. The other module cross-reference rules are contract text for now (Q-700)."""
from __future__ import annotations

import re

from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid
from .schema_step import load_schema

_TOKEN = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")
_NO_MONEY = {("projects", "timesheet"), ("projects", "activity_type")}
_DATE_TYPES = {"date", "datetime"}


def is_rigid_name(name: str, terms: dict) -> bool:
    """A name holds a rigid-zone substring, or a camelCase or snake_case token starting with a rigid-zone token."""
    low = name.lower()
    if any(t in low for t in as_list(terms.get("substrings")) if isinstance(t, str)):
        return True
    tokens = [t.lower() for t in _TOKEN.findall(name)]
    return any(tok.startswith(t) for tok in tokens for t in as_list(terms.get("tokens")) if isinstance(t, str))


def _entities(bp: dict) -> dict[str, tuple[int, dict]]:
    return {e["id"]: (i, e) for i, e in items(bp.get("entities")) if sid(e.get("id"))}


def rule_modules(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    modules = as_dict(bp.get("modules"))
    if not modules:
        return
    ents = _entities(bp)
    terms = as_dict(load_schema(ctx).get("x-rigid-zone-terms"))
    _rigid_fields(modules, ents, terms, rep)
    _view_dates(as_dict(modules.get("projects")), ents, rep)
    _invoicing(bp, as_dict(modules.get("projects")), ctx, rep)
    _warehouses(bp, as_dict(modules.get("manufacturing")), rep)


def _rigid_fields(modules: dict, ents: dict, terms: dict, rep: Report) -> None:
    """BP-MOD-001: no rate, cost, tax, amount, posting or valuation field on a module-bound entity."""
    for key, module in modules.items():
        for concept, eid in as_dict(as_dict(module).get("entities")).items():
            if not sid(eid) or eid not in ents:
                continue
            i, ent = ents[eid]
            for j, f in items(ent.get("fields")):
                fid = sid(f.get("id")) or ""
                if fid and is_rigid_name(fid, terms):
                    rep.error("BP-MOD-001", ptr("entities", i, "fields", j, "id"),
                              f"field '{fid}' on {key}.{concept} entity '{eid}' is a rigid-zone field (engine or certified component only)")
                elif (key, concept) in _NO_MONEY and f.get("type") == "money":
                    rep.error("BP-MOD-001", ptr("entities", i, "fields", j, "type"),
                              f"{key}.{concept} entity '{eid}' may not carry a money field ('{fid}')")


def _view_dates(projects: dict, ents: dict, rep: Report) -> None:
    """BP-MOD-002: timeline and calendar fields are date or datetime fields of the view's concept entity."""
    bound = as_dict(projects.get("entities"))
    for v, view in items(projects.get("views")):
        eid = sid(bound.get(view.get("concept")))
        if not eid or eid not in ents:
            continue
        types = {f.get("id"): f.get("type") for _, f in items(ents[eid][1].get("fields"))}
        for kind in ("timeline", "calendar"):
            for key, fid in as_dict(view.get(kind)).items():
                if key not in ("startField", "endField") or not sid(fid):
                    continue
                if types.get(fid) not in _DATE_TYPES:
                    rep.error("BP-MOD-002", ptr("modules", "projects", "views", v, kind, key),
                              f"'{fid}' is not a date or datetime field of entity '{eid}'")


def _invoicing(bp: dict, projects: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """BP-MOD-003: the timesheet invoicing component is listed and, when the registry is known, rigid."""
    comp = sid(as_dict(projects.get("timesheets")).get("invoicingComponent"))
    if not comp:
        return
    path = ptr("modules", "projects", "timesheets", "invoicingComponent")
    if comp not in {c.get("id") for _, c in items(bp.get("components"))}:
        rep.error("BP-MOD-003", path, f"invoicing component '{comp}' is not listed in components")
        return
    if ctx and ctx.registry is not None:
        kinds = {m.get("kind") for m in as_list(ctx.registry.get(comp)) if isinstance(m, dict)}
        if kinds and kinds != {"rigid"}:
            rep.error("BP-MOD-003", path, f"invoicing component '{comp}' is not a rigid (certified) component")


def _warehouses(bp: dict, mfg: dict, rep: Report) -> None:
    """BP-MOD-004: WIP, finished goods and scrap are locations of kind warehouse and three different ones."""
    wh = as_dict(mfg.get("warehouses"))
    kinds = {l.get("id"): l.get("kind") for _, l in items(bp.get("locations"))}
    seen: dict[str, str] = {}
    for key in ("workInProgress", "finishedGoods", "scrap"):
        lid = sid(wh.get(key))
        if not lid:
            continue
        path = ptr("modules", "manufacturing", "warehouses", key)
        if kinds.get(lid) != "warehouse":
            rep.error("BP-MOD-004", path, f"'{lid}' is not a location of kind warehouse")
        if lid in seen:
            rep.error("BP-MOD-004", path, f"{key} uses the same warehouse '{lid}' as {seen[lid]}")
        seen.setdefault(lid, key)
