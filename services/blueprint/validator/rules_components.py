"""Rules 8 and 9: component bindings against the registry, and computed functions."""
from __future__ import annotations

from . import semver
from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid


def _manifests(ctx: ValidationContext, cid: str) -> list[dict]:
    out = []
    for m in as_list((ctx.registry or {}).get(cid)):
        if isinstance(m, dict) and isinstance(m.get("version"), str):
            try:
                semver.parse_version(m["version"])
            except ValueError:
                continue
            out.append(m)
    return out


def resolve_components(bp: dict, ctx: ValidationContext | None) -> dict[str, dict]:
    """Component id -> highest registry manifest satisfying the Blueprint's versionRange (silent on problems)."""
    out: dict[str, dict] = {}
    if not ctx or ctx.registry is None:
        return out
    for _, c in items(bp.get("components")):
        cid, rng = sid(c.get("id")), sid(c.get("versionRange"))
        if not cid or not rng:
            continue
        ms = _manifests(ctx, cid)
        try:
            best = semver.highest_satisfying([m["version"] for m in ms], rng)
        except ValueError:
            continue
        if best:
            out[cid] = next(m for m in ms if m["version"] == best)
    return out


def _provides_capability(m: dict, cap: str) -> bool:
    return any(isinstance(p, dict) and p.get("capability") == cap for p in as_list(m.get("provides")))


def rule_components(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 8. Each listed component exists in the registry in a version inside its range, its
    `requires` are met by the other listed components, and engineCompatibility covers meta.engineTarget.
    engineRange is a range over the engine's own versions, which the Blueprint does not state, so only
    adapter and versionSet (against `testedAgainst`) are compared."""
    comps = list(items(bp.get("components")))
    if not comps:
        return
    if ctx is None or ctx.registry is None:
        rep.warn("BP-CMP-005", ptr("components"), "component bindings not checked: no component registry supplied")
        return
    resolved: dict[str, dict] = {}
    for i, c in comps:
        cid, rng = sid(c.get("id")), sid(c.get("versionRange"))
        if not cid or not rng:
            continue
        ms = _manifests(ctx, cid)
        if not ms:
            rep.error("BP-CMP-001", ptr("components", i, "id"), f"component '{cid}' is not in the registry")
            continue
        try:
            best = semver.highest_satisfying([m["version"] for m in ms], rng)
        except ValueError:
            rep.error("BP-CMP-007", ptr("components", i, "versionRange"), f"version range '{rng}' is not valid")
            continue
        if best is None:
            have = ", ".join(sorted(m["version"] for m in ms))
            rep.error("BP-CMP-002", ptr("components", i, "versionRange"),
                      f"no registry version of '{cid}' satisfies '{rng}' (available: {have})")
            continue
        resolved[cid] = next(m for m in ms if m["version"] == best)
    target = as_dict(as_dict(bp.get("meta")).get("engineTarget"))
    index = {cid: i for i, c in comps if (cid := sid(c.get("id")))}
    for cid, m in resolved.items():
        base = ("components", index[cid])
        for k, req in items(m.get("requires")):
            _check_requirement(rep, base, cid, k, req, resolved)
        if not target:
            rep.warn("BP-CMP-006", ptr("meta"), "engine compatibility not checked: meta.engineTarget is not set")
            target = {"_skip": True}
        if "_skip" in target:
            continue
        ec = as_dict(m.get("engineCompatibility"))
        if ec.get("adapter") != target.get("adapter"):
            rep.error("BP-CMP-004", ptr(*base, "id"),
                      f"'{cid}' targets adapter '{ec.get('adapter')}', Blueprint targets '{target.get('adapter')}'")
        vs = target.get("versionSet")
        tested = [t for t in as_list(ec.get("testedAgainst")) if isinstance(t, str)]
        if isinstance(vs, str) and vs not in tested:
            rep.error("BP-CMP-004", ptr(*base, "id"), f"'{cid}' is not tested against version set '{vs}'")


def _check_requirement(rep, base, cid, k, req, resolved) -> None:
    rng = sid(req.get("versionRange")) or "*"
    try:
        if "component" in req:
            other = resolved.get(req["component"])
            ok = other is not None and semver.satisfies(other["version"], rng)
            what = f"component '{req['component']}' {rng}"
        else:
            cap = req.get("capability")
            ok = any(o is not resolved[cid] and _provides_capability(o, cap) and semver.satisfies(o["version"], rng)
                     for o in resolved.values())
            what = f"capability '{cap}' {rng}"
    except (ValueError, TypeError):
        rep.error("BP-CMP-007", ptr(*base, "id"), f"'{cid}' has an invalid requirement range '{rng}'")
        return
    if not ok:
        rep.error("BP-CMP-003", ptr(*base, "id"), f"'{cid}' requires {what}, which the listed components do not provide")


def rule_functions(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 9. computed.function must be a `function` artifact (ref == function id) in the `provides`
    of a component bound to the same entity. The manifest schema can express this (artifact type
    'function'), so no prefix heuristic is used. Without a registry the check is skipped with a warning."""
    uses = [(i, j, f) for i, e in items(bp.get("entities")) for j, f in items(e.get("fields"))
            if isinstance(f.get("computed"), dict)]
    if not uses:
        return
    if ctx is None or ctx.registry is None:
        rep.warn("BP-FN-002", ptr("entities"), "computed functions not checked: no component registry supplied")
        return
    resolved = resolve_components(bp, ctx)
    entities = list(items(bp.get("entities")))
    for i, j, f in uses:
        fn = f["computed"].get("function")
        e = dict(entities)[i]
        provided = set()
        for _, b in items(e.get("components")):
            m = resolved.get(b.get("component"))
            for p in items(m.get("provides")) if m else []:
                for _, a in items(p[1].get("artifacts")):
                    if a.get("type") == "function" and isinstance(a.get("ref"), str):
                        provided.add(a["ref"])
        if isinstance(fn, str) and fn not in provided:
            rep.error("BP-FN-001", ptr("entities", i, "fields", j, "computed", "function"),
                      f"function '{fn}' is not provided by any component bound to entity '{e.get('id')}'")
