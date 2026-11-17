"""Component resolution against the registry: existence, version range, eligibility for the environment, engine
compatibility, dependencies and dependency cycles. Fails closed: anything not proven usable is an issue."""
from __future__ import annotations

from typing import Any

from ._deps import semver
from .result import Issue, ptr

ENVIRONMENTS = ("sandbox", "production")


def touches_ledger_or_tax(manifest: dict) -> bool:
    """A component is ledger or tax affecting when its certification says so, or when it is `rigid` (the manifest
    contract reserves `rigid` for ledger, tax, e-invoicing, payroll maths and audit)."""
    cert = manifest.get("certification") if isinstance(manifest.get("certification"), dict) else {}
    return cert.get("touchesLedgerOrTax") is True or manifest.get("kind") == "rigid"


def resolve_components(blueprint: dict, registry: Any, environment: str) -> tuple[dict[str, dict], list[Issue]]:
    """Map component id -> resolved manifest for every Blueprint binding, plus the issues found."""
    issues: list[Issue] = []
    if environment not in ENVIRONMENTS:
        return {}, [Issue("CMP-ENV-001", "", f"unknown environment '{environment}' (allowed: {', '.join(ENVIRONMENTS)})")]
    for i in getattr(registry, "errors", []):
        issues.append(Issue("CMP-REG-001", "", f"registry has an error, refusing to compile: {i}"))
    resolved: dict[str, dict] = {}
    bindings = sorted(enumerate(blueprint.get("components", [])), key=lambda t: t[1]["id"])
    for idx, b in bindings:
        cid, rng = b["id"], b["versionRange"]
        where = ptr("components", idx)
        if not registry.versions(cid):
            issues.append(Issue("CMP-COMP-001", where, f"component '{cid}' is not in the registry"))
            continue
        try:
            m = registry.resolve(cid, rng)
        except ValueError:
            issues.append(Issue("CMP-COMP-002", where + "/versionRange", f"version range '{rng}' is not valid"))
            continue
        if m is None:
            issues.append(Issue("CMP-COMP-002", where + "/versionRange",
                                f"no registry version of '{cid}' satisfies '{rng}'"))
            continue
        version = m["version"]
        if not registry.is_eligible(cid, version, environment):
            level = (m.get("certification") or {}).get("level")
            if touches_ledger_or_tax(m):
                issues.append(Issue("CMP-COMP-004", where, f"ledger or tax component '{cid}' {version} is at level "
                                                           f"'{level}', below the level allowed for {environment}"))
            else:
                issues.append(Issue("CMP-COMP-003", where, f"'{cid}' {version} at level '{level}' is not eligible "
                                                           f"for {environment}"))
        # Kept even when ineligible (the issue already refuses), so later checks do not report follow-on noise.
        resolved[cid] = m
    for r in registry.compatible(blueprint.get("components", []), blueprint["meta"].get("engineTarget")):
        if not r.ok and r.component in resolved:
            for reason in r.reasons:
                issues.append(Issue("CMP-COMP-005", "/meta/engineTarget", reason))
    issues += _check_requires(resolved)
    issues += _check_cycles(resolved)
    return resolved, issues


def _provides_capability(m: dict, cap: Any) -> bool:
    return any(isinstance(p, dict) and p.get("capability") == cap for p in m.get("provides", []))


def _requirement_targets(cid: str, req: dict, resolved: dict[str, dict]) -> tuple[list[str], str]:
    """Ids of resolved components that satisfy one `requires` entry, and a description of it."""
    rng = req.get("versionRange") if isinstance(req.get("versionRange"), str) else "*"
    if "component" in req:
        other = resolved.get(req["component"])
        hits = [req["component"]] if other is not None and semver.satisfies(other["version"], rng) else []
        return hits, f"component '{req['component']}' {rng}"
    cap = req.get("capability")
    hits = sorted(o for o, m in resolved.items()
                  if o != cid and _provides_capability(m, cap) and semver.satisfies(m["version"], rng))
    return hits, f"capability '{cap}' {rng}"


def _check_requires(resolved: dict[str, dict]) -> list[Issue]:
    issues = []
    for cid in sorted(resolved):
        for req in resolved[cid].get("requires", []):
            try:
                hits, what = _requirement_targets(cid, req, resolved)
            except (ValueError, TypeError):
                issues.append(Issue("CMP-COMP-006", "", f"'{cid}' has a requirement that cannot be evaluated"))
                continue
            if not hits:
                issues.append(Issue("CMP-COMP-006", "", f"'{cid}' requires {what}, which no resolved component provides"))
    return issues


def dependency_graph(resolved: dict[str, dict]) -> dict[str, list[str]]:
    """component id -> sorted ids it depends on (component requirements and providers of required capabilities)."""
    graph: dict[str, list[str]] = {}
    for cid in sorted(resolved):
        deps: set[str] = set()
        for req in resolved[cid].get("requires", []):
            try:
                deps.update(_requirement_targets(cid, req, resolved)[0])
            except (ValueError, TypeError):
                continue
        graph[cid] = sorted(deps)
    return graph


def _check_cycles(resolved: dict[str, dict]) -> list[Issue]:
    graph = dependency_graph(resolved)
    state: dict[str, int] = {}  # 1 visiting, 2 done
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in state:
                visit(nxt, stack)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node, [])
    return [Issue("CMP-COMP-007", "", "component dependency cycle: " + " -> ".join(c)) for c in cycles]
