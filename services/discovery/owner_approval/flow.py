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
- The machine does not trust this flow either way: its owner gate calls `verify` (the port below) and refuses without a
  current sealed approval by the calling owner for the digest IT computed and the quote digest, and every later gate
  re-checks it (ADR-0050 amendment). A rejection, a request for changes on a version, a changed quote or a hold stops it.
- Multi-owner rule (Q-540): any rejection blocks the Blueprint digest for good; any request for changes blocks that
  version (digest and quote) until the draft or the quote changes; otherwise one owner's approval is enough.
- One step-up per decision (Q-520): when the machine's gate is called it consumes the step-up, otherwise this flow does.
  A decision the gate refused does not count: the owner may approve again (explicit states: sealed decision, then the
  outcome confirmed or refused). Rejections and requests for changes are final.
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
from .text import NOTE_LIMIT, note as clean_note

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
MAX_SKEW = 300  # seconds a record may be behind the newest one (host clock steps), per record
MAX_TRIES = 5   # decisions one owner may seal on one version (refused approvals included)
_DATA = {"decision": {"decision", "reason", "note", "bpDigest", "quoteDigest", "gapDigest", "forward", "rollbacks"},
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


class _Settled(Exception):
    """Internal: the decision already has an outcome (another call settled it first)."""


class OwnerApproval:
    def __init__(self, *, identity, blueprints, quotes, gaps, holds, gate, content_digest, clock,
                 integrity_keys=None, key_id=None, audit=None, store=None, ephemeral=False):
        if any(p is None for p in (identity, blueprints, quotes, gaps, holds, gate, content_digest, clock)):
            raise OwnerApprovalError("OA-001", "ports")
        if store is None and ephemeral is not True:   # no durable store, no service: a restart must not forget a rejection
            raise OwnerApprovalError("OA-010", "store")
        keys = integrity_keys if integrity_keys is not None else {}
        self._log = SealedLog(keys, key_id if key_id is not None else (list(keys)[-1] if type(keys) is dict and keys else ""),
                              store=store)
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
        # only validated identifiers reach the audit sink (raw caller strings never do)
        t = tenant_id if type(tenant_id) is str and TENANT_RE.fullmatch(tenant_id) else None
        b = bp if type(bp) is str and ID_RE.fullmatch(bp) else None
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
        decisions, outcomes, max_at, latest, rejected, changes = [], {}, 0, {}, set(), set()
        for r in records:
            body = r["body"]
            try:
                typ, at, a, d = body["type"], body["at"], body["actor"], body["data"]
                if set(body) != {"type", "at", "actor", "data"} or typ not in _DATA or type(d) is not dict or set(d) != _DATA[typ] \
                        or type(at) is not int or not EARLIEST <= at <= LATEST or at < max_at - MAX_SKEW:
                    raise _corrupt()   # per record: a clock a few seconds behind is tolerated, a far-back one is not
                if type(a) is not dict or set(a) != {"subject", "role", "kind", "realm"} or a["role"] != OWNER or a["kind"] != "human" \
                        or a["realm"] != "tenant" or type(a["subject"]) is not str or not ID_RE.fullmatch(a["subject"]):
                    raise _corrupt()
                max_at = max(max_at, at)
                if typ == "decision":
                    dec, rsn, nt = d["decision"], d["reason"], d["note"]
                    if dec not in DECISIONS or rsn not in REASONS[dec] or type(nt) is not str or len(nt) > NOTE_LIMIT \
                            or clean_note(nt) != nt or d["forward"] not in ("none", "gate") or (dec == "approve" and d["forward"] != "gate"):
                        raise _corrupt()
                    for k in ("bpDigest", "quoteDigest", "gapDigest"):
                        if type(d[k]) is not str or not DIGEST_RE.fullmatch(d[k]):
                            raise _corrupt()
                    if type(d["rollbacks"]) is not int or d["rollbacks"] < 0:
                        raise _corrupt()
                    key = (a["subject"], d["bpDigest"], d["quoteDigest"])
                    prev = latest.get(key)
                    # one decision per owner per version; only an approval the gate REFUSED may be tried again
                    if prev is not None and not (prev["decision"] == "approve" and outcomes.get(prev["seq"], (None,))[0] == "refused"):
                        raise _corrupt("order")
                    if dec == "approve" and (d["bpDigest"] in rejected or (d["bpDigest"], d["quoteDigest"]) in changes):
                        raise _corrupt("order")
                    if dec == "reject":
                        rejected.add(d["bpDigest"])
                    elif dec == "request_changes":
                        changes.add((d["bpDigest"], d["quoteDigest"]))
                    x = {"seq": r["seq"], "subject": a["subject"], "at": at, **d}
                    latest[key] = x
                    decisions.append(x)
                else:
                    ref = next((x for x in decisions if x["seq"] == d["decisionSeq"]), None) if type(d["decisionSeq"]) is int else None
                    if ref is None or ref["forward"] != "gate" or d["decisionSeq"] in outcomes or d["outcome"] not in OUTCOMES \
                            or type(d["code"]) is not str or not (d["code"] == "" or CODE_RE.fullmatch(d["code"]) or d["code"] in ("unconfirmed", "lost")) \
                            or ref["subject"] != a["subject"]:
                        raise _corrupt("outcome")
                    outcomes[d["decisionSeq"]] = (d["outcome"], d["code"])
            except OwnerApprovalError:
                raise
            except Exception:
                raise _corrupt("shape") from None
        for x in decisions:
            x["outcome"], x["outcomeCode"] = outcomes.get(x["seq"], (None, None))
        return {"decisions": decisions, "latest": latest, "rejected": rejected, "changes": changes, "max_at": max_at}

    @staticmethod
    def _tries(folded, subject, bp_digest, quote_digest) -> int:
        """Decisions that count toward MAX_TRIES: a refusal with no gate code (a timeout) is the host's failure, not a try."""
        return sum(1 for x in folded["decisions"] if x["subject"] == subject and x["bpDigest"] == bp_digest
                   and x["quoteDigest"] == quote_digest and not (x["outcome"] == "refused" and x["outcomeCode"] == ""))

    def _records(self, t, bp):
        recs = self._log.read(t, bp)
        return recs, self._fold(t, bp, recs)

    @staticmethod
    def _effective(folded, bp_digest, quote_digest) -> str:
        """rejected beats all; a request for changes on this very version (by anyone) blocks; otherwise an approval of
        this version counts only when the gate confirmed it. An approval that saw another quote is `quote_changed`."""
        if bp_digest in folded["rejected"]:
            return "rejected"
        if (bp_digest, quote_digest) in folded["changes"]:
            return "changes_requested"
        state = "awaiting"
        for d in folded["decisions"]:
            if d["bpDigest"] != bp_digest or d["decision"] != "approve":
                continue
            if d["outcome"] == "confirmed":
                if d["quoteDigest"] == quote_digest:
                    return "approved"
                state = "quote_changed"
            elif d["outcome"] is None and d["quoteDigest"] == quote_digest:
                state = "pending" if state != "quote_changed" else state
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
            qstate = None          # a quote or gap report that does not check out has no state at all
            try:
                gaps = gaps_section(gap)
            except OwnerApprovalError:
                gaps = None
        try:
            st = self._gate.status(t, bp)
        except Exception:
            raise OwnerApprovalError("OA-004", "gate") from None
        if type(st) is not dict or type(st.get("state")) is not str or type(st.get("contentChanged")) is not bool \
                or type(st.get("contentDigest")) is not str:
            raise OwnerApprovalError("OA-004", "gate")
        owner = st.get("owner")
        if owner is not None and (type(owner) is not dict or type(owner.get("actor")) is not str or type(owner.get("digest")) is not str
                                  or type(owner.get("quoteDigest")) is not str):
            raise OwnerApprovalError("OA-004", "gate")
        if type(st.get("rollbacks")) is not int or st["rollbacks"] < 0:
            raise OwnerApprovalError("OA-004", "gate")   # needed to tell a pending approval from one a rollback spent
        if st["contentChanged"] or st["contentDigest"] != dg:
            blockers.append("stale")   # the author must record the new content as a revision first
        try:
            held = self._holds.held(t, bp)
        except Exception:
            raise OwnerApprovalError("OA-013", "holds") from None
        if held is not False:          # True, or anything unexpected, blocks
            blockers.append("held")
        summary = summary_section(content)
        if summary["moreItems"] or (gaps and gaps["moreItems"]) or (cost and cost["unpricedCount"] > len(cost["unpriced"])):
            blockers.append("too_large")   # never let the owner approve what the screen does not list in full
        return {"content": content, "summary": summary, "quoteState": qstate if cost else None,
                "bpDigest": dg, "quote": quote, "quoteDigest": quote["digest"] if cost else None,
                "gapDigest": quote.get("inputs", {}).get("gap_report_digest") if cost else None, "cost": cost, "gaps": gaps,
                "machine": st["state"], "machineOwner": owner, "rollbacks": st["rollbacks"], "blockers": blockers}

    # ----- the screen -----------------------------------------------------------------------------------
    def review(self, claims, *, tenant_id, blueprint_id) -> dict:
        """The owner's screen data. Needs the owner (human, tenant) but no step-up: reading decides nothing."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            p = self._actor(claims, t, gate=False)
            ctx = self._context(t, bp, self._now())
            blockers = list(ctx["blockers"])
            try:
                recs, folded = self._records(t, bp)
            except OwnerApprovalError:
                folded = {"decisions": [], "rejected": set(), "changes": set()}
                blockers.append("integrity")
            integrity = "integrity" in blockers
            eff = "integrity_error" if integrity else self._effective(folded, ctx["bpDigest"], ctx["quoteDigest"])
            mine = [d for d in folded["decisions"] if d["subject"] == p.subject and d["bpDigest"] == ctx["bpDigest"]
                    and d["quoteDigest"] == ctx["quoteDigest"] and not (d["decision"] == "approve" and d["outcome"] == "refused")]
            m = ctx["machine"]
            if eff == "rejected":
                blockers.append("rejected")
            if eff == "changes_requested":
                blockers.append("changes_requested")
            if m == "live":
                blockers.append("state")
            if mine:
                blockers.append("already_decided")
            if not integrity and self._tries(folded, p.subject, ctx["bpDigest"], ctx["quoteDigest"]) >= MAX_TRIES:
                blockers.append("tries")    # decide refuses every decision on this version past the cap (OA-007)
            base = set(blockers) - {"rejected", "changes_requested", "already_decided", "state", "too_large", "quote"}
            can_approve = not blockers and m == "draft"
            can_change = not base and not mine and m != "live" and ctx["quoteState"] in ("valid", "expired")
            if m != "draft" and eff not in ("approved", "integrity_error", "pending"):
                eff = "out_of_sync"     # the machine is past draft without a current approval of THIS version
            elif m == "draft" and eff == "approved":
                eff = "approval_spent"  # the plan was sent back to draft; this version needs a new version to approve again
            return {
                "schema": SCHEMA, "titleKey": "oa.title", "introKey": "oa.intro", "tenantId": t, "blueprintId": bp,
                "revision": ctx["content"]["meta"]["revision"], "blueprintDigest": ctx["bpDigest"], "quoteDigest": ctx["quoteDigest"],
                "buildState": m, "buildStateKey": f"oa.build.{m}",
                "state": {"value": eff, "labelKey": f"oa.state.{eff}"},
                "sections": [ctx["summary"], ctx["cost"], ctx["gaps"], simulation_section()],
                "confirmations": [{"key": c, "labelKey": f"oa.confirm.{c}"} for c in CONFIRMATIONS],
                "decisions": [{"key": d, "labelKey": f"oa.decision.{d}", "noteRequired": False,
                               "reasons": [{"value": r, "labelKey": f"oa.reason.{d}.{r}"} for r in REASONS[d]],
                               "allowed": (can_approve if d == "approve" else can_change)} for d in DECISIONS],
                "canDecide": can_approve or can_change,
                "blockers": [{"key": b, "labelKey": f"oa.blocker.{b}"} for b in dict.fromkeys(blockers)],
                "noteLimit": NOTE_LIMIT, "stepUpNoticeKey": "oa.step_up_notice", "evidenceNoticeKey": "oa.notice.not_live",
                "commitNoticeKey": "oa.notice.not_order",
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
            m = ctx["machine"]
            if m != "draft" and eff not in ("approved", "pending"):
                eff = "out_of_sync"
            elif m == "draft" and eff == "approved":
                eff = "approval_spent"
            return {"tenantId": t, "blueprintId": bp, "blueprintDigest": ctx["bpDigest"], "quoteDigest": ctx["quoteDigest"],
                    "state": eff, "buildState": m, "blockers": ctx["blockers"]}
        return self._run("status", tenant_id, blueprint_id, go)

    def verify(self, tenant_id, blueprint_id, content_digest, quote_digest, subject) -> dict:
        """The owner-approvals PORT the build state machine calls (ADR-0050 amendment). Re-derived from the verified log and
        the live sources on every call: `approvedBy` is `subject` only when that owner has a sealed approval (not refused)
        of exactly this content digest and quote digest and the content is still this digest; `blocked` when anything
        stops the build (a rejection of this content, a request for changes on this version, a hold); `quoteCurrent`
        when this quote is still the live, valid one."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            cd, qd, who = _dig(content_digest, "digest"), _dig(quote_digest, "quote_digest"), _ident(subject, "subject")
            ctx = self._context(t, bp, self._now())
            _, folded = self._records(t, bp)
            same, past_draft = ctx["bpDigest"] == cd, ctx["machine"] != "draft"
            # a confirmed approval moved the machine once; back at draft it is spent (a rollback happened since). One with no
            # outcome yet (in flight, or left by a crash) counts only when no rollback happened since it was sealed: it
            # records the machine's rollback count it saw (a count, not a time, so a same-second rollback is told apart).
            rb = ctx["rollbacks"]
            ok = same and any(d["subject"] == who and d["decision"] == "approve" and d["bpDigest"] == cd and d["quoteDigest"] == qd
                              and ((d["outcome"] is None and d["rollbacks"] == rb) or (d["outcome"] == "confirmed" and past_draft))
                              for d in folded["decisions"])
            blocked = cd in folded["rejected"] or (cd, qd) in folded["changes"] or "held" in ctx["blockers"]
            # validity counts at approval time only: past draft, the same quote (bound to this content and gap report,
            # arithmetic re-derived) stays current after it expires; at draft it must be valid now
            quote_ok = ctx["quoteState"] == "valid" or (past_draft and ctx["quoteState"] == "expired")
            return {"tenantId": t, "blueprintId": bp, "contentDigest": cd, "quoteDigest": qd, "approvedBy": who if ok else None,
                    "blocked": blocked, "quoteCurrent": same and ctx["quoteDigest"] == qd and quote_ok}
        return self._run("verify", tenant_id, blueprint_id, go)

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
            p = self._actor(claims, t, gate=False)
            at = self._now()
            ctx = self._context(t, bp, at)
            for code, key in (("OA-013", "held"), ("OA-012", "quote"), ("OA-006", "stale"), ("OA-017", "too_large")):
                # an expired quote or a plan too large to list stops an approval only; the owner may still say no
                if key in ctx["blockers"] and (decision == "approve" or key not in ("quote", "too_large")
                                               or (key == "quote" and ctx["quoteState"] != "expired")):
                    raise OwnerApprovalError(code)
            if ctx["bpDigest"] != seen_b or ctx["quoteDigest"] != seen_q:
                raise OwnerApprovalError("OA-006")
            m = ctx["machine"]
            if m == "live" or (decision == "approve" and m != "draft"):
                raise OwnerApprovalError("OA-005")
            # One step-up per decision (Q-520): when the machine's own gate is called it consumes the step-up; when no
            # gate call follows, this flow consumes it here. A single step-up never has to cover two calls.
            forward = decision == "approve" or m != "draft"
            if not forward:
                p = self._actor(claims, t, gate=True)
            actor = {"subject": p.subject, "role": OWNER, "kind": "human", "realm": "tenant"}
            data = {"decision": decision, "reason": reason, "note": text, "bpDigest": ctx["bpDigest"], "quoteDigest": ctx["quoteDigest"],
                    "gapDigest": ctx["gapDigest"], "forward": "gate" if forward else "none", "rollbacks": ctx["rollbacks"]}

            def check(existing):
                folded = self._fold(t, bp, existing)
                if at < folded["max_at"] - MAX_SKEW:
                    raise OwnerApprovalError("OA-002", "order")
                prev = folded["latest"].get((p.subject, data["bpDigest"], data["quoteDigest"]))
                if prev is not None and not (prev["decision"] == "approve" and prev["outcome"] == "refused"):
                    raise OwnerApprovalError("OA-007")
                if self._tries(folded, p.subject, data["bpDigest"], data["quoteDigest"]) >= MAX_TRIES:
                    raise OwnerApprovalError("OA-007", "tries")   # bounded log growth from refused approvals
                if decision == "approve":
                    if data["bpDigest"] in folded["rejected"]:
                        raise OwnerApprovalError("OA-008")
                    if (data["bpDigest"], data["quoteDigest"]) in folded["changes"]:
                        raise OwnerApprovalError("OA-016")
            rec = self._log.append(t, bp, {"type": "decision", "at": at, "actor": actor, "data": data}, check)
            if forward:
                self._forward(claims, t, bp, p, rec["seq"], decision, ctx)
            return self.review_state(t, bp)
        return self._run("decide", tenant_id, blueprint_id, go)

    def review_state(self, t, bp) -> dict:
        s = self.status(t, bp)
        return {k: s[k] for k in ("state", "buildState", "blueprintDigest", "quoteDigest")}

    def _outcome(self, t, bp, p, seq, outcome, code) -> str:
        """Seal the outcome of decision `seq` under the same fold rules as a decision (skew, one outcome per decision);
        return the outcome now on record. A second outcome (a racing reconcile) is refused, never appended."""
        actor = {"subject": p.subject, "role": OWNER, "kind": "human", "realm": "tenant"}
        at, settled = self._now(), []

        def check(existing):
            folded = self._fold(t, bp, existing)
            if at < folded["max_at"] - MAX_SKEW:
                raise OwnerApprovalError("OA-002", "order")
            ref = next((x for x in folded["decisions"] if x["seq"] == seq), None)
            if ref is None or ref["forward"] != "gate" or ref["subject"] != p.subject:
                raise OwnerApprovalError("OA-001", "outcome")
            if ref["outcome"] is not None:
                settled.append(ref["outcome"])
                raise _Settled()
        try:
            self._log.append(t, bp, {"type": "forward_outcome", "at": at, "actor": actor,
                                     "data": {"decisionSeq": seq, "outcome": outcome, "code": code}}, check)
        except _Settled:
            return settled[0]
        return outcome

    @staticmethod
    def _owner_matches(st, subject, bp_digest, quote_digest) -> bool:
        o = st.get("owner") if type(st) is dict else None
        return st.get("state") != "draft" and type(o) is dict and o.get("actor") == subject and o.get("digest") == bp_digest \
            and o.get("quoteDigest") == quote_digest

    def _forward(self, claims, t, bp, p, seq, decision, ctx):
        """Ask the machine's owner gate (approve) or roll the build back to draft (reject, request_changes after the draft
        moved on). The machine re-derives the approval through `verify`; a refusal or an unconfirmed answer is sealed as
        `refused` and does not count, and the owner may try again (an approval) because no decision took effect."""
        try:
            if decision == "approve":
                self._gate.approve_owner(claims, tenant_id=t, blueprint_id=bp, confirmations=list(CONFIRMATIONS),
                                         expected_digest=ctx["bpDigest"], quote_digest=ctx["quoteDigest"])
            else:
                self._gate.roll_back(claims, tenant_id=t, blueprint_id=bp, to_state="draft",
                                     reason="rejected" if decision == "reject" else "owner_reopened")
            st = self._gate.status(t, bp)
            if decision == "approve":
                if not self._owner_matches(st, p.subject, ctx["bpDigest"], ctx["quoteDigest"]):
                    raise OwnerApprovalError("OA-015", "unconfirmed")
            elif type(st) is not dict or st.get("state") != "draft":
                raise OwnerApprovalError("OA-015", "unconfirmed")
        except Exception as e:
            code = getattr(e, "detail", "") if isinstance(e, OwnerApprovalError) else getattr(e, "code", "")
            code = code if type(code) is str and (CODE_RE.fullmatch(code) or code == "unconfirmed") else ""
            try:  # a timeout may follow a success: settle from the machine's own recorded owner approval
                st = self._gate.status(t, bp)
            except Exception:
                st = None
            if decision == "approve" and st is not None and self._owner_matches(st, p.subject, ctx["bpDigest"], ctx["quoteDigest"]):
                if self._outcome(t, bp, p, seq, "confirmed", "") != "confirmed":
                    raise OwnerApprovalError("OA-015", "settled") from None
                return
            self._outcome(t, bp, p, seq, "refused", code)
            raise OwnerApprovalError("OA-015", code) from None
        if self._outcome(t, bp, p, seq, "confirmed", "") != "confirmed":
            raise OwnerApprovalError("OA-015", "settled")   # a reconcile sealed it refused first: fail closed

    def reconcile(self, claims, *, tenant_id, blueprint_id) -> dict:
        """After a crash between a sealed decision and its outcome: settle each pending forwarded decision of THIS owner from
        the machine's own record. An approval is confirmed only when the machine's owner approval names this owner, this
        content digest and this quote digest (never someone else's); a rollback only when the machine is at draft."""
        def go():
            t, bp = _tenant(tenant_id), _ident(blueprint_id, "blueprint")
            p = self._actor(claims, t, gate=False)
            ctx = self._context(t, bp, self._now())
            _, folded = self._records(t, bp)
            st = {"state": ctx["machine"], "owner": ctx["machineOwner"]}
            for d in folded["decisions"]:
                if d["subject"] == p.subject and d["forward"] == "gate" and d["outcome"] is None:
                    if d["decision"] == "approve":
                        ok = self._owner_matches(st, p.subject, d["bpDigest"], d["quoteDigest"]) and d["bpDigest"] == ctx["bpDigest"]
                    else:
                        ok = st["state"] == "draft"
                    self._outcome(t, bp, p, d["seq"], "confirmed" if ok else "refused", "" if ok else "lost")
            return self.review_state(t, bp)
        return self._run("reconcile", tenant_id, blueprint_id, go)
