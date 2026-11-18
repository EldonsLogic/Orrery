"""check_tool_api: re-check the hard rules on any definition set, and recompute risk, effects and agent flags.

The checker does not trust what a stored set says about itself: for every entity tool it derives the entity class,
the risk class, the effects and the agent flag again from policy (and the L0 registry the set was built with), and
requires equality. The content hash is mandatory. A hash is not a signature: protect stored sets by where they live.
"""
from __future__ import annotations

import re

from . import classify as C
from . import policy as P
from .result import Issue, canonical, hash_tools

_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_RANK = {r: i for i, r in enumerate(P.RISK_ORDER)}
_KINDS = {"read", "write", "admin"}
_PLAIN_VERBS = ("create", "update", "delete", "submit", "cancel")
_FIXED_ARGS = {"id", "expected_version"}


def _walk_props(schema, ptr="/input_schema"):
    """Yield (property name, pointer) for every property declared anywhere in a schema."""
    if isinstance(schema, dict):
        for k, v in schema.items():
            if k == "properties" and isinstance(v, dict):
                for name, sub in v.items():
                    yield name, f"{ptr}/properties/{name}"
                    yield from _walk_props(sub, f"{ptr}/properties/{name}")
            elif k == "required" and isinstance(v, list):
                for name in v:
                    yield name, f"{ptr}/required"
            else:
                yield from _walk_props(v, f"{ptr}/{k}")
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            yield from _walk_props(v, f"{ptr}/{i}")


def _objects_closed(schema, ptr="/input_schema"):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
            yield ptr
        for k, v in schema.items():
            yield from _objects_closed(v, f"{ptr}/{k}")
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            yield from _objects_closed(v, f"{ptr}/{i}")


def _props(schema) -> dict:
    p = schema.get("properties") if isinstance(schema, dict) else None
    return p if isinstance(p, dict) else {}


def _sensitive_inputs(sch) -> list[str]:
    """Sensitive properties at the top level and inside child-table items."""
    out = []
    for name, s in _props(sch).items():
        if name in _FIXED_ARGS:
            continue
        if C.schema_sensitivity(name, s):
            out.append(name)
        if isinstance(s, dict) and isinstance(s.get("items"), dict):
            out += [f"{name}/{n}" for n, x in _props(s["items"]).items() if C.schema_sensitivity(n, x)]
    return out


def _recompute_entity_tool(t, verb, cls, policy, add, p) -> None:
    """Derive kind, risk, effects and the agent flag for an entity tool; any difference is TAPI-RISK-003."""
    ent, sch = t["entity"], t.get("input_schema")
    has_wf = "state" in _props(t.get("output_schema"))
    sens = _sensitive_inputs(sch)
    egress = verb == "export"
    if verb in ("get", "list"):
        kind, risk = "read", "R0"
    elif egress:
        kind, risk = "write", P.RISK[cls]["export"]
    elif verb in P.SENSITIVE_VERBS.values():
        kind, risk = "write", P.RISK[cls][verb]
    elif verb in _PLAIN_VERBS:
        kind, risk = "write", P.RISK[cls][verb]
        if verb == "create" and sens:
            risk = "R4"
        elif sens:
            add("TAPI-RISK-003", p, f"generic {verb} carries sensitive field(s) {sens}; they belong to a protected R4 tool")
        bad = [n for n in _props(sch) if C.status_like(n, has_wf)]
        if bad and verb in ("create", "update"):
            add("TAPI-ARG-002", p, f"status-like field(s) {bad} must not be writable")
    elif verb == "transition":
        kind, risk = "write", _recompute_transitions(t, cls, add, p)
    else:
        add("TAPI-RISK-003", p, f"unknown entity verb {verb!r}; cannot recompute its risk")
        return
    eff = policy.effects(ent, cls, kind == "write" and not egress)
    agent = _RANK[risk] <= _RANK[P.MAX_AGENT_RISK] and verb not in P.AGENT_FORBIDDEN_KINDS
    if verb == "transition":
        agent = agent and any(tr.get("agent_creatable") is True for tr in t.get("transitions") or [])
    got = (t.get("kind"), t.get("risk_class"), t.get("effects"), t.get("agent_creatable"))
    if got != (kind, risk, eff, agent):
        add("TAPI-RISK-003", p, f"stored kind/risk/effects/agent flag {got} differ from policy {(kind, risk, eff, agent)}")
    ap = t.get("approval") if isinstance(t.get("approval"), dict) else {}
    if (egress or any(eff.values()) or _RANK[risk] >= _RANK["R3"]) and ap.get("agent_required") is not True:
        add("TAPI-APPROVAL-001", p, "this tool must require approval for agent callers")
    if verb in ("list", "export"):
        _check_hidden_filters(t, add, p)


def _recompute_transitions(t, cls, add, p) -> str:
    worst = "R0"
    for j, tr in enumerate(t.get("transitions") or []):
        tp = f"{p}/transitions/{tr.get('id', j)}"
        declared = tr.get("declared_kind")
        if declared is not None and declared not in P.TRANSITION_KINDS:
            add("TAPI-TRANS-001", tp, f"declared kind {declared!r} is not known")
            declared = None
        kind, forbidden = C.transition_kind(str(tr.get("id")), cls, tr.get("from_state_kind"), str(tr.get("to")),
                                            tr.get("to_state_kind"), tr.get("approval_step") is True, declared)
        risk = P.RISK[cls][kind]
        agent = _RANK[risk] <= _RANK[P.MAX_AGENT_RISK] and not forbidden
        got = (tr.get("kind"), tr.get("risk_class"), tr.get("agent_creatable"))
        if got != (kind, risk, agent):
            add("TAPI-RISK-003", tp, f"stored transition kind/risk/agent flag {got} differ from policy {(kind, risk, agent)}")
        worst = max(worst, risk, key=_RANK.get)
    return worst


def _check_hidden_filters(t, add, p) -> None:
    fa = t.get("field_access") if isinstance(t.get("field_access"), dict) else {}
    hidden = {f for v in (fa.get("hidden_by_role") or {}).values() for f in v}
    props = _props(t.get("input_schema"))
    keys = set()
    for arg in ("filter", "order_by"):
        s = props.get(arg) or {}
        s = s.get("items", s) if isinstance(s, dict) else {}
        keys |= set((_props(s).get("field") or {}).get("enum") or [])
    if keys & hidden:
        add("TAPI-HIDDEN-001", p, f"field(s) {sorted(keys & hidden)} are hidden from a calling role but filterable")


def check_tool_api(defs, registry=None) -> list[Issue]:
    """`registry` is the L0 registry the set was generated with (required when the set records one)."""
    issues: list[Issue] = []
    add = lambda code, ptr, fact: issues.append(Issue(code, ptr, fact))
    declared_hash, set_registry = None, None
    if isinstance(defs, dict):
        declared_hash, tools, set_registry = defs.get("contentHash"), defs.get("tools"), defs.get("registry")
    else:
        tools = defs
    if not isinstance(tools, list):
        return [Issue("TAPI-SHAPE-001", "/", "definition set must be a list of tools or an object with a tools list")]
    policy = C.Policy(registry)
    issues.extend(policy.errors)
    if (set_registry or None) != policy.meta:
        add("TAPI-REGISTRY-003", "/registry", "the registry given to the checker is not the one the set was built with")
    seen: set[str] = set()
    for i, t in enumerate(tools):
        name = t.get("name") if isinstance(t, dict) else None
        p = f"/tools/{name if isinstance(name, str) else i}"
        if not isinstance(t, dict) or not isinstance(name, str):
            add("TAPI-SHAPE-001", p, "tool must be an object with a string name")
            continue
        if not _NAME.match(name):
            add("TAPI-NAME-004", p, "name does not match <entity>.<verb> snake_case")
        if name in seen:
            add("TAPI-NAME-001", p, "duplicate tool name")
        seen.add(name)
        ent = t.get("entity")
        if ent is not None and not name.startswith(f"{ent}."):
            add("TAPI-NAME-004", p, "name does not start with its entity id")
        kind, risk = t.get("kind"), t.get("risk_class")
        if kind not in _KINDS:
            add("TAPI-SHAPE-002", p, f"kind {kind!r} is not read, write or admin")
        if risk not in _RANK:
            add("TAPI-RISK-002", p, f"risk class {risk!r} is not R0 to R4")
        if kind == "read" and risk != "R0":
            add("TAPI-RISK-004", p, "a read tool must be R0; anything riskier is a write")
        if risk == "R4" and t.get("agent_creatable") is not False:
            add("TAPI-RISK-001", p, "an R4 tool must not be agent-creatable")
        if name in P.AGENT_FORBIDDEN_TOOLS and t.get("agent_creatable") is not False:
            add("TAPI-RISK-001", p, "this tool must never be agent-creatable")
        if risk in _RANK and _RANK[risk] > _RANK[P.MAX_AGENT_RISK] and t.get("agent_creatable") is not False:
            add("TAPI-RISK-001", p, "risk above R3 must not be agent-creatable")
        for j, tr in enumerate(t.get("transitions") or []):
            tp = f"{p}/transitions/{tr.get('id', j)}"
            if tr.get("risk_class") not in _RANK:
                add("TAPI-RISK-002", tp, "transition risk class is not R0 to R4")
            elif tr.get("risk_class") == "R4" and tr.get("agent_creatable") is not False:
                add("TAPI-RISK-001", tp, "an R4 transition must not be agent-creatable")
            if tr.get("kind") in P.AGENT_FORBIDDEN_KINDS and tr.get("agent_creatable") is not False:
                add("TAPI-RISK-001", tp, "approve and reject transitions must not be agent-creatable")
            if risk in _RANK and tr.get("risk_class") in _RANK and _RANK[tr["risk_class"]] > _RANK[risk]:
                add("TAPI-RISK-002", tp, "tool risk class is below one of its transitions")
            if not tr.get("allowed_roles"):
                add("TAPI-ROLE-001", tp, "transition has no allowed roles")
        req = t.get("requires") if isinstance(t.get("requires"), dict) else {}
        if not req.get("roles"):
            add("TAPI-ROLE-001", p, "tool lists no role that may call it")
        if req.get("scope") != "from_caller":
            add("TAPI-ROLE-002", p, "scope must be from_caller")
        if kind in ("write", "admin") and t.get("idempotency") != "required":
            add("TAPI-IDEM-001", p, "write and admin tools require an idempotency key")
        eff = t.get("effects") if isinstance(t.get("effects"), dict) else {}
        ap = t.get("approval") if isinstance(t.get("approval"), dict) else {}
        if any(eff.get(k) for k in P.EFFECT_KEYS) and ap.get("agent_required") is not True:
            add("TAPI-APPROVAL-001", p, "ledger, tax or external-send tools must require approval for agent callers")
        sch = t.get("input_schema")
        if not isinstance(sch, dict) or sch.get("type") != "object":
            add("TAPI-SCHEMA-001", p, "input_schema must be an object schema")
            continue
        for name_, ptr in _walk_props(sch):
            if C.forbidden_arg(name_):
                add("TAPI-ARG-001", p + ptr, f"argument {name_!r} names a caller, role, tenant, user, owner, approver or scope")
        for ptr in _objects_closed(sch):
            add("TAPI-SCHEMA-001", p + ptr, "object schema must set additionalProperties false")
        # ---- recompute from policy -----------------------------------------------------------------------------
        if ent is None:
            if name not in P.PLATFORM_RISK:
                add("TAPI-RISK-003", p, "unknown platform tool; cannot recompute its risk")
            elif (risk, eff, t.get("agent_creatable")) != (
                    P.PLATFORM_RISK[name], {k: False for k in P.EFFECT_KEYS},
                    _RANK[P.PLATFORM_RISK[name]] <= _RANK[P.MAX_AGENT_RISK] and name not in P.AGENT_FORBIDDEN_TOOLS):
                add("TAPI-RISK-003", p, "platform tool risk, effects or agent flag differ from policy")
            continue
        cls = policy.entity_class(str(ent))
        if cls is None:
            add("TAPI-CLASS-001", p, f"entity {ent!r} has no reviewed class")
            continue
        if t.get("entity_class") != cls:
            add("TAPI-CLASS-002", p, f"stored entity class {t.get('entity_class')!r} differs from policy {cls!r}")
        if C.identity_entity(str(ent)):
            add("TAPI-DOMAIN-001", p, "identity and permission entities never get tools")
        _recompute_entity_tool(t, name.split(".", 1)[1], cls, policy, add, p)
    low = canonical(tools).lower()
    for n in P.ENGINE_NAMES:
        if n in low:
            add("TAPI-LEAK-001", "/", f"engine name {n!r} appears in the definitions")
    if not declared_hash:
        add("TAPI-HASH-002", "/contentHash", "content hash is missing; it is mandatory")
    elif declared_hash != hash_tools(tools):
        add("TAPI-HASH-001", "/contentHash", "content hash does not match the tools")
    return list(dict.fromkeys(issues))
