"""Rule 14: department assistants (ADR-0043).

An assistant is configuration of the one chat for a department. It has no authority of its own: every call
runs with the invoking user's role and scope. This rule refuses configuration that could widen that:
tools outside the tenant's generated tool set, tools above R2, tools an agent may not create, R2 tools
without per-call confirmation, approval and protected tools, limits above the caps, and unknown references.
"""
from __future__ import annotations

from .report import Report, ValidationContext, as_dict, as_list, items, ptr, sid

# Platform caps. They equal the maxima in contracts/blueprint.schema.json ($defs.assistant.limits); a test keeps
# them in step. A plan cap (ValidationContext.assistant_caps) may only lower them. Values are placeholders (Q-156).
PLATFORM_ASSISTANT_CAPS = {
    "perCall": {"maxToolCalls": 20, "maxRows": 200},
    "perDay": {"maxToolCalls": 500, "maxWrites": 100},
}
MAX_ASSISTANT_RISK = "R2"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}

# Refused whatever the tool set says (defence in depth; prompt-injection-defence 4.1, ALP section 6).
NEVER_TOOLS = {"approval.decide"}
NEVER_DOMAINS = {"blueprint", "approval_rule", "role", "permission", "grant", "agent", "assistant"}
NEVER_VERBS = {"approve", "reject", "update_bank_details", "update_contact_details", "update_access"}
# Platform tool domains an assistant may name besides Blueprint entities (contracts/tool-api.md section 2).
PLATFORM_DOMAINS = {"report", "metric", "approval", "help", "memory"}
# Role functions that may invoke any department's assistant.
CROSS_DEPARTMENT_FUNCTIONS = {"owner", "general_manager"}


def _tool_index(tool_set) -> dict[str, dict] | None:
    if tool_set is None:
        return None
    tools = tool_set.get("tools") if isinstance(tool_set, dict) else tool_set
    return {t["name"]: t for t in as_list(tools) if isinstance(t, dict) and sid(t.get("name"))}


def _cap(ctx: ValidationContext | None, group: str, key: str) -> int:
    cap = PLATFORM_ASSISTANT_CAPS[group][key]
    plan = as_dict(as_dict(ctx.assistant_caps if ctx else None).get(group)).get(key)
    if isinstance(plan, int) and not isinstance(plan, bool):
        cap = min(cap, plan)
    return cap


def _check_tool(base: tuple, j: int, entry: dict, a_roles: set[str], entities: set[str],
                index: dict[str, dict] | None, rep: Report) -> None:
    name = entry.get("tool")
    if not isinstance(name, str) or "." not in name:
        return  # schema step reports it
    path = ptr(*base, "tools", j, "tool")
    domain, verb = name.split(".", 1)
    if name in NEVER_TOOLS or domain in NEVER_DOMAINS or verb in NEVER_VERBS:
        rep.error("BP-AST-005", path, f"tool '{name}' may never be given to an assistant")
        return
    if domain not in entities and domain not in PLATFORM_DOMAINS:
        rep.error("BP-AST-006", path, f"tool '{name}' names no entity of this Blueprint and no platform domain")
        return
    if index is None:
        return
    tool = index.get(name)
    if tool is None:
        rep.error("BP-AST-006", path, f"tool '{name}' is not in the tenant's generated tool set")
        return
    risk = tool.get("risk_class")
    if risk not in RISK_ORDER or RISK_ORDER[risk] > RISK_ORDER[MAX_ASSISTANT_RISK]:
        rep.error("BP-AST-007", path, f"tool '{name}' is risk class {risk!r}; assistants allow at most {MAX_ASSISTANT_RISK}")
        return
    if tool.get("agent_creatable") is not True:
        rep.error("BP-AST-008", path, f"tool '{name}' is not agent-creatable")
        return
    if risk == MAX_ASSISTANT_RISK and entry.get("confirm") is not True:
        rep.error("BP-AST-009", ptr(*base, "tools", j), f"R2 tool '{name}' needs confirm=true")
    callers = {r for r in as_list(as_dict(tool.get("requires")).get("roles")) if isinstance(r, str)}
    if not callers & a_roles:
        rep.error("BP-AST-010", path, f"no role of this assistant may call tool '{name}'")


def rule_assistants(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 14. Fail closed on everything that is checkable; warn once for each check the context cannot run."""
    assistants = list(items(bp.get("assistants")))
    if not assistants:
        return
    roles = {r["id"]: r.get("function") for _, r in items(bp.get("roles")) if sid(r.get("id"))}
    functions = set(roles.values())
    entities = {e["id"] for _, e in items(bp.get("entities")) if sid(e.get("id"))}
    overrides = as_dict(as_dict(bp.get("i18n")).get("labelOverrides"))
    index = _tool_index(ctx.tool_set if ctx else None)
    catalog = ctx.instruction_keys if ctx else None
    if index is None:
        rep.warn("BP-AST-014", "/assistants", "no tool set supplied: tool membership, risk and caller checks not run")
    seen: set[str] = set()
    for i, a in assistants:
        base = ("assistants", i)
        aid, dept = sid(a.get("id")), a.get("department")
        if aid in seen:
            rep.error("BP-ID-001", ptr(*base, "id"), f"duplicate id '{aid}'")
        seen.add(aid)
        if isinstance(dept, str) and dept not in functions:
            rep.error("BP-AST-002", ptr(*base, "department"), f"no role in this Blueprint works in department '{dept}'")
        a_roles: set[str] = set()
        for k, r in enumerate(as_list(a.get("roles"))):
            if not isinstance(r, str):
                continue
            if r not in roles:
                rep.error("BP-AST-001", ptr(*base, "roles", k), f"role '{r}' does not exist")
                continue
            if roles[r] != dept and roles[r] not in CROSS_DEPARTMENT_FUNCTIONS:
                rep.error("BP-AST-003", ptr(*base, "roles", k), f"role '{r}' does not work in department '{dept}'")
                continue
            a_roles.add(r)
        for j, entry in items(a.get("tools")):
            _check_tool(base, j, entry, a_roles, entities, index, rep)
        limits = as_dict(a.get("limits"))
        for group in ("perCall", "perDay"):
            for key, value in as_dict(limits.get(group)).items():
                if key in PLATFORM_ASSISTANT_CAPS[group] and isinstance(value, int) and value > _cap(ctx, group, key):
                    rep.error("BP-AST-011", ptr(*base, "limits", group, key),
                              f"{group}.{key} {value} exceeds the cap {_cap(ctx, group, key)}")
        per_call, per_day = as_dict(limits.get("perCall")), as_dict(limits.get("perDay"))
        for small, big, what in ((per_call.get("maxToolCalls"), per_day.get("maxToolCalls"), "perCall.maxToolCalls"),
                                 (per_day.get("maxWrites"), per_day.get("maxToolCalls"), "perDay.maxWrites")):
            if isinstance(small, int) and isinstance(big, int) and small > big:
                rep.error("BP-AST-011", ptr(*base, "limits"), f"{what} exceeds perDay.maxToolCalls")
        key = a.get("instructionsKey")
        if isinstance(key, str) and key not in overrides:
            if catalog is None:
                rep.warn("BP-AST-015", ptr(*base, "instructionsKey"), f"instructions key '{key}' not checked: no platform catalog")
            elif key not in catalog:
                rep.error("BP-AST-012", ptr(*base, "instructionsKey"), f"instructions key '{key}' does not resolve")
