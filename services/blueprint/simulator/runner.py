"""Replay runner and the engine port. The same runner drives the simulated port (CI) and, later, a port that
calls the real tenant through the Tool API gateway.

Fail closed: any port exception, an `error` response or a malformed response stops the run. Remaining steps are
`not_run`, totals are not read and nothing is compared (report status `aborted`). Steps that are not `execute`
are never sent: R3 and R4 stay `held` (would need approval).

A port exception may have happened after the engine applied the call: that step is `in_doubt` (ADR-0028), its
document is listed in the report's `inDoubt`, and the run stops. A rerun with the same run epoch sends the same
idempotency keys, so the tenant converges (applied calls return `replayed`). A fresh run epoch on a tenant that
already holds data is refused (SIM-129) unless `on_existing` says `resume` (same epoch rerun) or `allow` (SIM-130).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .codes import Anomaly
from .money import MoneyError, parse_decimal
from .plan import AUTO_RUN, Plan
from .safe import ID_RE, safe_code


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
    outcome: str  # ok | replayed | held | parked | not_run | error | in_doubt
    record_id: str = None
    error_code: str = None


@dataclass
class RunResult:
    status: str  # completed | aborted
    outcomes: list = field(default_factory=list)
    totals: dict = None
    anomalies: list = field(default_factory=list)
    in_doubt: list = field(default_factory=list)  # source ids whose call may have been applied


def _resolve_args(args: dict, ids: dict):
    """(resolved arguments, unresolved reference step ids)."""
    out, missing = {}, []
    for k, v in args.items():
        if isinstance(v, dict) and set(v) == {"$ref"}:
            if v["$ref"] in ids:
                out[k] = ids[v["$ref"]]
            else:
                missing.append(v["$ref"])
        else:
            out[k] = v
    return out, missing


def _abort(result: RunResult, plan: Plan, done: set, step_id, source_id, reason: str, code="SIM-120") -> RunResult:
    result.status = "aborted"
    result.anomalies.append(Anomaly(code, (source_id,) if source_id else (), {"reason": reason, "stepId": step_id}))
    for s in plan.steps:
        if s.step_id not in done:
            result.outcomes.append(StepOutcome(s.step_id, "not_run"))
    return result


def _valid_totals(totals) -> bool:
    return isinstance(totals, dict) and all(
        isinstance(m, str) and isinstance(v, dict) and all(isinstance(c, str) and isinstance(a, str) for c, a in v.items())
        for m, v in totals.items())


def _has_data(totals) -> bool:
    for by in totals.values():
        for a in by.values():
            try:
                if parse_decimal(a) != 0:
                    return True
            except MoneyError:
                return True
    return False


def run_plan(plan: Plan, port: EnginePort, on_existing: str = "refuse") -> RunResult:
    """`on_existing`: `refuse` (fresh run: a tenant that already reports data aborts, SIM-129), `resume` (rerun of
    the same epoch: no pre-read) or `allow` (fresh run on a tenant with data, flagged SIM-130)."""
    result = RunResult("completed")
    ids, done = {}, set()
    if on_existing != "resume" and any(s.action == "execute" for s in plan.steps):
        try:
            pre = port.report_totals(plan.tenant_id, dict(plan.caller), plan.period)
        except Exception:  # noqa: BLE001
            return _abort(result, plan, done, None, None, "totals_preread_exception")
        if not _valid_totals(pre):
            return _abort(result, plan, done, None, None, "totals_preread_malformed")
        if _has_data(pre):
            if on_existing != "allow":
                return _abort(result, plan, done, None, None, "tenant_not_empty", code="SIM-129")
            result.anomalies.append(Anomaly("SIM-130", (), {}))
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
        args, missing = _resolve_args(s.arguments, ids)
        if missing and all(m in done for m in missing):  # the referenced step was parked or not run
            result.outcomes.append(StepOutcome(s.step_id, "not_run"))
            done.add(s.step_id)
            continue
        if missing:
            return _abort(result, plan, done, s.step_id, s.source_id, "unresolved_reference")
        call = ToolCall(plan.tenant_id, dict(plan.caller), s.tool, args, s.idempotency_key)
        try:
            resp = port.execute(call)
        except Exception:  # noqa: BLE001 - the call may have been applied: in doubt, stop, reconcile by rerun
            result.outcomes.append(StepOutcome(s.step_id, "in_doubt"))
            done.add(s.step_id)
            result.in_doubt.append(s.source_id)
            result.anomalies.append(Anomaly("SIM-128", (s.source_id,), {"stepId": s.step_id}))
            return _abort(result, plan, done, s.step_id, s.source_id, "exception_in_doubt")
        status = resp.get("status") if isinstance(resp, dict) else None
        if status == "pending_approval":  # a Blueprint approval rule parked it: not an error, not executed
            result.outcomes.append(StepOutcome(s.step_id, "parked"))
            result.anomalies.append(Anomaly("SIM-118", (s.source_id,), {"tool": s.tool}))
            done.add(s.step_id)
            continue
        rid = (resp.get("result") or {}).get("id") if status == "ok" and isinstance(resp.get("result"), dict) else None
        if status != "ok" or not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            err = resp.get("error") if status == "error" and isinstance(resp.get("error"), dict) else {}
            result.outcomes.append(StepOutcome(s.step_id, "error", error_code=safe_code(err.get("code"))))
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
