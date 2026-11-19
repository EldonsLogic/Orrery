"""Per-run tool allow-list and call classification. Roles come from the verified principal only (PI-RULE-4);
nothing the model or a document says can add a tool. An empty or unreadable input gives an empty list (fail closed).

Menu (what the model sees): tools the caller's roles may use, `agent_creatable`, at most R2, not in the forbidden set,
and, when an assistant is configured (ADR-0043), listed there with `confirm: true` for every R2 tool and not refused by
`authority.tool_refusal`. Classification (what happens to a call): run | propose | needs_approval | refused. A
transition call is checked against the chosen transition's own risk, flags and `allowed_roles`, and, for an
assistant, against its `transitions` list and the ADR-0043 refusals (`authority.py`)."""
from __future__ import annotations

from dataclasses import dataclass, field

from toolapi.policy import AGENT_FORBIDDEN_KINDS, AGENT_FORBIDDEN_TOOLS, RISK_ORDER

from . import authority as A
from .models import ToolSpec

_RANK = {r: i for i, r in enumerate(RISK_ORDER)}


@dataclass(frozen=True)
class AssistantConfig:
    """The part of a Blueprint `assistants[]` entry the runtime enforces. No identity or authority of its own."""
    id: str
    roles: tuple
    tools: tuple                      # of (tool name, confirm bool)
    max_tool_calls: int | None = None
    transitions: tuple = ()           # of (tool name, tuple of allowed transition ids); none listed: none allowed

    def transitions_for(self, tool: str) -> tuple:
        for n, ids in self.transitions or ():
            if n == tool:
                return tuple(i for i in (ids or ()) if isinstance(i, str))
        return ()


@dataclass(frozen=True)
class Decision:
    kind: str                         # run | propose | needs_approval | refused
    risk: str | None = None
    reason: str = ""


def _risk(d: dict) -> str | None:
    r = d.get("risk_class")
    return r if r in _RANK else None


def _roles_ok(d: dict, role_ids: set) -> bool:
    req = (d.get("requires") or {}).get("roles")
    return isinstance(req, list) and bool(role_ids & set(req))


def _text(d: dict) -> str:
    desc = d.get("description")
    if isinstance(desc, str):
        return desc[:500]
    labels = d.get("labels")
    return str(labels.get("en", ""))[:200] if isinstance(labels, dict) else ""


@dataclass
class Allowlist:
    role_ids: frozenset
    defs: dict = field(default_factory=dict)       # every tenant tool by name (classification only)
    menu: dict = field(default_factory=dict)       # name -> ToolSpec the model may see
    max_tool_calls: int | None = None
    assistant: AssistantConfig | None = None

    def specs(self) -> tuple:
        return tuple(self.menu[k] for k in sorted(self.menu))

    def classify(self, name, args, tainted: bool) -> Decision:
        d = self.defs.get(name) if isinstance(name, str) else None
        if d is None:
            return Decision("refused", None, "unknown_tool")
        if name in AGENT_FORBIDDEN_TOOLS:
            return Decision("refused", _risk(d), "forbidden")
        risk = _risk(d)
        if risk is None:
            return Decision("refused", None, "unclassified")  # unknown never means plain
        if self.assistant is not None:
            why = A.tool_refusal(name, d)
            if why:
                return Decision("refused", risk, why)
        if isinstance(d.get("transitions"), list) or name.endswith(".transition"):
            tid = args.get("transition_id") if isinstance(args, dict) else None
            ts = d.get("transitions") if isinstance(d.get("transitions"), list) else []
            t = next((x for x in ts if isinstance(x, dict) and x.get("id") == tid), None)
            if t is None or _risk(t) is None:
                return Decision("refused", risk, "invalid_arguments")
            if t.get("agent_creatable") is not True or t.get("kind") in AGENT_FORBIDDEN_KINDS:
                return Decision("refused", _risk(t), "forbidden")
            if self.assistant is not None:
                why = A.transition_refusal(tid, t, self.assistant.transitions_for(name))
                if why:
                    return Decision("refused", _risk(t), why)
            roles_t = t.get("allowed_roles")
            if not isinstance(roles_t, list) or not set(self.role_ids) & set(roles_t):
                return Decision("refused", _risk(t), "not_allowed")  # the chosen move's own roles
            risk = _risk(t)
        if not _roles_ok(d, set(self.role_ids)):
            return Decision("refused", risk, "not_allowed")
        if _RANK[risk] >= _RANK["R3"]:
            return Decision("needs_approval", risk, "human_approval")
        if name not in self.menu:
            return Decision("refused", risk, "not_allowed")
        if risk == "R2" or (risk == "R1" and tainted):  # a tainted value is never submitted without a human
            return Decision("propose", risk, "tainted" if risk == "R1" else "confirm")
        return Decision("run", risk)


def resolve_allowlist(tool_defs, role_ids, assistant: AssistantConfig | None = None) -> Allowlist:
    roles = frozenset(r for r in (role_ids or ()) if isinstance(r, str) and r)
    defs = {d["name"]: d for d in (tool_defs or ()) if isinstance(d, dict) and isinstance(d.get("name"), str)}
    out = Allowlist(role_ids=roles, defs=defs)
    if not roles:
        return out
    listed = None
    if assistant is not None:
        if not roles & set(assistant.roles):
            return out
        listed = {n: bool(c) for n, c in assistant.tools}
        out.max_tool_calls, out.assistant = assistant.max_tool_calls, assistant
    for name, d in sorted(defs.items()):
        risk = _risk(d)
        if risk is None or _RANK[risk] > _RANK["R2"] or name in AGENT_FORBIDDEN_TOOLS:
            continue
        if d.get("agent_creatable") is not True or not _roles_ok(d, set(roles)):
            continue
        if listed is not None and (name not in listed or (risk == "R2" and not listed[name])
                                   or A.tool_refusal(name, d)):
            continue
        schema = d.get("input_schema")
        out.menu[name] = ToolSpec(name, _text(d), schema if isinstance(schema, dict) else {}, risk,
                                  "propose" if risk == "R2" else "run")
    return out
