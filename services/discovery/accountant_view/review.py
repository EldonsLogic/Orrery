"""Accountant comments and per-section sign-off, recorded as DATA (DSC-016).

Same rules as the simulation sign-off (BPL-019 `simulator/signoff.py`): the signer is a verified human built by the
gateway from the identity service (never from the request body), bound to the tenant and holding the `accountant`
role; `decision`, `decided_at` and `now` have no defaults; this module never reads the clock; records are
append-only and final per (blueprint digest, section); a decision is bound to the exact Blueprint content, so any
edit makes it stale and it never counts. Nothing here approves anything for anyone: the result is evidence for the
owner approval flow (DSC-009) and the draft-to-live gate (BPL-020, ADR-0027), never an approval to go live.
Persistence must enforce unique keys on (tenant, digest, section, sequence) for decisions and on (tenant, comment_id) for
comments, and should assign comment ids itself (the in-memory `c000001` counter can race). A stored record that fails
the replay rules is quarantined (skipped, counted in `overall.quarantined`), never rendered and never blocks the view.
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
# Until Q-371 fixes role ids: the owner and any admin-equivalent role cannot review as accountant (case-insensitive).
OWNER_EQUIVALENT = frozenset({"owner", "admin", "administrator", "superadmin", "super_admin", "is_admin", "isadmin"})
FIRST_YEAR, LAST_YEAR = 2000, 2099
NOTE_LIMIT = 2000
MAX_SKEW = dt.timedelta(minutes=5)
EARLIEST = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
LATEST = dt.datetime(2100, 1, 1, tzinfo=dt.timezone.utc)
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

    def public(self, stale=False) -> dict:
        return {"section": self.section, "userId": self.user_id, "decision": self.decision,
                "decidedAt": self.decided_at, "note": self.note, "untrustedText": True, "stale": stale,
                "blueprintDigest": self.blueprint_digest}


@dataclass(frozen=True)
class Comment:
    tenant_id: str
    blueprint_digest: str
    section: str
    comment_id: str
    user_id: str
    created_at: str
    text: str

    def public(self, stale=False) -> dict:
        return {"commentId": self.comment_id, "section": self.section, "userId": self.user_id,
                "createdAt": self.created_at, "text": self.text, "untrustedText": True, "stale": stale,
                "blueprintDigest": self.blueprint_digest}


def clean_text(value) -> str:
    """NFC, no control, bidi, zero-width or other format characters (Cc, Cf), trimmed, length-capped."""
    if not isinstance(value, str):
        return ""
    t = unicodedata.normalize("NFC", value)
    t = "".join(c for c in t if c in "\n" or unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"))
    return t.strip()


def _aware(v, what):
    if not isinstance(v, dt.datetime) or v.tzinfo is None or v.utcoffset() is None:
        raise AccountantViewError("ACV-SO-001", f"{what} must be a timezone-aware datetime")
    return v.astimezone(dt.timezone.utc)


def _stamp(when, now) -> str:
    w, n = _aware(when, "timestamp"), _aware(now, "now")
    if w < EARLIEST or n < EARLIEST or w >= LATEST or n >= LATEST or abs(w - n) > MAX_SKEW:
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
    if not all(isinstance(r, str) for r in actor.role_ids):
        raise AccountantViewError("ACV-SO-004", "role")
    if {r.strip().lower() for r in actor.role_ids} & OWNER_EQUIVALENT:  # the reviewer is not the author (Q-373)
        raise AccountantViewError("ACV-SO-010", "a signer who also holds the owner role cannot review as accountant")
    return actor.subject


def _ts_ok(v) -> bool:
    if not isinstance(v, str) or not AT_RE.fullmatch(v):
        return False
    try:
        t = dt.datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return False
    return FIRST_YEAR <= t.year <= LAST_YEAR


def _strs(*vals) -> bool:
    return all(isinstance(v, str) for v in vals)


def _valid(r) -> bool:
    """Shape and content of one record (strict types first; a record can come from an untrusted store)."""
    if type(r) is Decision:
        return (_strs(r.tenant_id, r.blueprint_digest, r.section, r.user_id, r.decision, r.decided_at, r.note)
                and r.section in SECTIONS and bool(DIGEST_RE.fullmatch(r.blueprint_digest))
                and bool(ID_RE.fullmatch(r.user_id)) and r.decision in DECISIONS and _ts_ok(r.decided_at)
                and len(r.note) <= NOTE_LIMIT and clean_text(r.note) == r.note
                and (r.decision == "approved" or bool(r.note)))
    if type(r) is Comment:
        return (_strs(r.tenant_id, r.blueprint_digest, r.section, r.comment_id, r.user_id, r.created_at, r.text)
                and r.section in SECTIONS and bool(DIGEST_RE.fullmatch(r.blueprint_digest))
                and bool(ID_RE.fullmatch(r.user_id)) and bool(ID_RE.fullmatch(r.comment_id))
                and _ts_ok(r.created_at) and 0 < len(r.text) <= NOTE_LIMIT and clean_text(r.text) == r.text)
    return False


def _when(r) -> str:
    t = getattr(r, "decided_at", None) or getattr(r, "created_at", None)
    return t if isinstance(t, str) and AT_RE.fullmatch(t) else ""


def _transition_ok(prev, decision) -> bool:
    """none to anything; approved to changes_requested only (a rejection beats an approval, M4); a
    changes_requested is final for that Blueprint digest."""
    return prev is None or (prev == "approved" and decision == "changes_requested")


def check_records(records, tenant_id, signable=SECTIONS) -> tuple:
    """(accepted records, quarantined count). Materialise once. Not iterable, or any record of another tenant:
    refused (the store query is wrong). A malformed record, a decision on a section that cannot be signed, a
    decision the rules would not have allowed in that order, or a repeated comment id is quarantined: skipped and
    counted, never rendered, and it does not break the view for everyone."""
    if isinstance(records, (str, bytes, dict)) or records is None:
        raise AccountantViewError("ACV-REC-001", "records")
    try:
        items = tuple(records)
    except TypeError:
        raise AccountantViewError("ACV-REC-001", "records")
    if any(type(r) in (Decision, Comment) and (not isinstance(r.tenant_id, str) or r.tenant_id != tenant_id)
           for r in items):
        raise AccountantViewError("ACV-REC-001", "record of another tenant or without a tenant")
    # Oldest first by the record's own timestamp; the store's order is the tie-break (stable sort), so what is
    # "open" never depends on the order a store happens to return rows.
    items = tuple(sorted(items, key=_when))
    out, state, ids, bad = [], {}, set(), 0
    for r in items:
        if not _valid(r):
            bad += 1
        elif isinstance(r, Decision):
            key = (r.blueprint_digest, r.section)
            if r.section not in signable or not _transition_ok(state.get(key), r.decision):
                bad += 1
            else:
                state[key] = r.decision
                out.append(r)
        elif r.comment_id in ids:
            bad += 1
        else:
            ids.add(r.comment_id)
            out.append(r)
    return tuple(out), bad


def _context(bp, records, tenant_id):
    bp = check_blueprint(bp)
    sections = build_sections(bp)
    signable = tuple(s["id"] for s in sections if s["status"] in _SIGNABLE)
    accepted, bad = check_records(records, tenant_id, signable)
    return bp, blueprint_digest(bp), accepted, bad, sections


def _section(sections, name):
    if not isinstance(name, str) or name not in SECTIONS:
        raise AccountantViewError("ACV-SO-005", "section")
    return next(s for s in sections if s["id"] == name)


def record_decision(blueprint, records, *, tenant_id, actor, section, decision, decided_at, now, note) -> tuple:
    """Return `records` plus one decision (a new tuple). Per Blueprint digest and section: the first decision is
    free, a `changes_requested` may follow an `approved`, nothing follows a `changes_requested`."""
    bp, digest, accepted, _bad, sections = _context(blueprint, records, tenant_id)
    uid = _actor(actor, tenant_id)
    sec = _section(sections, section)
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise AccountantViewError("ACV-SO-001", "decision")
    if sec["status"] not in _SIGNABLE:
        raise AccountantViewError("ACV-SO-006", "this section is not in the Blueprint; nothing to sign off")
    when = _stamp(decided_at, now)
    prev = None
    for r in accepted:
        if isinstance(r, Decision) and r.blueprint_digest == digest and r.section == section:
            prev = r.decision
    if not _transition_ok(prev, decision):
        raise AccountantViewError("ACV-SO-007", "this section already has a final decision for this Blueprint")
    text = clean_text(note)
    if len(text) > NOTE_LIMIT:
        raise AccountantViewError("ACV-SO-011", "note too long")
    if decision == "changes_requested" and not text:
        raise AccountantViewError("ACV-SO-008", "a note is required when requesting changes")
    rec = Decision(tenant_id, digest, section, uid, decision, when, text)
    if not _valid(rec):
        raise AccountantViewError("ACV-SO-001", "record")
    return tuple(records) + (rec,)


def add_comment(blueprint, records, *, tenant_id, actor, section, text, created_at, now) -> tuple:
    """Return `records` plus one comment. Comments are never edited or removed. The id `c000001`, ... is a
    per-tenant fallback; a store should assign ids itself."""
    bp, digest, accepted, _bad, sections = _context(blueprint, records, tenant_id)
    uid = _actor(actor, tenant_id)
    _section(sections, section)
    when = _stamp(created_at, now)
    body = clean_text(text)
    if not body:
        raise AccountantViewError("ACV-SO-009", "empty comment")
    if len(body) > NOTE_LIMIT:
        raise AccountantViewError("ACV-SO-011", "comment too long")
    # Highest numeric id over every stored comment, quarantined ones included, so a corrupted row never frees its id.
    seen = [int(m.group(1)) for r in (records if isinstance(records, (tuple, list)) else ())
            if type(r) is Comment and isinstance(r.comment_id, str) and (m := re.fullmatch(r"c(\d{1,12})", r.comment_id))]
    n = max(seen, default=0) + 1
    rec = Comment(tenant_id, digest, section, f"c{n:06d}", uid, when, body)
    if not _valid(rec):
        raise AccountantViewError("ACV-SO-001", "record")
    return tuple(records) + (rec,)


def build_review(blueprint, records=(), *, tenant_id) -> dict:
    """The accountant screen's data: sections plus comments and sign-off state for this exact Blueprint, and the
    stale history (earlier versions' decisions and comments, with any open change request kept visible)."""
    bp, digest, accepted, bad, base = _context(blueprint, records, tenant_id)
    cur_dec, cur_com, old_dec, old_com = {}, [], [], []
    for r in accepted:
        now_ = r.blueprint_digest == digest
        if isinstance(r, Decision):
            (cur_dec.__setitem__(r.section, r) if now_ else old_dec.append(r))
        else:
            (cur_com if now_ else old_com).append(r)
    out, open_cr = [], []
    for s in base:
        d = cur_dec.get(s["id"])
        state = "not_applicable" if s["status"] not in _SIGNABLE else (d.decision if d else "awaiting")
        if state == "approved" and bad:  # fail closed: a dropped record might have been a rejection (R1)
            state = "integrity_error"
        stale_cr = [r for r in old_dec if r.section == s["id"]]
        pending = stale_cr[-1] if (d is None and stale_cr and stale_cr[-1].decision == "changes_requested") else None
        if pending:
            open_cr.append(s["id"])
        out.append({**s, "signOff": {"state": state, "stateLabelKey": "acv.state." + state,
                                     "decision": d.public() if d else None,
                                     "openChangeRequest": pending.public(stale=True) if pending else None},
                    "comments": [c.public() for c in cur_com if c.section == s["id"]]})
    signable = [s for s in out if s["signOff"]["state"] != "not_applicable"]
    not_reviewed = [s["id"] for s in out if s["signOff"]["state"] == "not_applicable"]
    states = [s["signOff"]["state"] for s in signable]
    if "changes_requested" in states:
        overall = "changes_requested"
    elif bad:
        overall = "integrity_error"
    elif states and all(x == "approved" for x in states):
        overall = "approved_signable_only" if not_reviewed else "approved"
    else:
        overall = "awaiting"
    return {"schema": "accountant_view/1", "version": VIEW_VERSION, "titleKey": "acv.title",
            "noticeKey": "acv.notice.read_only", "evidenceNoticeKey": "acv.notice.evidence_only",
            "tenantId": tenant_id, "blueprintId": bp["meta"]["id"], "revision": bp["meta"]["revision"],
            "buildState": bp["meta"]["buildState"], "blueprintDigest": digest, "sections": out,
            "history": {"decisions": [r.public(stale=True) for r in old_dec],
                        "comments": [r.public(stale=True) for r in old_com]},
            "overall": {"state": overall, "labelKey": "acv.state." + overall, "evidenceOnly": True,
                        "notReviewed": not_reviewed, "openChangeRequests": open_cr,
                        "staleRecords": len(old_dec) + len(old_com), "quarantined": bad}}
