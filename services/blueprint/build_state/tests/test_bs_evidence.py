"""BPL-020: evidence is re-derived at transition time; forged, stale, held, cross-tenant or malformed evidence blocks."""
import copy

import pytest

import sim_helpers as h
from build_state import SignOffLedger
from bs_support import BP, KEYS, T, World, code


# ---------- team review evidence ----------
FORGERIES = [
    {"eligible": "yes"}, {"eligible": 1}, {"eligible": False}, {"stale": True}, {"stale": 0}, {"hold": True}, {"hold": None},
    {"pinCurrent": False}, {"pinCurrent": 1}, {"pinCurrent": None}, {"tenantId": "t_other"}, {"subjectRef": "other-bp"},
    {"kind": "component_request"}, {"state": "claimed"}, {"evidenceOnly": False}, {"gate": "owner"}, {"seq": 99},
    {"headSeal": "other"}, {"contentDigest": "xyz"}, {"contentDigest": 5}, {"itemId": "item-2"}, {"approvedBy": ""},
    {"approvedBy": 7},
]


@pytest.mark.parametrize("patch", FORGERIES)
def test_forged_or_weak_review_evidence_is_refused(patch):
    w = World().to("owner_approved")
    w.rev.patch = patch
    assert code(w.review) in ("BS-006", "BS-001")
    assert w.state() == "owner_approved"


@pytest.mark.parametrize("override", [None, [], "approved", 5, {}, {"eligible": True}, ["eligible"]])
def test_review_port_garbage_is_refused(override):
    w = World().to("owner_approved")
    w.rev.approve(w.bps.d[(T, BP)])
    w.rev.override = override if override is not None else {"gate": "team_reviewed"}
    assert code(w.m.pass_team_review, "rev", **w.args(review_item_id="item-1", pinned_seq=7, pinned_head="head-seal-1")) == "BS-006"
    w.rev.override = None
    w.rev.raises = True
    assert code(w.review) == "BS-006"
    assert w.state() == "owner_approved"


def test_review_never_approved_or_pin_not_what_the_reviewer_saw():
    w = World().to("owner_approved")
    assert code(w.m.pass_team_review, "rev", **w.args(review_item_id="item-1", pinned_seq=7, pinned_head="head-seal-1")) == "BS-006"  # no approval
    w.rev.approve(w.bps.d[(T, BP)])
    for seq, head in ((8, "head-seal-1"), (7, "stale-head"), (True, "head-seal-1"), (7.0, "head-seal-1"), (7, None), (0, "h")):
        assert code(w.m.pass_team_review, "rev", **w.args(review_item_id="item-1", pinned_seq=seq, pinned_head=head)) in ("BS-006", "BS-001")
    assert code(w.m.pass_team_review, "rev", **w.args(review_item_id="bad id", pinned_seq=7, pinned_head="head-seal-1")) == "BS-001"
    assert w.state() == "owner_approved"


def test_later_gates_reverify_review_with_the_recorded_pin():
    w = World().to("team_reviewed")
    w.rev.seq += 1                      # the queue moved on after the gate: the pin is no longer current
    assert code(w.sandbox) == "BS-006"
    w.rev.seq -= 1
    w.sandbox()
    w.rev.hold = True                   # quarantine after the fact blocks every later promotion
    assert code(w.simulated) == "BS-006"
    w.rev.hold = False
    w.simulated()
    w.rev.hold = True
    assert code(w.cutover) == "BS-006"
    w.rev.hold = False
    w.cutover(); w.sign()
    w.rev.hold = True
    assert code(w.live) == "BS-006"
    assert w.state() == "simulated" and w.engine.calls[-1][1] == "sandbox"
    w.rev.hold = False
    assert w.live()["state"] == "live"


def test_review_digest_must_stay_the_same_everywhere():
    w = World().to("team_reviewed")
    w.rev.patch = {"contentDigest": "a" * 64}
    assert code(w.sandbox) == "BS-006"


# ---------- stale content ----------
@pytest.mark.parametrize("state,op", [("draft", "approve"), ("owner_approved", "review"), ("team_reviewed", "sandbox"),
                                      ("built_in_sandbox", "simulated"), ("simulated", "cutover")])
def test_content_changed_after_the_last_approval_blocks(state, op):
    w = World().to(state)
    w.set_content(edit="after approval")
    assert code(getattr(w, op)) == "BS-008"
    assert w.status()["contentChanged"] is True
    assert w.state() == state


def test_changed_after_signoff_blocks_go_live_and_revise_only_in_draft():
    w = World().to("cutover"); w.sign()
    w.set_content(edit="late")
    assert code(w.live) == "BS-008"
    assert code(lambda: w.m.revise("author", **w.args())) == "BS-005"
    w.m.roll_back("rev", **w.args(to_state="draft", reason="content_changed"))
    w.m.revise("author", **w.args())
    assert w.status()["contentChanged"] is False and w.state() == "draft"
    assert code(w.review) == "BS-005"
    w.approve(); w.review(); w.sandbox()
    assert code(w.simulated) is None  # the report is still bound to revision 3


def test_blueprint_store_failure_is_refused():
    w = World().to("draft")
    w.bps.d.clear()
    assert code(w.approve) == "BS-006"
    assert w.status()["contentChanged"] is True


# ---------- simulation report and sign-off ----------
def test_report_must_be_completed_passing_this_tenant_and_revision():
    bad = {}
    for name, edit in {
        "blocked": lambda x: x.update(verdict="blocked"),
        "aborted": lambda x: x.update(status="aborted"),
        "tenant": lambda x: x.update(tenantId="t_other"),
        "revision": lambda x: x.update(blueprintRevision=4),
        "garbage": lambda x: x.update(summary="x"),
    }.items():
        w = World().to("built_in_sandbox")
        rep = copy.deepcopy(w.report)
        edit(rep)
        w.sims.d[(T, w.sim_id)] = rep
        bad[name] = code(w.simulated)
    assert set(bad.values()) <= {"BS-006"}, bad
    w = World().to("built_in_sandbox")
    w.sims.d.clear()
    assert code(w.simulated) == "BS-006"
    assert code(w.m.confirm_simulated, "rev", **w.args(simulation_id="bad id")) == "BS-001"


def test_report_replaced_after_simulated_blocks_go_live():
    w = World().to("cutover"); w.sign()
    other = copy.deepcopy(w.report)
    other["summary"] = dict(other["summary"], records=other["summary"]["records"] + 1)
    w.sims.d[(T, w.sim_id)] = other
    assert code(w.live) == "BS-008"
    assert code(w.cutover) is not None


def test_go_live_needs_the_required_signoff_from_the_sealed_ledger():
    w = World().to("cutover")
    assert code(w.live) == "BS-006"                         # no sign-off
    w.sign(decision="rejected")
    assert code(w.live) == "BS-006"                         # a rejection blocks
    w = World().to("cutover")
    w.sign("owner")
    w2 = World(roles=("owner", "accountant")).to("cutover")
    w2.sign("owner")
    assert code(w2.live) == "BS-006"                        # the accountant is required by policy
    w2.sign("accountant", "u-acct")
    assert w2.live()["state"] == "live" and w.live()["state"] == "live"


def test_signoff_for_another_report_does_not_count():
    w = World().to("cutover")
    other = copy.deepcopy(w.report)
    other["summary"] = dict(other["summary"], records=other["summary"]["records"] + 1)
    w.sign(report=other)                                     # accepted, but of a report with another digest
    assert code(w.live) == "BS-006"


def test_a_forged_evidence_dict_has_no_authority():
    import inspect
    from build_state import BuildStateMachine
    for n in ("go_live", "pass_team_review", "confirm_simulated", "build_sandbox", "start_cutover"):
        assert not {"evidence", "records", "report", "verdict", "eligible"} & set(inspect.signature(getattr(BuildStateMachine, n)).parameters)
    w = World().to("cutover")
    w.sign()
    # a signoff port that lies (eligible without records) cannot help: the ledger is the only source
    class Liar:
        def records(self, t, sim):
            return ()
        def append(self, r):
            pass
    w.m._ledger = Liar()
    assert code(w.live) == "BS-006"


# ---------- Q-274: the sealed sign-off ledger ----------
def test_ledger_unique_key_and_seals():
    w = World().to("cutover")
    w.sign()
    rec = w.ledger.records(T, w.sim_id)[0]
    assert code(w.ledger.append, rec) == "BS-014"           # unique (simulation, digest, role)
    from dataclasses import replace
    assert code(w.ledger.append, replace(rec, user_id="u-other")) == "BS-014"
    assert code(w.ledger.append, replace(rec, decision="rejected", acknowledged=())) == "BS-014"   # cannot hide or flip a decision
    assert code(w.ledger.append, replace(rec, role="accountant", user_id="u-acct")) is None
    assert code(w.ledger.append, {"role": "owner"}) == "BS-001"
    assert code(w.ledger.append, replace(rec, role="boss")) == "BS-001"
    assert code(w.ledger.append, replace(rec, tenant_id="bad tenant")) == "BS-001"


def test_ledger_tampering_truncation_and_cross_tenant():
    w = World().to("cutover")
    w.sign(); w.sign("accountant", "u-acct")
    log = w.ledger._log
    key = (T, w.sim_id)
    good = copy.deepcopy(log._logs[key])
    log._logs[key][0]["body"]["record"]["decision"] = "rejected"         # edit
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    log._logs[key] = good[:1]                                            # cut tail
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    log._logs[key] = list(reversed(good))                                # reorder
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    log._logs[key] = good
    assert len(w.ledger.records(T, w.sim_id)) == 2
    del log._logs[key]; del log._heads[key]                              # whole stream deleted
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    assert code(w.live) == "BS-011"                                      # and go-live refuses, never treats it as "no records"
    log._logs[key] = good
    w.ledger._log._heads[key] = None
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    # another tenant sees nothing; records keep their tenant
    assert w.ledger.records("t_other", w.sim_id) == ()


def test_ledger_needs_a_key():
    for keys in ({}, None, {"k1": b"short"}, {"k1": "x" * 40}, {"k1": b"k" * 32, 5: b"k" * 32}):
        assert code(SignOffLedger, keys, "k1") == "BS-012"
    assert code(SignOffLedger, KEYS, "missing") == "BS-012"
    w = World().to("cutover")
    w.sign()
    w.ledger._log._keys.clear()                                          # key custody lost: fail closed, never sha256
    assert code(w.ledger.records, T, w.sim_id) == "BS-011"
    assert code(w.live) == "BS-011"
