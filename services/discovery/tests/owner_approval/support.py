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

    def regen(self, bp=None):
        self.bp = bp or make_bp()
        self.gap = make_gap(self.bp)
        self.quote = generate_quote(self.bp, self.gap, default_price_book(), now=datetime.fromtimestamp(self.t, timezone.utc))
        self.recorded = cdigest(self.bp)

    def revise(self, **extra):
        self.regen(make_bp(rev=self.bp["meta"]["revision"] + 1, extra=extra or {"workflows": []}))
        self.machine = "draft"


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


class Gate:
    def __init__(self, w):
        self.w = w

    def status(self, t, bp):
        return {"state": self.w.machine, "contentDigest": self.w.recorded, "contentChanged": self.w.recorded != cdigest(self.w.bp)}

    def approve_owner(self, claims, *, tenant_id, blueprint_id, confirmations):
        self.w.calls.append(("approve_owner", tenant_id, blueprint_id, list(confirmations)))
        if self.w.gate_error:
            raise self.w.gate_error
        if not self.w.gate_noop:
            self.w.machine = "owner_approved"

    def roll_back(self, claims, *, tenant_id, blueprint_id, to_state, reason):
        self.w.calls.append(("roll_back", to_state, reason))
        if self.w.gate_error:
            raise self.w.gate_error
        self.w.machine = to_state


class GateRefusal(Exception):
    def __init__(self, code):
        super().__init__("refused")
        self.code = code


class Claims:
    def __init__(self, subject="owner-1", kind="human", realm="tenant", tenant=T, roles=("owner",), step_up=True):
        self.subject, self.kind, self.realm, self.tenant, self.roles, self.step_up = subject, kind, realm, tenant, tuple(roles), step_up


class Identity:
    """Builds the Principal from claims; consumes a step-up only when asked, like the real adapter."""
    def __init__(self):
        self.override = None

    def resolve(self, claims, *, step_up):
        if self.override is not None:
            return self.override(claims, step_up) if callable(self.override) else self.override
        if step_up and not claims.step_up:
            raise RuntimeError("no step-up")
        return Principal(claims.subject, claims.kind, claims.realm, claims.tenant if claims.realm == "tenant" else None,
                         claims.roles, bool(step_up))


def build(w=None, **over):
    w = w or World()
    ident = Identity()
    kw = dict(identity=ident, blueprints=Store(w, "bp"), quotes=Store(w, "quote"), gaps=Store(w, "gap"), holds=Holds(w),
              gate=Gate(w), content_digest=cdigest, clock=lambda: w.t, integrity_keys=dict(KEYS), key_id="k1")
    kw.update(over)
    return OwnerApproval(**kw), w, ident


def seen(svc, claims=None, t=T):
    v = svc.review(claims or Claims(), tenant_id=t, blueprint_id=BP)
    return v["blueprintDigest"], v["quoteDigest"] or "0" * 64


def approve(svc, claims=None, **kw):
    sb, sq = seen(svc, claims)
    args = dict(tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", note="", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"])
    args.update(kw)
    return svc.decide(claims or Claims(), **args)
