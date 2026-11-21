"""Fakes for the ports. The gate fake stands in for the build state machine (the real one is wired by the host, Q-432)."""
import copy
import hashlib
import json
from datetime import datetime, timezone

from owner_approval import OwnerApproval, Principal
from quote import default_price_book, generate_quote

NOW = int(datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc).timestamp())
KEYS = {"k1": b"a" * 32}
T, BP = "t-1", "bp-1"


def cdigest(content):
    return hashlib.sha256(b"test|" + json.dumps(content, sort_keys=True).encode()).hexdigest()


def make_bp(rev=1, extra=None):
    bp = {"meta": {"id": BP, "revision": rev}, "company": {"country": "SA", "labels": {"ar": "شركة", "en": "Acme"}},
          "entities": [{"id": "customer", "labels": {"ar": "عميل", "en": "Customer"}}],
          "workflows": [{"id": "sales_order", "labels": {"ar": "طلب", "en": "Sales order"}}], "reports": [], "roles": [], "components": []}
    if extra:
        bp.update(extra)
    return bp


def make_gap(bp, uncovered=True):
    reqs = [{"id": "entity:customer", "kind": "entity", "ref": "customer", "status": "covered",
             "match": {"component": "core.crm", "version": "1.0.0"}}]
    requests = []
    if uncovered:
        reqs.append({"id": "report:aging", "kind": "report", "ref": "aging", "status": "uncovered", "match": None})
        requests.append({"request_key": "k-aging", "requirement_id": "report:aging", "kind": "report", "ref": "aging", "kind_hint": "configurable"})
    c = {k: sum(1 for r in reqs if r["status"] == k) for k in ("covered", "partial", "uncovered")}
    return {"schema": "1", "environment": "sandbox", "blueprint": {"id": BP, "revision": bp["meta"]["revision"]},
            "summary": {"total": len(reqs), **c, "malformed_blueprint_items": 0, "library_entries_rejected": 0},
            "requirements": reqs, "component_requests": requests}


class World:
    """The host's stores: Blueprint, gap, quote, hold, and the machine's folded state."""
    def __init__(self):
        self.t = NOW
        self.held = False
        self.machine = "draft"
        self.regen()
        self.calls, self.gate_error, self.gate_noop = [], None, False
        self.owner, self.before_approve, self.timeout_after, self.rollback_error = None, None, False, None

    def regen(self, bp=None):
        self.bp = bp or make_bp()
        self.gap = make_gap(self.bp)
        self.quote = generate_quote(self.bp, self.gap, default_price_book(), now=datetime.fromtimestamp(self.t, timezone.utc))
        self.recorded = cdigest(self.bp)

    def revise(self, **extra):
        self.regen(make_bp(rev=self.bp["meta"]["revision"] + 1, extra=extra or {"workflows": []}))
        self.machine, self.owner = "draft", None


class Store:
    def __init__(self, w, key):
        self.w, self.key = w, key

    def load(self, t, bp):
        return copy.deepcopy(getattr(self.w, self.key))


class Holds:
    def __init__(self, w):
        self.w = w

    def held(self, t, bp):
        return self.w.held


class GateRefusal(Exception):
    def __init__(self, code):
        super().__init__("refused")
        self.code = code


class Claims:
    def __init__(self, subject="owner-1", kind="human", realm="tenant", tenant=T, roles=("owner",), step_up=True, uses=None):
        self.subject, self.kind, self.realm, self.tenant, self.roles = subject, kind, realm, tenant, tuple(roles)
        self.uses = uses if uses is not None else (10 ** 6 if step_up else 0)   # fresh MFA step-ups left (ADR-0047: single use)


class Identity:
    """Builds the Principal from claims; consumes one step-up per `step_up=True` call, like the real adapter."""
    def __init__(self):
        self.override = None

    def resolve(self, claims, *, step_up):
        if self.override is not None:
            return self.override(claims, step_up) if callable(self.override) else self.override
        if step_up:
            if claims.uses <= 0:
                raise RuntimeError("no step-up")
            claims.uses -= 1
        return Principal(claims.subject, claims.kind, claims.realm, claims.tenant if claims.realm == "tenant" else None,
                         claims.roles, bool(step_up))


class Gate:
    """Mirrors the build state machine's owner gate after the ADR-0050 amendment: it resolves the caller with a step-up
    itself, computes the digest itself, and asks the owner-approvals port (`svc.verify`) before moving."""
    def __init__(self, w, ident):
        self.w, self.ident, self.svc = w, ident, None

    def status(self, t, bp):
        return {"state": self.w.machine, "contentDigest": self.w.recorded, "contentChanged": self.w.recorded != cdigest(self.w.bp),
                "owner": copy.deepcopy(self.w.owner)}

    def _human(self, claims):
        p = self.ident.resolve(claims, step_up=True)
        if p.kind != "human" or p.step_up is not True:
            raise GateRefusal("BS-003")
        return p

    def approve_owner(self, claims, *, tenant_id, blueprint_id, confirmations, expected_digest, quote_digest):
        self.w.calls.append(("approve_owner", tenant_id, blueprint_id, list(confirmations)))
        p = self._human(claims)
        if self.w.before_approve:
            self.w.before_approve()
        if self.w.gate_error:
            raise self.w.gate_error
        dg = cdigest(self.w.bp)
        if expected_digest != dg:
            raise GateRefusal("BS-008")
        if self.w.machine != "draft":
            raise GateRefusal("BS-005")
        ev = self.svc.verify(tenant_id, blueprint_id, dg, quote_digest, p.subject)
        if ev["quoteCurrent"] is not True:
            raise GateRefusal("BS-008")
        if ev["blocked"] or ev["approvedBy"] != p.subject:
            raise GateRefusal("BS-006")
        if not self.w.gate_noop:
            self.w.machine, self.w.recorded = "owner_approved", dg
            self.w.owner = {"actor": p.subject, "digest": dg, "quoteDigest": quote_digest}
        if self.w.timeout_after:
            raise TimeoutError("late")

    def roll_back(self, claims, *, tenant_id, blueprint_id, to_state, reason):
        self.w.calls.append(("roll_back", to_state, reason))
        self._human(claims)
        if self.w.rollback_error:
            raise self.w.rollback_error
        if self.w.gate_error:
            raise self.w.gate_error
        self.w.machine, self.w.owner = to_state, None


def build(w=None, **over):
    w = w or World()
    ident = Identity()
    gate = Gate(w, ident)
    kw = dict(identity=ident, blueprints=Store(w, "bp"), quotes=Store(w, "quote"), gaps=Store(w, "gap"), holds=Holds(w),
              gate=gate, content_digest=cdigest, clock=lambda: w.t, integrity_keys=dict(KEYS), key_id="k1")
    kw.update(over)
    svc = OwnerApproval(**kw)
    gate.svc = svc
    return svc, w, ident


def seen(svc, claims=None, t=T):
    v = svc.review(claims or Claims(), tenant_id=t, blueprint_id=BP)
    return v["blueprintDigest"], v["quoteDigest"] or "0" * 64


def approve(svc, claims=None, **kw):
    sb, sq = seen(svc, claims)
    args = dict(tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", note="", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"])
    args.update(kw)
    return svc.decide(claims or Claims(), **args)
