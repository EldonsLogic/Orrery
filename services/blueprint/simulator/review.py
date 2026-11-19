"""Review layer over a finished simulation report (BPL-019): derived anomaly rules, the owner sign-off view
model and the bilingual label catalogue. Deterministic code only: integers and Decimal text, no floats, no model
output (principles 3 and 6). Every text the owner reads is an i18n key (`labels.json`, en and ar); source text
only appears as sanitised params the screen must render as escaped data (principle 7).

The BPL-018 report is never changed here. Design: docs/architecture/simulator.md (BPL-019 section).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from .codes import CODES, Anomaly, sort_anomalies
from .compare import KNOWN_METRICS
from .money import MoneyError, minor_to_str
from .plan import sha256
from .report import validate_report
from .safe import clean_obj, clean_text

VIEW_VERSION = "0.1.0"
LARGE_BASIS_POINTS = 1000  # a mismatch of 10 percent or more of the expected value
ROLES = ("owner", "accountant")
_LABELS = Path(__file__).with_name("labels.json")


class ReviewError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class SignOffRecord:
    """One human decision, bound to the exact report content (`report_digest`). Append-only; never edited."""
    simulation_id: str
    report_digest: str
    role: str
    user_id: str
    decision: str
    decided_at: str  # UTC, ISO 8601, `Z`
    note: str
    acknowledged: tuple

    def public(self) -> dict:
        return {"role": self.role, "userId": self.user_id, "decision": self.decision, "decidedAt": self.decided_at,
                "note": self.note, "acknowledged": list(self.acknowledged)}


def labels(locale: str) -> dict:
    if locale not in ("en", "ar"):
        raise ValueError("locale")
    return dict(json.loads(_LABELS.read_text(encoding="utf-8"))[locale])


def report_digest(report: dict) -> str:
    """SHA-256 of the report with its sign-off fields blanked, so filling them in never changes the digest."""
    body = {k: v for k, v in report.items() if k != "signOff"}
    return sha256(body)


def _require_report(report) -> dict:
    if not isinstance(report, dict):
        raise ReviewError("RV-E01", "report")
    try:
        errors = validate_report(report)
    except Exception:  # a hostile structure must refuse, not crash the screen
        raise ReviewError("RV-E01", "report")
    if errors:
        raise ReviewError("RV-E01", ",".join(errors[:3]))
    return report


def _bp(diff: int, expected: int):
    """Whole basis points of |diff| over |expected| (integer floor), None when expected is zero."""
    return None if expected == 0 else abs(diff) * 10_000 // abs(expected)


def review_anomalies(report: dict) -> list:
    """Extra deterministic rules over the comparison rows (SIM-132 to SIM-136). Flags only."""
    out, compared = [], 0
    for r in report["comparison"]:
        exp, act, diff, tol = r["expectedMinor"], r["actualMinor"], r["differenceMinor"], r["toleranceMinor"]
        base = {"metric": r["metric"], "currency": r["currency"]}
        if r["status"] in ("match", "within_tolerance"):
            compared += 1
        if act is None or diff is None:
            continue
        if r["status"] == "within_tolerance" and tol > 0 and abs(diff) == tol:
            out.append(Anomaly("SIM-134", (), dict(base, differenceMinor=diff, toleranceMinor=tol)))
        elif r["status"] == "mismatch":
            if exp != 0 and act != 0 and (exp > 0) != (act > 0):
                out.append(Anomaly("SIM-132", (), dict(base, differenceMinor=diff)))
            elif exp != 0 and act == 0:
                out.append(Anomaly("SIM-133", (), dict(base, expectedMinor=exp)))
            else:
                bp = _bp(diff, exp)
                if bp is None or bp >= LARGE_BASIS_POINTS:
                    out.append(Anomaly("SIM-136", (), dict(base, differenceMinor=diff, basisPoints=bp)))
    if compared == 0:
        out.append(Anomaly("SIM-135", (), {"metrics": len(report["comparison"])}))
    return out


def fingerprint(anomaly_dict: dict) -> str:
    return sha256([anomaly_dict["code"], anomaly_dict["sourceIds"], anomaly_dict["params"]])[:16]


def _money(minor, currency):
    if minor is None:
        return None
    try:
        return minor_to_str(minor, currency)
    except MoneyError:
        return None


def _metric_key(metric: str) -> str:
    return f"signoff.metric.{metric}" if metric in KNOWN_METRICS else "signoff.metric.unknown"


def _verdict(report: dict, derived: list) -> str:
    v = report["verdict"]
    if v in ("aborted", "blocked"):
        return v
    if any(a.severity == "blocking" for a in derived):
        return "blocked"
    if v == "pass" and any(a.severity == "warning" for a in derived):
        return "pass_with_warnings"
    return v


def current_records(report: dict, records) -> tuple:
    """(records bound to this exact report, number of stale ones). Stale records never count."""
    digest, sim = report_digest(report), report["simulationId"]
    mine = tuple(r for r in records if r.report_digest == digest and r.simulation_id == sim)
    return mine, len(tuple(records)) - len(mine)


def sign_off_state(mine, required_roles) -> str:
    latest = {r.role: r.decision for r in mine}
    if "rejected" in latest.values():
        return "rejected"
    return "accepted" if all(latest.get(role) == "accepted" for role in required_roles) else "awaiting"


def build_view(report: dict, *, records=(), required_roles=("owner",)) -> dict:
    """The owner sign-off screen's data. Pure function of the report and the records; decides nothing."""
    report = _require_report(report)
    if not required_roles or set(required_roles) - set(ROLES):
        raise ReviewError("RV-E02", "required_roles")
    derived = review_anomalies(report)
    anomalies = []
    for a in sort_anomalies([Anomaly(x["code"], tuple(x["sourceIds"]), x["params"]) for x in report["anomalies"]
                             if x["code"] in CODES] + derived):
        d = a.to_dict()
        anomalies.append(dict(d, severityKey=f"signoff.severity.{a.severity}", fingerprint=fingerprint(d),
                              origin="review" if a in derived else "simulation"))
    verdict = _verdict(report, derived)
    can_accept = verdict not in ("blocked", "aborted")
    mine, stale = current_records(report, records)
    rows = []
    for r in report["comparison"]:
        c = r["currency"]
        rows.append({"metric": clean_text(r["metric"], 64), "metricKey": _metric_key(r["metric"]), "currency": c,
                     "expected": _money(r["expectedMinor"], c), "actual": _money(r["actualMinor"], c),
                     "difference": _money(r["differenceMinor"], c), "tolerance": _money(r["toleranceMinor"], c),
                     "documents": r["documents"], "status": r["status"],
                     "statusKey": f"signoff.status.{r['status']}",
                     "reasonKey": f"signoff.reason.{r['reason']}" if r["reason"] else None})
    sev = lambda s: sum(1 for a in anomalies if a["severity"] == s)
    return {
        "viewVersion": VIEW_VERSION, "simulationId": report["simulationId"], "reportDigest": report_digest(report),
        "tenantId": clean_text(report["tenantId"], 200), "period": copy.deepcopy(report["period"]),
        "status": report["status"], "verdict": verdict, "verdictKey": f"signoff.verdict.{verdict}",
        "headline": {"records": report["summary"]["records"], "excluded": report["summary"]["excluded"],
                     "metrics": len(rows), "matched": report["summary"]["matched"],
                     "withinTolerance": report["summary"]["withinTolerance"],
                     "mismatched": sum(1 for r in rows if r["status"] in ("mismatch", "invalid_actual")),
                     "held": report["summary"]["held"], "blocking": sev("blocking"), "warnings": sev("warning")},
        "rows": rows, "anomalies": anomalies,
        "signOff": {
            "requiredRoles": list(required_roles), "state": sign_off_state(mine, required_roles),
            "canAccept": can_accept, "blockedByKey": None if can_accept else f"signoff.blocked.{verdict}",
            "toAcknowledge": [a["fingerprint"] for a in anomalies if a["severity"] == "warning"],
            "records": [r.public() for r in mine], "staleRecords": stale,
        },
        # Sign-off is evidence for the draft-to-live gate (BPL-020); it never promotes a tenant by itself.
        "gate": {"gate": "BPL-020", "evidenceOnly": True,
                 "eligible": can_accept and sign_off_state(mine, required_roles) == "accepted"},
    }
