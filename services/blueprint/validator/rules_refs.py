"""Rule 3: ids are unique within their collection and every reference resolves."""
from __future__ import annotations

from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid


class _Refs:
    def __init__(self, bp: dict, ctx: ValidationContext | None, rep: Report):
        self.bp, self.ctx, self.rep = bp, ctx, rep
        self.entities = {e["id"]: e for _, e in items(bp.get("entities")) if sid(e.get("id"))}
        self.roles = {r["id"] for _, r in items(bp.get("roles")) if sid(r.get("id"))}
        self.locations = {x["id"] for _, x in items(bp.get("locations")) if sid(x.get("id"))}
        self.workflows = {w["id"]: w for _, w in items(bp.get("workflows")) if sid(w.get("id"))}
        self.approvals = {a["id"] for _, a in items(bp.get("approvals")) if sid(a.get("id"))}
        self.reports = {r["id"] for _, r in items(bp.get("reports")) if sid(r.get("id"))}
        self.components = {c["id"] for _, c in items(bp.get("components")) if sid(c.get("id"))}
        self.transitions = {
            t["id"] for w in self.workflows.values() for _, t in items(w.get("transitions")) if sid(t.get("id"))
        }

    def fields_of(self, entity_id):
        e = self.entities.get(entity_id)
        if e is None:
            return None
        return {f["id"] for _, f in items(e.get("fields")) if sid(f.get("id"))}

    def ref(self, path, value, valid, what) -> None:
        if isinstance(value, str) and value not in valid:
            self.rep.error("BP-REF-001", ptr(*path), f"{what} '{value}' does not exist")

    def refs(self, path, values, valid, what) -> None:
        for i, v in enumerate(as_list(values)):
            self.ref(path + (i,), v, valid, what)

    def field_ref(self, path, entity_id, field_id, what="field") -> None:
        """Resolve a field of an entity. Skipped when the entity itself does not resolve (reported elsewhere)."""
        fields = self.fields_of(entity_id)
        if fields is not None and isinstance(field_id, str) and field_id not in fields:
            self.rep.error("BP-REF-001", ptr(*path), f"{what} '{field_id}' is not a field of entity '{entity_id}'")

    def guard(self, path, entity_id, g) -> None:
        """guard.field is a field id of the entity, or relation.field through one of its relations."""
        f = as_dict(g).get("field")
        if not isinstance(f, str) or entity_id not in self.entities:
            return
        if "." not in f:
            self.field_ref(path + ("field",), entity_id, f, "guard field")
            return
        rel_id, fld = f.split(".", 1)
        rels = {r["id"]: r for _, r in items(self.entities[entity_id].get("relations")) if sid(r.get("id"))}
        if rel_id not in rels:
            self.rep.error("BP-REF-001", ptr(*path, "field"), f"relation '{rel_id}' does not exist on entity '{entity_id}'")
        else:
            self.field_ref(path + ("field",), rels[rel_id].get("target"), fld, "guard field")


def _dups(rep: Report, path: tuple, seq, key: str = "id", what: str = "id") -> None:
    seen: dict = {}
    for i, it in items(seq):
        v = it.get(key)
        if not isinstance(v, str):
            continue
        if v in seen:
            rep.error("BP-ID-001", ptr(*path, i, key), f"duplicate {what} '{v}' (first used at index {seen[v]})")
        else:
            seen[v] = i


def _unique(bp: dict, rep: Report) -> None:
    for coll in ("locations", "components", "entities", "workflows", "roles", "approvals", "reports", "integrations"):
        _dups(rep, (coll,), bp.get(coll))
    for i, e in items(bp.get("entities")):
        _dups(rep, ("entities", i, "fields"), e.get("fields"))
        _dups(rep, ("entities", i, "relations"), e.get("relations"))
        for j, f in items(e.get("fields")):
            _dups(rep, ("entities", i, "fields", j, "options"), f.get("options"), "value", "option value")
    for i, w in items(bp.get("workflows")):
        _dups(rep, ("workflows", i, "states"), w.get("states"))
        _dups(rep, ("workflows", i, "transitions"), w.get("transitions"))
    wt = as_dict(as_dict(as_dict(bp.get("company")).get("locale")).get("workingTime"))
    _dups(rep, ("company", "locale", "workingTime", "reducedPeriods"), wt.get("reducedPeriods"))


def rule_references(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    _unique(bp, rep)
    r = _Refs(bp, ctx, rep)
    for i, loc in items(bp.get("locations")):
        r.ref(("locations", i, "parent"), loc.get("parent"), r.locations, "parent location")
    for i, e in items(bp.get("entities")):
        base = ("entities", i)
        r.ref(base + ("workflow",), e.get("workflow"), r.workflows, "workflow")
        for j, c in items(e.get("components")):
            r.ref(base + ("components", j, "component"), c.get("component"), r.components,
                  "component (not listed in top-level components)")
        for j, rel in items(e.get("relations")):
            r.ref(base + ("relations", j, "target"), rel.get("target"), set(r.entities), "relation target entity")
        for j, f in items(e.get("fields")):
            fp = base + ("fields", j)
            if f.get("type") == "link":
                r.ref(fp + ("target",), f.get("target"), set(r.entities), "link target entity")
            r.refs(fp + ("visibleToRoles",), f.get("visibleToRoles"), r.roles, "role")
            comp = as_dict(f.get("computed"))
            own = r.fields_of(e.get("id")) if sid(e.get("id")) else None
            for k, inp in enumerate(as_list(comp.get("inputs"))):
                if own is not None and isinstance(inp, str) and inp not in own:
                    rep.error("BP-REF-001", ptr(*fp, "computed", "inputs", k),
                              f"computed input '{inp}' is not a field of entity '{e.get('id')}'")
    for i, w in items(r.bp.get("workflows")):
        base = ("workflows", i)
        r.ref(base + ("entity",), w.get("entity"), set(r.entities), "entity")
        states = {s["id"] for _, s in items(w.get("states")) if sid(s.get("id"))}
        for j, t in items(w.get("transitions")):
            tp = base + ("transitions", j)
            r.ref(tp + ("from",), t.get("from"), states, "state")
            r.ref(tp + ("to",), t.get("to"), states, "state")
            r.refs(tp + ("allowedRoles",), t.get("allowedRoles"), r.roles, "role")
            r.refs(tp + ("notify",), t.get("notify"), r.roles, "role")
            r.ref(tp + ("approval",), t.get("approval"), r.approvals, "approval rule")
            for k, g in enumerate(as_list(t.get("guards"))):
                r.guard(tp + ("guards", k), w.get("entity"), g)
    for i, role in items(bp.get("roles")):
        base = ("roles", i)
        for j, p in items(role.get("permissions")):
            pp = base + ("permissions", j)
            ent = p.get("entity")
            r.ref(pp + ("entity",), ent, set(r.entities), "entity")
            for key in ("hiddenFields", "readOnlyFields"):
                for k, fid in enumerate(as_list(p.get(key))):
                    r.field_ref(pp + (key, k), ent, fid)
        hv = as_dict(role.get("homeView"))
        r.refs(base + ("homeView", "reports"), hv.get("reports"), r.reports, "report")
        r.refs(base + ("homeView", "quickActions"), hv.get("quickActions"), r.transitions, "workflow transition")
    for i, a in items(bp.get("approvals")):
        base = ("approvals", i)
        ent = as_dict(a.get("appliesTo")).get("entity")
        r.ref(base + ("appliesTo", "entity"), ent, set(r.entities), "entity")
        for j, s in items(a.get("steps")):
            r.ref(base + ("steps", j, "approverRole"), s.get("approverRole"), r.roles, "role")
            r.ref(base + ("steps", j, "escalateToRole"), s.get("escalateToRole"), r.roles, "role")
        for j, g in enumerate(as_list(a.get("conditions"))):
            r.guard(base + ("conditions", j), ent, g)
    metric_ids, seen_metric = [], False
    for i, rp in items(bp.get("reports")):
        base = ("reports", i)
        ent = rp.get("entity")
        if ent is not None:
            r.ref(base + ("entity",), ent, set(r.entities), "entity")
        r.refs(base + ("visibleToRoles",), rp.get("visibleToRoles"), r.roles, "role")
        r.refs(base + ("schedule", "deliverTo"), as_dict(rp.get("schedule")).get("deliverTo"), r.roles, "role")
        for j, f in items(rp.get("filters")):
            r.field_ref(base + ("filters", j, "field"), ent, f.get("field"), "filter field")
        for j, m in items(rp.get("metrics")):
            seen_metric = True
            if isinstance(m.get("ref"), str):
                metric_ids.append((base + ("metrics", j, "ref"), m["ref"]))
            for k, g in enumerate(as_list(m.get("groupBy"))):
                r.field_ref(base + ("metrics", j, "groupBy", k), ent, g, "groupBy field")
    for i, it in items(bp.get("integrations")):
        for j, m in items(it.get("mappings")):
            tgt = m.get("target")
            if isinstance(tgt, str) and "." in tgt:
                en, fn = tgt.split(".", 1)
                tp = ("integrations", i, "mappings", j, "target")
                if en not in r.entities:
                    rep.error("BP-REF-001", ptr(*tp), f"mapping target entity '{en}' does not exist")
                else:
                    r.field_ref(tp, en, fn, "mapping target field")
    r.ref(("compliance", "eInvoicing", "componentId"),
          as_dict(as_dict(bp.get("compliance")).get("eInvoicing")).get("componentId"), r.components,
          "e-invoicing component (not listed in top-level components)")
    _registry(ctx, rep, "metrics", metric_ids, seen_metric, ("reports",), "metric")
    conns = [(("integrations", i, "connector"), it["connector"]) for i, it in items(bp.get("integrations"))
             if isinstance(it.get("connector"), str)]
    _registry(ctx, rep, "connectors", conns, bool(conns), ("integrations",), "connector")


def _registry(ctx, rep: Report, attr: str, refs, present: bool, where, what: str) -> None:
    """Metrics and connectors resolve only against registries supplied in ctx."""
    known = getattr(ctx, attr, None) if ctx else None
    if known is None:
        if present:
            rep.warn("BP-REF-002", ptr(*where), f"{what} references not checked: no {what} registry supplied")
        return
    for path, v in refs:
        if v not in known:
            rep.error("BP-REF-003", ptr(*path), f"{what} '{v}' is not in the {what} registry")
