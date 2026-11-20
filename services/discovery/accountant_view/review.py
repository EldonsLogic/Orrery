"""Accountant comments and per-section sign-off, recorded as DATA (DSC-016).

Same rules as the simulation sign-off (BPL-019 `simulator/signoff.py`): the signer is a verified human built by the
gateway from the identity service (never from the request body), bound to the tenant and holding the `accountant`
role; `decision`, `decided_at` and `now` have no defaults; this module never reads the clock; records are
append-only and final per (blueprint digest, section); a decision is bound to the exact Blueprint content, so any
edit makes it stale and it never counts. Nothing here approves anything for anyone: the result is evidence for the
owner approval flow (DSC-009) and the draft-to-live gate (BPL-020, ADR-0027), never an approval to go live.
Persistence must enforce a unique key on (tenant, digest, section) for decisions and on comment_id for comments.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass

from .errors import AccountantViewError
from .view import SECTIONS, VIEW_VERSION, blueprint_digest, build_sections, check_blueprint

ROLE = "accountant"
DECISIONS = ("approved", "changes_requested")
NOTE_LIMIT = 2000
MAX_SKEW = dt.timedelta(minutes=5)
EARLIEST = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
AT_RE = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")
_SIGNABLE = ("present", "empty")


@dataclass(frozen=True)
class Signer:
    """The verified principal (same shape as the simulator `Signer`). Only kind "human" may sign or comment."""
    tenant_id: str
    subject: str
    role_ids: tuple
    kind: str


@dataclass(frozen=True)
class Decision:
    tenant_id: str
    blueprint_digest: str
    section: str
    user_id: str
    decision: str
    decided_at: str
    note: str

    def public(self) -> dict:
        return {"section": self.section, "userId": self.user_id, "decision": self.decision,
                "decidedAt": self.decided_at, "note": self.note, "untrustedText": True}


@dataclass(frozen=True)
class Comment:
    tenant_id: str
    blueprint_digest: str
    section: str
    comment_id: str
    user_id: str
    created_at: str
    text: str

    def public(self) -> dict:
        return {"commentId": self.comment_id, "section": self.section, "userId": self.user_id,
                "createdAt": self.created_at, "text": self.text, "untrustedText": True}


def clean_text(value, limit=NOTE_LIMIT) -> str:
    """NFC, no control, bidi, zero-width or other format characters (Cc, Cf), trimmed, length-capped."""
    if not isinstance(value, str):
        return ""
    t = unicodedata.normalize("NFC", value)
    t = "".join(c for c in t if c in "\n" or unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"))
    return t.strip()[:limit]


def _aware(v, what):
    if not isinstance(v, dt.datetime) or v.tzinfo is None or v.utcoffset() is None:
        raise AccountantViewError("ACV-SO-001", f"{what} must be a timezone-aware datetime")
    return v.astimezone(dt.timezone.utc)


def _stamp(when, now) -> str:
    w, n = _aware(when, "timestamp"), _aware(now, "now")
    if w < EARLIEST or n < EARLIEST or abs(w - n) > MAX_SKEW:
        raise AccountantViewError("ACV-SO-001", "timestamp out of range")
    return w.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _actor(actor, tenant_id) -> str:
    if not isinstance(actor, Signer) or actor.kind != "human":
        raise AccountantViewError("ACV-SO-002", "only a verified signed-in human can sign off or comment")
    if not isinstance(actor.subject, str) or not ID_RE.fullmatch(actor.subject):
        raise AccountantViewError("ACV-SO-002", "user id")
    if not isinstance(tenant_id, str) or not tenant_id or actor.tenant_id != tenant_id:
        raise AccountantViewError("ACV-SO-003", "signer belongs to another tenant")
    if not isinstance(actor.role_ids, tuple) or ROLE not in actor.role_ids:
        raise AccountantViewError("ACV-SO-004", "role")
    return actor.subject


def _valid(r, tenant_id) -> bool:
    common = (isinstance(r.tenant_id, str) and r.tenant_id == tenant_id and r.section in SECTIONS
              and isinstance(r.blueprint_digest, str) and bool(DIGEST_RE.fullmatch(r.blueprint_digest))
              and isinstance(r.user_id, str) and bool(ID_RE.fullmatch(r.user_id)))
    if isinstance(r, Decision):
        return (common and r.decision in DECISIONS and bool(AT_RE.fullmatch(r.decided_at))
                and isinstance(r.note, str) and len(r.note) <= NOTE_LIMIT
                and (r.decision == "approved" or bool(r.note)))
    return (common and bool(ID_RE.fullmatch(r.comment_id)) and bool(AT_RE.fullmatch(r.created_at))
            and isinstance(r.text, str) and 0 < len(r.text) <= NOTE_LIMIT)


def check_records(records, tenant_id) -> tuple:
    """Materialise once; refuse (fail closed) anything malformed or from another tenant."""
    if isinstance(records, (str, bytes, dict)) or records is None:
        raise AccountantViewError("ACV-REC-001", "records")
    try:
        out = tuple(records)
    except TypeError:
        raise AccountantViewError("ACV-REC-001", "records")
    if not all(isinstance(r, (Decision, Comment)) and _valid(r, tenant_id) for r in out):
        raise AccountantViewError("ACV-REC-001", "malformed or foreign record")
    decisions = [(r.blueprint_digest, r.section) for r in out if isinstance(r, Decision)]
    ids = [r.comment_id for r in out if isinstance(r, Comment)]
    if len(set(decisions)) != len(decisions) or len(set(ids)) != len(ids):
        raise AccountantViewError("ACV-REC-002", "duplicate decision or comment id")
    return out


def _context(bp, records, tenant_id):
    bp = check_blueprint(bp)
    return bp, blueprint_digest(bp), check_records(records, tenant_id)


def _section(sections, name):
    if name not in SECTIONS:
        raise AccountantViewError("ACV-SO-005", "section")
    return next(s for s in sections if s["id"] == name)


def record_decision(blueprint, records, *, tenant_id, actor, section, decision, decided_at, now, note) -> tuple:
    """Return `records` plus one decision (a new tuple). Final per section and Blueprint digest."""
    bp, digest, records = _context(blueprint, records, tenant_id)
    uid = _actor(actor, tenant_id)
    sec = _section(build_sections(bp), section)
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise AccountantViewError("ACV-SO-001", "decision")
    if sec["status"] not in _SIGNABLE:
        raise AccountantViewError("ACV-SO-006", "this section is not in the Blueprint; nothing to sign off")
    when = _stamp(decided_at, now)
    if any(isinstance(r, Decision) and r.blueprint_digest == digest and r.section == section for r in records):
        raise AccountantViewError("ACV-SO-007", "this section already has a decision for this Blueprint")
    text = clean_text(note)
    if decision == "changes_requested" and not text:
        raise AccountantViewError("ACV-SO-008", "a note is required when requesting changes")
    return records + (Decision(tenant_id, digest, section, uid, decision, when, text),)


def add_comment(blueprint, records, *, tenant_id, actor, section, text, created_at, now) -> tuple:
    """Return `records` plus one comment. Comments are never edited or removed; ids are `c000001`, ... in order."""
    bp, digest, records = _context(blueprint, records, tenant_id)
    uid = _actor(actor, tenant_id)
    _section(build_sections(bp), section)
    when = _stamp(created_at, now)
    body = clean_text(text)
    if not body:
        raise AccountantViewError("ACV-SO-009", "empty comment")
    n = sum(isinstance(r, Comment) for r in records) + 1
    return records + (Comment(tenant_id, digest, section, f"c{n:06d}", uid, when, body),)


def build_review(blueprint, records=(), *, tenant_id) -> dict:
    """The accountant screen's data: sections plus comments and sign-off state for this exact Blueprint."""
    bp, digest, records = _context(blueprint, records, tenant_id)
    decisions = {r.section: r for r in records if isinstance(r, Decision) and r.blueprint_digest == digest}
    comments = [r for r in records if isinstance(r, Comment) and r.blueprint_digest == digest]
    stale = len(records) - len(decisions) - len(comments)
    out = []
    for s in build_sections(bp):
        d = decisions.get(s["id"])
        if s["status"] not in _SIGNABLE:
            state = "not_applicable"
        else:
            state = d.decision if d else "awaiting"
        out.append({**s, "signOff": {"state": state, "stateLabelKey": "acv.state." + state,
                                     "decision": d.public() if d else None},
                    "comments": [c.public() for c in comments if c.section == s["id"]]})
    signable = [s for s in out if s["signOff"]["state"] != "not_applicable"]
    if any(s["signOff"]["state"] == "changes_requested" for s in signable):
        overall = "changes_requested"
    elif signable and all(s["signOff"]["state"] == "approved" for s in signable):
        overall = "approved"
    else:
        overall = "awaiting"
    return {"schema": "accountant_view/1", "version": VIEW_VERSION, "titleKey": "acv.title",
            "noticeKey": "acv.notice.read_only", "evidenceNoticeKey": "acv.notice.evidence_only",
            "tenantId": tenant_id, "blueprintId": bp["meta"]["id"], "revision": bp["meta"]["revision"],
            "buildState": bp["meta"]["buildState"], "blueprintDigest": digest, "sections": out,
            "overall": {"state": overall, "labelKey": "acv.state." + overall, "evidenceOnly": True,
                        "staleRecords": stale}}
