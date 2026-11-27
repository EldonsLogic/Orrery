"""Module rules (ADR-0079, contracts/blueprint-modules.md): engine rigid-zone fields on bound entities, view date
fields, the timesheet invoicing component. The other module cross-reference rules are contract text for now (Q-700)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid
from .schema_step import DEFAULT_SCHEMA_PATH

RIGID_FIELDS_PATH = DEFAULT_SCHEMA_PATH.parent / "engine-rigid-fields.json"
_DATE_TYPES = {"date", "datetime"}
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def norm(name: str) -> str:
    """valuation_rate, valuationRate and ValuationRate are the same engine field."""
    return _NON_ALNUM.sub("", name.lower())


@lru_cache(maxsize=4)
def _load(path: str) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("concepts"), dict) else None


def load_rigid_fields(ctx: ValidationContext | None = None) -> dict | None:
    """contracts/engine-rigid-fields.json, or None when it is missing or unreadable (the rule then fails closed)."""
    return _load(str(RIGID_FIELDS_PATH))


def _names(groups: object) -> set[str]:
    return {norm(n) for names in as_dict(groups).values() for n in as_list(names) if isinstance(n, str)}


def rigid_set(data: dict, module: str, concept: str) -> set[str] | None:
    """Engine rigid-zone field names for a module concept: its record types' own fields plus their row fields
    (a Blueprint may model rows inline or as child_table entities). None when the concept is not in the list."""
    records = data["concepts"].get(f"{module}.{concept}")
    if not isinstance(records, list):
        return None
    out: set[str] = set()
    types = as_dict(data.get("recordTypes"))
    for rt in records:
        rec = types.get(rt)
        if not isinstance(rec, dict):
            return None
        out |= _names(rec.get("fields"))
        for row in as_dict(rec.get("rows")).values():
            out |= _names(row)
    return out


def _entities(bp: dict) -> dict[str, tuple[int, dict]]:
    return {e["id"]: (i, e) for i, e in items(bp.get("entities")) if sid(e.get("id"))}


def rule_modules(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    modules = as_dict(bp.get("modules"))
    if not modules:
        return
    ents = _entities(bp)
    _rigid_fields(modules, ents, load_rigid_fields(ctx), rep)
    _view_dates(as_dict(modules.get("projects")), ents, rep)
    _invoicing(bp, as_dict(modules.get("projects")), ctx, rep)


def _rows(eid: str, ents: dict) -> list[str]:
    """The bound entity and every entity reached from it through child_table relations, at any depth."""
    seen, todo = [eid], [eid]
    while todo:
        for _, rel in items(ents[todo.pop()][1].get("relations")):
            tgt = sid(rel.get("target"))
            if rel.get("kind") == "child_table" and tgt in ents and tgt not in seen:
                seen.append(tgt)
                todo.append(tgt)
    return seen


def _rigid_fields(modules: dict, ents: dict, data: dict | None, rep: Report) -> None:
    """BP-MOD-001: no Blueprint field or component parameter on a module-bound entity, or on its child_table rows,
    declares, overrides, renames or sets a default or options on an engine rigid-zone field
    (contracts/engine-rigid-fields.json). Custom fields with any other name are plain data and pass."""
    if data is None:
        rep.error("BP-MOD-001", ptr("modules"), "the engine rigid-zone field list is missing or unreadable")
        return
    for key, module in modules.items():
        for concept, eid in as_dict(as_dict(module).get("entities")).items():
            if not sid(eid) or eid not in ents:
                continue
            rigid = rigid_set(data, key, concept)
            if rigid is None:
                rep.error("BP-MOD-001", ptr("modules", key, "entities", concept),
                          f"no engine rigid-zone field list for concept {key}.{concept}")
                continue
            for row in _rows(eid, ents):
                i, ent = ents[row]
                where = f"{key}.{concept} entity '{eid}'" + (f" (row entity '{row}')" if row != eid else "")
                for j, f in items(ent.get("fields")):
                    fid = sid(f.get("id")) or ""
                    if fid and norm(fid) in rigid:
                        rep.error("BP-MOD-001", ptr("entities", i, "fields", j, "id"),
                                  f"field '{fid}' on {where} is an engine rigid-zone field (engine or certified component only)")
                for c, comp in items(ent.get("components")):
                    for pkey in as_dict(comp.get("parameters")):
                        if norm(pkey) in rigid:
                            rep.error("BP-MOD-001", ptr("entities", i, "components", c, "parameters", pkey),
                                      f"parameter '{pkey}' on {where} sets an engine rigid-zone field")


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
        if not kinds:
            rep.error("BP-MOD-003", path, f"invoicing component '{comp}' is not in the component registry")
        elif kinds != {"rigid"}:
            rep.error("BP-MOD-003", path, f"invoicing component '{comp}' is not a rigid (certified) component")
