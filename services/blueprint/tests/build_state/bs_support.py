"""Fakes for the ports and a World that drives a build. Synthetic data only."""
import copy
import datetime as dt
import hashlib
import json
from dataclasses import replace

import sim_helpers as h
from build_state import (BuildStateError, BuildStateMachine, Principal, SignOffLedger, content_digest)
from simulator import review, signoff

T = h.TENANT
BP = "bp-demo"
KEYS = {"k1": b"k" * 32, "k2": b"m" * 32}
UTC = dt.timezone.utc
T0 = dt.datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


def content(**extra):
    return {"meta": {"id": BP, "revision": 3, "buildState": "draft"}, "company": {"name": "Demo"}, **extra}


def P(subject, kind, realm, roles, tenant=None, step_up=True):
    return Principal(subject=subject, kind=kind, realm=realm, tenant_id=tenant, roles=tuple(roles), step_up=step_up)


class Identity:
    def __init__(self):
        self.table = {
            "author": P("u-author", "human", "staff", ["author"]),
            "agent": P("agent-1", "agent", "staff", ["author", "build_runner", "owner", "team_reviewer"]),
            "service": P("svc-1", "service", "staff", ["build_runner", "team_reviewer"]),
            "owner": P("u-owner", "human", "tenant", ["owner"], tenant=T),
            "owner2": P("u-owner2", "human", "tenant", ["owner"], tenant=T),
            "rev": P("u-rev", "human", "staff", ["team_reviewer"]),
            "rev2": P("u-rev2", "human", "staff", ["team_reviewer"]),
            "runner": P("svc-run", "service", "staff", ["build_runner"]),
        }
        self.calls = []

    def resolve(self, claims, *, step_up):
        self.calls.append((claims, step_up))
        p = self.table[claims]
        if step_up and not p.step_up:
            raise RuntimeError("no step-up")
        return replace(p, step_up=bool(step_up and p.step_up))


class Blueprints:
    def __init__(self):
        self.d = {(T, BP): content()}

    def load(self, t, bp):
        return copy.deepcopy(self.d[(t, bp)])


def qdigest(c):
    return hashlib.sha256(b"queue|" + json.dumps(c, sort_keys=True).encode()).hexdigest()


class Reviews:
    """Mimics PLT-013 `verify_evidence` output."""
    def __init__(self):
        self.approved = None
        self.item, self.seq, self.head, self.by = "item-1", 7, "head-seal-1", "u-reviewer-x"
        self.hold, self.patch, self.raises, self.override = False, {}, False, None
        self.newest_override, self.newest_item, self.newest_patch = None, None, {}
        self.calls = []

    def approve(self, c):
        self.approved = qdigest(c)

    def newest(self, t, ref, c):
        """Mimics `team_reviewed_evidence`: the newest blueprint_draft item for the subject."""
        self.newest_calls = getattr(self, "newest_calls", 0) + 1
        if self.newest_override is not None:
            return self.newest_override
        part = {"itemId": self.newest_item or self.item, "state": "approved", "stale": qdigest(c) != self.approved, "seq": self.seq,
                "headSeal": self.head, "eligible": self.approved is not None and qdigest(c) == self.approved and not self.hold}
        part.update(self.newest_patch)
        return {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": t, "subjectRef": ref,
                "items": {"blueprint_draft": part}, "missing": [], "eligible": part["eligible"]}

    def verify(self, t, item, c, pin_seq, pin_head):
        self.calls.append((t, item, pin_seq, pin_head))
        if self.raises:
            raise RuntimeError("down")
        if self.override is not None:
            return self.override
        ev = {"gate": "team_reviewed", "consumer": "BPL-020", "evidenceOnly": True, "tenantId": t, "itemId": item,
              "kind": "blueprint_draft", "subjectRef": BP, "revision": 1, "contentDigest": self.approved or "0" * 64,
              "seq": self.seq, "headSeal": self.head, "hold": self.hold, "state": "approved", "stale": qdigest(c) != self.approved,
              "eligible": self.approved is not None and qdigest(c) == self.approved and not self.hold,
              "approvedBy": self.by, "decidedAt": 1, "checklist": {}}
        if item != self.item:
            ev.update(state="pending", eligible=False)
        ev["pinCurrent"] = (pin_seq, pin_head) == (self.seq, self.head)
        if not ev["pinCurrent"]:
            ev["eligible"] = False
        ev.update(self.patch)
        return ev


class Sims:
    def __init__(self):
        self.d = {}

    def put(self, r):
        self.d[(r["tenantId"], r["simulationId"])] = copy.deepcopy(r)

    def load(self, t, sim):
        return copy.deepcopy(self.d[(t, sim)])


class Engine:
    def __init__(self):
        self.script, self.calls, self.statuses, self.status_script = [], [], {}, []

    def apply(self, t, kind, key, digest):
        self.calls.append((t, kind, key, digest))
        r = self.script.pop(0) if self.script else "confirmed"
        if isinstance(r, BaseException):
            raise r
        return r

    def status(self, t, key):
        r = self.status_script.pop(0) if self.status_script else "unknown"
        if isinstance(r, BaseException):
            raise r
        return r


QD = hashlib.sha256(b"quote-1").hexdigest()


class OwnerApprovals:
    """Mimics the DSC-009 `verify` port. `by` is the owner whose sealed approval exists (set by World.approve)."""
    def __init__(self):
        self.by, self.blocked, self.quote_current, self.raises, self.patch, self.calls = None, False, True, False, {}, []

    def verify(self, t, bp, dg, qd, subject):
        self.calls.append((t, bp, dg, qd, subject))
        if self.raises:
            raise RuntimeError("down")
        ev = {"tenantId": t, "blueprintId": bp, "contentDigest": dg, "quoteDigest": qd, "approvedBy": subject if self.by == subject else None,
              "blocked": self.blocked, "quoteCurrent": self.quote_current}
        ev.update(self.patch)
        return ev


class Clock:
    def __init__(self):
        self.t = 1_800_000_000
        self.value = None

    def __call__(self):
        if self.value is not None:
            return self.value
        self.t += 1
        return self.t


class World:
    def __init__(self, roles=("owner",), keys=KEYS):
        self.idn, self.bps, self.rev, self.sims, self.engine, self.clock = Identity(), Blueprints(), Reviews(), Sims(), Engine(), Clock()
        self.oa = OwnerApprovals()
        self.ledger = SignOffLedger(keys, "k1")
        self.errors = []
        self.audit = []
        self.m = BuildStateMachine(identity=self.idn, blueprints=self.bps, validator=lambda c: list(self.errors), reviews=self.rev,
                                   simulations=self.sims, signoffs=self.ledger, engine=self.engine, clock=self.clock,
                                   owner_approvals=self.oa, integrity_keys=keys, key_id="k1", required_signoff_roles=roles, audit=self.audit.append)
        self.report = copy.deepcopy(h.run(blueprint_id=BP, blueprint_digest=content_digest(content()))[0])
        self.sims.put(self.report)
        self.sim_id = self.report["simulationId"]

    # ---- drivers
    def args(self, **kw):
        return {"tenant_id": T, "blueprint_id": BP, **kw}

    def set_content(self, revision=None, **extra):
        c = content(**extra)
        if revision:
            c["meta"]["revision"] = revision
        self.bps.d[(T, BP)] = c

    def new_report(self, revision, tag="r"):
        """A report for another Blueprint revision (a different simulation, so a different digest)."""
        import re
        r = copy.deepcopy(self.report)
        r["blueprintRevision"] = revision
        r["blueprintDigest"] = content_digest(self.bps.d[(T, BP)])
        r["simulationId"] = hashlib.sha256(f"{tag}{revision}".encode()).hexdigest()
        self.sims.put(r)
        return r

    def create(self, who="author", **kw):
        return self.m.create(who, **self.args(**kw))

    def approve(self, who="owner", **over):
        self.oa.by = self.idn.table[who].subject
        c = self.bps.d.get((T, BP))
        kw = dict(confirmations=["summary", "quote", "gaps"], expected_digest=content_digest(c) if c else "0" * 64, quote_digest=QD)
        kw.update(over)
        return self.m.approve_owner(who, **self.args(**kw))

    def review(self, who="rev"):
        self.rev.approve(self.bps.d[(T, BP)])
        return self.m.pass_team_review(who, **self.args(pinned_seq=self.rev.seq, pinned_head=self.rev.head))

    def sandbox(self, who="runner"):
        return self.m.build_sandbox(who, **self.args())

    def simulated(self, who="rev"):
        return self.m.confirm_simulated(who, **self.args(simulation_id=self.sim_id))

    def cutover(self, who="rev"):
        return self.m.start_cutover(who, **self.args(checks=["opening_balances", "backups_verified", "compliance_onboarding"]))

    def sign(self, role="owner", user="u-owner", decision="accepted", report=None):
        report = report or self.report
        recs = self.ledger.records(T, report["simulationId"])
        view = review.build_view(report, records=recs)
        new = signoff.record_decision(report, recs, actor=signoff.Signer(T, user, (role,), "human"), role=role, decision=decision,
                                      decided_at=T0, now=T0, note="checked", acknowledged=view["signOff"]["toAcknowledge"])
        self.ledger.append(new[-1])

    def live(self, who="owner"):
        return self.m.go_live(who, **self.args())

    def to(self, state):
        steps = ["create", "approve", "review", "sandbox", "simulated", "cutover", "live"]
        goal = {"draft": 1, "owner_approved": 2, "team_reviewed": 3, "built_in_sandbox": 4, "simulated": 5, "cutover": 6, "live": 7}[state]
        for i, s in enumerate(steps[:goal]):
            if s == "live":
                self.sign()
            getattr(self, s)()
        return self

    def status(self):
        return self.m.status(T, BP)

    def state(self):
        return self.status()["state"]


def code(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except BuildStateError as e:
        return e.code
    return None
