"""Deterministic replay planner: source records -> ordered Tool API calls.

- Every step is a call to a tool of the tenant's generated tool set (contract 3), never a raw write.
- The caller is the replay user with the tenant's own roles; a step whose tool (or transition) does not allow
  one of those roles is `denied` (SIM-110). The gateway re-checks; this is a pre-check, never a widening.
- Risk comes from the tool set (`risk_class`, per transition when there is one); missing or unknown is R4.
  R0 to R2 steps are `execute`; R3 and R4 steps are `needs_approval` and are never sent to the port (SIM-109).
- Idempotency key per (tenant, period, run epoch, source record, stage): a rerun sends the same keys, so the
  gateway returns stored results and the tenant converges. Changed arguments under the same key are refused
  by the gateway (`idempotency_conflict`), which aborts the run (fail closed).
- A payment names its invoice by the engine record id: `against` is a `$ref` to the invoice's create step (the
  runner swaps in the id the engine returned), never the source document number. No ref is sent when the
  invoice is not in the plan before the payment (SIM-113, SIM-127); the payment is `blocked` when the invoice
  step is not executed.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

from .codes import Anomaly
from .model import KINDS
from .money import fmt

RISKS = ("R0", "R1", "R2", "R3", "R4")
AUTO_RUN = frozenset({"R0", "R1", "R2"})
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "platform:blueprint:simulator:replay")
MONEY_FIELDS = ("unit_price", "vat", "total", "gross", "deductions")
DECIMAL_FIELDS = ("qty",)
HEADER_SOURCES = ("party", "date", "due_date", "against", "number")
LINE_SOURCES = ("item", "warehouse", "qty", "unit_price", "vat", "total", "tax_code", "account",
                "employee", "gross", "deductions")
MAPPING_KEYS = {"entity", "header", "lines", "line", "money", "constants", "post"}


class SimulatorError(Exception):
    """Refusal before anything is planned or sent (bad mapping, bad tool set, bad caller)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


@dataclass
class Step:
    seq: int
    step_id: str
    source_id: str
    kind: str
    stage: str  # create | post
    tool: str
    transition_id: str
    risk_class: str
    action: str  # execute | needs_approval | unmapped | denied | invalid_arguments | blocked
    idempotency_key: str
    arguments: dict
    args_hash: str
    depends_on: str = None


@dataclass
class Plan:
    tenant_id: str
    period: tuple
    caller: dict
    tool_set_hash: str
    steps: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)


def _check_mapping(mapping) -> None:
    if not isinstance(mapping, dict) or set(mapping) - set(KINDS):
        raise SimulatorError("SIM-E01", "mapping kinds")
    for kind, m in mapping.items():
        if not isinstance(m, dict) or set(m) - MAPPING_KEYS or not isinstance(m.get("entity"), str):
            raise SimulatorError("SIM-E01", kind)
        if set(m.get("header") or {}) - set(HEADER_SOURCES) or set(m.get("line") or {}) - set(LINE_SOURCES):
            raise SimulatorError("SIM-E01", f"{kind} fields")
        if m.get("money", "object") not in ("object", "string"):
            raise SimulatorError("SIM-E01", f"{kind} money")
        post = m.get("post")
        if post is not None and (not isinstance(post, dict) or len(post) != 1 or
                                 not (isinstance(post.get("transition"), str) or post.get("verb") == "submit")):
            raise SimulatorError("SIM-E01", f"{kind} post")


def _tools(tool_set) -> dict:
    if not isinstance(tool_set, dict) or not isinstance(tool_set.get("tools"), list):
        raise SimulatorError("SIM-E02", "tool set")
    out = {}
    for t in tool_set["tools"]:
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            out[t["name"]] = t
    return out


def _value(src: str, value, currency: str, money_style: str):
    if value is None:
        return None
    if src in MONEY_FIELDS:
        return {"currency": currency, "value": fmt(value)} if money_style == "object" else fmt(value)
    if src in DECIMAL_FIELDS:
        return fmt(value)
    if src in ("date", "due_date"):
        return value.isoformat()
    return value


def build_arguments(record, m: dict, against_ref=None) -> dict:
    style = m.get("money", "object")
    args = dict(m.get("constants") or {})
    head = {"party": record.party, "date": record.posting_date, "due_date": record.due_date,
            "against": against_ref, "number": record.number}
    for src, target in sorted((m.get("header") or {}).items()):
        v = _value(src, head[src], record.currency, style)
        if target and v is not None:
            args[target] = v
    line_map = m.get("line") or {}
    lines = []
    for ln in record.lines:
        row = {}
        for src, target in sorted(line_map.items()):
            v = _value(src, getattr(ln, src), record.currency, style)
            if target and v is not None:
                row[target] = v
        lines.append(row)
    if m.get("lines"):
        args[m["lines"]] = lines
    elif lines:  # a one-line document (payment): line fields sit on the header
        for row in lines[:1]:
            args.update(row)
    return args


def _resolve(tools: dict, entity: str, post) -> tuple:
    """(tool name, transition id, risk, allowed roles, input schema) or None when the tool set lacks it."""
    if post is None:
        name, tid = f"{entity}.create", None
    elif "transition" in post:
        name, tid = f"{entity}.transition", post["transition"]
    else:
        name, tid = f"{entity}.submit", None
    tool = tools.get(name)
    if tool is None:
        return None
    risk, roles = tool.get("risk_class"), (tool.get("requires") or {}).get("roles")
    if tid is not None:
        tr = [t for t in tool.get("transitions") or [] if isinstance(t, dict) and t.get("id") == tid]
        if len(tr) != 1:
            return None
        risk, roles = tr[0].get("risk_class"), tr[0].get("allowed_roles")
    risk = risk if risk in RISKS else "R4"  # unknown never means safe
    roles = set(roles) if isinstance(roles, list) else set()
    return name, tid, risk, roles, tool.get("input_schema")


def _schema_ok(schema, args) -> bool:
    import jsonschema  # a declared dependency; an import failure stops the run (fail closed)

    if not isinstance(schema, dict):
        return False
    try:
        return jsonschema.Draft202012Validator(schema).is_valid(_placeholders(args))
    except jsonschema.SchemaError:
        return False


def _placeholders(v):
    """A `$ref` stands for an engine record id (a string) when the arguments are checked against the schema."""
    if isinstance(v, dict) and set(v) == {"$ref"}:
        return "ref"
    if isinstance(v, dict):
        return {k: _placeholders(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_placeholders(x) for x in v]
    return v


def idempotency_key(tenant_id: str, period: tuple, epoch: int, source_id: str, stage: str) -> str:
    return str(uuid.uuid5(_NS, canonical([tenant_id, period[0], period[1], epoch, source_id, stage])))


def plan_replay(records, *, tenant_id: str, period: tuple, tool_set: dict, mapping: dict, caller: dict,
                run_epoch: int = 0) -> Plan:
    """`records` in replay order (anomalies.check_records). `period` is (start, end) ISO dates.
    `caller` is {"user_id", "role_ids"} for the replay user, as identity reports them for this tenant."""
    _check_mapping(mapping)
    tools = _tools(tool_set)
    if (not isinstance(caller, dict) or not isinstance(caller.get("user_id"), str)
            or not isinstance(caller.get("role_ids"), list) or not caller["role_ids"]):
        raise SimulatorError("SIM-E03", "caller")
    if isinstance(run_epoch, bool) or not isinstance(run_epoch, int) or run_epoch < 0:
        raise SimulatorError("SIM-E01", "run_epoch")
    roles = set(caller["role_ids"])
    plan = Plan(tenant_id, tuple(period), {"user_id": caller["user_id"], "role_ids": sorted(roles)},
                tool_set.get("contentHash") or sha256(tool_set["tools"]))
    creates = {}  # (kind, number) -> create step, for payments to reference by engine record id
    for r in records:
        m = mapping.get(r.kind)
        target = {"payment_in": "sales_invoice", "payment_out": "purchase_invoice"}.get(r.kind)
        ref = creates.get((target, r.against)) if target and r.against is not None else None
        stages = [("create", None)] + ([("post", m["post"])] if m and m.get("post") else [])
        prev = None
        for stage, post in stages:
            step_id = f"{r.source_id}#{stage}"
            res = _resolve(tools, m["entity"], post) if m else None
            if stage == "create":
                args = build_arguments(r, m, {"$ref": ref.step_id} if ref else None) if m else {}
            else:
                args = {"id": {"$ref": prev.step_id}}
                if res and res[1]:
                    args["transition_id"] = res[1]
            name, tid, risk = (res[0], res[1], res[2]) if res else ("", None, "R4")
            if prev is not None and prev.action != "execute":
                action = "blocked"
                plan.anomalies.append(Anomaly("SIM-117", (r.source_id,), {"stage": stage, "dependsOn": prev.action}))
            elif stage == "create" and ref is not None and ref.action != "execute":
                action = "blocked"
                plan.anomalies.append(Anomaly("SIM-117", (r.source_id,), {"stage": stage, "dependsOn": ref.action}))
            elif res is None:
                action = "unmapped"
                plan.anomalies.append(Anomaly("SIM-108", (r.source_id,), {"stage": stage}))
            elif not roles & res[3]:
                action = "denied"
                plan.anomalies.append(Anomaly("SIM-110", (r.source_id,), {"tool": name}))
            elif stage == "create" and not _schema_ok(res[4], args):
                action = "invalid_arguments"
                plan.anomalies.append(Anomaly("SIM-111", (r.source_id,), {"tool": name}))
            elif risk not in AUTO_RUN:
                action = "needs_approval"
                plan.anomalies.append(Anomaly("SIM-109", (r.source_id,), {"tool": name, "riskClass": risk,
                                                                          "transitionId": tid}))
            else:
                action = "execute"
            step = Step(len(plan.steps) + 1, step_id, r.source_id, r.kind, stage, name, tid, risk, action,
                        idempotency_key(tenant_id, plan.period, run_epoch, r.source_id, stage), args,
                        sha256(args), prev.step_id if prev else None)
            plan.steps.append(step)
            if stage == "create":
                creates[(r.kind, r.number)] = step
            prev = step
    return plan
