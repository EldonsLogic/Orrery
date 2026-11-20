"""Human review queue and the `team_reviewed` gate evidence (PLT-013). Tier 3: approval authority.

What it is. A queue of items awaiting a verified staff human: a Blueprint draft, a component request, simulation
sign-off evidence. A reviewer claims an item (a lock that expires), fills the checklist and records one decision:
approved, changes_requested or rejected. Agents propose, humans decide (ADR-0048, ADR-0027): nothing here approves
for anyone, and the output (`gate_evidence`) is EVIDENCE for BPL-020. It never promotes a build; BPL-020 applies its
own policy, re-reads the stored content itself and must not trust `eligible` alone.

How it stays honest.
- Each item is an append-only log of events. State is never stored: it is folded from the log on every read, so a
  stored verdict, status or claim is never trusted. Every event carries a whole-record HMAC (a key derived per purpose,
  its key id inside the seal) chained to the previous seal, so editing, dropping, reordering or moving an event to
  another item or tenant fails closed (RQ-011). No key, no queue (RQ-012): there is no unsealed or sha256 fallback.
- Reviewers are verified staff-realm claims from the identity service (live token, active staff identity, current
  session version, MFA, a fresh MFA step-up to claim and decide) with the role `team_reviewer` from an injected
  resolver. Anything unexpected denies. The reviewer must not be the author or anyone listed in `involved` (requester,
  attester, signer), nor a staff member linked to one of them.
- A decision binds the item's content digest. The host passes the content it loaded from its own store, never the
  caller's; if it no longer matches, the decision is refused and an old approval reads as stale.
- Time is the caller's but bounded: whole seconds, inside a fixed window and within MAX_SKEW of the identity clock;
  an event may not be older than the one before it. Claims expire. Checklists are data (checklists.json).
- Items hold ids, digests and flags only, never the content. Audit lines carry the note's hash and length, never text.
- `hold` (quarantine) is sealed into the item and bars approval; only a resubmission with new content lifts it.

Trust assumptions (Q-440 to Q-446): the host vouches for `submit` and `resubmit` (it is not a reviewer act), the
integrity key custody, and a real store must enforce a unique key on (item_id, seq) so a race cannot store two events.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

from .canon import DIGEST_RE, content_digest, id_list, ident, note_text, tenant as _tenant_id
from .errors import ReviewError

from identity import IdentityError, Realm  # services/control-plane is on sys.path
from identity.audit import ALLOW, DENY
from identity.tokens import check_live

KINDS = ("blueprint_draft", "component_request", "simulation_signoff")
DECISIONS = ("approved", "changes_requested", "rejected")
STATES = ("pending", "claimed", "approved", "changes_requested", "rejected")
REVIEWER_ROLE = "team_reviewer"
MAX_SKEW = 300
EARLIEST, LATEST = 1_577_836_800, 4_102_444_800  # 2020-01-01 .. 2100-01-01
MIN_CLAIM, MAX_CLAIM, DEFAULT_CLAIM = 60, 86_400, 1_800
_HERE = Path(__file__).parent
_CHECKLISTS = json.loads((_HERE / "checklists.json").read_text(encoding="utf-8"))
_LABELS = json.loads((_HERE / "labels.json").read_text(encoding="utf-8"))
_EVENT_KEYS = {"schema", "item_id", "tenant_id", "seq", "prev", "type", "at", "actor", "data", "key_id", "seal"}
_DATA_KEYS = {
    "submitted": {"kind", "subject_ref", "revision", "content_digest", "hold", "involved", "author", "checklist_version"},
    "claimed": {"expires_at"}, "released": set(),
    "decided": {"revision", "content_digest", "decision", "checklist", "note", "note_sha256", "note_len"},
    "resubmitted": {"revision", "content_digest", "hold", "involved"},
}


def checklist_ids(kind: str) -> tuple:
    return tuple(_CHECKLISTS["kinds"][kind])


def label(key: str, lang: str) -> str:
    return _LABELS[lang][key]


def label_keys() -> set:
    """Every key the screens use; tests check both languages carry all of them."""
    keys = {f"review.kind.{k}" for k in KINDS} | {f"review.state.{s}" for s in STATES} | {f"review.decision.{d}" for d in DECISIONS}
    keys |= {f"review.item.{i}" for k in KINDS for i in checklist_ids(k)}
    return keys | {"review.title", "review.action.claim", "review.action.release", "review.check.pass", "review.check.fail",
                   "review.note", "review.stale_notice", "review.hold_notice", "review.evidence_notice"}


@dataclass
class _Item:
    id: str
    tenant: str
    kind: str
    subject_ref: str
    author: str
    involved: tuple
    revision: int
    digest: str
    hold: bool
    status: str            # "pending" | "claimed" | "approved" | "changes_requested" | "rejected" (claimed may have lapsed)
    claim: tuple | None    # (holder, expires_at)
    decisions: list
    last_at: int
    created: int


class ReviewQueue:
    def __init__(self, identity, roles, *, integrity_key: bytes | None = None, integrity_keys: dict | None = None,
                 key_id: str | None = None, claim_ttl: int = DEFAULT_CLAIM):
        keys = {**({"k1": integrity_key} if integrity_key is not None else {}), **(integrity_keys or {})}
        if not keys or any(type(k) is not bytes or len(k) < 32 for k in keys.values()):
            raise ReviewError("RQ-012")
        self._active = key_id or list(keys)[-1]
        if self._active not in keys or type(claim_ttl) is not int or not MIN_CLAIM <= claim_ttl <= MAX_CLAIM:
            raise ReviewError("RQ-012")
        self._keys, self._idn, self._roles, self._ttl = keys, identity, roles, claim_ttl
        self._logs: dict[str, list] = {}
        self._order = 0  # only names new item ids; never trusted for state

    # ----- sealing -------------------------------------------------------------------------------------------
    def _key(self, kid) -> bytes | None:
        master = self._keys.get(kid) if type(kid) is str else None
        return hmac.new(master, b"review-event-seal", hashlib.sha256).digest() if master else None

    def _mac(self, ev: dict) -> str:
        key = self._key(ev.get("key_id"))
        if key is None:
            raise ReviewError("RQ-011", "key")
        body = json.dumps({k: v for k, v in ev.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _append(self, item_id, tenant_id, typ, at, actor, data) -> None:
        log = self._logs.setdefault(item_id, [])
        ev = {"schema": "1", "item_id": item_id, "tenant_id": tenant_id, "seq": len(log) + 1,
              "prev": log[-1]["seal"] if log else "", "type": typ, "at": at, "actor": actor, "data": data, "key_id": self._active}
        ev["seal"] = self._mac(ev)
        log.append(ev)

    # ----- reading: every read folds the log and re-validates it ----------------------------------------------
    def _fold(self, item_id, tenant_id=None) -> _Item:
        log = self._logs.get(item_id) if type(item_id) is str else None
        if not log:
            raise ReviewError("RQ-004")
        it, prev, last = None, "", 0
        try:
            for i, ev in enumerate(log, 1):
                if type(ev) is not dict or set(ev) != _EVENT_KEYS or ev["schema"] != "1" or ev["item_id"] != item_id \
                        or ev["seq"] != i or ev["prev"] != prev or type(ev["at"]) is not int or ev["at"] < last \
                        or type(ev["data"]) is not dict or ev["type"] not in _DATA_KEYS or set(ev["data"]) != _DATA_KEYS[ev["type"]] \
                        or type(ev["seal"]) is not str or not hmac.compare_digest(ev["seal"], self._mac(ev)):
                    raise ReviewError("RQ-011", "event")
                if (it is None) != (i == 1) or (it is not None and ev["tenant_id"] != it.tenant):
                    raise ReviewError("RQ-011", "chain")
                it = self._apply(it, ev, item_id)
                prev, last = ev["seal"], ev["at"]
        except ReviewError as e:
            if e.code == "RQ-011":
                raise
            raise ReviewError("RQ-011", e.detail or e.code) from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ReviewError("RQ-011", "shape") from None
        it.last_at = last
        if tenant_id is not None and it.tenant != tenant_id:
            raise ReviewError("RQ-004")  # another tenant's item is indistinguishable from a missing one
        return it

    def _apply(self, it, ev, item_id) -> _Item:
        d, typ, at, actor = ev["data"], ev["type"], ev["at"], ev["actor"]
        bad = ReviewError("RQ-011", typ)
        if typ == "submitted":
            if it is not None or d["kind"] not in KINDS or d["revision"] != 1 or d["checklist_version"] != _CHECKLISTS["version"] \
                    or type(d["hold"]) is not bool or not DIGEST_RE.fullmatch(str(d["content_digest"])):
                raise bad
            _tenant_id(ev["tenant_id"]); ident(d["subject_ref"]); ident(d["author"])
            involved = id_list(list(d["involved"]), "involved")
            if actor != d["author"]:
                raise bad
            return _Item(item_id, ev["tenant_id"], d["kind"], d["subject_ref"], d["author"], involved, 1, d["content_digest"],
                         d["hold"], "pending", None, [], at, at)
        if it is None:
            raise bad
        live = it.status == "claimed" and it.claim is not None and it.claim[1] > at
        if typ == "claimed":
            ident(actor)
            if it.status not in ("pending", "claimed") or live or type(d["expires_at"]) is not int or not MIN_CLAIM <= d["expires_at"] - at <= MAX_CLAIM or self._conflict(it, actor):
                raise bad
            it.status, it.claim = "claimed", (actor, d["expires_at"])
        elif typ == "released":
            if not live or it.claim[0] != actor:
                raise bad
            it.status, it.claim = "pending", None
        elif typ == "decided":
            if not live or it.claim[0] != actor or self._conflict(it, actor) or d["revision"] != it.revision \
                    or d["content_digest"] != it.digest or d["decision"] not in DECISIONS or type(d["note"]) is not str \
                    or note_text(d["note"]) != d["note"] or d["note_len"] != len(d["note"]) \
                    or d["note_sha256"] != hashlib.sha256(d["note"].encode("utf-8")).hexdigest():
                raise bad
            ids, cl = checklist_ids(it.kind), d["checklist"]
            if type(cl) is not dict or set(cl) != set(ids) or any(v not in ("pass", "fail") for v in cl.values()):
                raise bad
            if d["decision"] == "approved" and (it.hold or any(v != "pass" for v in cl.values())):
                raise bad
            if d["decision"] != "approved" and not d["note"]:
                raise bad
            it.decisions.append({"reviewer": actor, "decision": d["decision"], "decidedAt": at, "revision": it.revision,
                                 "contentDigest": it.digest, "checklist": dict(cl), "note": d["note"],
                                 "noteSha256": d["note_sha256"], "noteLength": d["note_len"]})
            it.status, it.claim = d["decision"], None
        elif typ == "resubmitted":
            if it.status != "changes_requested" or actor != it.author or d["revision"] != it.revision + 1 \
                    or d["content_digest"] == it.digest or type(d["hold"]) is not bool or not DIGEST_RE.fullmatch(str(d["content_digest"])):
                raise bad
            it.involved = id_list(list(d["involved"]), "involved")
            it.revision, it.digest, it.hold, it.status, it.claim = d["revision"], d["content_digest"], d["hold"], "pending", None
        return it

    @staticmethod
    def _conflict(it, subject, linked=frozenset()) -> bool:
        return subject == it.author or subject in it.involved or bool(set(linked) & ({it.author} | set(it.involved)))

    def _state(self, it, now) -> str:
        if it.status == "claimed" and (it.claim is None or it.claim[1] <= now):
            return "pending"
        return it.status

    def _view(self, it, now) -> dict:
        state = self._state(it, now)
        return {"itemId": it.id, "tenantId": it.tenant, "kind": it.kind, "subjectRef": it.subject_ref, "revision": it.revision,
                "contentDigest": it.digest, "state": state, "hold": it.hold,
                "claim": ({"by": it.claim[0], "expiresAt": it.claim[1]} if state == "claimed" else None),
                "checklist": [{"id": i, "labelKey": f"review.item.{i}"} for i in checklist_ids(it.kind)],
                "decisions": copy.deepcopy(it.decisions), "labelKeys": {"kind": f"review.kind.{it.kind}", "state": f"review.state.{state}"}}

    # ----- caller checks --------------------------------------------------------------------------------------
    def _now(self, now) -> int:
        try:
            host = self._idn.now()
        except IdentityError:
            raise ReviewError("RQ-002", "host_clock") from None
        if type(now) is not int or not EARLIEST <= now <= LATEST or abs(now - host) > MAX_SKEW:
            raise ReviewError("RQ-002")
        return now

    def _reviewer(self, claims, now, step_up):
        """-> (subject, linked person ids). Fails closed on anything unexpected."""
        try:
            check_live(claims, self._idn.now())
            if claims.realm is not Realm.STAFF or claims.tenant is not None or claims.mfa_satisfied is not True:
                raise ReviewError("RQ-003", "realm")
            staff = self._idn.repo.get_staff(claims.subject)
            if staff is None or not staff.active or staff.session_version != claims.session_version:
                raise ReviewError("RQ-003", "staff")
            if step_up:
                self._idn.require_step_up(claims)
            roles = self._roles.roles_for(claims.subject)
        except IdentityError as e:
            raise ReviewError("RQ-003", e.code) from None
        except ReviewError:
            raise
        except Exception:
            raise ReviewError("RQ-003", "resolver") from None
        if type(roles) not in (tuple, list, frozenset) or REVIEWER_ROLE not in roles or not all(type(r) is str for r in roles):
            raise ReviewError("RQ-003", "role")
        return ident(claims.subject), frozenset(staff.linked_person_ids) | {claims.subject}

    def _audit(self, action, code, subject, tenant_id, detail):
        try:
            self._idn.audit.record(at=self._idn.clock(), action=action, decision=ALLOW if code == "OK" else DENY, code=code,
                                   realm="staff", subject=subject, tenant=tenant_id, detail=detail)
        except Exception:  # an audit failure must not turn a refusal into an allow; the action already ran or raised
            pass

    def _run(self, action, tenant_id, item_id, claims, fn):
        subject, extra = None, ""
        try:
            subject = getattr(claims, "subject", None) if claims is not None else None
            out, extra = fn()
        except ReviewError as e:
            self._audit(f"review.{action}", e.code, subject, tenant_id if isinstance(tenant_id, str) else None,
                        f"item={item_id if isinstance(item_id, str) else '-'} why={e.detail}"[:200])
            raise
        self._audit(f"review.{action}", "OK", subject, tenant_id, f"item={item_id} {extra}"[:200])
        return out

    # ----- host-side intake (not a reviewer act) --------------------------------------------------------------
    def submit(self, *, tenant_id, kind, subject_ref, content, author, involved, now, hold=False) -> str:
        """Open a review. `author` and `involved` (requester, attesters, signers) are ids the host vouches for; the
        content is digested, not stored. One open item per (tenant, kind, subject_ref)."""
        def go():
            t, at = _tenant_id(tenant_id), self._now(now)
            if kind not in KINDS or type(hold) is not bool:
                raise ReviewError("RQ-001", "kind")
            ref, who, inv = ident(subject_ref), ident(author, "author"), id_list(involved, "involved")
            digest = content_digest(content)
            tenant_state = self._idn.repo.get_tenant(t)
            if tenant_state is None or tenant_state.status.value not in ("trial", "active"):
                raise ReviewError("RQ-001", "tenant")
            if self._open(t, kind, ref, at) is not None:
                raise ReviewError("RQ-013")
            self._order += 1
            iid = f"rq-{self._order:06d}-{hashlib.sha256(f'{t}|{kind}|{ref}|{self._order}'.encode()).hexdigest()[:10]}"
            self._append(iid, t, "submitted", at, who, {"kind": kind, "subject_ref": ref, "revision": 1, "content_digest": digest,
                                                         "hold": hold, "involved": list(inv), "author": who,
                                                         "checklist_version": _CHECKLISTS["version"]})
            return iid, f"rev=1 digest={digest[:12]}"
        return self._run("submit", tenant_id, None, None, go)

    def resubmit(self, *, tenant_id, item_id, content, author, involved, now, hold=False) -> int:
        """The author answers `changes_requested` with new content (a new revision, back to pending, hold re-stated)."""
        def go():
            t, at = _tenant_id(tenant_id), self._now(now)
            it = self._fold(item_id, t)
            if it.status != "changes_requested" or type(hold) is not bool:
                raise ReviewError("RQ-005")
            if ident(author, "author") != it.author:
                raise ReviewError("RQ-003", "author")
            inv, digest = id_list(involved, "involved"), content_digest(content)
            if digest == it.digest or at < it.last_at:
                raise ReviewError("RQ-001", "unchanged")
            self._append(item_id, t, "resubmitted", at, it.author, {"revision": it.revision + 1, "content_digest": digest,
                                                                     "hold": hold, "involved": list(inv)})
            return it.revision + 1, f"rev={it.revision + 1} digest={digest[:12]}"
        return self._run("resubmit", tenant_id, item_id, None, go)

    def _items(self, t):
        """Folded items of one tenant. A broken log that claims this tenant raises (fail closed); others are skipped."""
        for iid in sorted(self._logs):
            try:
                yield self._fold(iid, t)
            except ReviewError as e:
                first = self._logs[iid][0] if self._logs[iid] and type(self._logs[iid][0]) is dict else {}
                if e.code == "RQ-011" and first.get("tenant_id") == t:
                    raise

    def _open(self, t, kind, ref, now):
        for it in self._items(t):
            if it.kind == kind and it.subject_ref == ref and it.status not in ("approved", "rejected"):
                return it
        return None

    # ----- reviewer acts --------------------------------------------------------------------------------------
    def claim(self, claims, *, tenant_id, item_id, now) -> dict:
        def go():
            t, at = _tenant_id(tenant_id), self._now(now)
            who, linked = self._reviewer(claims, at, step_up=True)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._conflict(it, who, linked):
                raise ReviewError("RQ-007")
            if self._state(it, at) != "pending":
                raise ReviewError("RQ-005")
            self._append(item_id, t, "claimed", at, who, {"expires_at": at + self._ttl})
            return self._view(self._fold(item_id, t), at), f"until={at + self._ttl}"
        return self._run("claim", tenant_id, item_id, claims, go)

    def release(self, claims, *, tenant_id, item_id, now) -> dict:
        def go():
            t, at = _tenant_id(tenant_id), self._now(now)
            who, _ = self._reviewer(claims, at, step_up=False)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._state(it, at) != "claimed" or it.claim[0] != who:
                raise ReviewError("RQ-006")
            self._append(item_id, t, "released", at, who, {})
            return self._view(self._fold(item_id, t), at), ""
        return self._run("release", tenant_id, item_id, claims, go)

    def decide(self, claims, *, tenant_id, item_id, decision, checklist, note, current_content, now) -> dict:
        """Record one decision on the claimed item. `current_content` is what the host loaded from its own store."""
        def go():
            t, at = _tenant_id(tenant_id), self._now(now)
            who, linked = self._reviewer(claims, at, step_up=True)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._conflict(it, who, linked):
                raise ReviewError("RQ-007")
            if self._state(it, at) != "claimed" or it.claim[0] != who:
                raise ReviewError("RQ-006")
            if decision not in DECISIONS or type(decision) is not str:
                raise ReviewError("RQ-001", "decision")
            if content_digest(current_content) != it.digest:
                raise ReviewError("RQ-008")
            ids = checklist_ids(it.kind)
            if type(checklist) is not dict or set(checklist) != set(ids) or any(v not in ("pass", "fail") or type(v) is not str for v in checklist.values()):
                raise ReviewError("RQ-009", "shape")
            text = note_text(note)
            if decision == "approved":
                if it.hold:
                    raise ReviewError("RQ-010")
                if any(v != "pass" for v in checklist.values()):
                    raise ReviewError("RQ-009", "failed_check")
            elif not text:
                raise ReviewError("RQ-014", "required")
            nh = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self._append(item_id, t, "decided", at, who, {"revision": it.revision, "content_digest": it.digest, "decision": decision,
                                                           "checklist": {k: checklist[k] for k in sorted(checklist)}, "note": text,
                                                           "note_sha256": nh, "note_len": len(text)})
            return self._view(self._fold(item_id, t), at), f"{decision} rev={it.revision} note_sha256={nh[:16]} note_len={len(text)}"
        return self._run("decide", tenant_id, item_id, claims, go)

    # ----- reads ----------------------------------------------------------------------------------------------
    def get(self, *, tenant_id, item_id, now) -> dict:
        t, at = _tenant_id(tenant_id), self._now(now)
        return self._view(self._fold(item_id, t), at)

    def list_items(self, claims, *, now, tenant_id=None, state=None) -> list:
        """Metadata of valid items for a verified reviewer (no content exists here). Broken logs are skipped and
        reported by `invalid()`; a state filter keeps lapsed claims under `pending`."""
        at = self._now(now)
        self._reviewer(claims, at, step_up=False)
        if tenant_id is not None:
            _tenant_id(tenant_id)
        if state is not None and state not in STATES:
            raise ReviewError("RQ-001", "state")
        out = []
        for iid in sorted(self._logs):
            try:
                it = self._fold(iid, tenant_id)
            except ReviewError:
                continue
            v = self._view(it, at)
            if state in (None, v["state"]):
                out.append(v)
        return out

    def invalid(self) -> list:
        bad = []
        for iid in sorted(self._logs):
            try:
                self._fold(iid)
            except ReviewError as e:
                bad.append((iid, e.code))
        return bad

    # ----- the gate output: evidence only ---------------------------------------------------------------------
    def gate_evidence(self, *, tenant_id, item_id, current_content, now) -> dict:
        """What BPL-020 may read for one item. Recomputed from the sealed log and the host's current content; fresh
        means the approved digest equals the digest of that content. Never an instruction to promote."""
        t, at = _tenant_id(tenant_id), self._now(now)
        it = self._fold(item_id, t)
        fresh = content_digest(current_content) == it.digest
        approved = it.status == "approved" and not it.hold
        last = it.decisions[-1] if it.decisions else None
        return {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": it.tenant, "itemId": it.id,
                "kind": it.kind, "subjectRef": it.subject_ref, "revision": it.revision, "contentDigest": it.digest,
                "state": self._state(it, at), "stale": not fresh, "eligible": bool(approved and fresh),
                "approvedBy": last["reviewer"] if approved and last else None,
                "decidedAt": last["decidedAt"] if approved and last else None,
                "checklist": last["checklist"] if approved and last else None}

    def team_reviewed_evidence(self, *, tenant_id, subject_ref, required: dict, now) -> dict:
        """Evidence for one subject across kinds: `required` maps kind -> the host's current content. The Blueprint
        draft is always required. The newest item per kind counts; a missing, open, rejected or stale item blocks."""
        t, at = _tenant_id(tenant_id), self._now(now)
        ref = ident(subject_ref)
        if type(required) is not dict or "blueprint_draft" not in required or any(k not in KINDS for k in required):
            raise ReviewError("RQ-001", "required")
        parts, missing = {}, []
        mine = [it for it in self._items(t) if it.subject_ref == ref]
        for kind in sorted(required):
            digest = content_digest(required[kind])
            best = max((it for it in mine if it.kind == kind), key=lambda it: (it.created, it.id), default=None)
            if best is None:
                missing.append(kind)
                continue
            parts[kind] = {"itemId": best.id, "state": self._state(best, at), "stale": digest != best.digest,
                           "eligible": best.status == "approved" and not best.hold and digest == best.digest}
        return {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": t, "subjectRef": ref,
                "items": parts, "missing": missing,
                "eligible": not missing and all(p["eligible"] for p in parts.values())}
