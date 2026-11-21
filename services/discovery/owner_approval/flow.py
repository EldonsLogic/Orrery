"""Owner approval flow, draft to owner_approved (DSC-009, Tier 3: approval authority). See README.md.

What it is: the owner (a verified human with the owner role of THAT tenant, with a fresh step-up) reads a plain
summary of the draft (what will be built, what it costs, what is not covered, what the simulation will check) and
records one of approve, request_changes or reject with a typed reason and an optional note.

How it stays honest (the PLT-013, BPL-019, BPL-020 and DSC-016 lessons, applied):
- Never auto-approve and never trust a stored value. Every call re-derives from the host sources: the Blueprint content
  and its digest, the quote draft (digest re-verified, bound to this content and gap report, arithmetic re-derived,
  still valid), the build state. A decision carries the digests the owner SAW; if the draft or the quote changed since,
  it is refused (OA-006) and the owner must read again. No method accepts a record, a verdict or evidence from the caller.
- The decision is sealed (whole-record HMAC with key id, chained, per-tenant manifest; no key, no log) bound to tenant,
  Blueprint digest and quote digest. Any unreadable or inconsistent stored record fails closed (OA-009): nothing is
  approved while the log is damaged, and a hold on the draft blocks approval too.
- One decision per owner per version (Blueprint digest and quote digest). A rejection of a Blueprint digest beats every
  approval of it, whoever approved and whenever; the draft must be changed to get a new digest.
- Humans only: agent, assistant and service principals and staff principals never decide. A principal that also holds
  the team reviewer or build runner role cannot decide. Time is the host clock only.
- The approval is evidence, not the gate. After the decision is sealed the flow asks the build state machine's owner
  gate (through the injected port) to move draft to owner_approved; the machine re-derives and re-checks everything
  itself. A refusal is sealed as an outcome and shown; the flow never moves the state by itself.
"""
from __future__ import annotations

import contextvars
import re

from .errors import OwnerApprovalError
from .ledger import SealedLog
from .ports import CONFLICT_ROLES, KINDS, OWNER, REALMS, Principal
from .sections import cost_section, check_quote, gaps_section, simulation_section, summary_section
from .text import NOTE_LIMIT, clean, note as clean_note

import datetime as _dt

DECISIONS = ("approve", "request_changes", "reject")
REASONS = {"approve": ("agree",), "request_changes": ("wrong_details", "wrong_price", "missing_something", "unclear"),
           "reject": ("not_for_us", "too_expensive", "wrong_company", "other")}
CONFIRMATIONS = ("gaps", "quote", "summary")  # the build state machine requires exactly these three
OUTCOMES = ("confirmed", "refused")
EARLIEST, LATEST = 1_577_836_800, 4_102_444_800
ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
TENANT_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CODE_RE = re.compile(r"^[A-Z]{2,4}-[0-9]{3}$")
SCHEMA = "owner_approval/1"
_WHO = contextvars.ContextVar("owner_approval_who", default=None)
_DATA = {"decision": {"decision", "reason", "note", "bpDigest", "quoteDigest", "gapDigest"},
         "forward_outcome": {"decisionSeq", "outcome", "code"}}


def _ident(v, what):
    if type(v) is not str or not ID_RE.fullmatch(v):
        raise OwnerApprovalError("OA-001", what)
    return v


def _tenant(v):
    if type(v) is not str or not TENANT_RE.fullmatch(v):
        raise OwnerApprovalError("OA-001", "tenant")
    return v


def _dig(v, what):
    if type(v) is not str or not DIGEST_RE.fullmatch(v):
        raise OwnerApprovalError("OA-001", what)
    return v


def _corrupt(why="record"):
    return OwnerApprovalError("OA-009", why)


class OwnerApproval:
    def __init__(self, *, identity, blueprints, quotes, gaps, holds, gate, content_digest, clock,
                 integrity_keys=None, key_id=None, audit=None):
        if any(p is None for p in (identity, blueprints, quotes, gaps, holds, gate, content_digest, clock)):
            raise OwnerApprovalError("OA-001", "ports")
        keys = integrity_keys if integrity_keys is not None else {}
        self._log = SealedLog(keys, key_id if key_id is not None else (list(keys)[-1] if type(keys) is dict and keys else ""))
        self._idn, self._bps, self._quotes, self._gaps, self._holds = identity, blueprints, quotes, gaps, holds
        self._gate, self._digest, self._clock, self._audit_cb = gate, content_digest, clock, audit

    # ----- clock, audit, actor ------------------------------------------------------------------------------
    def _now(self) -> int:
        try:
            v = self._clock()
        except Exception:
            raise OwnerApprovalError("OA-002", "host_clock") from None
        if type(v) is not int or not EARLIEST <= v <= LATEST:
            raise OwnerApprovalError("OA-002")
        return v

    def _audit(self, action, code, tenant, bp):
        if self._audit_cb is None:
            return
        try:
            self._audit_cb({"action": f"owner_approval.{action}", "code": code, "subject": _WHO.get(), "tenant": tenant, "blueprint": bp})
        except Exception:  # an audit failure never turns a refusal into an allow
            pass

    def _run(self, action, tenant_id, bp, fn):
        tok = _WHO.set(None)
        t, b = (tenant_id if type(tenant_id) is str else None), (bp if type(bp) is str else None)
        try:
            out = fn()
        except OwnerApprovalError as e:
            self._audit(action, e.code, t, b)
            raise
        except Exception:
            self._audit(action, "OA-001", t, b)
            raise OwnerApprovalError("OA-001", "unexpected") from None
        else:
            self._audit(action, "OK", t, b)
            return out
        finally:
            _WHO.reset(tok)

    def _actor(self, claims, t, *, gate) -> Principal:
        try:
            p = self._idn.resolve(claims, step_up=bool(gate))
        except OwnerApprovalError:
            raise
        except Exception:
            raise OwnerApprovalError("OA-003", "resolver") from None
        if type(p) is not Principal or type(p.subject) is not str or type(p.kind) is not str or type(p.realm) is not str \
                or type(p.roles) is not tuple or not all(type(r) is str for r in p.roles) or type(p.step_up) is not bool \
                or not ID_RE.fullmatch(p.subject):
            raise OwnerApprovalError("OA-003", "principal")
        _WHO.set(p.subject)
        if p.kind not in KINDS or p.realm not in REALMS or p.kind != "human":
            raise OwnerApprovalError("OA-003", "human")
        if p.realm != "tenant" or p.tenant_id is None:
            raise OwnerApprovalError("OA-003", "realm")
        if type(p.tenant_id) is not str or p.tenant_id != t:
            raise OwnerApprovalError("OA-011")
        if OWNER not in p.roles or CONFLICT_ROLES & set(p.roles):
            raise OwnerApprovalError("OA-003", "role")
        if gate and p.step_up is not True:
            raise OwnerApprovalError("OA-003", "step_up")
        return p

    # ----- the log: one rule set for write time and read time ---------------------------------------------
    def _fold(self, t, bp, records) -> dict:
        decisions, outcomes, last_at, seen, rejected = [], {}, 0, set(), set()
        for r in records:
            body = r["body"]
            try:
                typ, at, a, d = body["type"], body["at"], body["actor"], body["data"]
                if set(body) != {"type", "at", "actor", "data"} or typ not in _DATA or type(d) is not dict or set(d) != _DATA[typ] \
                        or type(at) is not int or not EARLIEST <= at <= LATEST or at < last_at:
                    raise _corrupt()
                if type(a) is not dict or set(a) != {"subject", "role", "kind", "realm"} or a["role"] != OWNER or a["kind"] != "human" \
                        or a["realm"] != "tenant" or type(a["subject"]) is not str or not ID_RE.fullmatch(a["subject"]):
                    raise _corrupt()
                last_at = at
                if typ == "decision":
                    dec, rsn, nt = d["decision"], d["reason"], d["note"]
                    if dec not in DECISIONS or rsn not in REASONS[dec] or type(nt) is not str or len(nt) > NOTE_LIMIT \
                            or clean_note(nt) != nt:
                        raise _corrupt()
                    for k in ("bpDigest", "quoteDigest", "gapDigest"):
                        if type(d[k]) is not str or not DIGEST_RE.fullmatch(d[k]):
                            raise _corrupt()
                    key = (a["subject"], d["bpDigest"], d["quoteDigest"])
                    if key in seen or (dec == "approve" and d["bpDigest"] in rejected):
                        raise _corrupt("order")
                    seen.add(key)
                    if dec == "reject":
                        rejected.add(d["bpDigest"])
                    decisions.append({"seq": r["seq"], "subject": a["subject"], "at": at, **d})
                else:
                    ref = next((x for x in decisions if x["seq"] == d["decisionSeq"]), None) if type(d["decisionSeq"]) is int else None
                    if ref is None or d["decisionSeq"] in outcomes or d["outcome"] not in OUTCOMES or type(d["code"]) is not str \
                            or not (d["code"] == "" or CODE_RE.fullmatch(d["code"]) or d["code"] in ("unconfirmed", "lost")) \
                            or ref["subject"] != a["subject"]:
                        raise _corrupt("outcome")
                    outcomes[d["decisionSeq"]] = d["outcome"]
            except OwnerApprovalError:
                raise
            except Exception:
                raise _corrupt("shape") from None
        for x in decisions:
            x["outcome"] = outcomes.get(x["seq"])
        return {"decisions": decisions}

    def _records(self, t, bp):
        recs = self._log.read(t, bp)
        return recs, self._fold(t, bp, recs)

    @staticmethod
    def _effective(folded, bp_digest, quote_digest) -> str:
        """rejected beats all; otherwise the last decision on this Blueprint digest wins. An approval counts only when
        the gate confirmed it AND it saw this very quote."""
        state = "awaiting"
        for d in folded["decisions"]:
            if d["bpDigest"] != bp_digest:
                continue
            if d["decision"] == "reject":
                return "rejected"
            if d["decision"] == "request_changes":
                state = "changes_requested"
            elif d["outcome"] == "confirmed":
                state = "approved" if d["quoteDigest"] == quote_digest else "quote_changed"
            elif d["outcome"] is None:
                state = "pending"
        return state

    # ----- host sources, re-derived on every call -------------------------------------------------------
    def _load(self, port, t, bp, what):
        try:
            v = port.load(t, bp)
        except Exception:
            raise OwnerApprovalError("OA-004", what) from None
        if type(v) is not dict:
            raise OwnerApprovalError("OA-004", what)
        return v

    def _context(self, t, bp, now) -> dict:
        content = self._load(self._bps, t, bp, "blueprint")
        meta = content.get("meta")
        if type(meta) is not dict or meta.get("id") != bp or type(meta.get("revision")) is not int:
            raise OwnerApprovalError("OA-004", "blueprint")
        try:
            dg = self._digest(content)
        except Exception:
            raise OwnerApprovalError("OA-004", "digest") from None
        if type(dg) is not str or not DIGEST_RE.fullmatch(dg):
            raise OwnerApprovalError("OA-004", "digest")
        quote, gap = self._load(self._quotes, t, bp, "quote"), self._load(self._gaps, t, bp, "gaps")
        blockers, qstate, cost = [], None, None
        try:
            qstate = check_quote(quote, content, gap, bp, _dt.datetime.fromtimestamp(now, _dt.timezone.utc))
            cost = cost_section(quote, qstate)
            gaps = gaps_section(gap)
            if qstate != "valid":
                blockers.append("quote")
        except OwnerApprovalError:
            blockers.append("quote")
            gaps = gaps_section(gap) if "requirements" in gap else None
        try:
            st = self._gate.status(t, bp)
        except Exception:
            raise OwnerApprovalError("OA-004", "gate") from None
        if type(st) is not dict or type(st.get("state")) is not str or type(st.get("contentChanged")) is not bool \
                or type(st.get("contentDigest")) is not str:
            raise OwnerApprovalError("OA-004", "gate")
        if st["contentChanged"] or st["contentDigest"] != dg:
            blockers.append("stale")   # the author must record the new content as a revision first
        try:
            held = self._holds.held(t, bp)
        except Exception:
            raise OwnerApprovalError("OA-013", "holds") from None
        if held is not False:          # True, or anything unexpected, blocks
            blockers.append("held")
        return {"content": content, "bpDigest": dg, "quote": quote, "quoteDigest": quote["digest"] if cost else None,
                "gapDigest": quote.get("inputs", {}).get("gap_report_digest") if cost else None, "cost": cost, "gaps": gaps,
                "machine": st["state"], "blockers": blockers}

    # ----- the screen -----------------------------------------------------------------------------------
    def review(self, claims, *, tenant_id, blueprint_id) -> dict:
        """The owner's screen data. Needs the owner (human, tenant) but no step-up: reading decides nothing."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            p = self._actor(claims, t, gate=False)
            now = self._now()
            ctx = self._context(t, bp, now)
            blockers = list(ctx["blockers"])
            try:
                recs, folded = self._records(t, bp)
            except OwnerApprovalError:
                recs, folded = (), {"decisions": []}
                blockers.append("integrity")
            eff = "integrity_error" if "integrity" in blockers else (
                self._effective(folded, ctx["bpDigest"], ctx["quoteDigest"]))
            mine = [d for d in folded["decisions"] if d["subject"] == p.subject and d["bpDigest"] == ctx["bpDigest"]
                    and d["quoteDigest"] == ctx["quoteDigest"]]
            if eff == "rejected":
                blockers.append("rejected")
            if ctx["machine"] not in ("draft", "owner_approved"):
                blockers.append("state")
            if mine:
                blockers.append("already_decided")
            can_approve = not blockers and ctx["machine"] == "draft"
            can_change = not (set(blockers) - {"rejected"}) and ctx["machine"] in ("draft", "owner_approved")
            if eff == "approved" and ctx["machine"] == "draft":
                eff = "out_of_sync"
            return {
                "schema": SCHEMA, "titleKey": "oa.title", "introKey": "oa.intro", "tenantId": t, "blueprintId": bp,
                "revision": ctx["content"]["meta"]["revision"], "blueprintDigest": ctx["bpDigest"], "quoteDigest": ctx["quoteDigest"],
                "buildState": ctx["machine"], "buildStateKey": f"oa.build.{ctx['machine']}",
                "state": {"value": eff, "labelKey": f"oa.state.{eff}"},
                "sections": [summary_section(ctx["content"]), ctx["cost"], ctx["gaps"], simulation_section()],
                "confirmations": [{"key": c, "labelKey": f"oa.confirm.{c}"} for c in CONFIRMATIONS],
                "decisions": [{"key": d, "labelKey": f"oa.decision.{d}", "noteRequired": False,
                               "reasons": [{"value": r, "labelKey": f"oa.reason.{d}.{r}"} for r in REASONS[d]],
                               "allowed": (can_approve if d == "approve" else can_change)} for d in DECISIONS],
                "canDecide": can_approve or can_change,
                "blockers": [{"key": b, "labelKey": f"oa.blocker.{b}"} for b in dict.fromkeys(blockers)],
                "noteLimit": NOTE_LIMIT, "stepUpNoticeKey": "oa.step_up_notice", "evidenceNoticeKey": "oa.notice.not_live",
                "history": [{"seq": d["seq"], "subject": d["subject"], "decision": d["decision"],
                             "decisionKey": f"oa.decision.{d['decision']}", "reasonKey": f"oa.reason.{d['decision']}.{d['reason']}",
                             "note": d["note"], "untrustedText": True, "at": d["at"], "outcome": d["outcome"],
                             "stale": d["bpDigest"] != ctx["bpDigest"] or d["quoteDigest"] != ctx["quoteDigest"]}
                            for d in folded["decisions"]],
            }
        out = self._run("review", tenant_id, blueprint_id, go)
        out["sections"] = [s for s in out["sections"] if s]
        return out

    def status(self, tenant_id, blueprint_id) -> dict:
        """Host-internal read of the verified approval state for the CURRENT draft (no principal)."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            ctx = self._context(t, bp, self._now())
            _, folded = self._records(t, bp)
            eff = self._effective(folded, ctx["bpDigest"], ctx["quoteDigest"])
            return {"tenantId": t, "blueprintId": bp, "blueprintDigest": ctx["bpDigest"], "quoteDigest": ctx["quoteDigest"],
                    "state": eff, "buildState": ctx["machine"], "blockers": ctx["blockers"]}
        return self._run("status", tenant_id, blueprint_id, go)

    # ----- the decision ---------------------------------------------------------------------------------
    def decide(self, claims, *, tenant_id, blueprint_id, decision, reason, note="", seen_blueprint_digest,
               seen_quote_digest, confirmations=()) -> dict:
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            if type(decision) is not str or decision not in DECISIONS or type(reason) is not str or reason not in REASONS[decision]:
                raise OwnerApprovalError("OA-001", "decision")
            if type(note) is not str or len(note) > NOTE_LIMIT * 4:
                raise OwnerApprovalError("OA-001", "note")
            text = clean_note(note)
            if len(text) > NOTE_LIMIT:
                raise OwnerApprovalError("OA-001", "note")
            seen_b, seen_q = _dig(seen_blueprint_digest, "seen"), _dig(seen_quote_digest, "seen")
            if decision == "approve" and (type(confirmations) not in (list, tuple) or tuple(sorted(confirmations)) != CONFIRMATIONS):
                raise OwnerApprovalError("OA-014")
            p = self._actor(claims, t, gate=True)
            at = self._now()
            ctx = self._context(t, bp, at)
            for code, key in (("OA-013", "held"), ("OA-012", "quote"), ("OA-006", "stale")):
                if key in ctx["blockers"]:
                    raise OwnerApprovalError(code)
            if ctx["bpDigest"] != seen_b or ctx["quoteDigest"] != seen_q:
                raise OwnerApprovalError("OA-006")
            if ctx["machine"] != "draft" and not (ctx["machine"] == "owner_approved" and decision != "approve"):
                raise OwnerApprovalError("OA-005")
            actor = {"subject": p.subject, "role": OWNER, "kind": "human", "realm": "tenant"}
            data = {"decision": decision, "reason": reason, "note": text, "bpDigest": ctx["bpDigest"],
                    "quoteDigest": ctx["quoteDigest"], "gapDigest": ctx["gapDigest"]}

            def check(existing):
                folded = self._fold(t, bp, existing)
                if existing and at < existing[-1]["body"]["at"]:
                    raise OwnerApprovalError("OA-002", "order")
                for d in folded["decisions"]:
                    if d["subject"] == p.subject and d["bpDigest"] == data["bpDigest"] and d["quoteDigest"] == data["quoteDigest"]:
                        raise OwnerApprovalError("OA-007")
                    if decision == "approve" and d["bpDigest"] == data["bpDigest"] and d["decision"] == "reject":
                        raise OwnerApprovalError("OA-008")
            rec = self._log.append(t, bp, {"type": "decision", "at": at, "actor": actor, "data": data}, check)
            self._forward(claims, t, bp, p, rec["seq"], decision, ctx)
            return self.review_state(t, bp)
        return self._run("decide", tenant_id, blueprint_id, go)

    def review_state(self, t, bp) -> dict:
        s = self.status(t, bp)
        return {k: s[k] for k in ("state", "buildState", "blueprintDigest", "quoteDigest")}

    def _outcome(self, t, bp, p, seq, outcome, code):
        actor = {"subject": p.subject, "role": OWNER, "kind": "human", "realm": "tenant"}
        self._log.append(t, bp, {"type": "forward_outcome", "at": self._now(), "actor": actor,
                                 "data": {"decisionSeq": seq, "outcome": outcome, "code": code}})

    def _forward(self, claims, t, bp, p, seq, decision, ctx):
        """Ask the machine's owner gate (approve) or roll back an earlier owner approval (reject, request_changes)."""
        if decision != "approve" and ctx["machine"] != "owner_approved":
            return  # the draft is already a draft; nothing to move (and no outcome is needed)
        try:
            if decision == "approve":
                self._gate.approve_owner(claims, tenant_id=t, blueprint_id=bp, confirmations=list(CONFIRMATIONS))
            else:
                self._gate.roll_back(claims, tenant_id=t, blueprint_id=bp, to_state="draft",
                                     reason="rejected" if decision == "reject" else "owner_reopened")
            st = self._gate.status(t, bp)
            want = "owner_approved" if decision == "approve" else "draft"
            if type(st) is not dict or st.get("state") != want or (decision == "approve" and st.get("contentDigest") != ctx["bpDigest"]):
                raise OwnerApprovalError("OA-015", "unconfirmed")
        except Exception as e:
            code = getattr(e, "detail", "") if isinstance(e, OwnerApprovalError) else getattr(e, "code", "")
            code = code if type(code) is str and (CODE_RE.fullmatch(code) or code == "unconfirmed") else ""
            self._outcome(t, bp, p, seq, "refused", code)
            raise OwnerApprovalError("OA-015", code) from None
        self._outcome(t, bp, p, seq, "confirmed", "")

    def reconcile(self, claims, *, tenant_id, blueprint_id) -> dict:
        """After a crash between the sealed decision and its outcome: settle each pending approval of THIS owner from the
        machine's own state (owner_approved on the same digest means confirmed, anything else means lost)."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            p = self._actor(claims, t, gate=False)
            ctx = self._context(t, bp, self._now())
            _, folded = self._records(t, bp)
            for d in folded["decisions"]:
                if d["subject"] == p.subject and d["decision"] == "approve" and d["outcome"] is None:
                    ok = ctx["machine"] == "owner_approved" and d["bpDigest"] == ctx["bpDigest"]
                    self._outcome(t, bp, p, d["seq"], "confirmed" if ok else "refused", "" if ok else "lost")
            return self.review_state(t, bp)
        return self._run("reconcile", tenant_id, blueprint_id, go)
