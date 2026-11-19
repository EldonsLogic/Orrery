"""Review layer over a finished simulation report (BPL-019): derived anomaly rules, the owner sign-off view
model and the bilingual label catalogue. Deterministic code only: integers and Decimal text, no floats, no model
output (principles 3 and 6). Every text the owner reads is an i18n key (`labels.json`, en and ar); source text
only appears as sanitised params the screen must render as escaped data (principle 7).

The BPL-018 report is never changed here. Design: docs/architecture/simulator.md (BPL-019 section).
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .codes import CODES, Anomaly, sort_anomalies
from .compare import KNOWN_METRICS
from .money import EXPONENT, MoneyError, minor_to_str
from .plan import sha256
from .report import validate_report
from .safe import ID_RE, clean_obj, clean_text

VIEW_VERSION = "0.1.0"
LARGE_BASIS_POINTS = 1000  # a mismatch of 10 percent or more of the expected value
ROLES = ("owner", "accountant")
DECISIONS = ("accepted", "rejected")
NOTE_LIMIT = 2000
MAX_DEPTH = 32  # deeper report structures are refused, never recursed into
MAX_ABS_INT = 10 ** 18  # the money limit (money.parse_decimal); larger integers are refused
_VERDICT_RANK = {"pass": 0, "pass_with_warnings": 1, "blocked": 2, "aborted": 3}
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{16}$")
DECIDED_AT_RE = re.compile(r"^(20[0-9]{2})-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")
_LABELS = Path(__file__).with_name("labels.json")


class ReviewError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class SignOffRecord:
    """One human decision, bound to the exact report content (`report_digest`). Append-only; never edited.
    Records read back from a store are validated (`check_records`) and never trusted as they come."""
    tenant_id: str
    simulation_id: str
    report_digest: str
    role: str
    user_id: str
    decision: str
    decided_at: str  # UTC, ISO 8601 with milliseconds, `Z`
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


def _plain(x, depth=0) -> None:
    """Refuse floats (jsonschema counts 100000.0 as an integer), integers beyond the money limit and nesting
    deep enough to crash the validator. Booleans are left to the schema, which refuses them as integers."""
    if depth > MAX_DEPTH:
        raise ReviewError("RV-E01", "nesting")
    if isinstance(x, float):
        raise ReviewError("RV-E01", "float")
    if isinstance(x, int) and not isinstance(x, bool) and abs(x) > MAX_ABS_INT:
        raise ReviewError("RV-E01", "integer out of range")
    if isinstance(x, dict):
        for v in x.values():
            _plain(v, depth + 1)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _plain(v, depth + 1)


def _require_report(report) -> dict:
    if not isinstance(report, dict):
        raise ReviewError("RV-E01", "report")
    _plain(report)
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
        if r["currency"] not in EXPONENT:
            out.append(Anomaly("SIM-137", (), dict(base)))
        # A trivial 0 == 0 row with no documents backs no evidence and does not count as compared.
        if r["status"] in ("match", "within_tolerance") and (r["documents"] > 0 or exp != 0 or (act or 0) != 0):
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
                    out.append(Anomaly("SIM-136", (), dict(base, differenceMinor=diff, basisPoints=bp,
                                                           percent=LARGE_BASIS_POINTS // 100)))
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


def _verdict(report: dict, anomalies: list) -> str:
    """Recomputed from the report's status, summary, in-doubt list and every finding; the stored verdict can
    only make it stricter, never looser (a report is caller-supplied and may be inconsistent)."""
    s = report["summary"]
    if report["status"] == "aborted":
        computed = "aborted"
    elif (any(a.severity == "blocking" for a in anomalies) or report["inDoubt"]
          or any(s[k] for k in ("blocking", "mismatched", "inDoubt", "errors", "notRun"))):
        computed = "blocked"
    elif (any(a.severity == "warning" for a in anomalies)
          or any(s[k] for k in ("warnings", "notCompared", "held", "parked"))):
        computed = "pass_with_warnings"
    else:
        computed = "pass"
    stored = report["verdict"]
    return stored if _VERDICT_RANK.get(stored, 3) > _VERDICT_RANK[computed] else computed


def _valid_record(r) -> bool:
    return (isinstance(r, SignOffRecord)
            and all(isinstance(v, str) for v in (r.tenant_id, r.simulation_id, r.report_digest, r.role, r.user_id,
                                                  r.decision, r.decided_at, r.note))
            and 0 < len(r.tenant_id) <= 200 and bool(ID_RE.fullmatch(r.simulation_id))
            and bool(_DIGEST_RE.fullmatch(r.report_digest)) and r.role in ROLES and bool(ID_RE.fullmatch(r.user_id))
            and r.decision in DECISIONS and bool(DECIDED_AT_RE.fullmatch(r.decided_at))
            and len(r.note) <= NOTE_LIMIT and isinstance(r.acknowledged, tuple)
            and all(isinstance(f, str) and FINGERPRINT_RE.fullmatch(f) for f in r.acknowledged)
            and (r.decision == "accepted" or not r.acknowledged))


def check_records(records) -> tuple:
    """Materialise `records` once (an iterator is read exactly once) and refuse any malformed record."""
    if isinstance(records, (str, bytes, dict)) or records is None:
        raise ReviewError("RV-E03", "records")
    try:
        out = tuple(records)
    except TypeError:
        raise ReviewError("RV-E03", "records")
    if not all(_valid_record(r) for r in out):
        raise ReviewError("RV-E03", "malformed sign-off record")
    return out


def current_records(report: dict, records) -> tuple:
    """(records bound to this exact report, number of stale ones). Stale records never count. More than one
    record per role or per person for the same report is an integrity error (a race, or a store without the
    unique key on simulation, digest and role) and fails closed: nothing may hide an earlier rejection."""
    records = check_records(records)
    digest, sim = report_digest(report), report["simulationId"]
    mine = tuple(r for r in records if r.report_digest == digest and r.simulation_id == sim)
    if any(r.tenant_id != report["tenantId"] for r in mine):
        raise ReviewError("RV-E04", "sign-off record from another tenant")
    roles, users = [r.role for r in mine], [r.user_id for r in mine]
    if len(set(roles)) != len(roles) or len(set(users)) != len(users):
        raise ReviewError("RV-E04", "more than one decision per role or person")
    return mine, len(records) - len(mine)


def sign_off_state(mine, required_roles) -> str:
    """Any rejection wins, whatever its order; accepted needs every required role's acceptance."""
    if any(r.decision != "accepted" for r in mine):
        return "rejected"
    accepted = {r.role for r in mine}
    return "accepted" if all(role in accepted for role in required_roles) else "awaiting"


def build_view(report: dict, *, records=(), required_roles=("owner",)) -> dict:
    """The owner sign-off screen's data. Pure function of the report and the records; decides nothing."""
    report = _require_report(report)
    required_roles = tuple(required_roles) if isinstance(required_roles, (list, tuple)) else ()
    if not required_roles or set(required_roles) - set(ROLES) or len(set(required_roles)) != len(required_roles):
        raise ReviewError("RV-E02", "required_roles")
    mine, stale = current_records(report, records)
    derived = review_anomalies(report)
    # An unknown code (a newer simulator, or a forged report) is never dropped: it blocks acceptance.
    derived += [Anomaly("SIM-138", tuple(x["sourceIds"]), {"code": x["code"]}) for x in report["anomalies"]
                if x["code"] not in CODES]
    found = [Anomaly(x["code"], tuple(x["sourceIds"]), x["params"]) for x in report["anomalies"] if x["code"] in CODES]
    anomalies = []
    for a in sort_anomalies(found + derived):
        d = a.to_dict()
        anomalies.append(dict(d, severityKey=f"signoff.severity.{a.severity}", fingerprint=fingerprint(d),
                              origin="review" if a in derived else "simulation"))
    verdict = _verdict(report, found + derived)
    can_accept = verdict not in ("blocked", "aborted")
    state = sign_off_state(mine, required_roles)
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
            "requiredRoles": list(required_roles), "state": state,
            "canAccept": can_accept, "blockedByKey": None if can_accept else f"signoff.blocked.{verdict}",
            # Unique and sorted: identical warnings share one fingerprint and are acknowledged once.
            "toAcknowledge": sorted({a["fingerprint"] for a in anomalies if a["severity"] == "warning"}),
            "records": [r.public() for r in mine], "staleRecords": stale,
        },
        # Sign-off is evidence for the draft-to-live gate (BPL-020); it never promotes a tenant by itself.
        "gate": {"gate": "BPL-020", "evidenceOnly": True,
                 "eligible": can_accept and state == "accepted"},
    }
