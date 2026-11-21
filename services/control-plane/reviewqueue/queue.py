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
  another item or tenant fails closed (RQ-011). Tail cuts and deleted items are caught by two sealed anchors kept
  outside the logs and written in the same step as every append: a per-item head (seq and head seal) and a queue
  manifest (every item id with tenant, seq and head, plus a global counter). Every read checks both: a shorter log, a
  missing item or a rolled-back log is RQ-011 (no approval, no evidence). Rolling back logs, heads and manifest
  together needs an external anchor (Q-481). No key, no queue (RQ-012): there is no unsealed or sha256 fallback.
- Reviewers are verified staff-realm claims from the identity service (live token, active staff identity, current
  session version, MFA, a fresh MFA step-up to claim and decide) with the role `team_reviewer` from an injected
  resolver. Anything unexpected denies. A step-up is consumed by one decision. The reviewer must not be the author or
  anyone in `involved` (requester, attester, signer, and the staff accounts the host says are linked to the author),
  nor a staff member linked to a customer person in it. `involved` only grows (resubmission unions); component
  requests and sign-offs need it non-empty; `linked_staff` is a required host input.
- A decision binds the item's content digest. The host passes the content it loaded from its own store, never the
  caller's; if it no longer matches, the decision is refused and an old approval reads as stale.
- Time is the identity (host) clock only, never the caller's: whole seconds inside a fixed window; an act older than
  the item's last event is refused (RQ-002). Claims expire. Checklists are data (checklists.json).
- Items hold ids, digests and flags only, never the content. Audit lines carry the note's hash and length, never text.
- `hold` (quarantine) can be set at submit or later by a verified staff principal (`hold_item`, any state); it bars
  approval and makes evidence ineligible. A resubmission never lifts it: only an explicit `clear_hold` by a verified
  staff human other than the author and the involved ids does, audited.
- Consumers (BPL-020, DSC-009) call `verify_evidence` (or `team_reviewed_evidence`) with a service principal; the queue
  re-derives everything from its sealed log and anchors and says whether a pinned (`seq`, `headSeal`) is still current.
  No API accepts an evidence object as authority.

Trust assumptions (Q-440 to Q-446, Q-480 to Q-486): the host vouches for `submit`, `resubmit` and `hold_item` (not reviewer
acts), the integrity key custody, and a real store must write the event, the head and the manifest in ONE atomic
transaction with a unique key on (item_id, seq) (Q-441); this in-memory store does it by assigning all three together.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
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
HOLD_REASONS = ("injection", "scan", "compliance", "other")
NEEDS_INVOLVED = ("component_request", "simulation_signoff")
REVIEWER_ROLE = "team_reviewer"
READER_ROLES = frozenset({"team_reviewer", "evidence_reader"})   # evidence_reader: proposed service role for BPL-020 and DSC-009 (Q-490)
HOLD_ROLES = frozenset({"team_reviewer", "hold_issuer"})         # hold_issuer: proposed service role for scanners (Q-490)
EARLIEST, LATEST = 1_577_836_800, 4_102_444_800  # 2020-01-01 .. 2100-01-01
MIN_CLAIM, MAX_CLAIM, DEFAULT_CLAIM = 60, 86_400, 1_800
_HERE = Path(__file__).parent
_CHECKLISTS = json.loads((_HERE / "checklists.json").read_text(encoding="utf-8"))
_LABELS = json.loads((_HERE / "labels.json").read_text(encoding="utf-8"))
_EVENT_KEYS = {"schema", "item_id", "tenant_id", "seq", "prev", "type", "at", "actor", "data", "key_id", "seal"}
_DATA_KEYS = {
    "submitted": {"kind", "subject_ref", "revision", "content_digest", "hold", "involved", "author", "checklist_version", "seq_no"},
    "held": {"reason"}, "hold_cleared": set(),
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
                   "review.state.invalid", "review.note", "review.stale_notice", "review.hold_notice", "review.evidence_notice"}


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
    created: int          # the sealed global submission number (never caller time)
    head_seq: int = 0
    head_seal: str = ""


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
        self._heads: dict[str, dict] = {}   # sealed per-item head: (seq, head seal), outside the log
        self._used_stepups: dict = {}       # (subject, auth_time) -> item id; a step-up decides once (volatile, Q-483)
        self._manifest = self._seal({"schema": "1", "n": 0, "items": []}, b"review-manifest-seal")

    # ----- sealing -------------------------------------------------------------------------------------------
    def _key(self, kid, purpose) -> bytes | None:
        master = self._keys.get(kid) if type(kid) is str else None
        return hmac.new(master, purpose, hashlib.sha256).digest() if master else None

    def _mac(self, rec: dict, purpose=b"review-event-seal") -> str:
        key = self._key(rec.get("key_id"), purpose)
        if key is None:
            raise ReviewError("RQ-011", "key")
        body = json.dumps({k: v for k, v in rec.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _seal(self, rec: dict, purpose) -> dict:
        rec = {**rec, "key_id": self._active}
        rec["seal"] = self._mac(rec, purpose)
        return rec

    def _manifest_map(self) -> dict:
        """item_id -> (tenant, seq, head seal), from the sealed manifest; anything wrong is RQ-011."""
        m = self._manifest
        try:
            if type(m) is not dict or set(m) != {"schema", "n", "items", "key_id", "seal"} or m["schema"] != "1" \
                    or type(m["n"]) is not int or type(m["seal"]) is not str \
                    or not hmac.compare_digest(m["seal"], self._mac(m, b"review-manifest-seal")):
                raise ReviewError("RQ-011", "manifest")
            out = {}
            for row in m["items"]:
                iid, ten, seq, hd = row
                if iid in out or type(seq) is not int:
                    raise ReviewError("RQ-011", "manifest")
                out[iid] = (ten, seq, hd)
            return out
        except ReviewError:
            raise
        except Exception:
            raise ReviewError("RQ-011", "manifest") from None

    def _append(self, item_id, tenant_id, typ, at, actor, data) -> None:
        """Event, head and manifest are built first and then assigned together (a real store: one transaction)."""
        mf = self._manifest_map()
        log = self._logs.get(item_id, [])
        if (item_id in mf) != bool(log):
            raise ReviewError("RQ-011", "anchor")
        ev = {"schema": "1", "item_id": item_id, "tenant_id": tenant_id, "seq": len(log) + 1,
              "prev": log[-1]["seal"] if log else "", "type": typ, "at": at, "actor": actor, "data": data, "key_id": self._active}
        ev["seal"] = self._mac(ev)
        mf[item_id] = (tenant_id, ev["seq"], ev["seal"])
        head = self._seal({"item_id": item_id, "tenant_id": tenant_id, "seq": ev["seq"], "head": ev["seal"]}, b"review-head-seal")
        manifest = self._seal({"schema": "1", "n": self._manifest["n"] + 1,
                               "items": [[k, *mf[k]] for k in sorted(mf)]}, b"review-manifest-seal")
        self._logs[item_id] = log + [ev]
        self._heads[item_id] = head
        self._manifest = manifest

    # ----- reading: every read folds the log and re-validates it and its anchors ------------------------------
    def _fold(self, item_id, tenant_id=None) -> _Item:
        mf = self._manifest_map()
        entry = mf.get(item_id) if type(item_id) is str else None
        if entry is None:
            if type(item_id) is str and self._logs.get(item_id):
                raise ReviewError("RQ-011", "unanchored")  # a log the manifest never saw
            raise ReviewError("RQ-004")
        if tenant_id is not None and entry[0] != tenant_id:
            raise ReviewError("RQ-004")  # another tenant's item is indistinguishable from a missing one
        log = self._logs.get(item_id)
        if not log:
            raise ReviewError("RQ-011", "deleted")
        head = self._heads.get(item_id)
        try:
            if type(head) is not dict or set(head) != {"item_id", "tenant_id", "seq", "head", "key_id", "seal"} \
                    or not hmac.compare_digest(str(head["seal"]), self._mac(head, b"review-head-seal")) \
                    or head["item_id"] != item_id or head["seq"] != len(log) or head["head"] != log[-1].get("seal") \
                    or entry != (head["tenant_id"], len(log), log[-1].get("seal")):
                raise ReviewError("RQ-011", "head")
        except ReviewError:
            raise
        except Exception:
            raise ReviewError("RQ-011", "head") from None
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
        it.last_at, it.head_seq, it.head_seal = last, len(log), prev
        return it

    def _apply(self, it, ev, item_id) -> _Item:
        d, typ, at, actor = ev["data"], ev["type"], ev["at"], ev["actor"]
        bad = ReviewError("RQ-011", typ)
        if typ == "submitted":
            if it is not None or d["kind"] not in KINDS or d["revision"] != 1 or d["checklist_version"] != _CHECKLISTS["version"] \
                    or type(d["hold"]) is not bool or not DIGEST_RE.fullmatch(str(d["content_digest"])) \
                    or type(d["seq_no"]) is not int or d["seq_no"] < 1:
                raise bad
            _tenant_id(ev["tenant_id"]); ident(d["subject_ref"]); ident(d["author"])
            involved = id_list(list(d["involved"]), "involved")
            if actor != d["author"] or (d["kind"] in NEEDS_INVOLVED and not involved):
                raise bad
            return _Item(item_id, ev["tenant_id"], d["kind"], d["subject_ref"], d["author"], involved, 1, d["content_digest"],
                         d["hold"], "pending", None, [], at, d["seq_no"])
        if it is None:
            raise bad
        live = it.status == "claimed" and it.claim is not None and it.claim[1] > at
        if typ == "held":
            if d["reason"] not in HOLD_REASONS or it.hold:
                raise bad
            ident(actor)
            it.hold = True
        elif typ == "hold_cleared":
            ident(actor)
            if not it.hold or self._conflict(it, actor):
                raise bad
            it.hold = False
        elif typ == "claimed":
            ident(actor)
            if it.status not in ("pending", "claimed") or live or type(d["expires_at"]) is not int \
                    or not MIN_CLAIM <= d["expires_at"] - at <= MAX_CLAIM or self._conflict(it, actor):
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
            if not (it.status == "changes_requested" or (it.hold and it.status in ("pending", "claimed", "approved"))) \
                    or actor != it.author or d["revision"] != it.revision + 1 \
                    or d["content_digest"] == it.digest or d["hold"] is not it.hold or not DIGEST_RE.fullmatch(str(d["content_digest"])):
                raise bad
            added = id_list(list(d["involved"]), "involved")
            if not set(it.involved) <= set(added):  # the stored list is already the union: it may only grow
                raise bad
            it.involved = added
            it.revision, it.digest, it.status, it.claim = d["revision"], d["content_digest"], "pending", None
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
                "contentDigest": it.digest, "state": state, "hold": it.hold, "seq": it.head_seq, "headSeal": it.head_seal,
                "claim": ({"by": it.claim[0], "expiresAt": it.claim[1]} if state == "claimed" else None),
                "checklist": [{"id": i, "labelKey": f"review.item.{i}"} for i in checklist_ids(it.kind)],
                "decisions": copy.deepcopy(it.decisions), "labelKeys": {"kind": f"review.kind.{it.kind}", "state": f"review.state.{state}"}}

    # ----- caller checks --------------------------------------------------------------------------------------
    def _now(self) -> int:
        """The identity (host) clock; a bad reading fails this call closed."""
        try:
            host = self._idn.now()
        except Exception:
            raise ReviewError("RQ-002", "host_clock") from None
        if type(host) is not int or not EARLIEST <= host <= LATEST:
            raise ReviewError("RQ-002")
        return host

    def _reviewer(self, claims, step_up, roles_ok=frozenset({REVIEWER_ROLE})):
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
            linked = frozenset(staff.linked_person_ids) | {claims.subject}
        except IdentityError as e:
            raise ReviewError("RQ-003", e.code) from None
        except ReviewError:
            raise
        except Exception:
            raise ReviewError("RQ-003", "resolver") from None
        if type(roles) not in (tuple, list, frozenset) or not all(type(r) is str for r in roles) or not set(roles) & roles_ok:
            raise ReviewError("RQ-003", "role")
        return ident(claims.subject), linked

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
        except Exception:  # never let a raw error escape unaudited and untyped
            self._audit(f"review.{action}", "RQ-001", subject, tenant_id if isinstance(tenant_id, str) else None,
                        f"item={item_id if isinstance(item_id, str) else '-'} why=unexpected"[:200])
            raise ReviewError("RQ-001", "unexpected") from None
        self._audit(f"review.{action}", "OK", subject, tenant_id, f"item={item_id} {extra}"[:200])
        return out

    # ----- host-side intake (not a reviewer act) --------------------------------------------------------------
    def submit(self, *, tenant_id, kind, subject_ref, content, author, involved, linked_staff, hold=False) -> str:
        """Open a review. `author`, `involved` (requester, attesters, signers) and `linked_staff` (staff accounts of
        the same human as the author; required, an empty list means the host asserts none) are ids the host vouches
        for. Component requests and sign-offs need a non-empty `involved`. The content is digested, not stored."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            if kind not in KINDS or type(hold) is not bool:
                raise ReviewError("RQ-001", "kind")
            ref, who = ident(subject_ref), ident(author, "author")
            inv = id_list([*self._seq(involved, "involved"), *self._seq(linked_staff, "linked_staff")], "involved")
            if kind in NEEDS_INVOLVED and not id_list(self._seq(involved, "involved"), "involved"):
                raise ReviewError("RQ-001", "involved_required")
            digest = content_digest(content)
            tenant_state = self._idn.repo.get_tenant(t)
            if tenant_state is None or tenant_state.status.value not in ("trial", "active"):
                raise ReviewError("RQ-001", "tenant")
            if self._open(t, kind, ref) is not None:
                raise ReviewError("RQ-013")
            mf = self._manifest_map()
            iid = "rq-" + secrets.token_hex(16)
            if iid in mf or iid in self._logs:
                raise ReviewError("RQ-011", "id_collision")
            self._append(iid, t, "submitted", at, who, {"kind": kind, "subject_ref": ref, "revision": 1, "content_digest": digest,
                                                         "hold": hold, "involved": list(inv), "author": who,
                                                         "checklist_version": _CHECKLISTS["version"],
                                                         "seq_no": self._manifest["n"] + 1})
            return iid, f"rev=1 digest={digest[:12]}"
        return self._run("submit", tenant_id, None, None, go)

    @staticmethod
    def _seq(v, what):
        if type(v) not in (list, tuple):  # None (absent), a generator, a set or a string all fail closed
            raise ReviewError("RQ-001", what)
        return v

    def resubmit(self, *, tenant_id, item_id, content, author, involved, linked_staff) -> int:
        """The author answers `changes_requested` (or a hold) with new content: a new revision, back to pending. The
        ids in `involved` and `linked_staff` are ADDED to the stored list; nobody is ever removed. A resubmission never
        changes the hold: a held item stays held until `clear_hold` (N1)."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            it = self._fold(item_id, t)
            if not (it.status == "changes_requested" or (it.hold and it.status in ("pending", "claimed", "approved"))):
                raise ReviewError("RQ-005")
            if ident(author, "author") != it.author:
                raise ReviewError("RQ-003", "author")
            union = tuple(sorted(set(it.involved) | set(id_list(self._seq(involved, "involved"), "involved"))
                                 | set(id_list(self._seq(linked_staff, "linked_staff"), "linked_staff"))))
            digest = content_digest(content)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if digest == it.digest:
                raise ReviewError("RQ-001", "unchanged")
            self._append(item_id, t, "resubmitted", at, it.author, {"revision": it.revision + 1, "content_digest": digest,
                                                                     "hold": it.hold, "involved": list(union)})
            return it.revision + 1, f"rev={it.revision + 1} digest={digest[:12]}"
        return self._run("resubmit", tenant_id, item_id, None, go)

    def hold_item(self, claims, *, tenant_id, item_id, reason) -> None:
        """Quarantine at any time (an injection or scan finding after submit or approval). The actor is a verified staff
        principal (role `team_reviewer` or the proposed `hold_issuer`), recorded and audited. Bars approval and makes
        evidence ineligible until `clear_hold`."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            who, _ = self._reviewer(claims, step_up=False, roles_ok=HOLD_ROLES)
            it = self._fold(item_id, t)
            if reason not in HOLD_REASONS:
                raise ReviewError("RQ-001", "reason")
            if it.hold:
                raise ReviewError("RQ-005")
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            self._append(item_id, t, "held", at, who, {"reason": reason})
            return None, f"reason={reason}"
        return self._run("hold", tenant_id, item_id, claims, go)

    def clear_hold(self, claims, *, tenant_id, item_id) -> dict:
        """Lift a hold. Only an explicit act of a verified staff human (fresh step-up, role `team_reviewer`) who is not
        the author, in `involved` or linked to them; a resubmission never lifts it. Audited."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            who, linked = self._reviewer(claims, step_up=True)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._conflict(it, who, linked):
                raise ReviewError("RQ-007")
            if not it.hold:
                raise ReviewError("RQ-005")
            self._append(item_id, t, "hold_cleared", at, who, {})
            return self._view(self._fold(item_id, t), at), ""
        return self._run("clear_hold", tenant_id, item_id, claims, go)

    def _items(self, t):
        """Folded items of one tenant, from the sealed manifest (a deleted log raises RQ-011: fail closed)."""
        for iid, (ten, _, _) in sorted(self._manifest_map().items()):
            if ten == t:
                yield self._fold(iid, t)

    def _open(self, t, kind, ref):
        for it in self._items(t):
            if it.kind == kind and it.subject_ref == ref and it.status not in ("approved", "rejected"):
                return it
        return None

    # ----- reviewer acts --------------------------------------------------------------------------------------
    def claim(self, claims, *, tenant_id, item_id) -> dict:
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            who, linked = self._reviewer(claims, step_up=True)
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

    def release(self, claims, *, tenant_id, item_id) -> dict:
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            who, _ = self._reviewer(claims, step_up=False)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._state(it, at) != "claimed" or it.claim[0] != who:
                raise ReviewError("RQ-006")
            self._append(item_id, t, "released", at, who, {})
            return self._view(self._fold(item_id, t), at), ""
        return self._run("release", tenant_id, item_id, claims, go)

    def decide(self, claims, *, tenant_id, item_id, decision, checklist, note, current_content) -> dict:
        """Record one decision on the claimed item. `current_content` is what the host loaded from its own store. The
        reviewer's step-up is spent by this decision: the next one needs a new MFA sign-in."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            who, linked = self._reviewer(claims, step_up=True)
            it = self._fold(item_id, t)
            if at < it.last_at:
                raise ReviewError("RQ-002", "regression")
            if self._conflict(it, who, linked):
                raise ReviewError("RQ-007")
            if self._state(it, at) != "claimed" or it.claim[0] != who:
                raise ReviewError("RQ-006")
            if type(decision) is not str or decision not in DECISIONS:
                raise ReviewError("RQ-001", "decision")
            if content_digest(current_content) != it.digest:
                raise ReviewError("RQ-008")
            ids = checklist_ids(it.kind)
            if type(checklist) is not dict or set(checklist) != set(ids) or any(type(v) is not str or v not in ("pass", "fail") for v in checklist.values()):
                raise ReviewError("RQ-009", "shape")
            text = note_text(note)
            if decision == "approved":
                if it.hold:
                    raise ReviewError("RQ-010")
                if any(v != "pass" for v in checklist.values()):
                    raise ReviewError("RQ-009", "failed_check")
            elif not text:
                raise ReviewError("RQ-014", "required")
            spent = (who, claims.auth_time)
            if spent in self._used_stepups:
                raise ReviewError("RQ-003", "stepup_used")
            nh = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self._append(item_id, t, "decided", at, who, {"revision": it.revision, "content_digest": it.digest, "decision": decision,
                                                           "checklist": {k: checklist[k] for k in sorted(checklist)}, "note": text,
                                                           "note_sha256": nh, "note_len": len(text)})
            self._used_stepups[spent] = item_id
            return self._view(self._fold(item_id, t), at), f"{decision} rev={it.revision} note_sha256={nh[:16]} note_len={len(text)}"
        return self._run("decide", tenant_id, item_id, claims, go)

    # ----- reads (verified staff only; items hold ids, digests and reviewer notes, never content) ---------------
    def get(self, claims, *, tenant_id, item_id) -> dict:
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            self._reviewer(claims, step_up=False, roles_ok=READER_ROLES)
            return self._view(self._fold(item_id, t), at), ""
        return self._run("get", tenant_id, item_id, claims, go)

    def list_items(self, claims, *, tenant_id=None, state=None) -> list:
        """Items for a verified reviewer. A log that fails its checks is listed with state `invalid` (never hidden);
        a state filter keeps lapsed claims under `pending`."""
        def go():
            at = self._now()
            self._reviewer(claims, step_up=False, roles_ok=READER_ROLES)
            if tenant_id is not None:
                _tenant_id(tenant_id)
            if state is not None and state not in STATES + ("invalid",):
                raise ReviewError("RQ-001", "state")
            out = []
            for iid, (ten, _, _) in sorted(self._manifest_map().items()):
                if tenant_id is not None and ten != tenant_id:
                    continue
                try:
                    v = self._view(self._fold(iid, ten), at)
                except ReviewError as e:
                    v = {"itemId": iid, "tenantId": ten, "state": "invalid", "code": e.code, "labelKeys": {"state": "review.state.invalid"}}
                if state in (None, v["state"]):
                    out.append(v)
            return out, ""
        return self._run("list", tenant_id, None, claims, go)

    def invalid(self) -> list:
        try:
            ids = set(self._manifest_map()) | set(self._logs)
        except ReviewError as e:
            return [("*", e.code)]
        bad = []
        for iid in sorted(ids):
            try:
                self._fold(iid)
            except ReviewError as e:
                bad.append((iid, e.code))
        return bad

    # ----- the gate output: evidence only ---------------------------------------------------------------------
    def gate_evidence(self, claims, *, tenant_id, item_id, current_content) -> dict:
        """What BPL-020 may read for one item. Recomputed from the sealed log, its anchors and the host's current
        content; fresh means the approved digest equals the digest of that content. `seq` and `headSeal` let BPL-020
        pin what it read. Never an instruction to promote."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            self._reviewer(claims, step_up=False, roles_ok=READER_ROLES)
            it = self._fold(item_id, t)
            fresh = content_digest(current_content) == it.digest
            approved = it.status == "approved" and not it.hold
            last = it.decisions[-1] if it.decisions else None
            return {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": it.tenant, "itemId": it.id,
                    "kind": it.kind, "subjectRef": it.subject_ref, "revision": it.revision, "contentDigest": it.digest,
                    "seq": it.head_seq, "headSeal": it.head_seal, "hold": it.hold,
                    "state": self._state(it, at), "stale": not fresh, "eligible": bool(approved and fresh),
                    "approvedBy": last["reviewer"] if approved and last else None,
                    "decidedAt": last["decidedAt"] if approved and last else None,
                    "checklist": last["checklist"] if approved and last else None}, f"eligible={approved and fresh}"
        return self._run("evidence", tenant_id, item_id, claims, go)

    def verify_evidence(self, claims, *, tenant_id, item_id, current_content, pinned_seq=None, pinned_head=None) -> dict:
        """For BPL-020 and DSC-009: re-derive the evidence for an item from the sealed log and its anchors (the queue
        re-validates head and manifest seals itself) and say whether a pin the consumer holds (`seq` and `headSeal` from
        an earlier read) is still the head. The caller is a verified staff-realm principal with `evidence_reader` (a
        proposed service role, Q-490) or `team_reviewer`. The API takes ids, content the consumer loaded from its own
        store and a pin; it never accepts an evidence object, so a constructed dict has no authority. `eligible` is
        False when a pin is given and no longer current."""
        pin = (pinned_seq, pinned_head)
        if pin != (None, None) and (type(pinned_seq) is not int or type(pinned_head) is not str):
            raise ReviewError("RQ-001", "pin")
        out = self.gate_evidence(claims, tenant_id=tenant_id, item_id=item_id, current_content=current_content)
        out["pinCurrent"] = None if pin == (None, None) else bool(pinned_seq == out["seq"] and pinned_head == out["headSeal"])
        if out["pinCurrent"] is False:
            out["eligible"] = False
        return out

    def team_reviewed_evidence(self, claims, *, tenant_id, subject_ref, required: dict) -> dict:
        """Evidence for one subject across kinds: `required` maps kind -> the host's current content. The Blueprint
        draft is always required. The newest item per kind (by the sealed submission number, not by time) counts; a
        missing, open, rejected, held or stale item, or any broken log of the tenant, blocks."""
        def go():
            t, at = _tenant_id(tenant_id), self._now()
            self._reviewer(claims, step_up=False, roles_ok=READER_ROLES)
            ref = ident(subject_ref)
            if type(required) is not dict or "blueprint_draft" not in required or any(k not in KINDS for k in required):
                raise ReviewError("RQ-001", "required")
            parts, missing = {}, []
            mine = [it for it in self._items(t) if it.subject_ref == ref]
            for kind in sorted(required):
                digest = content_digest(required[kind])
                best = max((it for it in mine if it.kind == kind), key=lambda it: it.created, default=None)
                if best is None:
                    missing.append(kind)
                    continue
                parts[kind] = {"itemId": best.id, "state": self._state(best, at), "stale": digest != best.digest, "seq": best.head_seq,
                               "headSeal": best.head_seal,
                               "eligible": best.status == "approved" and not best.hold and digest == best.digest}
            ok = not missing and all(p["eligible"] for p in parts.values())
            return {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": t, "subjectRef": ref,
                    "items": parts, "missing": missing, "eligible": ok}, f"eligible={ok}"
        return self._run("evidence", tenant_id, None, claims, go)
