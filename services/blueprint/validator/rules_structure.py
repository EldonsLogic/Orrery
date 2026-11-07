"""Rules 4 to 7: locale coverage, workflow graph, approvals, role scope."""
from __future__ import annotations

from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid
from .schema_step import load_schema, walk_refs


def rule_i18n(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 4. Every localizedText (found by walking the contract, so new positions are covered)
    carries a non-empty string for every locale in meta.locales; default and company locales are listed."""
    meta = as_dict(bp.get("meta"))
    locales = [x for x in as_list(meta.get("locales")) if isinstance(x, str)]
    if not locales:
        return
    schema = load_schema(ctx)
    for name, path, value in walk_refs(bp, schema, schema):
        if name != "localizedText" or not isinstance(value, dict):
            continue
        missing = [loc for loc in locales if not (isinstance(value.get(loc), str) and value[loc].strip())]
        if missing:
            rep.error("BP-I18N-001", ptr(*path), f"localized text is missing locale(s): {', '.join(missing)}")
    for path, v in ((("meta", "defaultLocale"), meta.get("defaultLocale")),
                    (("i18n", "defaultLocale"), as_dict(bp.get("i18n")).get("defaultLocale"))):
        if isinstance(v, str) and v not in locales:
            rep.error("BP-I18N-002", ptr(*path), f"default locale '{v}' is not in meta.locales")
    langs = as_dict(as_dict(bp.get("company")).get("languages"))
    cand = [(("company", "languages", "primary"), langs.get("primary"))]
    cand += [(("company", "languages", "secondary", i), v) for i, v in enumerate(as_list(langs.get("secondary")))]
    for path, v in cand:
        if isinstance(v, str) and v not in locales:
            rep.error("BP-I18N-003", ptr(*path), f"company language '{v}' is not in meta.locales")


def rule_workflow(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 5. One initial state, at least one final, all states reachable, no dead ends."""
    for i, w in items(bp.get("workflows")):
        base = ("workflows", i)
        states = [(j, s) for j, s in items(w.get("states")) if sid(s.get("id"))]
        kind = {s["id"]: s.get("kind") for _, s in states}
        initial = [s for s, k in kind.items() if k == "initial"]
        if len(initial) != 1:
            rep.error("BP-WF-001", ptr(*base, "states"), f"expected exactly one initial state, found {len(initial)}")
        if not any(k == "final" for k in kind.values()):
            rep.error("BP-WF-002", ptr(*base, "states"), "workflow has no final state")
        edges: dict[str, list[str]] = {}
        for j, t in items(w.get("transitions")):
            a, b = t.get("from"), t.get("to")
            if not (isinstance(a, str) and isinstance(b, str)):
                continue
            edges.setdefault(a, []).append(b)
            if kind.get(a) == "final":
                rep.warn("BP-WF-005", ptr(*base, "transitions", j, "from"), f"transition leaves final state '{a}'")
        seen, stack = set(initial), list(initial)
        while stack:
            for nxt in edges.get(stack.pop(), []):
                if nxt in kind and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for j, s in states:
            if initial and s["id"] not in seen:
                rep.error("BP-WF-003", ptr(*base, "states", j), f"state '{s['id']}' is not reachable from the initial state")
            if s.get("kind") != "final" and not edges.get(s["id"]):
                rep.error("BP-WF-004", ptr(*base, "states", j), f"non-final state '{s['id']}' has no outgoing transition")


def rule_approvals(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 6.

    Step roles must exist (reported as BP-REF-001 by rule 3). Step orders must be unique and run 1..n.
    Interpretation of 'a role cannot approve its own submission unless selfApproval is true and the
    owner role holds it': selfApproval=true is accepted only when a role whose function is 'owner'
    has the 'approve' action on appliesTo.entity. selfApproval=false (default) is always accepted.
    """
    owner_approves: set[str] = set()
    for _, r in items(bp.get("roles")):
        if r.get("function") == "owner":
            for _, p in items(r.get("permissions")):
                if "approve" in as_list(p.get("actions")) and sid(p.get("entity")):
                    owner_approves.add(p["entity"])
    for i, a in items(bp.get("approvals")):
        base = ("approvals", i)
        orders = [s.get("order") for _, s in items(a.get("steps"))]
        ints = [o for o in orders if isinstance(o, int) and not isinstance(o, bool)]
        if len(ints) == len(orders) and sorted(ints) != list(range(1, len(ints) + 1)):
            rep.error("BP-APR-002", ptr(*base, "steps"),
                      f"step orders must be unique and contiguous from 1, got {orders}")
        ent = as_dict(a.get("appliesTo")).get("entity")
        if a.get("selfApproval") is True and ent not in owner_approves:
            rep.error("BP-APR-003", ptr(*base, "selfApproval"),
                      "selfApproval is true but no owner-function role holds 'approve' on the entity")


def rule_roles(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 7. Scope values are locations of the same kind; one admin role; an owner role (warning)."""
    kinds = {x["id"]: x.get("kind") for _, x in items(bp.get("locations")) if sid(x.get("id"))}
    roles = list(items(bp.get("roles")))
    for i, r in roles:
        sc = as_dict(r.get("scope"))
        t = sc.get("type")
        if t in ("branch", "warehouse", "department"):
            for j, v in enumerate(as_list(sc.get("values"))):
                if isinstance(v, str) and kinds.get(v) != t:
                    why = "does not exist" if v not in kinds else f"is a {kinds[v]}, not a {t}"
                    rep.error("BP-ROLE-001", ptr("roles", i, "scope", "values", j), f"scope value '{v}' {why}")
    if roles and not any(r.get("isAdmin") is True for _, r in roles):
        rep.error("BP-ROLE-002", ptr("roles"), "at least one role must have isAdmin true")
    if roles and not any(r.get("function") == "owner" for _, r in roles):
        rep.warn("BP-ROLE-003", ptr("roles"), "no role has function 'owner'")
