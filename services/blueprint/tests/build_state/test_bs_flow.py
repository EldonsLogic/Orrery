"""BPL-020: the allowed path, exactly the allowed transitions, humans only, separation of duties, rollback."""
import inspect
from dataclasses import replace

import pytest

from build_state import BuildStateError, BuildStateMachine, STATES
from bs_support import BP, T, World, code, P


def test_full_path_to_live():
    w = World()
    assert w.create()["state"] == "draft"
    assert w.approve()["state"] == "owner_approved"
    assert w.review()["state"] == "team_reviewed"
    assert w.sandbox()["state"] == "built_in_sandbox"
    assert w.simulated()["state"] == "simulated"
    assert w.cutover()["cutoverStarted"] is True and w.state() == "simulated"
    w.sign()
    s = w.live()
    assert s["state"] == "live" and s["pending"] is None
    kinds = [c[1] for c in w.engine.calls]
    assert kinds == ["sandbox", "live"]
    assert all(c[3] == s["contentDigest"] for c in w.engine.calls)
    assert w.m.verify_tenant(T) == []


OPS = {
    "create": lambda w: w.create(),
    "revise": lambda w: (w.set_content(revision=w.status()["revision"] + 1, x=1), w.m.revise("author", **w.args()))[1],
    "approve": lambda w: w.approve(),
    "review": lambda w: w.review(),
    "sandbox": lambda w: w.sandbox(),
    "simulated": lambda w: w.simulated(),
    "cutover": lambda w: w.cutover(),
    "live": lambda w: w.live(),
}
# state -> operations that may succeed from it (cutover leaves the state "simulated")
ALLOWED = {"draft": {"revise", "approve"}, "owner_approved": {"review"}, "team_reviewed": {"sandbox"},
           "built_in_sandbox": {"simulated"}, "simulated": {"cutover"}, "live": set()}


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("op", sorted(OPS))
def test_only_allowed_transitions(state, op):
    w = World()
    w.to(state)
    before = dict(w.status(), contentChanged=None)
    if op == "create" or op not in ALLOWED[state]:
        assert code(OPS[op], w) is not None
        assert dict(w.status(), contentChanged=None) == before
    else:
        OPS[op](w)  # allowed, and moves exactly one step
        assert w.state() in (state, STATES[STATES.index(state) + 1])


def test_no_state_skipping_and_nothing_automatic():
    w = World().to("draft")
    for op in ("review", "sandbox", "simulated", "cutover", "live"):
        assert code(OPS[op], w) is not None
    w.clock.t += 10 ** 6  # time passing promotes nothing
    assert w.state() == "draft"
    public = [n for n, f in inspect.getmembers(BuildStateMachine, inspect.isfunction) if not n.startswith("_")]
    for n in public:
        if n not in ("status", "verify_tenant"):
            assert "claims" in inspect.signature(getattr(BuildStateMachine, n)).parameters, n  # every change needs a principal
    for n in public:
        assert not {"now", "at", "decided_at", "evidence", "records", "verdict", "state"} & set(inspect.signature(getattr(BuildStateMachine, n)).parameters)


@pytest.mark.parametrize("who", ["agent", "service", "runner", "author"])
def test_agents_and_services_never_pass_a_gate(who):
    w = World().to("draft")
    assert code(w.approve, who) == "BS-003"
    w.approve()
    assert code(w.review, who) == "BS-003"
    w.review()
    w.sandbox()
    assert code(w.simulated, who) == "BS-003"
    w.simulated()
    assert code(w.cutover, who) == "BS-003"
    w.cutover(); w.sign()
    assert code(w.live, who) == "BS-003"
    assert code(lambda: w.m.roll_back(who, **w.args(to_state="draft", reason="other"))) == "BS-003"
    assert w.state() == "simulated"


def test_step_up_and_kind_are_both_required_and_claims_are_not_trusted():
    w = World().to("draft")
    w.idn.table["owner"] = replace(w.idn.table["owner"], step_up=False)
    assert code(w.approve) == "BS-003"
    w.idn.table["owner"] = replace(w.idn.table["owner"], step_up=True, kind="agent")
    assert code(w.approve) == "BS-003"
    # a resolver that hands back something that is not a Principal (dict signer, subclass-less lookalike) is refused
    class Dict:
        def resolve(self, claims, *, step_up):
            return {"subject": "u-owner", "kind": "human", "realm": "tenant", "tenant_id": T, "roles": ("owner",), "step_up": True}
    w.m._idn = Dict()
    assert code(w.approve) == "BS-003"
    class Boom:
        def resolve(self, claims, *, step_up):
            raise KeyError("x")
    w.m._idn = Boom()
    assert code(w.approve) == "BS-003"
    assert w.state() == "draft"


def test_step_up_flag_must_be_true_even_if_resolver_returns_it_false():
    w = World().to("draft")
    class Lax:
        def resolve(self, claims, *, step_up):
            return P("u-owner", "human", "tenant", ["owner"], tenant=T, step_up=False)
    w.m._idn = Lax()
    assert code(w.approve) == "BS-003"


def test_roles_realms_and_tenant_binding():
    w = World().to("draft")
    assert code(w.approve, "rev") == "BS-003"             # a reviewer is not the owner
    w.idn.table["owner"] = P("u-owner", "human", "tenant", ["owner"], tenant="t_other")
    assert code(w.approve) == "BS-017"                    # another tenant's owner
    w.idn.table["owner"] = P("u-owner", "human", "staff", ["owner"])
    assert code(w.approve) == "BS-003"                    # the owner role only counts in the tenant realm
    w.idn.table["owner"] = P("u-owner", "human", "tenant", ["owner"], tenant=None)
    assert code(w.approve) == "BS-017"
    w.idn.table["owner"] = P("u-owner", "human", "tenant", ["owner"], tenant=T)
    w.approve()
    w.idn.table["rev"] = P("u-rev", "human", "tenant", ["team_reviewer"], tenant=T)
    assert code(w.review) == "BS-003"                     # team_reviewer only counts for staff


def test_separation_of_duties():
    w = World()
    w.idn.table["author"] = P("u-rev", "human", "staff", ["author"])   # the author is also the reviewer's account
    w.create(who="author", involved=["u-rev2"])
    w.approve()
    assert code(w.review, "rev") == "BS-007"             # the author cannot approve
    assert code(w.review, "rev2") == "BS-007"            # nor anyone listed as involved
    w.rev.by = "u-rev2"
    w.idn.table["rev3"] = P("u-rev3", "human", "staff", ["team_reviewer"])
    assert code(w.review, "rev3") == "BS-007"            # the queue's approver is involved
    w.rev.by = "u-fine"
    w.review("rev3")
    # the owner cannot pass the team gate and the team reviewer cannot be the owner's counterpart
    w2 = World().to("owner_approved")
    w2.idn.table["rev"] = P("u-owner", "human", "staff", ["team_reviewer"])
    assert code(w2.review) == "BS-007"
    # a staff author cannot approve as owner
    w3 = World()
    w3.idn.table["owner"] = P("u-author", "human", "tenant", ["owner"], tenant=T)
    w3.create()
    assert code(w3.approve) == "BS-007"


def test_validator_must_pass_and_confirmations_are_exact():
    w = World().to("draft")
    w.errors = ["BP-REF-001"]
    assert code(w.approve) == "BS-006"
    w.errors = []
    for bad in (["summary"], ["summary", "quote"], ["summary", "quote", "gaps", "x"], "summary", None, {"summary", "quote", "gaps"} - {"gaps"},
                iter(["summary", "quote", "gaps"]), ["summary", "summary", "quote"]):
        assert code(lambda: w.m.approve_owner("owner", **w.args(confirmations=bad))) in ("BS-009",)
    assert w.state() == "draft"
    w.errors = "not a list"
    assert code(w.approve) == "BS-006"


def test_input_checks():
    w = World()
    for t in ("", None, 5, "a b", "x" * 65, b"t"):
        assert code(w.m.create, "author", tenant_id=t, blueprint_id=BP) == "BS-001"
    for bp in ("", None, "a/b", "x" * 81, ["bp"]):
        assert code(w.m.create, "author", tenant_id=T, blueprint_id=bp) == "BS-001"
    for inv in ("u-1", iter(["u-1"]), {"u-1"}, ["u-1", "u-1"], [1], ["a b"]):
        assert code(w.m.create, "author", tenant_id=T, blueprint_id=BP, involved=inv) == "BS-001"
    w.set_content(score=1.5)  # floats are refused, so one content has one digest
    assert code(w.create) == "BS-001"
    w.bps.d[(T, BP)] = ["not", "a", "dict"]
    assert code(w.create) == "BS-001"
    w.bps.d[(T, BP)] = {"meta": {"id": "other", "revision": 3}}
    assert code(w.create) == "BS-006"
    w.bps.d[(T, BP)] = {"meta": {"id": BP, "revision": True}}
    assert code(w.create) == "BS-006"
    assert code(w.m.status, T, BP) == "BS-004"
    w.set_content()
    w.create()
    assert code(w.create) == "BS-013"
    assert code(w.m.status, "t_other", BP) == "BS-004"   # another tenant cannot see the build


def test_rollback_goes_to_draft_only_with_its_own_gate_and_voids_approvals():
    w = World().to("team_reviewed")
    assert code(lambda: w.m.roll_back("agent", **w.args(to_state="draft", reason="other"))) == "BS-003"
    for to in ("owner_approved", "team_reviewed", "built_in_sandbox", "simulated", "live", "nowhere"):
        assert code(lambda: w.m.roll_back("rev", **w.args(to_state=to, reason="other"))) in ("BS-016", "BS-001")   # M2: the contract allows draft only
    assert code(lambda: w.m.roll_back("rev", **w.args(to_state="draft", reason="because"))) == "BS-001"
    assert w.state() == "team_reviewed"
    assert w.m.roll_back("rev", **w.args(to_state="draft", reason="rejected"))["state"] == "draft"
    assert w.status()["approvals"] == []
    assert code(w.review) == "BS-005"
    assert code(lambda: w.m.roll_back("owner", **w.args(to_state="draft", reason="other"))) == "BS-016"   # already draft
    w.approve(); w.review(); w.sandbox(); w.simulated()
    w.m.roll_back("owner", **w.args(to_state="draft", reason="owner_reopened"))
    w.approve(); w.review(); w.sandbox(); w.simulated()
    assert w.state() == "simulated"


def test_nothing_after_live():
    w = World().to("live")
    assert code(lambda: w.m.roll_back("owner", **w.args(to_state="draft", reason="other"))) == "BS-016"
    for op in ("approve", "review", "sandbox", "simulated", "cutover", "live"):
        assert code(getattr(w, op)) is not None
    w.set_content(revision=9, changed=True)
    assert code(lambda: w.m.revise("author", **w.args())) == "BS-005"
    assert w.state() == "live"
