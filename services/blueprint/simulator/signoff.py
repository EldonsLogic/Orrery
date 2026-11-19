"""Owner (and accountant) sign-off on a simulation report (BPL-019).

A human decision is recorded with who and when, bound to the exact report content, append-only and final per
role. Nothing here decides for anyone: `decision`, `decided_at`, `actor` and `acknowledged` have no defaults, an
agent or service principal is refused, and accepting a report whose verdict is `blocked` or `aborted` is
refused. The result is evidence for the draft-to-live gate (BPL-020, ADR-0027: a human floor); it does not
promote a tenant and does not replace that gate's own approval.

The caller (the gateway or the web handler) supplies `actor` as a `Signer` built from the identity service's
verified claims (PLT-005; never from the request body), and `decided_at` and `now` from its own clock; this
module never reads the clock. A signer from another tenant than the report's is refused. Records read back are
validated and fail closed (review.check_records); BPL-020 must still compare `reportDigest` with the digest of
the report it stored itself, never one a caller supplies.
"""
from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass

from .review import (DECISIONS, FINGERPRINT_RE, NOTE_LIMIT, ROLES, ReviewError, SignOffRecord, build_view,
                     check_records, current_records, report_digest)
from .report import validate_report
from .safe import ID_RE, clean_text

__all__ = ["ALL_LABEL_KEYS", "SignOffError", "SignOffRecord", "Signer", "apply_signoffs", "gate_evidence",
           "record_decision"]

MAX_SKEW = dt.timedelta(minutes=5)  # decided_at must be within this of the caller's clock (no back- or future-dating)
EARLIEST = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
# Static label keys the sign-off screen uses (dynamic families, sim.* and signoff.status.* and so on, are
# covered by the same labels.json and its test).
ALL_LABEL_KEYS = ("signoff.title", "signoff.expected", "signoff.actual", "signoff.difference", "signoff.tolerance",
                  "signoff.metric_column", "signoff.status_column", "signoff.anomalies", "signoff.warnings_ack",
                  "signoff.note", "signoff.accept", "signoff.reject", "signoff.decided_by", "signoff.decided_at",
                  "signoff.stale_notice", "signoff.gate_notice", "signoff.role.owner", "signoff.role.accountant",
                  "signoff.state.awaiting", "signoff.state.accepted", "signoff.state.rejected",
                  "signoff.severity.blocking", "signoff.severity.warning", "signoff.severity.info",
                  "signoff.blocked.blocked", "signoff.blocked.aborted")


@dataclass(frozen=True)
class Signer:
    """The verified principal deciding (same shape as the AG-UI `Principal`, plus the principal kind). Tenant,
    subject, roles and kind come from the identity service, never from the request."""
    tenant_id: str
    subject: str
    role_ids: tuple
    kind: str  # "human", "agent" or "service"; only "human" may sign


class SignOffError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _aware(value, what):
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SignOffError("SO-E01", f"{what} must be a timezone-aware datetime")
    return value.astimezone(dt.timezone.utc)


def _utc(value, now) -> str:
    when, clock = _aware(value, "decided_at"), _aware(now, "now")
    if when < EARLIEST or clock < EARLIEST or abs(when - clock) > MAX_SKEW:
        raise SignOffError("SO-E01", "decided_at out of range")
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _actor(actor, role, tenant_id):
    if not isinstance(actor, Signer) or actor.kind != "human":
        raise SignOffError("SO-E02", "only a verified signed-in human can sign off")
    if not isinstance(actor.subject, str) or not ID_RE.fullmatch(actor.subject):
        raise SignOffError("SO-E02", "user id")
    if not isinstance(actor.tenant_id, str) or actor.tenant_id != tenant_id:
        raise SignOffError("SO-E11", "signer belongs to another tenant")
    if role not in ROLES or not isinstance(actor.role_ids, tuple) or role not in actor.role_ids:
        raise SignOffError("SO-E03", "role")
    return actor.subject


def _records(records) -> tuple:
    try:
        return check_records(records)
    except ReviewError as e:
        raise SignOffError("SO-E09", str(e))


def record_decision(report, records, *, actor, role, decision, decided_at, now, note, acknowledged) -> tuple:
    """Return `records` plus one new decision (a new tuple; the input is never changed). Persistence must
    enforce a unique key on (simulation_id, report_digest, role) so a race cannot store two decisions."""
    records = _records(records)
    try:
        view = build_view(report, records=records)
        mine, _ = current_records(report, records)
    except ReviewError as e:
        raise SignOffError("SO-E09", str(e))
    uid = _actor(actor, role, report["tenantId"])
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise SignOffError("SO-E01", "decision")
    when = _utc(decided_at, now)
    if any(r.role == role for r in mine):
        raise SignOffError("SO-E04", "this role has already decided on this report")
    if any(r.user_id == uid for r in mine):
        raise SignOffError("SO-E08", "one person cannot hold two sign-off roles")
    text = clean_text(note if isinstance(note, str) else "", NOTE_LIMIT).strip()
    if decision == "accepted":
        if not view["signOff"]["canAccept"]:
            raise SignOffError("SO-E05", view["verdict"])
        if (not isinstance(acknowledged, (list, tuple))
                or not all(isinstance(f, str) and FINGERPRINT_RE.fullmatch(f) for f in acknowledged)
                or sorted(acknowledged) != view["signOff"]["toAcknowledge"]):
            raise SignOffError("SO-E06", "every warning must be acknowledged, once, and nothing else")
        if view["signOff"]["toAcknowledge"] and not text:
            raise SignOffError("SO-E07", "a note is required when accepting with warnings")
        ack = tuple(sorted(acknowledged))
    else:
        ack = ()
    rec = SignOffRecord(tenant_id=report["tenantId"], simulation_id=report["simulationId"], report_digest=report_digest(report), role=role,
                        user_id=uid, decision=decision, decided_at=when, note=text, acknowledged=ack)
    return records + (rec,)


def apply_signoffs(report: dict, records) -> dict:
    """A copy of the report with `signOff` filled from the current records (schema-valid; digest unchanged)."""
    records = _records(records)
    try:
        build_view(report, records=records)
        mine, _ = current_records(report, records)
    except ReviewError as e:
        raise SignOffError("SO-E09", str(e))
    out = copy.deepcopy(report)
    for r in mine:
        out["signOff"][r.role] = {"userId": r.user_id, "decision": r.decision, "decidedAt": r.decided_at,
                                  "note": r.note or None}
    if validate_report(out):
        raise SignOffError("SO-E09", "report")
    return out


def gate_evidence(report, records, *, required_roles=("owner",)) -> dict:
    """What BPL-020 may read: who accepted which exact report, under which required roles. Evidence only, never
    an approval to go live; BPL-020 applies its own role policy and does not trust `eligible` alone."""
    try:
        records = check_records(records)
        view = build_view(report, records=records, required_roles=required_roles)
        mine, _ = current_records(report, records)
    except ReviewError as e:
        raise SignOffError("SO-E10", str(e))
    accepted = {r.role for r in mine if r.decision == "accepted"}
    return {"gate": "BPL-020", "evidenceOnly": True, "simulationId": report["simulationId"],
            "tenantId": report["tenantId"], "requiredRoles": list(view["signOff"]["requiredRoles"]),
            "reportDigest": view["reportDigest"], "verdict": view["verdict"],
            "eligible": view["gate"]["eligible"],
            "missingRoles": [r for r in required_roles if r not in accepted],
            "decisions": [r.public() for r in mine]}
