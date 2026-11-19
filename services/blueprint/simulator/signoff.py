"""Owner (and accountant) sign-off on a simulation report (BPL-019).

A human decision is recorded with who and when, bound to the exact report content, append-only and final per
role. Nothing here decides for anyone: `decision`, `decided_at`, `actor` and `acknowledged` have no defaults, an
agent or service principal is refused, and accepting a report whose verdict is `blocked` or `aborted` is
refused. The result is evidence for the draft-to-live gate (BPL-020, ADR-0027: a human floor); it does not
promote a tenant and does not replace that gate's own approval.

The caller (the gateway or the web handler) supplies `actor` from the authenticated session and `decided_at`
from its own clock; this module never reads the clock and never trusts an actor it cannot validate.
"""
from __future__ import annotations

import copy
import datetime as dt

from .review import (ROLES, ReviewError, SignOffRecord, build_view, current_records, report_digest,
                     sign_off_state)
from .report import validate_report
from .safe import ID_RE, clean_text

__all__ = ["ALL_LABEL_KEYS", "SignOffError", "SignOffRecord", "apply_signoffs", "gate_evidence", "record_decision"]

NOTE_LIMIT = 2000
# Static label keys the sign-off screen uses (dynamic families, sim.* and signoff.status.* and so on, are
# covered by the same labels.json and its test).
ALL_LABEL_KEYS = ("signoff.title", "signoff.expected", "signoff.actual", "signoff.difference", "signoff.tolerance",
                  "signoff.metric_column", "signoff.status_column", "signoff.anomalies", "signoff.warnings_ack",
                  "signoff.note", "signoff.accept", "signoff.reject", "signoff.decided_by", "signoff.decided_at",
                  "signoff.stale_notice", "signoff.gate_notice", "signoff.role.owner", "signoff.role.accountant",
                  "signoff.state.awaiting", "signoff.state.accepted", "signoff.state.rejected",
                  "signoff.severity.blocking", "signoff.severity.warning", "signoff.severity.info",
                  "signoff.blocked.blocked", "signoff.blocked.aborted")


class SignOffError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _utc(value) -> str:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SignOffError("SO-E01", "decided_at must be a timezone-aware datetime")
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _actor(actor, role):
    if not isinstance(actor, dict) or actor.get("kind") != "human":
        raise SignOffError("SO-E02", "only a signed-in human can sign off")
    uid = actor.get("userId")
    if not isinstance(uid, str) or not ID_RE.fullmatch(uid):
        raise SignOffError("SO-E02", "user id")
    roles = actor.get("roles")
    if role not in ROLES or not isinstance(roles, (list, tuple)) or role not in roles:
        raise SignOffError("SO-E03", "role")
    return uid


def record_decision(report, records, *, actor, role, decision, decided_at, note, acknowledged) -> tuple:
    """Return `records` plus one new decision (a new tuple; the input is never changed)."""
    try:
        view = build_view(report, records=records)
    except ReviewError as e:
        raise SignOffError("SO-E09", str(e))
    uid = _actor(actor, role)
    if decision not in ("accepted", "rejected") or not isinstance(decision, str):
        raise SignOffError("SO-E01", "decision")
    when = _utc(decided_at)
    mine, _ = current_records(report, records)
    if any(r.role == role for r in mine):
        raise SignOffError("SO-E04", "this role has already decided on this report")
    if any(r.user_id == uid for r in mine):
        raise SignOffError("SO-E08", "one person cannot hold two sign-off roles")
    text = clean_text(note if isinstance(note, str) else "", NOTE_LIMIT).strip()
    if decision == "accepted":
        if not view["signOff"]["canAccept"]:
            raise SignOffError("SO-E05", view["verdict"])
        if not isinstance(acknowledged, (list, tuple)) or sorted(acknowledged) != sorted(view["signOff"]["toAcknowledge"]):
            raise SignOffError("SO-E06", "every warning must be acknowledged")
        if view["signOff"]["toAcknowledge"] and not text:
            raise SignOffError("SO-E07", "a note is required when accepting with warnings")
        ack = tuple(sorted(acknowledged))
    else:
        ack = ()
    rec = SignOffRecord(simulation_id=report["simulationId"], report_digest=report_digest(report), role=role,
                        user_id=uid, decision=decision, decided_at=when, note=text, acknowledged=ack)
    return tuple(records) + (rec,)


def apply_signoffs(report: dict, records) -> dict:
    """A copy of the report with `signOff` filled from the current records (schema-valid; digest unchanged)."""
    out = copy.deepcopy(report)
    mine, _ = current_records(report, records)
    for r in mine:
        out["signOff"][r.role] = {"userId": r.user_id, "decision": r.decision, "decidedAt": r.decided_at,
                                  "note": r.note or None}
    if validate_report(out):
        raise SignOffError("SO-E09", "report")
    return out


def gate_evidence(report, records, *, required_roles=("owner",)) -> dict:
    """What BPL-020 may read: who accepted which exact report. Evidence only, never an approval to go live."""
    try:
        view = build_view(report, records=records, required_roles=required_roles)
    except ReviewError as e:
        raise SignOffError("SO-E10", str(e))
    mine, _ = current_records(report, records)
    accepted = {r.role for r in mine if r.decision == "accepted"}
    return {"gate": "BPL-020", "evidenceOnly": True, "simulationId": report["simulationId"],
            "reportDigest": view["reportDigest"], "verdict": view["verdict"],
            "eligible": view["gate"]["eligible"],
            "missingRoles": [r for r in required_roles if r not in accepted],
            "decisions": [r.public() for r in mine]}
