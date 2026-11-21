"""PR #224 review regressions (H1 to H3, M1 to M5, L1 to L7). Each test names the probe it pins."""
import json
from datetime import datetime, timezone

import pytest

from owner_approval import OwnerApprovalError
from quote import default_price_book, generate_quote
from support import BP, NOW, T, Claims, GateRefusal, approve, build, cdigest, make_bp, seen


def code(fn, *a, **k):
    with pytest.raises(OwnerApprovalError) as e:
        fn(*a, **k)
    return e.value.code


def args(svc, claims=None, **kw):
    sb, sq = seen(svc, claims)
    base = dict(tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear", note="", seen_blueprint_digest=sb, seen_quote_digest=sq)
    base.update(kw)
    return base


def log(svc):
    return svc._log._logs[(T, BP)]


# ---- H1: the machine gate cannot be reached without the sealed approval --------------------------------
def test_h1_direct_machine_approval_without_a_sealed_approval_is_refused():
    svc, w, _ = build()
    c = Claims()
    with pytest.raises(GateRefusal) as e:
        w.gate_obj = svc._gate.approve_owner(c, tenant_id=T, blueprint_id=BP, confirmations=["gaps", "quote", "summary"],
                                             expected_digest=cdigest(w.bp), quote_digest=w.quote["digest"])
    assert e.value.code == "BS-006" and w.machine == "draft"


def test_h1_probe4_reject_then_direct_machine_approve_is_refused():
    svc, w, _ = build()
    svc.decide(Claims("owner-2"), **args(svc, Claims("owner-2"), decision="reject", reason="other"))
    approve_ev = svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")
    assert approve_ev["approvedBy"] is None and approve_ev["blocked"] is True
    with pytest.raises(GateRefusal):
        svc._gate.approve_owner(Claims(), tenant_id=T, blueprint_id=BP, confirmations=["gaps", "quote", "summary"],
                                expected_digest=cdigest(w.bp), quote_digest=w.quote["digest"])
    assert w.machine == "draft"


def test_h1_probe5_failed_rollback_after_rejection_still_blocks_every_later_gate():
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    w.rollback_error = GateRefusal("BS-010")
    assert code(svc.decide, Claims("owner-2"), **args(svc, Claims("owner-2"), decision="reject", reason="other")) == "OA-015"
    assert w.machine == "owner_approved"                      # the rollback failed ...
    ev = svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")
    assert ev["blocked"] is True                              # ... but the machine's later gates now refuse (port answer)
    assert svc.status(T, BP)["state"] == "out_of_sync"       # rejected, yet the machine did not roll back: shown, not hidden
    assert svc.review(Claims(), tenant_id=T, blueprint_id=BP)["canDecide"] is False


def test_h1_probe3_quote_regenerated_after_approval_is_not_current():
    svc, w, _ = build()
    approve(svc)
    old = w.quote["digest"]
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc), discount_bp=500)
    assert svc.verify(T, BP, cdigest(w.bp), old, "owner-1")["quoteCurrent"] is False


def test_h1_verify_binds_subject_digest_and_hold():
    svc, w, _ = build()
    approve(svc)
    dg, qd = cdigest(w.bp), w.quote["digest"]
    assert svc.verify(T, BP, dg, qd, "owner-1")["approvedBy"] == "owner-1"
    assert svc.verify(T, BP, dg, qd, "owner-2")["approvedBy"] is None
    assert svc.verify(T, BP, "0" * 64, qd, "owner-1")["approvedBy"] is None
    assert svc.verify(T, BP, dg, "0" * 64, "owner-1")["approvedBy"] is None and svc.verify(T, BP, dg, "0" * 64, "owner-1")["quoteCurrent"] is False
    w.held = True
    assert svc.verify(T, BP, dg, qd, "owner-1")["blocked"] is True
    for bad in (("x", qd, "owner-1"), (dg, None, "owner-1"), (dg, qd, ""), (dg, qd, None)):
        assert code(svc.verify, T, BP, *bad) == "OA-001"


# ---- H2: no approval of content the owner never saw ----------------------------------------------------
def test_h2_content_changes_between_the_flow_check_and_the_gate():
    svc, w, _ = build()
    sb, sq = seen(svc)
    w.before_approve = w.revise                               # the author records a revision right before the gate runs
    c = code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
             seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"])
    assert c == "OA-015" and w.machine == "draft"             # the machine refused (digest it computed differs)
    assert log(svc)[-1]["body"]["data"]["outcome"] == "refused"
    w.before_approve = None
    assert svc.status(T, BP)["state"] == "awaiting"


def test_h2_machine_past_draft_without_a_current_approval_is_out_of_sync():
    svc, w, _ = build()
    w.machine, w.owner = "owner_approved", {"actor": "x", "digest": cdigest(w.bp), "quoteDigest": "0" * 64}
    assert svc.status(T, BP)["state"] == "out_of_sync"
    assert svc.review(Claims(), tenant_id=T, blueprint_id=BP)["state"]["value"] == "out_of_sync"


# ---- H3: one step-up per decision; a refused gate call is not a decision ----------------------------------
def test_h3_a_single_use_step_up_is_enough_to_approve():
    svc, w, _ = build()
    c = Claims(uses=1)
    assert approve(svc, c)["state"] == "approved" and c.uses == 0


def test_h3_reject_without_a_gate_call_consumes_exactly_one_step_up():
    svc, w, _ = build()
    c = Claims(uses=1)
    svc.decide(c, **args(svc, c, decision="reject", reason="other"))
    assert c.uses == 0 and svc.status(T, BP)["state"] == "rejected"
    c2 = Claims(uses=0)
    assert code(svc.decide, c2, **args(svc, c2, decision="request_changes")) == "OA-003"


def test_h3_refused_or_timed_out_gate_call_does_not_lock_the_owner_out():
    svc, w, _ = build()
    c = Claims()
    w.gate_error = GateRefusal("BS-003")
    assert code(approve, svc, c) == "OA-015"
    w.gate_error = None
    assert approve(svc, c)["state"] == "approved"             # retry with the same version is allowed
    svc, w, _ = build()
    w.gate_error = TimeoutError("slow")
    assert code(approve, svc) == "OA-015"
    w.gate_error = None
    assert approve(svc)["state"] == "approved"
    assert [r["body"]["type"] for r in log(svc)] == ["decision", "forward_outcome", "decision", "forward_outcome"]


def test_h3_approval_with_no_step_up_is_refused_by_the_gate_and_can_be_retried():
    svc, w, _ = build()
    c = Claims(uses=0)
    assert code(approve, svc, c) == "OA-015" and w.machine == "draft"
    c.uses = 1
    assert approve(svc, c)["state"] == "approved"


def test_h3_a_timeout_after_the_machine_approved_is_settled_as_confirmed():
    svc, w, _ = build()
    w.timeout_after = True
    out = approve(svc)
    assert out["state"] == "approved" and log(svc)[-1]["body"]["data"]["outcome"] == "confirmed"


def test_h3_a_real_recorded_decision_still_locks_the_owner_for_that_version():
    svc, w, _ = build()
    approve(svc)
    w.machine, w.owner = "draft", None   # rolled back by a reviewer
    assert code(approve, svc) == "OA-007"
    assert svc.status(T, BP)["state"] == "approval_spent"
    svc, w, _ = build()
    svc.decide(Claims(), **args(svc))
    assert code(svc.decide, Claims(), **args(svc)) == "OA-007"


# ---- M1: clock steps ------------------------------------------------------------------------------------
def test_m1_a_one_second_backward_clock_step_does_not_break_the_stream():
    svc, w, _ = build()
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 600, timezone.utc))
    sb, sq = seen(svc)
    ticks = iter([NOW, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1, NOW - 1])
    svc._clock = lambda: next(ticks, NOW - 1)
    svc.decide(Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb, seen_quote_digest=sq,
               confirmations=["gaps", "quote", "summary"])
    svc._clock = lambda: NOW - 2
    assert svc.status(T, BP)["state"] == "approved"           # no integrity error
    assert svc.review(Claims("owner-2"), tenant_id=T, blueprint_id=BP)["state"]["value"] == "approved"


def test_m1_a_far_back_clock_is_refused_at_write_and_corrupt_at_read():
    svc, w, _ = build()
    svc.decide(Claims(), **args(svc))
    svc._clock = lambda: NOW - 1000
    w.t = NOW - 1000
    w.regen()
    assert code(svc.decide, Claims("owner-2"), **args(svc, Claims("owner-2"))) == "OA-002"
    assert len(log(svc)) == 1


# ---- M2: what the owner sees covers what the digest binds --------------------------------------------------
def test_m2_summary_lists_approvals_integrations_assistants_locations_and_compliance():
    svc, w, _ = build()
    extra = {"approvals": [{"id": "big-orders", "labels": {"ar": "ا", "en": "Big orders"}}],
             "integrations": [{"id": "bank-feed", "labels": {"ar": "ب", "en": "Bank feed"}}],
             "assistants": [{"id": "sales-helper", "labels": {"ar": "ج", "en": "Sales helper"}}],
             "locations": [{"id": "hq", "labels": {"ar": "د", "en": "Head office"}}],
             "compliance": {"country": "SA", "vat": {"registered": True}, "eInvoicing": {"mode": "phase2"}}}
    w.regen({**make_bp(), **extra})
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    summ = v["sections"][0]
    assert {k: summ["counts"][k] for k in ("approval", "integration", "assistant", "location")} == {"approval": 1, "integration": 1, "assistant": 1, "location": 1}
    assert {i["kind"] for i in summ["items"]} >= {"approval", "integration", "assistant", "location"}
    assert summ["compliance"] == {"country": "SA", "vatRegistered": True, "eInvoicingMode": "phase2", "untrustedText": True}
    assert [n["key"] for n in summ["notShown"]] == ["branding", "i18n"] and summ["notShownNoticeKey"] == "oa.summary.not_shown"


# ---- M3: the owner can stop the build after owner_approved ---------------------------------------------
@pytest.mark.parametrize("stage", ["owner_approved", "team_reviewed", "built_in_sandbox", "simulated"])
def test_m3_reject_after_the_machine_moved_on_rolls_back(stage):
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    w.machine = stage
    out = svc.decide(Claims("owner-2"), **args(svc, Claims("owner-2"), decision="reject", reason="not_for_us"))
    assert w.calls[-1] == ("roll_back", "draft", "rejected") and w.machine == "draft" and out["state"] == "rejected"


def test_m3_nothing_after_live_and_approve_only_from_draft():
    svc, w, _ = build()
    w.machine = "live"
    assert code(svc.decide, Claims(), **args(svc)) == "OA-005"
    svc, w, _ = build()
    w.machine = "team_reviewed"
    assert code(approve, svc) == "OA-005"


# ---- M4: several owners ---------------------------------------------------------------------------------
def test_m4_one_owners_request_for_changes_is_not_overridden_by_another_approval():
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    svc.decide(Claims("owner-2"), **args(svc, Claims("owner-2")))      # asks for changes, machine rolled back
    assert w.machine == "draft"
    assert code(approve, svc, Claims("owner-3")) == "OA-016"
    v = svc.review(Claims("owner-3"), tenant_id=T, blueprint_id=BP)
    assert v["state"]["value"] == "changes_requested" and v["decisions"][0]["allowed"] is False
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["blocked"] is True
    # a new quote or a new draft resolves it
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc), discount_bp=100)
    w.t += 1   # N3: an approval in flight counts only when it is newer than the machine's last rollback
    assert approve(svc, Claims("owner-3"))["state"] == "approved"


# ---- M5: reconcile credits only the right owner ---------------------------------------------------------
def test_m5_reconcile_does_not_credit_another_owners_machine_approval():
    svc, w, _ = build()
    orig = svc._outcome
    svc._outcome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    with pytest.raises(OwnerApprovalError):
        approve(svc, Claims("owner-1"))
    svc._outcome = orig
    w.owner = {"actor": "someone-else", "digest": cdigest(w.bp), "quoteDigest": w.quote["digest"]}   # machine says another actor
    svc.reconcile(Claims("owner-1"), tenant_id=T, blueprint_id=BP)
    assert log(svc)[-1]["body"]["data"] == {"decisionSeq": 1, "outcome": "refused", "code": "lost"}
    assert svc.status(T, BP)["state"] != "approved"


def test_m5_reconcile_confirms_the_owners_own_approval_and_settles_rollbacks():
    svc, w, _ = build()
    orig = svc._outcome
    svc._outcome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    with pytest.raises(OwnerApprovalError):
        approve(svc, Claims("owner-1"))
    svc._outcome = orig
    assert svc.reconcile(Claims("owner-1"), tenant_id=T, blueprint_id=BP)["state"] == "approved"
    svc._outcome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    with pytest.raises(OwnerApprovalError):
        svc.decide(Claims("owner-2"), **args(svc, Claims("owner-2"), decision="reject", reason="other"))
    svc._outcome = orig
    svc.reconcile(Claims("owner-2"), tenant_id=T, blueprint_id=BP)
    assert log(svc)[-1]["body"]["data"]["outcome"] == "confirmed"   # the machine is at draft: the rollback took effect


# ---- L: labels, wording, text ------------------------------------------------------------------------------
def test_l1_cost_notes_for_unpriced_incomplete_and_placeholder_have_labels():
    svc, w, _ = build()
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    cost = v["sections"][1]
    assert cost["notes"] == ["oa.cost.placeholder"]
    w.gap["requirements"].append({"id": "component:x", "kind": "component", "ref": "x", "status": "uncovered", "match": None})
    w.gap["summary"].update(total=3, uncovered=2)
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc))
    cost = svc.review(Claims(), tenant_id=T, blueprint_id=BP)["sections"][1]
    assert "oa.cost.unpriced" in cost["notes"] and "oa.cost.incomplete" in cost["notes"] and "oa.cost.placeholder" in cost["notes"]
    en = __import__("owner_approval").labels("en")
    assert all(k in en for k in cost["notes"])


def test_l2_wording_does_not_say_you_approved_and_says_approval_is_not_an_order():
    from owner_approval import labels
    en = labels("en")
    assert "You approved" not in json.dumps(en) and "accountant" not in json.dumps(en).lower()
    svc, w, _ = build()
    assert svc.review(Claims(), tenant_id=T, blueprint_id=BP)["commitNoticeKey"] == "oa.notice.not_order"
    assert "not an order" in en["oa.notice.not_order"]


def test_l4_combining_marks_are_bounded_and_cuts_are_flagged():
    from owner_approval.text import clean, clean_cut
    stacked = "a" + "́" * 50 + "b"
    assert len(clean(stacked)) == 1 + 3 + 1 and clean(stacked).endswith("b")   # NFC folds the first mark; at most 3 survive
    assert clean_cut("x" * 200, 80) == ("x" * 80, True) and clean_cut("short", 80) == ("short", False)
    svc, w, _ = build()
    w.bp["entities"][0]["labels"]["en"] = "y" * 200
    w.regen(w.bp)
    item = svc.review(Claims(), tenant_id=T, blueprint_id=BP)["sections"][0]["items"][0]
    assert item["labels"]["cut"] is True and len(item["labels"]["en"]) == 80


def test_l7_malformed_gap_report_is_a_blocker_not_an_error():
    svc, w, _ = build()
    w.gap["requirements"] = "nope"
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    assert v["canDecide"] is False and "quote" in [b["key"] for b in v["blockers"]]
