"""PR #224 Tier 3 security review regressions (H1, H2, M4, M5, L7, L8). Each test names the finding it pins."""
from datetime import datetime, timezone

import pytest

from owner_approval import OwnerApproval, OwnerApprovalError
from owner_approval.ledger import MemoryStore
from quote import default_price_book, generate_quote
from support import BP, KEYS, NOW, T, Claims, GateRefusal, approve, build, cdigest, make_bp, seen


def code(fn, *a, **k):
    with pytest.raises(OwnerApprovalError) as e:
        fn(*a, **k)
    return e.value.code


def outcomes(svc):
    return [r for r in svc._log._logs[(T, BP)] if r["body"]["type"] == "forward_outcome"]


def reject_args(svc, claims, decision="reject", reason="other"):
    sb, sq = seen(svc, claims)
    return dict(tenant_id=T, blueprint_id=BP, decision=decision, reason=reason, note="", seen_blueprint_digest=sb, seen_quote_digest=sq)


# ---- H1: outcome appends go through the same fold rules ---------------------------------------------
def test_h1_reconcile_during_an_in_flight_approve_leaves_one_outcome_and_a_readable_log():
    svc, w, _ = build()
    w.before_approve = lambda: svc.reconcile(Claims(), tenant_id=T, blueprint_id=BP)   # same owner, second tab
    assert code(approve, svc) == "OA-015"
    assert len(outcomes(svc)) == 1                       # the second outcome for this decisionSeq was refused
    assert svc.status(T, BP)["state"] == "awaiting"      # readable, no OA-009
    w.before_approve = None
    approve(svc)                                         # a refused approval may be tried again
    assert svc.status(T, BP)["state"] == "approved"


def test_h1_reconcile_between_the_gate_check_and_the_move_fails_closed_not_corrupt():
    svc, w, _ = build()
    real = svc.verify

    def racing_verify(*a):
        out = real(*a)
        svc.reconcile(Claims(), tenant_id=T, blueprint_id=BP)   # machine still at draft: settles as refused
        return out
    svc._gate.svc = type("P", (), {"verify": staticmethod(racing_verify)})()
    assert code(approve, svc) == "OA-015"
    assert len(outcomes(svc)) == 1 and w.machine == "owner_approved"
    assert svc.status(T, BP)["state"] == "out_of_sync"   # shown, and the port no longer credits it
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["approvedBy"] is None


def test_h1_clock_step_back_between_decision_and_outcome_is_refused_not_sealed():
    svc, w, _ = build()
    w.t = NOW + 1000
    w.before_approve = lambda: setattr(w, "t", NOW + 500)   # host clock steps back 500 s mid-call
    assert code(approve, svc) == "OA-002"
    assert outcomes_or_none(svc) == [] and svc.status(T, BP)["state"] == "pending"   # readable, no OA-009
    w.t, w.before_approve = NOW + 1001, None
    svc.reconcile(Claims(), tenant_id=T, blueprint_id=BP)
    assert svc.status(T, BP)["state"] == "approved"


def outcomes_or_none(svc):
    return outcomes(svc) if (T, BP) in svc._log._logs else None


# ---- H2: the owner is never told the summary is complete when it is not ------------------------------
def test_h2_more_items_than_shown_blocks_approval_but_not_reject():
    svc, w, _ = build()
    many = [{"id": f"wf-{i}", "labels": {"ar": "ع", "en": f"Flow {i}"}} for i in range(201)]
    many[-1]["labels"]["en"] = "Pay supplier without approval"
    w.regen(make_bp(extra={"workflows": many}))
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    assert v["sections"][0]["moreItems"] > 0 and "too_large" in [b["key"] for b in v["blockers"]]
    assert [d["allowed"] for d in v["decisions"]] == [False, True, True]
    assert code(approve, svc) == "OA-017"
    svc.decide(Claims(), **reject_args(svc, Claims()))
    assert svc.status(T, BP)["state"] == "rejected"


def test_h2_summary_shows_permissions_approval_rules_integration_targets_and_assistant_tools():
    svc, w, _ = build()
    extra = {"roles": [{"id": "clerk", "labels": {"ar": "ك", "en": "Clerk"}, "isAdmin": True,
                        "permissions": [{"entity": "payment", "actions": ["create", "approve"]}]}],
             "approvals": [{"id": "pay", "labels": {"ar": "د", "en": "Pay"}, "selfApproval": True,
                            "appliesTo": {"entity": "payment", "action": "payment"},
                            "steps": [{"order": 1, "approverRole": "clerk", "mode": "any_one"}]}],
             "integrations": [{"id": "bank", "labels": {"ar": "ب", "en": "Bank"}, "connector": "bank.feed", "direction": "out"}],
             "assistants": [{"id": "helper", "labels": {"ar": "م", "en": "Helper"}, "roles": ["clerk"],
                             "tools": [{"tool": "payments.create"}]}]}
    w.regen(make_bp(extra=extra))
    items = {i["kind"]: i for i in svc.review(Claims(), tenant_id=T, blueprint_id=BP)["sections"][0]["items"]}
    assert items["role"]["details"] == {"admin": True, "chatActions": True, "permissions": [{"entity": "payment", "actions": ["create", "approve"]}]}
    assert items["approval"]["details"] == {"entity": "payment", "action": "payment", "selfApproval": True,
                                            "steps": [{"order": 1, "approverRole": "clerk", "mode": "any_one"}]}
    assert items["integration"]["details"] == {"connector": "bank.feed", "direction": "out"}
    assert items["assistant"]["details"] == {"roles": ["clerk"], "tools": ["payments.create"]}
    assert "details" not in items["workflow"]


# ---- M4: quote expiry after approval does not stop the approved build ------------------------------------
def test_m4_expired_quote_still_current_after_approval_but_not_at_draft():
    svc, w, _ = build()
    approve(svc)
    dg, qd = cdigest(w.bp), w.quote["digest"]
    w.t = NOW + 31 * 86400
    assert svc.verify(T, BP, dg, qd, "owner-1")["quoteCurrent"] is True        # later gates keep going
    assert svc.verify(T, BP, dg, "0" * 64, "owner-1")["quoteCurrent"] is False  # but only the same quote
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(w.t, timezone.utc), discount_bp=500)
    assert svc.verify(T, BP, dg, qd, "owner-1")["quoteCurrent"] is False        # a new quote replaced it
    svc2, w2, _ = build()
    w2.t = NOW + 31 * 86400
    assert svc2.verify(T, BP, cdigest(w2.bp), w2.quote["digest"], "owner-1")["quoteCurrent"] is False  # at draft: validity


def test_m4_owner_can_still_reject_after_the_quote_expired():
    svc, w, _ = build()
    approve(svc)
    w.t = NOW + 31 * 86400
    svc.decide(Claims("owner-2"), **reject_args(svc, Claims("owner-2")))
    assert w.machine == "draft" and svc.status(T, BP)["state"] == "rejected"


# ---- M5: decisions survive a restart; no store, no service -------------------------------------------
def test_m5_without_a_store_the_service_refuses_unless_explicitly_ephemeral():
    svc, w, ident = build()
    kw = dict(identity=ident, blueprints=svc._bps, quotes=svc._quotes, gaps=svc._gaps, holds=svc._holds, gate=svc._gate,
              content_digest=cdigest, clock=lambda: w.t, integrity_keys=dict(KEYS), key_id="k1")
    with pytest.raises(OwnerApprovalError) as e:
        OwnerApproval(**kw)
    assert e.value.code == "OA-010"


def test_m5_a_rejection_survives_a_restart_on_the_same_store():
    store = MemoryStore()
    svc, w, _ = build(store=store, ephemeral=False)
    svc.decide(Claims("owner-1"), **reject_args(svc, Claims("owner-1")))
    svc2, _, _ = build(w, store=store, ephemeral=False)              # new instance, same durable store
    assert code(approve, svc2, Claims("owner-2")) == "OA-008" and w.machine == "draft"


def test_m5_a_store_that_fails_to_read_fails_closed():
    class Broken(MemoryStore):
        def records(self, tenant, stream):
            raise IOError("down")
    svc, w, _ = build(store=Broken(), ephemeral=False)
    assert code(approve, svc) == "OA-009" and w.machine == "draft"


# ---- L7: an approval spent by a rollback is not credited at draft ----------------------------------------
def test_l7_confirmed_approval_is_not_credited_after_a_rollback_to_draft():
    svc, w, _ = build()
    approve(svc)
    w.machine, w.owner = "draft", None                                   # a reviewer sent it back
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["approvedBy"] is None


# ---- L8: refused approvals per owner per version are capped --------------------------------------------
def test_l8_refused_approvals_are_capped_per_owner_and_version():
    svc, w, _ = build()
    w.gate_error = GateRefusal("BS-006")
    for _ in range(5):
        assert code(approve, svc) == "OA-015"
    assert code(approve, svc) == "OA-007"
