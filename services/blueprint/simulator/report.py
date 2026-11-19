"""`simulate(...)`: normalise -> check -> plan -> run -> compare -> machine-readable report (report.schema.json).

The report carries no timestamps and no free text: same inputs, same report, same `simulationId`. Sign-off
fields are left empty for BPL-019 (owner and accountant decide there, never the simulator).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .anomalies import check_records
from .codes import sort_anomalies
from .compare import blocked_metrics, check_tolerances, compare, expected_totals
from .model import normalise
from .plan import SimulatorError, plan_replay, sha256
from .runner import run_plan

SCHEMA_PATH = Path(__file__).with_name("report.schema.json")
SCHEMA_VERSION = "0.1.0"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_report(report: dict) -> list:
    """Schema errors as JSON-pointer strings (empty list when valid)."""
    import jsonschema

    v = jsonschema.Draft202012Validator(load_schema())
    return sorted("/" + "/".join(map(str, e.absolute_path)) for e in v.iter_errors(report))


def _empty_signer() -> dict:
    return {"userId": None, "decision": None, "decidedAt": None, "note": None}


def _period(period) -> tuple:
    try:
        start, end = (dt.date.fromisoformat(p) for p in period)
    except (TypeError, ValueError):
        raise SimulatorError("SIM-E04", "period")
    if start > end:
        raise SimulatorError("SIM-E04", "period")
    return start, end


def simulate(rows, *, tenant_id: str, period: tuple, tool_set: dict, mapping: dict, caller: dict, port,
             connector_id: str = "intake", findings=None, kind_aliases=None, tax_codes=None, accounts=None,
             tolerances=None, run_epoch: int = 0) -> dict:
    """Replay one month of intake rows on the tenant behind `port` and return the report dict."""
    start, end = _period(period)
    rules = check_tolerances(tolerances)
    norm = normalise(rows, connector_id=connector_id, kind_aliases=kind_aliases, findings=findings)
    kept, found = check_records(norm.records, period_start=start, period_end=end, tax_codes=tax_codes,
                                accounts=accounts)
    plan = plan_replay(kept, tenant_id=tenant_id, period=(start.isoformat(), end.isoformat()), tool_set=tool_set,
                       mapping=mapping, caller=caller, run_epoch=run_epoch)
    run = run_plan(plan, port)
    rows_cmp, cmp_found = compare(expected_totals(kept, end), run.totals, blocked=blocked_metrics(plan.steps),
                                  rules=rules, aborted=run.status == "aborted")
    anomalies = sort_anomalies(norm.anomalies + found + plan.anomalies + run.anomalies + cmp_found)
    outcomes = {o.step_id: o for o in run.outcomes}
    prov = {r.source_id: list(r.provenance) for r in kept}
    steps = []
    for s in plan.steps:
        o = outcomes[s.step_id]
        steps.append({"seq": s.seq, "stepId": s.step_id, "sourceId": s.source_id, "kind": s.kind, "stage": s.stage,
                      "tool": s.tool, "transitionId": s.transition_id, "riskClass": s.risk_class,
                      "action": s.action, "outcome": o.outcome, "idempotencyKey": s.idempotency_key,
                      "argsHash": s.args_hash, "recordId": o.record_id, "errorCode": o.error_code,
                      "provenance": prov.get(s.source_id, [])})
    excluded = sorted({sid for a in anomalies if a.code in ("SIM-105", "SIM-107", "SIM-114", "SIM-115", "SIM-116")
                       for sid in a.source_ids})
    count = lambda seq, key, val: sum(1 for x in seq if x[key] == val)
    summary = {
        "records": len(kept), "excluded": len(excluded), "steps": len(steps),
        "executed": count(steps, "outcome", "ok"), "replayed": count(steps, "outcome", "replayed"),
        "held": count(steps, "outcome", "held"), "parked": count(steps, "outcome", "parked"),
        "notRun": count(steps, "outcome", "not_run"), "errors": count(steps, "outcome", "error"),
        "metrics": len(rows_cmp), "matched": count(rows_cmp, "status", "match"),
        "withinTolerance": count(rows_cmp, "status", "within_tolerance"),
        "mismatched": count(rows_cmp, "status", "mismatch") + count(rows_cmp, "status", "invalid_actual"),
        "notCompared": count(rows_cmp, "status", "not_compared") + count(rows_cmp, "status", "blocked_by_approval"),
        "blocking": sum(1 for a in anomalies if a.severity == "blocking"),
        "warnings": sum(1 for a in anomalies if a.severity == "warning"),
    }
    sim_id = sha256([tenant_id, plan.period, run_epoch, plan.tool_set_hash,
                     [(s.step_id, s.idempotency_key, s.args_hash, s.action) for s in plan.steps]])
    return {
        "schemaVersion": SCHEMA_VERSION, "simulationId": sim_id, "tenantId": tenant_id,
        "period": {"start": plan.period[0], "end": plan.period[1]},
        "blueprintRevision": tool_set.get("blueprintRevision") if isinstance(tool_set.get("blueprintRevision"), int) else None,
        "toolSetHash": plan.tool_set_hash, "runEpoch": run_epoch, "status": run.status, "summary": summary,
        "excluded": excluded, "steps": steps, "comparison": rows_cmp,
        "anomalies": [a.to_dict() for a in anomalies],
        "signOff": {"owner": _empty_signer(), "accountant": _empty_signer()},
    }
