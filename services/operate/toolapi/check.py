"""check_tool_api: re-check the hard rules on any definition set (a list of tools, or a set with `tools`)."""
from __future__ import annotations

import re

from . import policy as P
from .generate import norm_arg
from .result import Issue, canonical, hash_tools

_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_RANK = {r: i for i, r in enumerate(P.RISK_ORDER)}
_KINDS = {"read", "write", "admin"}


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


def check_tool_api(defs) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda code, ptr, fact: issues.append(Issue(code, ptr, fact))
    declared_hash = None
    if isinstance(defs, dict):
        declared_hash, tools = defs.get("contentHash"), defs.get("tools")
    else:
        tools = defs
    if not isinstance(tools, list):
        return [Issue("TAPI-SHAPE-001", "/", "definition set must be a list of tools or an object with a tools list")]
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
            if norm_arg(name_) in P.FORBIDDEN_ARG_NAMES:
                add("TAPI-ARG-001", p + ptr, f"argument {name_!r} is a caller, role, tenant, user or scope field")
        for ptr in _objects_closed(sch):
            add("TAPI-SCHEMA-001", p + ptr, "object schema must set additionalProperties false")
    low = canonical(tools).lower()
    for n in P.ENGINE_NAMES:
        if n in low:
            add("TAPI-LEAK-001", "/", f"engine name {n!r} appears in the definitions")
    if declared_hash is not None and declared_hash != hash_tools(tools):
        add("TAPI-HASH-001", "/contentHash", "content hash does not match the tools")
    return list(dict.fromkeys(issues))
