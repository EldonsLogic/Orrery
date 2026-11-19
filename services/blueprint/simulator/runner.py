"""Replay runner and the engine port. The same runner drives the simulated port (CI) and, later, a port that
calls the real tenant through the Tool API gateway.

Fail closed: any port exception, an `error` response or a malformed response stops the run. Remaining steps are
`not_run`, totals are not read and nothing is compared (report status `aborted`). Steps that are not `execute`
are never sent: R3 and R4 stay `held` (would need approval).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .codes import Anomaly
from .plan import AUTO_RUN, Plan


@dataclass(frozen=True)
class ToolCall:
    tenant_id: str
    caller: dict
    tool: str
    arguments: dict
    idempotency_key: str


class EnginePort(Protocol):
    """What the simulator needs from a compiled tenant. Implementations: `SimulatedPort` now; a gateway-backed
    port (Tool API calls with the replay user's own session, `report.run` for totals) once a real tenant exists.

    `execute` returns a Tool API response: {"status": "ok", "result": {"id": ...}, "replayed": bool} or
    {"status": "pending_approval", ...} or {"status": "error", "error": {"code": ...}}.
    `report_totals` returns {metric: {currency: "decimal string"}}; a metric the tenant cannot report is absent.
    """

    def execute(self, call: ToolCall) -> dict: ...

    def report_totals(self, tenant_id: str, caller: dict, period: tuple) -> dict: ...


@dataclass
class StepOutcome:
    step_id: str
    outcome: str  # ok | replayed | held | parked | not_run | error
    record_id: str = None
    error_code: str = None


@dataclass
class RunResult:
    status: str  # completed | aborted
    outcomes: list = field(default_factory=list)
    totals: dict = None
    anomalies: list = field(default_factory=list)


def _resolve_args(args: dict, ids: dict):
    out = {}
    for k, v in args.items():
        if isinstance(v, dict) and set(v) == {"$ref"}:
            if v["$ref"] not in ids:
                return None
            out[k] = ids[v["$ref"]]
        else:
            out[k] = v
    return out


def _abort(result: RunResult, plan: Plan, done: set, step_id, source_id, reason: str) -> RunResult:
    result.status = "aborted"
    result.anomalies.append(Anomaly("SIM-120", (source_id,) if source_id else (), {"reason": reason, "stepId": step_id}))
    for s in plan.steps:
        if s.step_id not in done:
            result.outcomes.append(StepOutcome(s.step_id, "not_run"))
    return result


def _valid_totals(totals) -> bool:
    return isinstance(totals, dict) and all(
        isinstance(m, str) and isinstance(v, dict) and all(isinstance(c, str) and isinstance(a, str) for c, a in v.items())
        for m, v in totals.items())


def run_plan(plan: Plan, port: EnginePort) -> RunResult:
    result = RunResult("completed")
    ids, done = {}, set()
    for s in plan.steps:
        if s.action != "execute":
            result.outcomes.append(StepOutcome(s.step_id, "held" if s.action == "needs_approval" else "not_run"))
            done.add(s.step_id)
            continue
        if s.risk_class not in AUTO_RUN:  # defence in depth: the planner never marks these `execute`
            return _abort(result, plan, done, s.step_id, s.source_id, "risk")
        if s.depends_on and s.depends_on not in ids:  # the create step was parked: nothing to post
            result.outcomes.append(StepOutcome(s.step_id, "not_run"))
            done.add(s.step_id)
            continue
        args = _resolve_args(s.arguments, ids)
        if args is None:
            return _abort(result, plan, done, s.step_id, s.source_id, "unresolved_reference")
        call = ToolCall(plan.tenant_id, dict(plan.caller), s.tool, args, s.idempotency_key)
        try:
            resp = port.execute(call)
        except Exception:  # noqa: BLE001 - any port failure stops the run; details stay in the port's own log
            return _abort(result, plan, done, s.step_id, s.source_id, "exception")
        status = resp.get("status") if isinstance(resp, dict) else None
        if status == "pending_approval":  # a Blueprint approval rule parked it: not an error, not executed
            result.outcomes.append(StepOutcome(s.step_id, "parked"))
            result.anomalies.append(Anomaly("SIM-118", (s.source_id,), {"tool": s.tool}))
            done.add(s.step_id)
            continue
        rid = (resp.get("result") or {}).get("id") if status == "ok" and isinstance(resp.get("result"), dict) else None
        if status != "ok" or not isinstance(rid, str) or not rid:
            err = resp.get("error") if status == "error" and isinstance(resp.get("error"), dict) else {}
            code = err.get("code") if isinstance(err.get("code"), str) else None
            result.outcomes.append(StepOutcome(s.step_id, "error", error_code=code))
            done.add(s.step_id)
            return _abort(result, plan, done, s.step_id, s.source_id,
                          "error" if status == "error" else "malformed_response")
        ids[s.step_id] = rid
        result.outcomes.append(StepOutcome(s.step_id, "replayed" if resp.get("replayed") is True else "ok", rid))
        done.add(s.step_id)
    try:
        totals = port.report_totals(plan.tenant_id, dict(plan.caller), plan.period)
    except Exception:  # noqa: BLE001
        return _abort(result, plan, done, None, None, "totals_exception")
    if not _valid_totals(totals):
        return _abort(result, plan, done, None, None, "totals_malformed")
    result.totals = totals
    return result
