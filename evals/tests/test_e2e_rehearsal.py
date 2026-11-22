"""QA-009: end-to-end rehearsal, discovery to a simulated Blueprint to live, on synthetic data.

Offline and deterministic: no network, no model, no real engine. Every service is the real code; only the ports are
fakes (identity, review queue, the engine adapter fake, the simulated tenant). Chain, each hand-off asserted:

  interview -> answers -> Blueprint draft -> gap report and quote -> sealed owner approval (DSC-009)
  -> build state machine (BPL-020, real gates) -> team review -> compile + apply in a fake sandbox -> simulated month
  -> sign-off -> cutover -> go live (compile for production + apply on a second fake site). The simulated month
  contains the golden-path sale (before go-live; no sales-order step, the simulator has none).

Expected numbers are copied from docs/specs/golden-path-trading-sale.md (section 5); nothing here computes tax or
ledger maths. What is a stand-in is listed in the QA-009 log, not hidden here.
"""
import copy
import datetime as dt
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ("services/blueprint", "services/blueprint/tests/simulator", "services/blueprint/tests/build_state",
            "services/blueprint/tests/compiler", "services/discovery", "services/discovery/templates"):
    if os.path.join(REPO, sub) not in sys.path:
        sys.path.insert(0, os.path.join(REPO, sub))

import adapter.fake as adapter_fake  # noqa: E402
import bs_support as bs  # noqa: E402
import cmp_helpers as cmp  # noqa: E402
import owner_approval as oa  # noqa: E402
from adapter import testkit  # noqa: E402
from adapter.harness import make_harness  # noqa: E402
from build_state import BuildStateError, BuildStateMachine, SignOffLedger, content_digest  # noqa: E402
from compiler import compile_blueprint  # noqa: E402
from gap_analysis import analyse  # noqa: E402
from instantiate import instantiate  # noqa: E402
from interview import Interviewer, load_catalog  # noqa: E402
from quote import default_price_book, generate_quote  # noqa: E402
from simulator import review, signoff  # noqa: E402

from evals.harness import sim_accuracy as sa  # noqa: E402

NOW = dt.datetime(2026, 11, 22, 9, 0, tzinfo=dt.timezone.utc)
T = bs.T
KEYS = {"k1": b"r" * 32}
CONFIRM = ["gaps", "quote", "summary"]
# Golden path (spec section 5): 10 pieces sold at 15.00 out of 100 opened at cost 10.00; no tax on this path.
GOLDEN_ROWS = [
    sa._r(1, "stock_in", "OPEN-1", "2026-03-01", "opening stock", item="ITEM-001", warehouse="W1", qty="100", unit_price="10.00"),
    sa._r(2, "stock_out", "DN-1", "2026-03-02", "delivery", item="ITEM-001", warehouse="W1", qty="10"),
    sa._r(3, "sales_invoice", "SI-1", "2026-03-02", "invoice", party="CUST-001", item="ITEM-001", qty="10", unit_price="15.00",
          vat="0", tax_code="ZERO", due_date="2026-03-31"),
]
GOLDEN_EXPECTED = {"sales_net": 15000, "vat_output": 0, "stock_value": 90000, "receivables_not_due": 15000}   # minor units


class NamePort:
    """Scripted extraction port for the interview: only the company name needs it, the rest parses deterministically."""
    def extract(self, request):
        return {"values": {"name_ar": "شركة اختبار للتجارة", "name_en": "Sample Trading Co."}, "confidence": 0.95}


class Ident:
    """One session table for both services; each wants its own Principal class (the packages share no code, Q-432)."""
    def __init__(self, cls=None):
        self.base, self.cls = bs.Identity(), cls

    def resolve(self, claims, *, step_up):
        p = self.base.resolve(claims, step_up=step_up)
        return p if self.cls is None else self.cls(p.subject, p.kind, p.realm, p.tenant_id, p.roles, p.step_up)


class Store:
    def __init__(self, v):
        self.v = v

    def load(self, t, bp):
        return copy.deepcopy(self.v)


class NoHolds:
    def held(self, t, bp):
        return False


class EnginePort:
    """The machine's engine port over the compiler and the adapter fake: compile what the host holds (never what the
    caller sends), apply to one fake site per kind, answer only confirmed or failed. A production compile needs the
    certified registry and a verified mapping (synthetic, from the compiler test inputs); a sandbox takes the draft."""
    SITES = {"sandbox": ("t_rehearsal_sbx", "sandbox"), "live": ("t_rehearsal_live", "production")}

    def __init__(self, blueprints, bp_id):
        self.blueprints, self.bp_id, self.h = blueprints, bp_id, make_harness()
        self.calls, self.artifacts, self.sites = [], {}, set()

    def apply(self, t, kind, key, digest):
        self.calls.append((kind, key, digest))
        content = self.blueprints.load(t, self.bp_id)
        if content_digest(content) != digest:
            return "failed"
        if kind == "live":
            _, reg, mapping = cmp.production_inputs()
            res = compile_blueprint(content, reg, mapping, environment="production")
        else:
            res = cmp.compile_fixture(bp=content, environment="sandbox")
        if not res.ok:
            return "failed"
        site, klass = self.SITES[kind]
        if site not in self.sites:
            assert testkit.provision(self.h, tenant=site, site_class=klass, blueprint_id=self.bp_id, target=res.artifact["engineTarget"])["ok"]
            self.sites.add(site)
        out = testkit.apply_artifact(self.h, res.artifact, tenant=site)
        self.artifacts[kind] = res.artifact
        return "confirmed" if out["ok"] and out["result"]["status"] == "applied" else "failed"

    def status(self, t, key):
        return "unknown"


class Rehearsal:
    """The interview fixture drives a draft; the real machine and approval flow run behind fake identity and review ports."""
    def __init__(self, monkeypatch):
        # Open questions Q-53 (canonical adapter id) and Q-77 (Studio drops the attachment field for the fake): the
        # fake names the engine "frappe" and lacks "attachment", the compiler output targets "change_engine".
        monkeypatch.setattr(adapter_fake, "ADAPTER_ID", "change_engine")
        monkeypatch.setattr(adapter_fake, "SUPPORTED_TYPES", set(adapter_fake.SUPPORTED_TYPES) | {"attachment"})
        self.t = int(NOW.timestamp())
        iv = Interviewer(load_catalog(), NamePort())
        s = iv.start("rehearsal-1", "en")
        for text in ("Sample Trading Co. / شركة اختبار للتجارة", "Saudi Arabia"):
            iv.answer(s, text)
        while s.state != "complete":
            iv.answer(s, "I don't know")
        self.draft_input = iv.draft_input(s)
        tmpl = os.path.join(REPO, "services/discovery/templates/trading-distribution/blueprint.template.json")
        self.bps = Store(instantiate(tmpl, self.draft_input["answers"], now="2026-11-22T09:00:00Z"))
        self.bp, self.bp_id = self.bps.v, self.bps.v["meta"]["id"]
        self.gap = analyse(self.bp, cmp.manifests())
        self.quote = generate_quote(self.bp, self.gap, default_price_book(), now=NOW)
        self.rev, self.sims, self.engine = bs.Reviews(), bs.Sims(), EnginePort(self.bps, self.bp_id)
        self.rev.patch = {"subjectRef": self.bp_id}
        self.ledger = SignOffLedger(KEYS, "k1")
        late = _Late()
        self.m = BuildStateMachine(identity=Ident(), blueprints=self.bps, validator=lambda c: [], reviews=self.rev, simulations=self.sims,
                                   signoffs=self.ledger, engine=self.engine, clock=self.clock, owner_approvals=late, integrity_keys=KEYS,
                                   key_id="k1")
        self.oa = oa.OwnerApproval(identity=Ident(oa.Principal), blueprints=self.bps, quotes=Store(self.quote), gaps=Store(self.gap),
                                   holds=NoHolds(), gate=self.m, content_digest=content_digest, clock=self.clock, integrity_keys=KEYS,
                                   key_id="k1", ephemeral=True)
        late.target = self.oa   # the machine's owner gate asks the approval flow's `verify` port
        self.report = None

    @property
    def clock(self):
        def tick():
            self.t += 1
            return self.t
        return tick

    def args(self, **kw):
        return {"tenant_id": T, "blueprint_id": self.bp_id, **kw}

    def decide(self, who="owner", decision="approve", reason="agree"):
        v = self.oa.review(who, **self.args())
        return self.oa.decide(who, **self.args(decision=decision, reason=reason, note="", seen_blueprint_digest=v["blueprintDigest"],
                                               seen_quote_digest=v["quoteDigest"], confirmations=CONFIRM))

    def team_review(self):
        self.rev.approve(self.bps.v)
        return self.m.pass_team_review("rev", **self.args(pinned_seq=self.rev.seq, pinned_head=self.rev.head))

    def simulate_month(self):
        ts = sa.tool_set()
        ts["blueprintRevision"] = self.bp["meta"]["revision"]
        port = sa.SimulatedPort(ts, copy.deepcopy(sa.MAPPING), tax_rates=sa.TAX_RATES)
        self.report = sa.simulate(copy.deepcopy(GOLDEN_ROWS), tenant_id=T, period=sa.PERIOD, tool_set=ts, mapping=copy.deepcopy(sa.MAPPING),
                                  caller=dict(sa.CALLER), port=port, blueprint_id=self.bp_id, blueprint_digest=content_digest(self.bps.v),
                                  tolerances={"default": {"per_line_minor": 1}})
        self.sims.put(self.report)
        return port

    def sign(self):
        recs = self.ledger.records(T, self.report["simulationId"])
        view = review.build_view(self.report, records=recs)
        new = signoff.record_decision(self.report, recs, actor=signoff.Signer(T, "u-owner", ("owner",), "human"), role="owner",
                                      decision="accepted", decided_at=bs.T0, now=bs.T0, note="checked",
                                      acknowledged=view["signOff"]["toAcknowledge"])
        self.ledger.append(new[-1])


class _Late:
    """The machine needs its owner_approvals port at construction and the approval flow needs the machine as its gate."""
    target = None

    def verify(self, *a):
        return self.target.verify(*a)


def to_cutover(w):
    w.m.create("author", **w.args())
    w.decide()
    w.team_review()
    w.m.build_sandbox("runner", **w.args())
    w.simulate_month()
    w.m.confirm_simulated("rev", **w.args(simulation_id=w.report["simulationId"]))
    w.m.start_cutover("rev", **w.args(checks=["opening_balances", "backups_verified", "compliance_onboarding"]))
    w.sign()


def refused(fn, *a, **k):
    with pytest.raises((BuildStateError, oa.OwnerApprovalError)) as e:
        fn(*a, **k)
    return e.value.code


@pytest.fixture
def w(monkeypatch):
    return Rehearsal(monkeypatch)


def test_e2e_discovery_to_simulated_month_with_golden_sale_to_live(w):
    # 1 interview: a draft input that still needs the owner (agents draft, humans approve)
    d = w.draft_input
    assert d["status"] == "draft" and d["requires_owner_approval"] is True and d["ready"] is True and d["validation_errors"] == []
    # 2 answers -> Blueprint draft from the template, in draft, carrying the interview's company
    assert w.bp["meta"]["buildState"] == "draft" and w.bp["company"]["legalName"]["en"] == "Sample Trading Co."
    # 3 requirements: the gap report and the quote are about this exact revision
    assert w.gap["blueprint"] == {"id": w.bp_id, "revision": w.bp["meta"]["revision"]} and w.gap["summary"]["total"] > 0
    assert w.quote["digest"] and w.quote["totals"]
    # 4 draft -> sealed owner approval -> machine owner_approved (the machine re-derives the digest and asks `verify`)
    assert w.m.create("author", **w.args())["state"] == "draft"
    v = w.oa.review("owner", **w.args())
    assert v["blueprintDigest"] == content_digest(w.bp) and v["canDecide"] is True
    out = w.decide()
    assert out["state"] == "approved" and out["buildState"] == "owner_approved"
    assert w.m.status(T, w.bp_id)["owner"]["digest"] == content_digest(w.bp)
    ev = w.oa.verify(T, w.bp_id, content_digest(w.bp), v["quoteDigest"], "u-owner")
    assert ev["approvedBy"] == "u-owner" and ev["blocked"] is False and ev["quoteCurrent"] is True
    # 5 team review, then compile + apply in the fake sandbox (the port compiles what the host holds)
    assert w.team_review()["state"] == "team_reviewed"
    assert w.m.build_sandbox("runner", **w.args())["state"] == "built_in_sandbox"
    sbx = w.engine.artifacts["sandbox"]
    assert sbx["blueprint"]["id"] == w.bp_id and sbx["blueprint"]["target"]["revision"] == w.bp["meta"]["revision"]
    assert testkit.status(w.engine.h, "t_rehearsal_sbx")["applied"]["artifactId"] == sbx["artifactId"]
    # 6 simulated month on the fake tenant: the golden path, expected rows from the spec; then the owner signs off
    port = w.simulate_month()
    got = {r["metric"]: r for r in w.report["comparison"] if r["currency"] == "SAR"}
    for metric, minor in GOLDEN_EXPECTED.items():   # spec numbers, not recomputed here
        assert (got[metric]["actualMinor"], got[metric]["expectedMinor"], got[metric]["status"]) == (minor, minor, "match"), metric
    assert w.report["verdict"] == "pass"
    assert w.report["status"] == "completed" and w.report["blueprintDigest"] == content_digest(w.bp)
    assert w.m.confirm_simulated("rev", **w.args(simulation_id=w.report["simulationId"]))["state"] == "simulated"
    assert w.m.start_cutover("rev", **w.args(checks=["opening_balances", "backups_verified", "compliance_onboarding"]))["cutoverStarted"]
    assert refused(w.m.go_live, "owner", **w.args()) == "BS-006"   # no owner sign-off on the report yet
    w.sign()
    # 7 go live: production compile (certified registry, verified mapping) and apply on a second fake site
    assert w.m.go_live("owner", **w.args())["state"] == "live"
    live = w.engine.artifacts["live"]
    assert live["blueprint"]["target"]["hash"] == sbx["blueprint"]["target"]["hash"]   # the content the owner approved
    assert [c[0] for c in w.engine.calls] == ["sandbox", "live"] and {c[2] for c in w.engine.calls} == {content_digest(w.bp)}
    # 8 the simulated month's golden-path sale posted its documents in order (before go-live), totals as the spec expects
    assert [port.docs[i]["kind"] for i in port.post_order] == ["stock_in", "stock_out", "sales_invoice"]
    assert w.m.verify_tenant(T) == [] and w.m.status(T, w.bp_id)["state"] == "live"


def test_unapproved_blueprint_cannot_pass_any_later_gate_or_go_live(w):
    w.m.create("author", **w.args())
    w.rev.approve(w.bps.v)
    assert refused(w.m.pass_team_review, "rev", **w.args(pinned_seq=w.rev.seq, pinned_head=w.rev.head)) == "BS-005"
    assert refused(w.m.build_sandbox, "runner", **w.args()) == "BS-005"
    assert refused(w.m.go_live, "owner", **w.args()) == "BS-008"   # no approval chain to re-derive
    assert w.engine.calls == [] and w.m.status(T, w.bp_id)["state"] == "draft"
    # the machine's own owner gate refuses when no sealed owner decision backs it
    assert refused(w.m.approve_owner, "owner", **w.args(confirmations=CONFIRM, expected_digest=content_digest(w.bp),
                                                        quote_digest=w.quote["digest"])) == "BS-006"
    assert w.m.status(T, w.bp_id)["state"] == "draft"


@pytest.mark.parametrize("who", ["author", "rev", "agent", "service"])
def test_only_a_human_owner_can_approve(w, who):
    w.m.create("author", **w.args())
    v = w.oa.review("owner", **w.args())
    with pytest.raises(oa.OwnerApprovalError):
        w.oa.decide(who, **w.args(decision="approve", reason="agree", note="", seen_blueprint_digest=v["blueprintDigest"],
                                  seen_quote_digest=v["quoteDigest"], confirmations=CONFIRM))
    assert w.m.status(T, w.bp_id)["state"] == "draft" and w.engine.calls == []


def test_content_change_after_approval_is_refused(w):
    w.m.create("author", **w.args())
    w.decide()
    w.bps.v["company"]["legalName"]["en"] = "Changed After Approval"   # the host store moved on after the owner saw it
    w.rev.approve(w.bps.v)
    assert refused(w.m.pass_team_review, "rev", **w.args(pinned_seq=w.rev.seq, pinned_head=w.rev.head)) == "BS-008"
    assert w.engine.calls == []


def test_owner_rejection_rolls_back_and_blocks_that_content(w):
    w.m.create("author", **w.args())
    assert w.decide(decision="reject", reason=oa.REASONS["reject"][0])["state"] == "rejected"
    assert w.m.status(T, w.bp_id)["state"] == "draft"
    v = w.oa.review("owner", **w.args())
    assert refused(w.m.approve_owner, "owner", **w.args(confirmations=CONFIRM, expected_digest=content_digest(w.bp),
                                                        quote_digest=v["quoteDigest"])) == "BS-006"


def test_failed_sandbox_apply_stops_the_build_before_simulation(w, monkeypatch):
    w.m.create("author", **w.args())
    w.decide()
    w.team_review()
    monkeypatch.setattr(w.engine, "apply", lambda t, kind, key, digest: "failed")
    assert refused(w.m.build_sandbox, "runner", **w.args()) == "BS-015"
    assert w.m.status(T, w.bp_id)["state"] == "team_reviewed"
    w.simulate_month()
    assert refused(w.m.confirm_simulated, "rev", **w.args(simulation_id=w.report["simulationId"])) == "BS-005"


def test_approval_evidence_is_bound_to_the_digests_the_owner_saw(w):
    w.m.create("author", **w.args())
    v = w.oa.review("owner", **w.args())
    w.decide()
    dg, qd = content_digest(w.bp), v["quoteDigest"]
    assert w.oa.verify(T, w.bp_id, dg, qd, "u-owner")["approvedBy"] == "u-owner"
    assert w.oa.verify(T, w.bp_id, "0" * 64, qd, "u-owner")["approvedBy"] is None   # swapped content digest
    assert w.oa.verify(T, w.bp_id, dg, "0" * 64, "u-owner")["approvedBy"] is None   # swapped quote digest


def test_a_tenant_realm_agent_with_the_owner_role_is_refused_by_the_human_check(w):
    w.m.create("author", **w.args())
    v = w.oa.review("owner", **w.args())
    bs_table = w.oa._idn.base.table
    bs_table["owner_agent"] = bs.P("agent-9", "agent", "tenant", ["owner"], tenant=T)
    with pytest.raises(oa.OwnerApprovalError) as e:
        w.oa.decide("owner_agent", **w.args(decision="approve", reason="agree", note="", seen_blueprint_digest=v["blueprintDigest"],
                                            seen_quote_digest=v["quoteDigest"], confirmations=CONFIRM))
    assert (e.value.code, e.value.detail) == ("OA-003", "human")


def test_a_rejection_blocks_even_after_an_approval_of_the_same_content(w):
    w.m.create("author", **w.args())
    assert w.decide()["buildState"] == "owner_approved"   # owner 1 approves first
    v = w.oa.review("owner2", **w.args())
    assert w.decide("owner2", decision="reject", reason=oa.REASONS["reject"][0])["state"] == "rejected"
    ev = w.oa.verify(T, w.bp_id, content_digest(w.bp), v["quoteDigest"], "u-owner")
    assert ev["blocked"] is True   # the earlier approval existed; the rejection is what refuses
    assert w.m.status(T, w.bp_id)["state"] == "draft"
    assert refused(w.m.approve_owner, "owner", **w.args(confirmations=CONFIRM, expected_digest=content_digest(w.bp),
                                                        quote_digest=v["quoteDigest"])) == "BS-006"


def test_a_stale_quote_cannot_be_approved(w):
    w.m.create("author", **w.args())
    v = w.oa.review("owner", **w.args())
    w.t += 400 * 86400   # past any price-book validity
    assert w.oa.verify(T, w.bp_id, content_digest(w.bp), v["quoteDigest"], "u-owner")["quoteCurrent"] is False
    with pytest.raises(oa.OwnerApprovalError):
        w.oa.decide("owner", **w.args(decision="approve", reason="agree", note="", seen_blueprint_digest=v["blueprintDigest"],
                                      seen_quote_digest=v["quoteDigest"], confirmations=CONFIRM))
    assert w.m.status(T, w.bp_id)["state"] == "draft"


def test_content_changed_between_sandbox_and_live_never_goes_live(w):
    to_cutover(w)
    w.bps.v["company"]["legalName"]["en"] = "Changed After Sign-off"
    assert refused(w.m.go_live, "owner", **w.args()) == "BS-008"
    assert [c[0] for c in w.engine.calls] == ["sandbox"] and "live" not in w.engine.artifacts
    assert w.m.status(T, w.bp_id)["state"] == "simulated"
