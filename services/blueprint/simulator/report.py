"""`simulate(...)`: normalise -> check -> plan -> run -> compare -> machine-readable report (report.schema.json).

The report carries no timestamps: same inputs, same report, same `simulationId` (which identifies the plan, not
the outcome). It has no model-written text, but params and ids can carry source text (item, party, sheet, number):
every such string and every port string is sanitised (safe.py: control and bidi characters stripped, length
capped, codes and keys allow-listed) and `simulate` validates its own output against the schema before returning
it. `verdict` is computed for BPL-019; sign-off fields stay empty (owner and accountant decide there).
"""
from __future__ import annotations

import datetime as dt
import decimal
from decimal import localcontext
import json
from pathlib import Path

from .anomalies import check_records
from .codes import sort_anomalies
from .compare import blocked_metrics, check_tolerances, compare, expected_totals
from .model import normalise
from .money import CTX
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
             tolerances=None, run_epoch: int = 0, on_existing: str = "refuse") -> dict:
    """Replay one month of intake rows on the tenant behind `port` and return the report dict.

    `on_existing`: `refuse` (default; a tenant that already reports data aborts the run, SIM-129), `resume`
    (rerun of the same `run_epoch` after an abort or in-doubt call; idempotency keys converge it) or `allow`
    (fresh epoch on a tenant with data, flagged SIM-130; totals will include the earlier documents)."""
    if on_existing not in ("refuse", "resume", "allow"):
        raise SimulatorError("SIM-E01", "on_existing")
    try:
        with localcontext(CTX):  # exact arithmetic; rounding, invalid or overflow raises instead of passing
            report = _simulate(rows, tenant_id, period, tool_set, mapping, caller, port, connector_id, findings,
                               kind_aliases, tax_codes, accounts, tolerances, run_epoch, on_existing)
    except decimal.DecimalException:
        raise SimulatorError("SIM-E05", "decimal arithmetic")
    errors = validate_report(report)  # never hand out a report that breaks its own schema
    if errors:
        raise SimulatorError("SIM-E06", ",".join(errors[:5]))
    return report


def _verdict(status: str, summary: dict) -> str:
    if status == "aborted":
        return "aborted"
    if summary["blocking"] or summary["mismatched"]:
        return "blocked"
    if summary["warnings"] or summary["notCompared"] or summary["held"] or summary["parked"]:
        return "pass_with_warnings"
    return "pass"


def _simulate(rows, tenant_id, period, tool_set, mapping, caller, port, connector_id, findings, kind_aliases,
              tax_codes, accounts, tolerances, run_epoch, on_existing) -> dict:
    start, end = _period(period)
    rules = check_tolerances(tolerances)
    norm = normalise(rows, connector_id=connector_id, kind_aliases=kind_aliases, findings=findings)
    kept, found = check_records(norm.records, period_start=start, period_end=end, tax_codes=tax_codes,
                                accounts=accounts)
    plan = plan_replay(kept, tenant_id=tenant_id, period=(start.isoformat(), end.isoformat()), tool_set=tool_set,
                       mapping=mapping, caller=caller, run_epoch=run_epoch)
    run = run_plan(plan, port, on_existing)
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
        "notRun": count(steps, "outcome", "not_run"), "errors": count(steps, "outcome", "error"), "inDoubt": count(steps, "outcome", "in_doubt"),
        "metrics": len(rows_cmp), "matched": count(rows_cmp, "status", "match"),
        "withinTolerance": count(rows_cmp, "status", "within_tolerance"),
        "mismatched": count(rows_cmp, "status", "mismatch") + count(rows_cmp, "status", "invalid_actual"),
        "notCompared": count(rows_cmp, "status", "not_compared") + count(rows_cmp, "status", "blocked_by_approval"),
        "blocking": sum(1 for a in anomalies if a.severity == "blocking"),
        "warnings": sum(1 for a in anomalies if a.severity == "warning"),
    }
    in_doubt = sorted(set(run.in_doubt))
    sim_id = sha256([tenant_id, plan.period, run_epoch, plan.tool_set_hash,
                     [(s.step_id, s.idempotency_key, s.args_hash, s.action) for s in plan.steps]])
    return {
        "schemaVersion": SCHEMA_VERSION, "simulationId": sim_id, "tenantId": tenant_id,
        "period": {"start": plan.period[0], "end": plan.period[1]},
        "blueprintRevision": tool_set.get("blueprintRevision") if isinstance(tool_set.get("blueprintRevision"), int) else None,
        "toolSetHash": plan.tool_set_hash, "runEpoch": run_epoch, "status": run.status, "verdict": _verdict(run.status, summary),
        "summary": summary, "inDoubt": in_doubt,
        "excluded": excluded, "steps": steps, "comparison": rows_cmp,
        "anomalies": [a.to_dict() for a in anomalies],
        "signOff": {"owner": _empty_signer(), "accountant": _empty_signer()},
    }
