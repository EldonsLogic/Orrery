"""Build state machine, draft to live, with the human gates (BPL-020, Tier 3: approval authority).

States and the ONLY allowed transitions (contracts/build-states.md; the Blueprint's `meta.buildState` mirrors the
folded state, the control plane's log is the source of truth):

    (none) -> draft                       created (author: human or agent)
    draft  -> draft                       revised (author), approvals reset
    draft  -> owner_approved              GATE: the owner, a human with a fresh step-up, AND a current sealed owner approval
                                          (DSC-009) for this content digest and quote digest, re-checked at every later gate
    owner_approved -> team_reviewed       GATE: a named team reviewer, a human with a fresh step-up
    team_reviewed -> built_in_sandbox     sandbox build through the engine port (outcome confirmed by the port)
    built_in_sandbox -> simulated         GATE: a team reviewer confirms the simulation report
    simulated -> simulated                GATE: a team reviewer starts the cutover (checks confirmed)
    simulated -> live                     GATE: the owner confirms; the live apply must be confirmed by the port
    any state before live -> an earlier state   rollback, GATE: owner or team reviewer (human, step-up)

Nothing else. `live` is terminal here: changes after go-live go through the change path (diff, simulate, approve,
apply), and posted ledger data is never rolled back (contract, Rollback rules 2 and 6).

How it stays honest (the PLT-013 and BPL-019 lessons, applied):
- State is never stored. The sealed log (sealed.py: whole-record HMAC with key id, chained, per-tenant head and
  manifest anchors, no key no machine, no unsealed fallback) is folded on every read; the same transition rules run at
  write time and at read time, so a forged, reordered, truncated or replayed record is BS-011 and promotes nothing.
- Every gate re-derives its evidence at transition time from sources the host owns: the Blueprint content is loaded
  from the host store and digested here; team review is re-verified through the review port with the sequence and head
  pinned at the review gate; the simulation report is re-loaded and its sign-off is re-derived from the sealed
  ledger records (never an evidence dict, never `eligible` alone) with the required roles and the report digest. No
  method accepts an evidence object, a record or a verdict from the caller. If the content changed after any approval
  (digest differs), the transition is BS-008 and the build must be re-approved.
- Humans only: a gate needs a Principal that the identity adapter built from verified claims with kind "human" and a
  consumed step-up (ports.py states the claim assumptions). Agents and services can create and revise drafts and run
  the sandbox build (role build_runner), never a gate. The machine has no timers, no callbacks and no auto
  transition: each promotion is one explicit call by one human.
- Separation of duties: a team-gate actor is not an author, not in `involved` (requester, quote preparer, linked
  staff the host lists) and not an owner-gate actor; an owner-gate actor is not a staff-realm author or a reviewer.
- Tenant-bound: the log record, the principal, the report and the sign-off ledger must all carry the same tenant; a
  valid record replayed into another tenant or Blueprint fails its seal and its chain.
- Time is the host clock only; a record older than the last is refused. Fail closed: any port error, malformed answer
  or unknown field refuses.
- Applies are write-ahead: `apply_started` (idempotency key, content digest) is sealed BEFORE the port is called;
  only a "confirmed" answer moves the state. An exception, a timeout or any other answer is recorded as "unknown" and
  the build stays applying/unknown (no new apply, no rollback) until `resolve_apply` gets a definite answer.
- Quarantine: the review evidence carries `hold`; any hold blocks every later promotion.
"""
from __future__ import annotations

import contextvars
import copy
import hashlib
from dataclasses import dataclass, field

from simulator import review, signoff

from .canon import DIGEST_RE, content_digest, digest as _digest, ident, id_list, tenant as _tenant
from .errors import BuildStateError
from .ledger import SignOffLedger
from .ports import KINDS, OWNER, REALMS, REVIEWER, ROLE_REALM, RUNNER, Principal
from .sealed import SealedLog

_WHO = contextvars.ContextVar("build_state_who", default=None)   # per-call actor for audit, never on the instance
STATES = ("draft", "owner_approved", "team_reviewed", "built_in_sandbox", "simulated", "live")
_IDX = {s: i for i, s in enumerate(STATES)}
AUTHOR = "author"
CONFIRMATIONS = ("gaps", "quote", "summary")
CUTOVER_CHECKS = ("backups_verified", "compliance_onboarding", "opening_balances")
APPLY_LEASE = 900  # seconds an apply may stay in flight before it can be reconciled to unknown
REASONS = ("rejected", "owner_reopened", "content_changed", "sandbox_failed", "simulation_rejected", "other")
OUTCOMES = ("confirmed", "failed", "unknown")
PASSING_VERDICTS = ("pass", "pass_with_warnings")
EARLIEST, LATEST = 1_577_836_800, 4_102_444_800  # 2020-01-01 and 2100-01-01 in epoch seconds
_STAGE = {"owner": 1, "review": 2, "sandbox": 3, "sim": 4, "cutover": 4}  # a stage survives rollback to this index or later
_DATA = {
    "created": {"digest", "revision", "involved"}, "revised": {"digest", "revision", "involved"},
    "owner_approved": {"digest", "confirmations", "quoteDigest"},
    "team_reviewed": {"digest", "itemId", "pinSeq", "pinHead", "reviewDigest", "approvedBy"},
    "rolled_back": {"from", "to", "reason", "digest"}, "recovery_cleared": {"kind", "key", "digest"},
    "apply_started": {"kind", "key", "digest", "attempt", "simulationId", "reportDigest"},
    "apply_outcome": {"kind", "key", "outcome"},
    "simulated": {"digest", "simulationId", "reportDigest", "revision", "verdict"},
    "cutover_started": {"digest", "simulationId", "reportDigest", "checks"},
}
_ACTOR_KEYS = {"subject", "kind", "realm", "role"}


@dataclass
class _B:
    tenant: str
    bp: str
    state: str = "draft"
    pending: object = None          # {"kind", "key", "outcome", "at"}; outcome None (applying) or "unknown"
    rejected_reports: set = field(default_factory=set)   # report digests of a simulation a reviewer rejected (rollback)
    recovery: object = None         # {"kind", "key"}: a live apply failed; the site may need recovery (human clears)
    digest: str = ""
    revision: int = 0
    authors: dict = field(default_factory=dict)       # subject -> realm
    involved: set = field(default_factory=set)
    att: dict = field(default_factory=dict)           # owner, review, sandbox, sim, cutover
    attempts: dict = field(default_factory=dict)
    gate_actors: dict = field(default_factory=lambda: {OWNER: set(), REVIEWER: set()})
    last_at: int = 0
    head_seq: int = 0
    head_seal: str = ""
    rollbacks: int = 0              # rollbacks so far (an owner approval with no outcome sealed before the last one is spent)


def idempotency_key(tenant_id, bp, kind, digest, attempt) -> str:
    return "bs-" + hashlib.sha256(f"orrery.buildstate.apply.v1|{tenant_id}|{bp}|{kind}|{digest}|{attempt}".encode()).hexdigest()[:40]


def _bad(code="BS-011", why="record"):
    return BuildStateError(code, why)


class BuildStateMachine:
    def __init__(self, *, identity, blueprints, validator, reviews, simulations, signoffs, engine, clock, owner_approvals,
                 integrity_keys: dict | None = None, key_id: str | None = None, required_signoff_roles=("owner",), audit=None):
        keys = integrity_keys if integrity_keys is not None else {}
        roles = tuple(required_signoff_roles) if type(required_signoff_roles) in (tuple, list) else ()
        if not roles or len(set(roles)) != len(roles) or any(r not in review.ROLES for r in roles) or "owner" not in roles:
            raise BuildStateError("BS-001", "required_signoff_roles")
        if not isinstance(signoffs, SignOffLedger):
            raise BuildStateError("BS-001", "signoffs")
        if any(p is None for p in (identity, blueprints, validator, reviews, simulations, signoffs, engine, clock, owner_approvals)):
            raise BuildStateError("BS-001", "ports")
        self._log = SealedLog(keys, key_id if key_id is not None else (list(keys)[-1] if keys else ""), "orrery.buildstate.log.v1")
        self._idn, self._bps, self._validate, self._reviews, self._sims = identity, blueprints, validator, reviews, simulations
        self._ledger, self._engine, self._clock, self._audit_cb = signoffs, engine, clock, audit
        self._owner_ap = owner_approvals
        self._policy = roles

    # ----- host clock, audit, actor --------------------------------------------------------------------------
    def _now(self) -> int:
        try:
            v = self._clock()
        except Exception:
            raise BuildStateError("BS-002", "host_clock") from None
        if type(v) is not int or not EARLIEST <= v <= LATEST:
            raise BuildStateError("BS-002")
        return v

    def _audit(self, action, code, subject, tenant_id, bp):
        if self._audit_cb is None:
            return
        try:
            self._audit_cb({"action": f"build.{action}", "code": code, "subject": subject, "tenant": tenant_id, "blueprint": bp})
        except Exception:  # an audit failure never turns a refusal into an allow
            pass

    def _run(self, action, tenant_id, bp, claims, fn):
        tok = _WHO.set(None)
        subject = getattr(claims, "subject", None) if not isinstance(claims, (str, bytes, dict)) else None
        t = tenant_id if isinstance(tenant_id, str) else None
        b = bp if isinstance(bp, str) else None
        try:
            out = fn()
        except BuildStateError as e:
            who = _WHO.get() or (subject if isinstance(subject, str) else None)
            self._audit(action, e.code, who, t, b)
            raise
        except Exception:
            self._audit(action, "BS-001", _WHO.get(), t, b)
            raise BuildStateError("BS-001", "unexpected") from None
        else:
            self._audit(action, "OK", _WHO.get(), tenant_id, bp)
            return out
        finally:
            _WHO.reset(tok)

    def _actor(self, claims, t, roles, *, gate):
        try:
            p = self._idn.resolve(claims, step_up=bool(gate))
        except BuildStateError:
            raise
        except Exception:
            raise BuildStateError("BS-003", "resolver") from None
        if type(p) is not Principal or type(p.subject) is not str or type(p.kind) is not str or type(p.realm) is not str \
                or type(p.roles) is not tuple or not all(type(r) is str for r in p.roles) or type(p.step_up) is not bool:
            raise BuildStateError("BS-003", "principal")
        if not ID_RE_OK(p.subject):
            raise BuildStateError("BS-003", "principal")
        _WHO.set(p.subject)
        if p.kind not in KINDS or p.realm not in REALMS:
            raise BuildStateError("BS-003", "principal")
        if p.realm == "tenant":
            if type(p.tenant_id) is not str or p.tenant_id != t:
                raise BuildStateError("BS-017")
        elif p.tenant_id is not None:
            raise BuildStateError("BS-003", "realm")
        if gate and (p.kind != "human" or p.step_up is not True):
            raise BuildStateError("BS-003", "human_step_up")
        matched = [r for r in roles if r in p.roles and ROLE_REALM.get(r, p.realm) == p.realm]
        if not matched:
            raise BuildStateError("BS-003", "role")
        return p, matched[0]

    # ----- fold: one rule set for write time and read time -------------------------------------------------
    def _check_actor(self, typ, a, d):
        if type(a) is not dict or set(a) != _ACTOR_KEYS or a["kind"] not in KINDS or a["realm"] not in REALMS:
            raise _bad()
        ident(a["subject"], "subject")
        role, kind, realm = a["role"], a["kind"], a["realm"]
        gate = {"owner_approved": OWNER, "team_reviewed": REVIEWER, "simulated": REVIEWER, "cutover_started": REVIEWER}.get(typ)
        if typ == "apply_started" and d["kind"] == "live":
            gate = OWNER
        if gate:
            if kind != "human" or role != gate or realm != ROLE_REALM[gate]:
                raise BuildStateError("BS-003", "gate_actor")
        elif typ in ("rolled_back", "recovery_cleared"):
            if kind != "human" or role not in (OWNER, REVIEWER) or realm != ROLE_REALM[role]:
                raise BuildStateError("BS-003", "gate_actor")
        elif typ == "apply_started":  # sandbox
            if role not in (RUNNER, REVIEWER) or realm != "staff" or (role == REVIEWER and kind != "human"):
                raise BuildStateError("BS-003", "actor")
        elif typ == "apply_outcome":
            if role not in (RUNNER, REVIEWER, OWNER) or realm != ROLE_REALM[role]:
                raise BuildStateError("BS-003", "actor")
        elif role != AUTHOR:
            raise BuildStateError("BS-003", "actor")
        return gate or (role if typ in ("rolled_back", "recovery_cleared") else None)

    def _sod(self, b, a, role):
        s = a["subject"]
        if role == REVIEWER:
            if s in b.authors or s in b.involved or s in b.gate_actors[OWNER]:
                raise BuildStateError("BS-007")
        elif role == OWNER:
            if "staff" in b.authors.get(s, ()) or s in b.gate_actors[REVIEWER]:
                raise BuildStateError("BS-007")

    def _step(self, b, body, t, bp):
        """Apply one record to the state (b is None before `created`). Raises a typed error when the transition is not
        allowed; read-time folds turn every such error into BS-011."""
        if type(body) is not dict or set(body) != {"type", "at", "actor", "data"}:
            raise _bad()
        typ, at, a, d = body["type"], body["at"], body["actor"], body["data"]
        if typ not in _DATA or type(d) is not dict or set(d) != _DATA[typ] or type(at) is not int or not EARLIEST <= at <= LATEST:
            raise _bad()
        if (b is None) != (typ == "created") or (b is not None and at < b.last_at):
            raise BuildStateError("BS-002" if b is not None and typ != "created" else "BS-004", "order")
        gate = self._check_actor(typ, a, d)
        n = copy.deepcopy(b) if b is not None else _B(t, bp)
        n.last_at = at
        S = n.state
        if typ in ("created", "revised"):
            _digest(d["digest"])
            if type(d["revision"]) is not int or d["revision"] < 1 or type(d["involved"]) is not list:
                raise _bad()
            if typ == "revised":
                if S != "draft" or n.pending or n.recovery:
                    raise BuildStateError("BS-005")
                if d["revision"] <= n.revision or d["digest"] == n.digest:   # a new content digest AND a higher revision
                    raise BuildStateError("BS-008", "revision")
            n.digest, n.revision = d["digest"], d["revision"]
            n.authors.setdefault(a["subject"], set()).add(a["realm"])
            n.involved |= set(id_list(d["involved"], "involved"))
            n.att = {}
            return n
        if (n.pending or n.recovery) and typ not in ("apply_outcome", "recovery_cleared"):
            raise BuildStateError("BS-010")
        if typ not in ("apply_outcome", "rolled_back") and d.get("digest") != n.digest:
            raise BuildStateError("BS-008")
        if typ == "owner_approved":
            if S != "draft":
                raise BuildStateError("BS-005")
            if type(d["confirmations"]) is not list or tuple(sorted(d["confirmations"])) != CONFIRMATIONS:
                raise BuildStateError("BS-009")
            self._sod(n, a, OWNER)
            _digest(d["quoteDigest"])
            n.state, n.att["owner"] = "owner_approved", {"actor": a["subject"], "digest": d["digest"], "quoteDigest": d["quoteDigest"]}
        elif typ == "team_reviewed":
            if S != "owner_approved":
                raise BuildStateError("BS-005")
            ident(d["itemId"])
            if type(d["pinSeq"]) is not int or d["pinSeq"] < 1 or type(d["pinHead"]) is not str or not d["pinHead"]:
                raise _bad()
            _digest(d["reviewDigest"]); ident(d["approvedBy"])
            self._sod(n, a, REVIEWER)
            n.state = "team_reviewed"
            n.att["review"] = {k: d[k] for k in ("itemId", "pinSeq", "pinHead", "reviewDigest", "approvedBy")}
        elif typ == "rolled_back":
            if S == "live" or d["from"] != S or d["to"] != "draft" or S == "draft" or d["reason"] not in REASONS:
                raise BuildStateError("BS-016")
            if n.pending:
                raise BuildStateError("BS-010")
            if d["digest"] != n.digest:
                raise BuildStateError("BS-008")
            if d["reason"] == "simulation_rejected" and "sim" in n.att:
                n.rejected_reports.add(n.att["sim"]["reportDigest"])   # a rejected simulation stays rejected
            n.state, n.rollbacks = d["to"], n.rollbacks + 1
            n.att = {k: v for k, v in n.att.items() if _STAGE[k] <= _IDX[d["to"]]}
        elif typ == "apply_started":
            kind = d["kind"]
            if kind not in ("sandbox", "live"):
                raise _bad()
            want = {"sandbox": "team_reviewed", "live": "simulated"}[kind]
            if S != want or (kind == "live" and "cutover" not in n.att):
                raise BuildStateError("BS-005")
            n.attempts[kind] = n.attempts.get(kind, 0) + 1
            if d["attempt"] != n.attempts[kind] or d["key"] != idempotency_key(t, bp, kind, n.digest, d["attempt"]):
                raise _bad("BS-011", "key")
            if kind == "live":
                sim = n.att["sim"]
                if (d["simulationId"], d["reportDigest"]) != (sim["simulationId"], sim["reportDigest"]):
                    raise BuildStateError("BS-008")
                self._sod(n, a, OWNER)
                n.gate_actors[OWNER].add(a["subject"])
            elif (d["simulationId"], d["reportDigest"]) != (None, None):
                raise _bad()
            n.pending = {"kind": kind, "key": d["key"], "outcome": None, "at": at}
        elif typ == "apply_outcome":
            p = n.pending or n.recovery
            if not p or d["kind"] != p["kind"] or d["key"] != p["key"] or d["outcome"] not in OUTCOMES:
                raise BuildStateError("BS-005")
            if n.recovery and not n.pending and d["outcome"] != "confirmed":
                raise BuildStateError("BS-005")   # after a failed mark only a confirmation can reconcile
            if d["outcome"] == "confirmed":
                n.state = "built_in_sandbox" if p["kind"] == "sandbox" else "live"
                if p["kind"] == "sandbox":
                    n.att["sandbox"] = {"key": p["key"]}
                n.pending = n.recovery = None
            elif d["outcome"] == "failed":
                n.pending = None
                if p["kind"] == "live":
                    n.recovery = {"kind": "live", "key": p["key"]}   # never treated as clean (contract, Rollback rule 4)
            else:
                n.pending = {**p, "outcome": "unknown"}
        elif typ == "recovery_cleared":
            if not n.recovery or (d["kind"], d["key"]) != (n.recovery["kind"], n.recovery["key"]) or d["digest"] != n.digest:
                raise BuildStateError("BS-005")
            self._sod(n, a, a["role"])
            n.recovery = None
        elif typ == "simulated":
            if S != "built_in_sandbox" or d["verdict"] not in PASSING_VERDICTS or d["revision"] != n.revision:
                raise BuildStateError("BS-005")
            ident(d["simulationId"], "simulation"); _digest(d["reportDigest"])
            if d["reportDigest"] in n.rejected_reports:
                raise BuildStateError("BS-006", "report_rejected")
            self._sod(n, a, REVIEWER)
            n.state = "simulated"
            n.att["sim"] = {"actor": a["subject"], "simulationId": d["simulationId"], "reportDigest": d["reportDigest"], "revision": d["revision"]}
        elif typ == "cutover_started":
            sim = n.att.get("sim")
            if S != "simulated" or "cutover" in n.att or not sim:
                raise BuildStateError("BS-005")
            if (d["simulationId"], d["reportDigest"]) != (sim["simulationId"], sim["reportDigest"]):
                raise BuildStateError("BS-008")
            if type(d["checks"]) is not list or tuple(sorted(d["checks"])) != CUTOVER_CHECKS:
                raise BuildStateError("BS-009")
            self._sod(n, a, REVIEWER)
            n.att["cutover"] = {"actor": a["subject"]}
        if gate in (OWNER, REVIEWER):
            n.gate_actors[gate].add(a["subject"])
        return n

    def _fold(self, t, bp, records) -> _B:
        b = None
        try:
            for r in records:
                try:
                    b = self._step(b, r["body"], t, bp)
                except BuildStateError as e:
                    raise BuildStateError("BS-011", e.code) from None
        except BuildStateError:
            raise
        except Exception:
            raise BuildStateError("BS-011", "shape") from None
        if b is None:
            raise BuildStateError("BS-004")
        b.head_seq, b.head_seal = len(records), records[-1]["seal"]
        return b

    def _load(self, t, bp, missing_ok=False):
        recs = self._log.read(t, bp)
        if not recs:
            if missing_ok:
                return None
            raise BuildStateError("BS-004")
        return self._fold(t, bp, recs)

    def _write(self, b, t, bp, p, role, at, typ, data, strict=True):
        body = {"type": typ, "at": at, "actor": {"subject": p.subject, "kind": p.kind, "realm": p.realm, "role": role}, "data": data}

        def check(existing):
            cur = self._fold(t, bp, existing) if existing else None
            seen = (cur.head_seq, cur.head_seal) if cur else (0, "")
            if strict and seen != ((b.head_seq, b.head_seal) if b else (0, "")):
                raise BuildStateError("BS-005", "concurrent")
            self._step(cur, body, t, bp)  # the same rules as a read-time fold
        self._log.append(t, bp, body, check)
        return self._load(t, bp)

    # ----- evidence, re-derived at transition time --------------------------------------------------------------
    def _content(self, t, bp):
        try:
            content = self._bps.load(t, bp)
        except BuildStateError:
            raise
        except Exception:
            raise BuildStateError("BS-006", "blueprint_store") from None
        dg = content_digest(content)
        meta = content.get("meta") if type(content) is dict else None
        if type(meta) is not dict or meta.get("id") != bp or type(meta.get("revision")) is not int or isinstance(meta.get("revision"), bool) or meta["revision"] < 1:
            raise BuildStateError("BS-006", "blueprint_meta")
        return content, dg, meta["revision"]

    def _valid(self, content):
        try:
            errors = self._validate(copy.deepcopy(content))
        except Exception:
            raise BuildStateError("BS-006", "validator") from None
        if type(errors) not in (list, tuple) or errors:
            raise BuildStateError("BS-006", "validator")

    @staticmethod
    def _need(b, state):
        if b.state != state:
            raise BuildStateError("BS-005")

    def _fresh(self, b, dg):
        if dg != b.digest:
            raise BuildStateError("BS-008")

    def _review(self, t, bp, content, pin_seq, pin_head, recorded=None):
        """Re-derive the team review. The item is never chosen by the caller: the queue's newest `blueprint_draft`
        item for this Blueprint and content (`newest`) must be eligible, and its sequence and head must be the pin the
        reviewer saw (or the recorded one at later gates). A newer held, rejected or open item blocks. Then that item is
        verified (`verify`) for hold, staleness, digest and approver."""
        if type(pin_seq) is not int or isinstance(pin_seq, bool) or pin_seq < 1 or type(pin_head) is not str or not pin_head:
            raise BuildStateError("BS-001", "pin")
        try:
            nw = self._reviews.newest(t, bp, copy.deepcopy(content))
        except Exception:
            raise BuildStateError("BS-006", "review_port") from None
        items = nw.get("items") if type(nw) is dict else None
        it = items.get("blueprint_draft") if type(items) is dict else None
        ok = type(nw) is dict and nw.get("gate") == "team_reviewed" and nw.get("evidenceOnly") is True and nw.get("tenantId") == t \
            and nw.get("subjectRef") == bp and nw.get("eligible") is True and nw.get("missing") == [] and type(it) is dict \
            and it.get("eligible") is True and it.get("stale") is False and it.get("state") == "approved" \
            and type(it.get("itemId")) is str and ID_RE_OK(it["itemId"]) and it.get("seq") == pin_seq and it.get("headSeal") == pin_head
        if not ok or (recorded is not None and recorded["itemId"] != it["itemId"]):
            raise BuildStateError("BS-006", "review_newest")
        item_id = it["itemId"]
        try:
            ev = self._reviews.verify(t, item_id, copy.deepcopy(content), pin_seq, pin_head)
        except Exception:
            raise BuildStateError("BS-006", "review_port") from None
        ok = type(ev) is dict and ev.get("gate") == "team_reviewed" and ev.get("evidenceOnly") is True and ev.get("tenantId") == t \
            and ev.get("itemId") == item_id and ev.get("kind") == "blueprint_draft" and ev.get("subjectRef") == bp \
            and ev.get("hold") is False and ev.get("stale") is False and ev.get("eligible") is True \
            and ev.get("state") == "approved" and ev.get("pinCurrent") is True and ev.get("seq") == pin_seq \
            and ev.get("headSeal") == pin_head and type(ev.get("contentDigest")) is str and DIGEST_RE.fullmatch(ev["contentDigest"]) \
            and type(ev.get("approvedBy")) is str and ID_RE_OK(ev["approvedBy"])
        if not ok or (recorded is not None and ev["contentDigest"] != recorded["reviewDigest"]):
            raise BuildStateError("BS-006", "review")
        return {**ev, "itemId": item_id}

    def _owner_approval(self, t, bp, dg, quote_digest, subject):
        """Re-derive the owner's sealed approval (DSC-009, ADR-0050 amendment) through the port. It must name `subject`
        as the approving owner for exactly this content digest (computed here) and quote digest, the quote must still be
        the current one, and nothing may block it (a rejection, a request for changes or a hold). Any error refuses."""
        _digest(quote_digest, "quote_digest")
        try:
            ev = self._owner_ap.verify(t, bp, dg, quote_digest, subject)
        except Exception:
            raise BuildStateError("BS-006", "owner_approval_port") from None
        keys = {"tenantId", "blueprintId", "contentDigest", "quoteDigest", "approvedBy", "blocked", "quoteCurrent"}
        if type(ev) is not dict or set(ev) != keys or ev["tenantId"] != t or ev["blueprintId"] != bp or ev["contentDigest"] != dg \
                or ev["quoteDigest"] != quote_digest or type(ev["blocked"]) is not bool or type(ev["quoteCurrent"]) is not bool:
            raise BuildStateError("BS-006", "owner_approval")
        if ev["quoteCurrent"] is not True:
            raise BuildStateError("BS-008", "quote")
        if ev["blocked"] is not False or type(ev["approvedBy"]) is not str or ev["approvedBy"] != subject:
            raise BuildStateError("BS-006", "owner_approval")

    def _upstream(self, t, bp, b, content, dg, through):
        """Re-derive every approval below `through` that the current state implies (owner, team review)."""
        self._fresh(b, dg)
        o = b.att.get("owner", {})
        if o.get("digest") != dg:
            raise BuildStateError("BS-008")
        self._owner_approval(t, bp, dg, o["quoteDigest"], o["actor"])
        if through >= _IDX["team_reviewed"]:
            r = b.att.get("review")
            if not r:
                raise BuildStateError("BS-006", "review")
            self._review(t, bp, content, r["pinSeq"], r["pinHead"], r)

    def _report(self, t, bp, sim_id, revision, digest):
        try:
            report = self._sims.load(t, sim_id)
        except Exception:
            raise BuildStateError("BS-006", "simulation_store") from None
        try:
            view = review.build_view(report, records=(), required_roles=self._policy)
        except review.ReviewError:
            raise BuildStateError("BS-006", "report") from None
        if report.get("tenantId") != t or report.get("simulationId") != sim_id or report.get("status") != "completed" \
                or view["verdict"] not in PASSING_VERDICTS or report.get("blueprintRevision") != revision or report.get("inDoubt"):
            raise BuildStateError("BS-006", "report")
        if report.get("blueprintId") is None or report.get("blueprintDigest") is None:
            raise BuildStateError("BS-006", "report_unbound")    # an old report that names no Blueprint content is refused
        if report["blueprintId"] != bp or report["blueprintDigest"] != digest:
            raise BuildStateError("BS-008", "report_content")    # simulated from other content (or another Blueprint)
        return report, view["reportDigest"]

    def _signoff(self, t, report, sim_id, recorded):
        recs = self._ledger.records(t, sim_id)
        try:
            ev = signoff.gate_evidence(report, recs, required_roles=self._policy)
        except (signoff.SignOffError, review.ReviewError):
            raise BuildStateError("BS-006", "signoff") from None
        mine = [r for r in recs if r.simulation_id == sim_id and r.report_digest == recorded]
        accepted = {r.role for r in mine if r.decision == "accepted"}
        # derived here from the sealed records; `eligible` alone is never trusted
        if type(ev) is not dict or ev.get("gate") != "BPL-020" or ev.get("evidenceOnly") is not True or ev.get("tenantId") != t \
                or ev.get("simulationId") != sim_id or ev.get("reportDigest") != recorded or ev.get("eligible") is not True \
                or ev.get("requiredRoles") != list(self._policy) or ev.get("missingRoles") != [] \
                or any(r.decision != "accepted" for r in mine) or not set(self._policy) <= accepted \
                or len({r.user_id for r in mine}) != len(mine):
            raise BuildStateError("BS-006", "signoff")

    # ----- apply through the engine port --------------------------------------------------------------------------
    @staticmethod
    def _norm(v):
        return v if type(v) is str and v in OUTCOMES else "unknown"

    def _record_outcome(self, t, bp, kind, key, p, role, out, target):
        """Record a definite or unknown outcome. Allowed while pending (the only record allowed then) even if the head
        moved; if another path already recorded it (state moved by this key) the result is read back, not refused."""
        try:
            self._write(self._load(t, bp), t, bp, p, role, self._now(), "apply_outcome", {"kind": kind, "key": key, "outcome": out}, strict=False)
        except BuildStateError as e:
            if e.code != "BS-005":
                raise
            b = self._load(t, bp)
            if not (out == "confirmed" and b.state == target and not b.pending):
                raise
        return self._load(t, bp)

    def _finish(self, t, bp, out):
        if out == "failed":
            raise BuildStateError("BS-015")
        if out == "unknown":
            raise BuildStateError("BS-010", "unknown")

    def _apply(self, t, bp, kind, p, role, dg):
        b = self._load(t, bp)
        pend = b.pending
        try:
            out = self._norm(self._engine.apply(t, kind, pend["key"], dg))
        except Exception:
            out = "unknown"
        target = "built_in_sandbox" if kind == "sandbox" else "live"
        b = self._record_outcome(t, bp, kind, pend["key"], p, role, out, target)
        self._finish(t, bp, out)
        return b

    # ----- public operations ----------------------------------------------------------------------------------------
    def create(self, claims, *, tenant_id, blueprint_id, involved=()):
        """(none) -> draft. An author (a human or an agent) starts the build; `involved` are the ids the host lists
        (requester, quote preparer, linked staff)."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            inv = id_list(involved, "involved")
            p, role = self._actor(claims, t, (AUTHOR,), gate=False)
            at = self._now()
            _, dg, rev = self._content(t, bp)
            if self._log.read(t, bp):
                raise BuildStateError("BS-013")
            self._write(None, t, bp, p, role, at, "created", {"digest": dg, "revision": rev, "involved": list(inv)})
            return self.status(t, bp)
        return self._run("create", tenant_id, blueprint_id, claims, go)

    def revise(self, claims, *, tenant_id, blueprint_id, involved=()):
        """draft -> draft: record the content now in the host store as a new draft revision (approvals reset)."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            inv = id_list(involved, "involved")
            p, role = self._actor(claims, t, (AUTHOR,), gate=False)
            at, b = self._now(), self._load(t, bp)
            _, dg, rev = self._content(t, bp)
            if dg == b.digest:
                raise BuildStateError("BS-001", "unchanged")
            self._write(b, t, bp, p, role, at, "revised", {"digest": dg, "revision": rev, "involved": list(inv)})
            return self.status(t, bp)
        return self._run("revise", tenant_id, blueprint_id, claims, go)

    def approve_owner(self, claims, *, tenant_id, blueprint_id, confirmations, expected_digest, quote_digest):
        """draft -> owner_approved. GATE: the owner (human, step-up) confirms the summary, the quote and the gaps. The
        content digest is computed here and must equal `expected_digest` (the one the owner saw); a current sealed owner
        approval for that digest and `quote_digest` by this very owner must exist and nothing may block it."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (OWNER,), gate=True)
            at, b = self._now(), self._load(t, bp)
            self._need(b, "draft")
            content, dg, _ = self._content(t, bp)
            self._fresh(b, dg)
            self._valid(content)
            if type(confirmations) not in (list, tuple) or tuple(sorted(confirmations)) != CONFIRMATIONS:
                raise BuildStateError("BS-009")
            if type(expected_digest) is not str or expected_digest != dg:
                raise BuildStateError("BS-008", "expected_digest")
            self._owner_approval(t, bp, dg, quote_digest, p.subject)
            self._write(b, t, bp, p, role, at, "owner_approved", {"digest": dg, "confirmations": sorted(confirmations), "quoteDigest": quote_digest})
            return self.status(t, bp)
        return self._run("owner_approve", tenant_id, blueprint_id, claims, go)

    def pass_team_review(self, claims, *, tenant_id, blueprint_id, pinned_seq, pinned_head):
        """owner_approved -> team_reviewed. GATE: a named team reviewer (human, step-up) who read the queue evidence
        (`pinned_seq`, `pinned_head` are what they saw of the newest queue item for this Blueprint); the item is derived and the evidence re-derived here through the review port."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (REVIEWER,), gate=True)
            at, b = self._now(), self._load(t, bp)
            self._need(b, "owner_approved")
            content, dg, _ = self._content(t, bp)
            self._upstream(t, bp, b, content, dg, _IDX["owner_approved"])
            ev = self._review(t, bp, content, pinned_seq, pinned_head)
            if ev["approvedBy"] in b.authors or ev["approvedBy"] in b.involved or ev["approvedBy"] in b.gate_actors[OWNER]:
                raise BuildStateError("BS-007")
            self._write(b, t, bp, p, role, at, "team_reviewed", {"digest": dg, "itemId": ev["itemId"], "pinSeq": pinned_seq,
                                                                 "pinHead": pinned_head, "reviewDigest": ev["contentDigest"],
                                                                 "approvedBy": ev["approvedBy"]})
            return self.status(t, bp)
        return self._run("team_review", tenant_id, blueprint_id, claims, go)

    def build_sandbox(self, claims, *, tenant_id, blueprint_id):
        """team_reviewed -> built_in_sandbox through the engine port. Not a gate: a build runner (agent or service) or a
        team reviewer may run it, but only on a build whose approvals re-derive now. Moves only on a confirmed answer."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (RUNNER, REVIEWER), gate=False)
            at, b = self._now(), self._load(t, bp)
            self._need(b, "team_reviewed")
            content, dg, _ = self._content(t, bp)
            self._upstream(t, bp, b, content, dg, _IDX["team_reviewed"])
            n = b.attempts.get("sandbox", 0) + 1
            self._write(b, t, bp, p, role, at, "apply_started", {"kind": "sandbox", "key": idempotency_key(t, bp, "sandbox", dg, n),
                                                                 "digest": dg, "attempt": n, "simulationId": None, "reportDigest": None})
            self._apply(t, bp, "sandbox", p, role, dg)
            return self.status(t, bp)
        return self._run("build_sandbox", tenant_id, blueprint_id, claims, go)

    def confirm_simulated(self, claims, *, tenant_id, blueprint_id, simulation_id):
        """built_in_sandbox -> simulated. GATE: a team reviewer confirms a completed, passing report for this Blueprint
        revision (the report is re-loaded from the host store; its digest is recorded)."""
        def go():
            t, bp, sim = _tenant(tenant_id), ident(blueprint_id, "blueprint"), ident(simulation_id, "simulation")
            p, role = self._actor(claims, t, (REVIEWER,), gate=True)
            at, b = self._now(), self._load(t, bp)
            self._need(b, "built_in_sandbox")
            content, dg, rev = self._content(t, bp)
            self._upstream(t, bp, b, content, dg, _IDX["team_reviewed"])
            report, rd = self._report(t, bp, sim, rev, dg)
            self._write(b, t, bp, p, role, at, "simulated", {"digest": dg, "simulationId": sim, "reportDigest": rd, "revision": rev,
                                                            "verdict": review.build_view(report, required_roles=self._policy)["verdict"]})
            return self.status(t, bp)
        return self._run("confirm_simulated", tenant_id, blueprint_id, claims, go)

    def start_cutover(self, claims, *, tenant_id, blueprint_id, checks):
        """simulated -> simulated with the cutover started. GATE: a team reviewer confirms the cutover checks."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (REVIEWER,), gate=True)
            at, b = self._now(), self._load(t, bp)
            content, dg, rev = self._content(t, bp)
            self._upstream(t, bp, b, content, dg, _IDX["team_reviewed"])
            sim = b.att.get("sim")
            if b.state != "simulated" or not sim:
                raise BuildStateError("BS-005")
            _, rd = self._report(t, bp, sim["simulationId"], rev, dg)
            if rd != sim["reportDigest"]:
                raise BuildStateError("BS-008")
            if type(checks) not in (list, tuple) or tuple(sorted(checks)) != CUTOVER_CHECKS:
                raise BuildStateError("BS-009")
            self._write(b, t, bp, p, role, at, "cutover_started", {"digest": dg, "simulationId": sim["simulationId"],
                                                                  "reportDigest": rd, "checks": sorted(checks)})
            return self.status(t, bp)
        return self._run("start_cutover", tenant_id, blueprint_id, claims, go)

    def go_live(self, claims, *, tenant_id, blueprint_id):
        """simulated -> live. GATE: the owner (human, step-up) confirms after cutover started. Re-derives the owner
        approval, the team review, the report and its sign-off from the sealed ledger (required roles, report digest),
        then applies through the engine port. Live only on a confirmed answer; otherwise the build stays applying."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (OWNER,), gate=True)
            at, b = self._now(), self._load(t, bp)
            content, dg, rev = self._content(t, bp)
            self._upstream(t, bp, b, content, dg, _IDX["team_reviewed"])
            sim, rd = self._live_checks(t, bp, b, dg, rev)
            n = b.attempts.get("live", 0) + 1
            self._write(b, t, bp, p, role, at, "apply_started", {"kind": "live", "key": idempotency_key(t, bp, "live", dg, n), "digest": dg,
                                                                 "attempt": n, "simulationId": sim["simulationId"], "reportDigest": rd})
            self._apply(t, bp, "live", p, role, dg)
            return self.status(t, bp)
        return self._run("go_live", tenant_id, blueprint_id, claims, go)

    def _live_checks(self, t, bp, b, dg, rev):
        """Everything go-live needs besides the actor: the cutover, the report (bound to this content) and its sign-off
        from the sealed ledger. Also re-run before any re-issue of a live apply, so a non-human can never start the
        first real production apply on stale approval."""
        sim = b.att.get("sim")
        if b.state != "simulated" or not sim or "cutover" not in b.att:
            raise BuildStateError("BS-005")
        report, rd = self._report(t, bp, sim["simulationId"], rev, dg)
        if rd != sim["reportDigest"]:
            raise BuildStateError("BS-008")
        self._signoff(t, report, sim["simulationId"], rd)
        return sim, rd

    def reconcile_apply(self, claims, *, tenant_id, blueprint_id):
        """A pending apply with no recorded outcome (a crash, a lost reply) past its lease (host clock) becomes
        `unknown`, so a human or the adapter confirmation can resolve it. Before the lease it is refused: the apply
        may still be running, and nothing may start or mark anything meanwhile."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (RUNNER, REVIEWER, OWNER), gate=False)
            b, now = self._load(t, bp), self._now()
            pend = b.pending
            if not pend:
                raise BuildStateError("BS-005")
            if pend["outcome"] is None:
                if now < pend["at"] + APPLY_LEASE:
                    raise BuildStateError("BS-010", "in_flight")
                self._record_outcome(t, bp, pend["kind"], pend["key"], p, role, "unknown", None)
            return self.status(t, bp)
        return self._run("reconcile_apply", tenant_id, blueprint_id, claims, go)

    def resolve_apply(self, claims, *, tenant_id, blueprint_id):
        """Settle an `unknown` apply (or reconcile a live apply after a failed mark): ask the adapter for the outcome by
        its idempotency key and, if it is not confirmed, re-issue the SAME apply (idempotent by key and input), whose
        definite answer is recorded. Never allowed while the apply may still be in flight (before the lease), never
        with a new key. A runner can only record what the adapter answered; a `failed` live apply is not clean: it
        becomes `recovery` and only a human clears it."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (RUNNER, REVIEWER, OWNER), gate=False)
            b = self._load(t, bp)
            cur = b.pending or b.recovery
            if not cur or (b.pending and b.pending["outcome"] is None):
                raise BuildStateError("BS-005" if not cur else "BS-010", "in_flight")
            target = "built_in_sandbox" if cur["kind"] == "sandbox" else "live"
            try:
                out = self._norm(self._engine.status(t, cur["key"]))
            except Exception:
                out = "unknown"
            if out != "confirmed" and b.pending:
                content, dg, rev = self._content(t, bp)       # every go-live check again, then the same key
                self._upstream(t, bp, b, content, dg, _IDX["team_reviewed"])
                if cur["kind"] == "live":
                    self._live_checks(t, bp, b, dg, rev)
                try:
                    out = self._norm(self._engine.apply(t, cur["kind"], cur["key"], dg))
                except Exception:
                    out = "unknown"
            if out != "confirmed" and not b.pending:
                raise BuildStateError("BS-010", "recovery")
            if out == "unknown" and b.pending["outcome"] == "unknown":
                raise BuildStateError("BS-010", "unknown")
            self._record_outcome(t, bp, cur["kind"], cur["key"], p, role, out, target)
            self._finish(t, bp, out)
            return self.status(t, bp)
        return self._run("resolve_apply", tenant_id, blueprint_id, claims, go)

    def clear_recovery(self, claims, *, tenant_id, blueprint_id):
        """GATE: after a live apply failed, a human (owner or team reviewer, step-up) clears the recovery block once the
        adapter says the key definitely failed. Only then can a new go-live (a new key) start."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            p, role = self._actor(claims, t, (REVIEWER, OWNER), gate=True)
            at, b = self._now(), self._load(t, bp)
            if not b.recovery:
                raise BuildStateError("BS-005")
            self._sod(b, {"subject": p.subject}, role)
            try:
                out = self._norm(self._engine.status(t, b.recovery["key"]))
            except Exception:
                out = "unknown"
            if out != "failed":
                raise BuildStateError("BS-010", "recovery")
            self._write(b, t, bp, p, role, at, "recovery_cleared", {"kind": "live", "key": b.recovery["key"], "digest": b.digest})
            return self.status(t, bp)
        return self._run("clear_recovery", tenant_id, blueprint_id, claims, go)

    def roll_back(self, claims, *, tenant_id, blueprint_id, to_state, reason):
        """Any state before live -> draft (the contract's only rollback). GATE: the owner or a team reviewer (human,
        step-up). All approvals are void. Not possible while an apply is pending, in recovery, or after live."""
        def go():
            t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
            if to_state != "draft":
                raise BuildStateError("BS-016")
            if type(to_state) is not str or to_state not in _IDX or type(reason) is not str or reason not in REASONS:
                raise BuildStateError("BS-001", "rollback")
            p, role = self._actor(claims, t, (REVIEWER, OWNER), gate=True)
            at, b = self._now(), self._load(t, bp)
            self._write(b, t, bp, p, role, at, "rolled_back", {"from": b.state, "to": to_state, "reason": reason, "digest": b.digest})
            return self.status(t, bp)
        return self._run("roll_back", tenant_id, blueprint_id, claims, go)

    # ----- reads (no claims: nothing here decides; the host gates who may see it) ------------------------------------
    def status(self, tenant_id, blueprint_id) -> dict:
        """The folded state and what is pending, with i18n label keys. Recomputed from the sealed log on every call;
        `contentChanged` says the host store no longer matches the last recorded digest (approvals will refuse)."""
        t, bp = _tenant(tenant_id), ident(blueprint_id, "blueprint")
        b = self._load(t, bp)
        try:
            _, dg, _ = self._content(t, bp)
            changed = dg != b.digest
        except BuildStateError:
            changed = True
        pend = b.pending
        return {"tenantId": t, "blueprintId": bp, "state": b.state, "stateKey": f"bs.state.{b.state}", "contentDigest": b.digest,
                "revision": b.revision, "contentChanged": changed, "headSeq": b.head_seq, "headSeal": b.head_seal,
                "pending": None if not pend else {"kind": pend["kind"], "status": "unknown" if pend["outcome"] == "unknown" else "applying",
                                                  "kindKey": f"bs.pending.{pend['kind']}",
                                                  "statusKey": f"bs.pending.{'unknown' if pend['outcome'] == 'unknown' else 'applying'}"},
                "recovery": None if not b.recovery else {"kind": b.recovery["kind"], "needsRecovery": True}, "cutoverStarted": "cutover" in b.att, "approvals": sorted(b.att),
                "owner": None if "owner" not in b.att else dict(b.att["owner"]), "rollbacks": b.rollbacks}

    def verify_tenant(self, tenant_id) -> list:
        """(blueprint id, code) for every build of the tenant whose log fails; an unreadable manifest raises BS-011."""
        t = _tenant(tenant_id)
        bad = []
        for bp in self._log.streams(t):
            try:
                self._load(t, bp)
            except BuildStateError as e:
                bad.append((bp, e.code))
        return bad


def ID_RE_OK(v):
    try:
        ident(v)
        return True
    except BuildStateError:
        return False
