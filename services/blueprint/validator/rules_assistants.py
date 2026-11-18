"""Rule 14: department assistants (ADR-0043).

An assistant is configuration of the one chat for a department. It has no authority of its own: every call
runs with the invoking user's role and scope, as an agent-class caller (Tool API section 4). This rule refuses
configuration that could widen that: tools outside the tenant's generated tool set, tools above R2, tools an agent
may not create, R2 tools without per-call confirmation, approval and protected tools, approve, reject and reversal
moves, limits above the caps, and unknown references.

Fail closed: the static checks below run with or without a supplied tool set. Without one, only checks that need
the generated risk, agent flag and caller roles are skipped, and BP-AST-014 warns that they did not run.
"""
from __future__ import annotations

import re

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
NEVER_VERBS = {"approve", "reject", "update_bank_details", "update_contact_details", "update_access",
               # R3/R4 or posting verbs on some entity class (tool-api.md section 11): refused without a tool set too.
               "submit", "cancel", "amend", "delete"}
# Entities that post to the ledger or move stock (tool-api.md section 11 entity class). Only these verbs may be
# given to an assistant on them; their transitions post (R3 or R4) and are refused. Copied from the Tool API
# policy table (services/operate/toolapi/policy.py); a test keeps these sets a superset of it.
POSTING_ENTITY_IDS = {
    "sales_invoice", "purchase_invoice", "credit_note", "debit_note", "payment", "payment_entry", "journal_entry",
    "pos_invoice", "expense_claim", "payroll_entry", "salary_slip", "landed_cost_voucher", "period_closing_voucher",
    "payment_request", "bank_transaction",
    "delivery_note", "purchase_receipt", "stock_transfer", "stock_entry", "stock_reconciliation", "goods_receipt",
}
POSTING_NAME_TOKENS = {
    "invoice", "invoices", "bill", "bills", "receipt", "receipts", "voucher", "vouchers", "entry", "entries",
    "payment", "payments", "payroll", "ledger", "journal", "salary", "payslip", "expense", "expenses", "refund",
    "credit", "debit", "tax", "vat", "depreciation", "settlement", "remittance", "payout", "disbursement", "cheque",
    "pos", "stock", "inventory", "delivery", "shipment", "dispatch", "transfer", "adjustment", "reconciliation",
    "closing", "accrual", "provision", "cash",
}
POSTING_ENTITY_VERBS = {"get", "list", "create", "update", "export"}
# Transition kinds and id tokens an assistant may never be given (agents never approve or reject; reversals are R4).
NEVER_TRANSITION_KINDS = {"approve", "reject", "reversal"}
NEVER_TRANSITION_TOKENS = {
    "approve", "approved", "approval", "authorise", "authorize", "authorised", "authorized", "accept", "accepted",
    "confirm", "confirmed", "release", "released", "signoff",
    "reject", "rejected", "decline", "declined", "deny", "denied",
    "void", "voided", "reverse", "reversed", "reversal", "refund", "refunded", "return", "returned", "amend",
    "amended", "writeoff", "unpost", "reopen", "undo", "rollback",
}
NEVER_TRANSITION_PHRASES = {("sign", "off"), ("write", "off"), ("written", "off")}
# Platform tools an assistant may name (allowlist; contracts/tool-api.md section 2). memory.* needs a memory scope.
PLATFORM_TOOLS = {"report.run", "metric.query", "approval.list_mine", "help.explain", "memory.note"}
PLATFORM_DOMAINS = {t.split(".", 1)[0] for t in PLATFORM_TOOLS}
# Role functions that may invoke any department's assistant.
CROSS_DEPARTMENT_FUNCTIONS = {"owner", "general_manager"}

_SPLIT = re.compile(r"[^a-z0-9]+")


def _token_list(name: str) -> list[str]:
    return [t for t in _SPLIT.split(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()) if t]


def _tokens(name: str) -> set[str]:
    return set(_token_list(name))


def never_transition(tid: str) -> bool:
    toks = _token_list(tid)
    return bool(set(toks) & NEVER_TRANSITION_TOKENS) or any(p in NEVER_TRANSITION_PHRASES for p in zip(toks, toks[1:]))


def posting_entity(eid: str) -> bool:
    return eid in POSTING_ENTITY_IDS or bool(_tokens(eid) & POSTING_NAME_TOKENS)


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


def _workflow_index(bp: dict) -> dict[str, dict[str, dict]]:
    """entity id -> transition id -> transition, from the Blueprint's own workflows."""
    out: dict[str, dict[str, dict]] = {}
    for _, w in items(bp.get("workflows")):
        ent = sid(w.get("entity"))
        if ent:
            out.setdefault(ent, {}).update({t["id"]: t for _, t in items(w.get("transitions")) if sid(t.get("id"))})
    return out


def _check_transitions(base: tuple, j: int, entry: dict, entity: str, tool: dict | None, a_roles: set[str],
                       workflows: dict[str, dict[str, dict]], rep: Report) -> None:
    """Each allowlisted move must exist, be no approve, reject or reversal, and (with a tool set) be agent-creatable,
    at most R2 and callable by an assistant role. The schema requires the allowlist on every transition tool."""
    declared = workflows.get(entity, {})
    generated = {t["id"]: t for t in as_list(as_dict(tool).get("transitions"))
                 if isinstance(t, dict) and sid(t.get("id"))} if tool is not None else None
    for k, tid in enumerate(as_list(entry.get("transitions"))):
        if not isinstance(tid, str):
            continue
        path = ptr(*base, "tools", j, "transitions", k)
        bt = declared.get(tid)
        if bt is None or (generated is not None and tid not in generated):
            rep.error("BP-AST-006", path, f"transition '{tid}' does not exist on '{entity}'")
            continue
        if (bt.get("kind") in NEVER_TRANSITION_KINDS or bt.get("approval") is not None
                or never_transition(tid)):
            rep.error("BP-AST-005", path, f"transition '{tid}' is an approve, reject or reversal move")
            continue
        if generated is None:
            continue
        gt = generated[tid]
        risk = gt.get("risk_class")
        if gt.get("kind") in NEVER_TRANSITION_KINDS:
            rep.error("BP-AST-005", path, f"transition '{tid}' is kind {gt.get('kind')!r}")
        elif risk not in RISK_ORDER or RISK_ORDER[risk] > RISK_ORDER[MAX_ASSISTANT_RISK]:
            rep.error("BP-AST-007", path, f"transition '{tid}' is risk class {risk!r}; at most {MAX_ASSISTANT_RISK}")
        elif gt.get("agent_creatable") is not True:
            rep.error("BP-AST-008", path, f"transition '{tid}' is not agent-creatable")
        elif not {r for r in as_list(gt.get("allowed_roles")) if isinstance(r, str)} & a_roles:
            rep.error("BP-AST-010", path, f"no role of this assistant may make transition '{tid}'")


def _check_tool(base: tuple, j: int, entry: dict, a_roles: set[str], entities: set[str], memory_on: bool,
                workflows: dict[str, dict[str, dict]], index: dict[str, dict] | None, rep: Report) -> None:
    name = entry.get("tool")
    if not isinstance(name, str) or "." not in name:
        return  # schema step reports it
    path = ptr(*base, "tools", j, "tool")
    domain, verb = name.split(".", 1)
    if name in NEVER_TOOLS or domain in NEVER_DOMAINS or verb in NEVER_VERBS:
        rep.error("BP-AST-005", path, f"tool '{name}' may never be given to an assistant")
        return
    if domain in entities:
        if posting_entity(domain) and verb not in POSTING_ENTITY_VERBS:
            rep.error("BP-AST-005", path, f"tool '{name}' posts to the ledger or moves stock")
            return
    elif name not in PLATFORM_TOOLS:
        rep.error("BP-AST-006", path, f"tool '{name}' names no entity of this Blueprint and no platform tool")
        return
    elif domain == "memory" and not memory_on:
        rep.error("BP-AST-016", path, f"tool '{name}' needs memory.scope session or department")
        return
    tool = None
    if index is not None:
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
    if verb == "transition" and domain in entities:
        _check_transitions(base, j, entry, domain, tool, a_roles, workflows, rep)


def rule_assistants(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 14. Fail closed on everything that is checkable; warn once for each check the context cannot run."""
    assistants = list(items(bp.get("assistants")))
    if not assistants:
        return
    roles = {r["id"]: r.get("function") for _, r in items(bp.get("roles")) if sid(r.get("id"))}
    functions = set(roles.values())
    entities = {e["id"] for _, e in items(bp.get("entities")) if sid(e.get("id"))}
    workflows = _workflow_index(bp)
    overrides = as_dict(as_dict(bp.get("i18n")).get("labelOverrides"))
    index = _tool_index(ctx.tool_set if ctx else None)
    catalog = ctx.instruction_keys if ctx else None
    if index is None:
        rep.warn("BP-AST-014", "/assistants",
                 "no tool set supplied: static refusals ran; generated risk, agent-creatable and caller checks did not")
    seen: set[str] = set()
    for i, a in assistants:
        base = ("assistants", i)
        aid, dept = sid(a.get("id")), a.get("department")
        if aid is not None:
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
        memory_on = as_dict(a.get("memory")).get("scope") in ("session", "department")
        tool_names: set[str] = set()
        for j, entry in items(a.get("tools")):
            name = sid(entry.get("tool"))
            if name is not None:
                if name in tool_names:
                    rep.error("BP-ID-001", ptr(*base, "tools", j, "tool"), f"duplicate tool '{name}'")
                    continue
                tool_names.add(name)
            _check_tool(base, j, entry, a_roles, entities, memory_on, workflows, index, rep)
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
