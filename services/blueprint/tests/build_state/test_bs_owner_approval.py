"""BPL-020 / DSC-009 (ADR-0050 amendment): the owner gate requires a CURRENT sealed owner approval, and every later
gate re-checks it. Each test is a regression for a review probe."""
import pytest

from build_state import BuildStateMachine, content_digest
from bs_support import BP, QD, T, World, code


def drafted():
    w = World()
    w.create()
    return w


def test_no_owner_approval_no_gate():
    """H1: calling the machine gate directly without a sealed approval is refused."""
    w = drafted()
    w.oa.by = None
    for who in ("owner", "owner2"):
        w.oa.by = None
        c = code(w.m.approve_owner, who, **w.args(confirmations=["gaps", "quote", "summary"],
                 expected_digest=content_digest(w.bps.d[(T, BP)]), quote_digest=QD))
        assert c == "BS-006"
    assert w.state() == "draft"


def test_approval_of_another_owner_does_not_cover_this_caller():
    w = drafted()
    w.oa.by = "u-owner2"
    assert code(w.m.approve_owner, "owner", **w.args(confirmations=["gaps", "quote", "summary"],
                expected_digest=content_digest(w.bps.d[(T, BP)]), quote_digest=QD)) == "BS-006"


def test_blocked_by_rejection_changes_or_hold_refuses_the_gate():
    for attr, val in (("blocked", True),):
        w = drafted()
        setattr(w.oa, attr, val)
        assert code(w.approve) == "BS-006" and w.state() == "draft"


def test_quote_must_still_be_current():
    w = drafted()
    w.oa.quote_current = False
    assert code(w.approve) == "BS-008" and w.state() == "draft"


def test_expected_digest_must_equal_the_machines_own():
    """H2: the machine never reaches owner_approved on content the owner did not see."""
    w = drafted()
    old = content_digest(w.bps.d[(T, BP)])
    w.set_content(revision=4, extra_item=1)          # host store moved, not yet recorded
    assert code(w.approve, expected_digest=old) == "BS-008"
    assert w.state() == "draft"
    w.m.revise("author", **w.args())
    assert code(w.approve, expected_digest=old) == "BS-008"
    assert w.approve()["state"] == "owner_approved"


@pytest.mark.parametrize("bad", [None, 5, b"x", ["x"], "short", "A" * 64])
def test_quote_digest_shape_is_strict(bad):
    w = drafted()
    assert code(w.approve, quote_digest=bad) == "BS-001"


def test_port_answers_are_validated_on_exact_types():
    for patch in ({"tenantId": "other"}, {"blueprintId": "x"}, {"contentDigest": "0" * 64}, {"quoteDigest": "1" * 64},
                  {"approvedBy": 5}, {"approvedBy": ["u-owner"]}, {"blocked": 0}, {"blocked": None}, {"quoteCurrent": 1}, {"extra": 1}):
        w = drafted()
        w.oa.patch = patch
        assert code(w.approve) in ("BS-006", "BS-008"), patch
        assert w.state() == "draft"
    w = drafted()
    w.oa.raises = True
    assert code(w.approve) == "BS-006"


def test_later_gates_recheck_the_owner_approval():
    """H1: a rejection, a quote change or a hold after owner approval stops team review, sandbox, simulation, go-live."""
    for attr, val, want in (("blocked", True, "BS-006"), ("quote_current", False, "BS-008"), ("by", "someone-else", "BS-006")):
        w = drafted()
        w.approve()
        setattr(w.oa, attr, val)
        assert code(w.review) == want
        assert w.state() == "owner_approved"
    w = drafted()
    w.approve(); w.review(); w.sandbox()
    w.oa.blocked = True
    assert code(w.simulated) == "BS-006"
    w.oa.blocked = False
    w.simulated(); w.cutover(); w.sign()
    w.oa.quote_current = False
    assert code(w.live) == "BS-008" and w.engine.calls[-1][1] == "sandbox"


def test_status_exposes_the_recorded_owner_approval():
    w = drafted()
    assert w.status()["owner"] is None
    w.approve()
    o = w.status()["owner"]
    assert o == {"actor": "u-owner", "digest": content_digest(w.bps.d[(T, BP)]), "quoteDigest": QD}


def test_status_exposes_the_rollback_count():
    w = drafted()
    w.approve()
    assert w.status()["rollbacks"] == 0
    w.m.roll_back("rev", **w.args(to_state="draft", reason="rejected"))
    assert w.status()["rollbacks"] == 1


def test_constructor_requires_the_port():
    w = World()
    with pytest.raises(Exception):
        BuildStateMachine(identity=w.idn, blueprints=w.bps, validator=lambda c: [], reviews=w.rev, simulations=w.sims,
                          signoffs=w.ledger, engine=w.engine, clock=w.clock, owner_approvals=None,
                          integrity_keys={"k1": b"k" * 32}, key_id="k1")
