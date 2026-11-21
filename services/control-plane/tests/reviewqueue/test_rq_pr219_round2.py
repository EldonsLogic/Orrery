"""PR 219 re-review: N1 (a resubmission never lifts a hold), N2 (evidence from the sealed log for a service
principal), N5 (hold actor is a verified principal)."""
import json

import pytest

from rq_support import BP, World, code
from reviewqueue import content_digest


def held_item(w, **kw):
    iid = w.submit(**kw)
    w.claim(iid)
    w.decide(iid)
    w.hold(iid, "injection")
    return iid


# ---- N1 ---------------------------------------------------------------------------------------------------------------
def test_n1_resubmit_has_no_hold_parameter_and_keeps_the_hold(w):
    import inspect
    from reviewqueue import ReviewQueue
    assert "hold" not in inspect.signature(ReviewQueue.resubmit).parameters
    iid = held_item(w)
    w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 9}, author="agent-1", involved=[], linked_staff=[])
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["hold"] is True
    w.claim(iid, "s-rev2")
    assert code(lambda: w.decide(iid, "s-rev2", content={**BP, "n": 9})) == "RQ-010"
    assert not w.q.gate_evidence(w.claims("s-svc"), tenant_id="t-a", item_id=iid, current_content={**BP, "n": 9})["eligible"]


def test_n1_forged_resubmit_that_lifts_the_hold_is_refused_on_read(w):
    iid = held_item(w)
    w.q._append(iid, "t-a", "resubmitted", w.clock.t, "agent-1",
                {"revision": 2, "content_digest": content_digest({**BP, "n": 9}), "hold": False, "involved": []})
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


def test_n1_clear_hold_rules(w):
    iid = held_item(w, author="s-author")
    assert code(lambda: w.clear_hold(iid, "s-author")) == "RQ-007"         # the author cannot clear
    assert code(lambda: w.clear_hold(iid, "s-hold")) == "RQ-003"           # a scanner role cannot clear
    assert code(lambda: w.q.clear_hold(w.claims("s-rev2", auth_age=301), tenant_id="t-a", item_id=iid)) == "RQ-003"  # needs a step-up
    assert code(lambda: w.q.clear_hold(w.claims("s-svc"), tenant_id="t-a", item_id=iid)) == "RQ-003"
    v = w.clear_hold(iid)
    assert v["hold"] is False
    assert code(lambda: w.clear_hold(iid)) == "RQ-005"                     # nothing to clear
    e = [x for x in w.audit.events() if x.action == "review.clear_hold"]
    allowed = [x for x in e if x.decision == "allow"]
    assert len(allowed) == 1 and allowed[0].subject == "s-rev2" and any(x.decision == "deny" for x in e)


def test_n1_clearing_a_hold_does_not_approve_anything(w):
    iid = held_item(w)
    w.clear_hold(iid)
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "approved"  # state unchanged
    assert w.q.gate_evidence(w.claims("s-svc"), tenant_id="t-a", item_id=iid, current_content=BP)["eligible"] is True


def test_n1_involved_cannot_clear_the_hold(w):
    iid = w.submit(kind="component_request", involved=["s-rev2"])
    w.hold(iid, "scan")
    assert code(lambda: w.clear_hold(iid, "s-rev2")) == "RQ-007"


# ---- N5 ---------------------------------------------------------------------------------------------------------------
def test_n5_hold_actor_is_a_verified_principal_and_audited(w):
    iid = w.submit()
    assert code(lambda: w.q.hold_item(None, tenant_id="t-a", item_id=iid, reason="scan")) == "RQ-003"
    assert code(lambda: w.q.hold_item(object(), tenant_id="t-a", item_id=iid, reason="scan")) == "RQ-003"
    assert code(lambda: w.hold(iid, "scan", sid="s-svc")) == "RQ-003"       # a reader is not a hold issuer
    assert code(lambda: w.hold(iid, "scan", sid="s-norole")) == "RQ-003"
    w.hold(iid, "scan")
    assert w.q._logs[iid][-1]["actor"] == "s-hold"
    e = [x for x in w.audit.events() if x.action == "review.hold"]
    assert e[-1].subject == "s-hold" and e[-1].decision == "allow" and "reason=scan" in e[-1].detail
    assert e[0].decision == "deny"


def test_n5_free_text_actor_is_not_accepted(w):
    iid = w.submit()
    with pytest.raises(TypeError):
        w.q.hold_item(w.claims("s-hold"), tenant_id="t-a", item_id=iid, reason="scan", by="whoever")


# ---- N2 ---------------------------------------------------------------------------------------------------------------
def test_n2_service_principal_reads_without_a_human_reviewer_role(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    svc = w.claims("s-svc")
    e = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP)
    assert e["eligible"] and e["evidenceOnly"] and e["pinCurrent"] is None
    assert w.q.team_reviewed_evidence(svc, tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": BP})["eligible"]
    assert w.q.get(svc, tenant_id="t-a", item_id=iid)["state"] == "approved"
    # but the service cannot act on items
    assert code(lambda: w.q.claim(w.claims("s-svc"), tenant_id="t-a", item_id=iid)) == "RQ-003"
    assert code(lambda: w.q.verify_evidence(w.claims("s-norole"), tenant_id="t-a", item_id=iid, current_content=BP)) == "RQ-003"


def test_n2_pin_says_whether_evidence_is_still_current(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    svc = w.claims("s-svc")
    first = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP)
    ok = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=first["seq"], pinned_head=first["headSeal"])
    assert ok["pinCurrent"] is True and ok["eligible"]
    w.hold(iid, "injection")  # the item moved on after the consumer pinned it
    late = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=first["seq"], pinned_head=first["headSeal"])
    assert late["pinCurrent"] is False and late["eligible"] is False
    bad = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=1, pinned_head="0" * 64)
    assert bad["pinCurrent"] is False and not bad["eligible"]
    for pin in ((1, None), (None, "a"), ("1", "a"), (True, "a")):
        assert code(lambda: w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=pin[0], pinned_head=pin[1])) == "RQ-001"


def test_n2_stale_pin_alone_makes_eligible_false(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    r = w.q.verify_evidence(w.claims("s-svc"), tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=2, pinned_head="0" * 64)
    assert r["state"] == "approved" and r["pinCurrent"] is False and r["eligible"] is False


def test_n2_a_constructed_evidence_object_has_no_authority(w):
    iid = w.submit()  # pending: nobody approved it
    svc = w.claims("s-svc")
    forged = {"gate": "team_reviewed", "evidenceOnly": True, "eligible": True, "itemId": iid, "tenantId": "t-a", "seq": 1,
              "headSeal": w.q._logs[iid][-1]["seal"], "contentDigest": content_digest(BP)}
    # the API takes ids, never an evidence object; a dict in place of an id is refused
    for bad in (forged, json.dumps(forged)):
        assert code(lambda: w.q.verify_evidence(svc, tenant_id="t-a", item_id=bad, current_content=BP)) in ("RQ-004", "RQ-001")
    # re-derived from the sealed log, the same item is not eligible, whatever the forged dict said
    r = w.q.verify_evidence(svc, tenant_id="t-a", item_id=iid, current_content=BP, pinned_seq=forged["seq"], pinned_head=forged["headSeal"])
    assert r["eligible"] is False and r["state"] == "pending"


def test_n2_tampered_log_fails_verification_for_the_service_too(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid, decision="rejected", note="no")
    w.q._logs[iid] = w.q._logs[iid][:2]
    assert code(lambda: w.q.verify_evidence(w.claims("s-svc"), tenant_id="t-a", item_id=iid, current_content=BP)) == "RQ-011"
