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
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ("services/blueprint", "services/blueprint/tests/simulator", "services/blueprint/tests/build_state",
            "services/blueprint/tests/compiler", "services/discovery", "services/discovery/templates", "services/operate"):
    if os.path.join(REPO, sub) not in sys.path:
        sys.path.insert(0, os.path.join(REPO, sub))

import adapter.fake as adapter_fake  # noqa: E402
import bs_support as bs  # noqa: E402
import cmp_helpers as cmp  # noqa: E402
import owner_approval as oa  # noqa: E402
from adapter import testkit  # noqa: E402
from adapter.harness import FakeHarness  # noqa: E402
from build_state import BuildStateError, BuildStateMachine, SignOffLedger, content_digest  # noqa: E402
from compiler import compile_blueprint  # noqa: E402
from gap_analysis import analyse  # noqa: E402
from instantiate import instantiate  # noqa: E402
from interview import Interviewer, load_catalog  # noqa: E402
from quote import default_price_book, generate_quote  # noqa: E402
from simulator import review, signoff  # noqa: E402
from simulator.money import minor_to_str  # noqa: E402
from toolapi.generate import generate_tool_api  # noqa: E402
from validator.report import ValidationContext  # noqa: E402
from validator.validate import validate  # noqa: E402

from evals.harness import sim_accuracy as sa  # noqa: E402

NOW = dt.datetime(2026, 11, 22, 9, 0, tzinfo=dt.timezone.utc)
T = bs.T
KEYS = {"k1": b"r" * 32}
CONFIRM = ["gaps", "quote", "summary"]
# Golden path (spec section 5): 10 pieces sold at 15.00 out of 100 opened at cost 10.00; no tax on this path.
# The generated Tool API carries no unit cost on a purchase receipt and its delivery note needs a sales order, so the
# stock legs (and the 900.00 stock value) are not replayable through it: opening stock is an opening balance at cutover
# (`opening_balances` check) and the month replays the sale only. Listed as open in the QA-009 log.
GOLDEN_ROWS = [
    sa._r(1, "sales_invoice", "SI-1", "2026-03-02", "invoice", party="CUST-001", item="ITEM-001", qty="10", unit_price="15.00",
          vat="0", tax_code="ZERO", due_date="2026-03-31"),
]
GOLDEN_EXPECTED = {"sales_net": 15000, "vat_output": 0, "receivables_not_due": 15000}   # minor units
MAPPING_FIXTURE = os.path.join(REPO, "evals/tests/fixtures/engine-mapping-interview-template.json")


def mapping_fixture():
    """The compiler mapping that matches the interview template (the shared golden-path mapping names three ZATCA
    invoice fields the template does not carry). A test fixture: contracts/ is not edited."""
    with open(MAPPING_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def replay_mapping(tool_set):
    """The simulator's replay mapping, read off the generated tool set: required single-value fields (branch,
    warehouse) become constants; the invoice posts through its `submit_invoice` transition."""
    props = next(t for t in tool_set["tools"] if t["name"] == "sales_invoice.create")["input_schema"]["properties"]
    return {"sales_invoice": {"entity": "sales_invoice", "lines": "lines", "post": {"transition": "submit_invoice"},
                              "constants": {"branch": props["branch"]["enum"][0]},
                              "header": {"party": "customer", "date": "invoice_date"},
                              "line": {"item": "item", "qty": "quantity", "unit_price": "unit_price"}}}


class RealValidator:
    """The Blueprint validator the machine runs at the owner gate: real rules, fixture registry (what the host wires)."""
    def __init__(self):
        reg = {}
        for m in cmp.manifests():
            reg.setdefault(m["id"], []).append(m)
        self.ctx = ValidationContext(registry=reg)

    def __call__(self, content):
        return [str(i) for i in validate(content, self.ctx).errors]


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
    certified registry and a verified mapping (synthetic, from the interview-template mapping fixture); a sandbox takes the draft."""
    SITES = {"sandbox": ("t_rehearsal_sbx", "sandbox"), "live": ("t_rehearsal_live", "production")}

    def __init__(self, blueprints, bp_id):
        self.blueprints, self.bp_id, self.h = blueprints, bp_id, FakeHarness()   # not make_harness(): ADAPTER_HARNESS must not switch it
        self.calls, self.artifacts, self.sites = [], {}, set()

    def apply(self, t, kind, key, digest):
        self.calls.append((kind, key, digest))
        content = self.blueprints.load(t, self.bp_id)
        if content_digest(content) != digest:
            return "failed"
        if kind == "live":
            mapping = mapping_fixture()
            mapping["status"] = "verified"   # synthetic, as cmp.production_inputs does; the real mapping stays draft until the bench run
            mapping["engine"]["versionSet"] = content["meta"]["engineTarget"]["versionSet"]
            res = compile_blueprint(content, cmp.registry([cmp.certify(m) for m in cmp.manifests()]), mapping, environment="production")
        else:
            res = cmp.compile_fixture(bp=content, mp=mapping_fixture(), environment="sandbox")
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
        self.m = BuildStateMachine(identity=Ident(), blueprints=self.bps, validator=RealValidator(), reviews=self.rev, simulations=self.sims,
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
        """Tools and replay mapping come from the sandbox Blueprint (the generated Tool API), not from a fixture."""
        res = generate_tool_api(self.bps.load(T, self.bp_id))
        assert res.ok
        ts = res.definition_set()
        assert ts["blueprintRevision"] == self.bp["meta"]["revision"]
        mp = replay_mapping(ts)
        port = sa.SimulatedPort(ts, mp, tax_rates=sa.TAX_RATES)
        self.report = sa.simulate(copy.deepcopy(GOLDEN_ROWS), tenant_id=T, period=sa.PERIOD, tool_set=ts, mapping=mp,
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


def approve_held(report, port):
    """Stand-in for the owner or accountant releasing the held R3 posts: the simulated port parks R3 and has no approval
    queue, so the approved post is applied to the draft it created. Returns the kinds posted."""
    kinds = []
    for step in report["steps"]:
        if step["outcome"] == "held":
            create = next(s for s in report["steps"] if s["sourceId"] == step["sourceId"] and s["stage"] == "create")
            assert port._post({"id": create["recordId"]})["status"] == "ok"
            kinds.append(step["kind"])
    return kinds


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
    # the generated trading tool set holds invoice posting for approval (R3): the hold comes first, nothing is posted yet
    post = next(s for s in w.report["steps"] if s["stepId"].endswith("SI-1#post"))
    assert (post["tool"], post["riskClass"], post["action"], post["outcome"]) == ("sales_invoice.transition", "R3", "needs_approval", "held")
    assert w.report["summary"]["held"] == 1 and port.post_order == [] and w.report["verdict"] == "pass_with_warnings"
    got = {r["metric"]: r for r in w.report["comparison"] if r["currency"] == "SAR"}
    # the receivable exists only once the invoice is posted, so it is not compared while the hold stands; the draft's net and VAT match
    assert (got["receivables_not_due"]["actualMinor"], got["receivables_not_due"]["status"]) == (None, "blocked_by_approval")
    for metric in ("sales_net", "vat_output"):
        assert (got[metric]["actualMinor"], got[metric]["expectedMinor"], got[metric]["status"]) == (GOLDEN_EXPECTED[metric],) * 2 + ("match",)
    # the approval is granted (stand-in for the R3 `approval.decide`), then the posted totals are the spec's
    assert approve_held(w.report, port) == ["sales_invoice"]
    totals = port.report_totals(T, dict(sa.CALLER), sa.PERIOD)
    for metric in ("sales_net", "vat_output"):
        assert totals[metric]["SAR"] == minor_to_str(GOLDEN_EXPECTED[metric], "SAR"), metric
    # the generated invoice has payment_terms_days, not a due date, so the port ages it from the invoice date: the spec's
    # 150.00 receivable is all there, in an aging bucket the spec does not name (open item in the QA-009 log)
    assert sum(float(v["SAR"]) for k, v in totals.items() if k.startswith("receivables_")) == GOLDEN_EXPECTED["receivables_not_due"] / 100
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
    # 8 the golden-path sale posted only after its approval (before go-live)
    assert [port.docs[i]["kind"] for i in port.post_order] == ["sales_invoice"]
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


def test_an_invalid_draft_stays_in_draft_at_the_owner_gate(w):
    assert RealValidator()(w.bp) == []   # the interview's draft is valid as built
    del w.bps.v["company"]["legalName"]["en"]   # a draft that breaks the Blueprint schema
    assert RealValidator()(w.bps.v) != []
    w.m.create("author", **w.args())
    v = w.oa.review("owner", **w.args())
    with pytest.raises((BuildStateError, oa.OwnerApprovalError)):
        w.oa.decide("owner", **w.args(decision="approve", reason="agree", note="", seen_blueprint_digest=content_digest(w.bps.v),
                                      seen_quote_digest=v["quoteDigest"], confirmations=CONFIRM))
    assert refused(w.m.approve_owner, "owner", **w.args(confirmations=CONFIRM, expected_digest=content_digest(w.bps.v),
                                                        quote_digest=v["quoteDigest"])) == "BS-006"
    assert w.m.status(T, w.bp_id)["state"] == "draft" and w.engine.calls == []


def test_an_inherited_adapter_harness_variable_cannot_switch_the_backend(monkeypatch):
    monkeypatch.setenv("ADAPTER_HARNESS", "no_such_module:factory")   # would raise if the rehearsal went through make_harness()
    assert isinstance(Rehearsal(monkeypatch).engine.h, FakeHarness)
