"""PR 219 review probes as regressions: H1, H2, M1 to M5 and the LOW items."""
import copy
import hashlib
import json

import pytest

from rq_support import BP, World, code
from reviewqueue import ReviewQueue, checklist_ids, content_digest


def get(w, iid, sid="s-rev2", tenant="t-a"):
    return w.q.get(w.claims(sid), tenant_id=tenant, item_id=iid)


def ev(w, iid, content=BP, sid="s-rev2"):
    return w.q.gate_evidence(w.claims(sid), tenant_id="t-a", item_id=iid, current_content=content)


def tr(w, required=None, ref="bp-1", tenant="t-a"):
    return w.q.team_reviewed_evidence(w.claims("s-rev2"), tenant_id=tenant, subject_ref=ref, required=required or {"blueprint_draft": BP})


def sub(w, **kw):
    base = dict(tenant_id="t-a", kind="blueprint_draft", subject_ref="x", content=BP, author="a", involved=[], linked_staff=[])
    return w.q.submit(**{**base, **kw})


# ---- H1: separation of duties fails closed -------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["component_request", "simulation_signoff"])
def test_h1_empty_involved_refused_for_requester_and_signer_kinds(w, kind):
    for empty in ([], ()):
        assert code(lambda: sub(w, kind=kind, involved=empty)) == "RQ-001"
    assert code(lambda: sub(w, kind=kind, involved=[], linked_staff=["s-rev1"])) == "RQ-001"  # linked staff is not a requester


def test_h1_resubmit_unions_involved_never_replaces(w):
    iid = w.submit(kind="component_request", involved=["s-rev2"])
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-007"
    w.claim(iid)
    w.decide(iid, kind="component_request", decision="changes_requested", note="x")
    w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 7}, author="agent-1", involved=[], linked_staff=[])
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-007"  # the probe: s-rev2 stays barred


def test_h1_forged_narrowed_involved_is_refused_on_read(w):
    iid = w.submit(kind="component_request", involved=["s-rev2"])
    w.claim(iid)
    w.decide(iid, kind="component_request", decision="changes_requested", note="x")
    w.q._append(iid, "t-a", "resubmitted", w.clock.t, "agent-1",
                {"revision": 2, "content_digest": content_digest({**BP, "n": 7}), "hold": False, "involved": ["req-1"]})
    assert code(lambda: get(w, iid, "s-rev1")) == "RQ-011"


def test_h1_absent_linked_staff_fails_closed(w):
    for bad in (None, "s-1", {"s-1"}, (x for x in [])):
        assert code(lambda: sub(w, linked_staff=bad)) == "RQ-001"


# ---- M5 ------------------------------------------------------------------------------------------------------------
def test_m5_linked_staff_account_of_author_cannot_review(w):
    iid = w.submit(author="s-author", linked_staff=["s-rev2"])
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-007"
    w.claim(iid, "s-rev1")


# ---- H2 --------------------------------------------------------------------------------------------------------------
def rejected_item(w, **kw):
    iid = w.submit(**kw)
    w.claim(iid)
    w.decide(iid, decision="rejected", note="no")
    return iid


def test_h2_cut_tail_is_refused_and_cannot_be_approved(w):
    iid = rejected_item(w)
    w.q._logs[iid] = w.q._logs[iid][:2]  # the rejection is cut off, the chain prefix is valid
    assert code(lambda: get(w, iid)) == "RQ-011"
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-011"
    assert code(lambda: ev(w, iid)) == "RQ-011"
    assert (iid, "RQ-011") in w.q.invalid()


def test_h2_rollback_to_older_copy(w):
    iid = w.submit()
    old = copy.deepcopy(w.q._logs[iid])
    w.claim(iid)
    w.q._logs[iid] = old
    assert code(lambda: get(w, iid)) == "RQ-011"


def test_h2_deleted_item_cannot_make_evidence_eligible(w):
    a = w.submit(ref="bp-1")
    w.claim(a)
    w.decide(a)
    assert tr(w)["eligible"]
    c = w.submit(ref="bp-1")
    w.claim(c, "s-rev2")
    w.decide(c, "s-rev2", decision="rejected", note="no")
    assert not tr(w)["eligible"]
    del w.q._logs[c]  # delete the refusal
    assert code(lambda: tr(w)) == "RQ-011"
    assert code(lambda: get(w, c)) == "RQ-011"
    assert code(lambda: w.submit(ref="other")) == "RQ-011"  # the tenant stays closed until fixed


def test_h2_deleted_item_and_its_head_still_caught_by_manifest(w):
    iid = rejected_item(w)
    del w.q._logs[iid]
    del w.q._heads[iid]
    assert code(lambda: get(w, iid)) == "RQ-011"
    assert w.q.invalid() == [(iid, "RQ-011")]


def test_h2_rewrite_and_rehash_without_key_fails(w):
    iid = rejected_item(w)
    e = w.q._logs[iid][-1]
    e["data"]["decision"] = "approved"
    body = json.dumps({k: v for k, v in e.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    e["seal"] = hashlib.sha256(body.encode()).hexdigest()
    w.q._heads[iid]["head"] = e["seal"]  # re-pointing the head at the rehash fails: the head and manifest are sealed
    assert code(lambda: get(w, iid)) == "RQ-011"


def test_h2_manifest_tamper_and_unanchored_log_fail_closed(w):
    iid = w.submit()
    w.q._manifest["n"] += 1
    assert code(lambda: get(w, iid)) == "RQ-011"
    assert w.q.invalid() == [("*", "RQ-011")]
    w2 = World()
    i2 = w2.submit()
    w2.q._logs["rq-injected"] = copy.deepcopy(w2.q._logs[i2])
    assert code(lambda: get(w2, "rq-injected")) == "RQ-011"


def test_h2_evidence_carries_seq_and_head_seal(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    e = ev(w, iid)
    assert e["seq"] == 3 and e["headSeal"] == w.q._logs[iid][-1]["seal"]


def test_h2_manifest_and_heads_move_with_every_append(w):
    iid = w.submit()
    n0 = w.q._manifest["n"]
    w.claim(iid)
    assert w.q._manifest["n"] == n0 + 1 and w.q._heads[iid]["seq"] == 2


# ---- M1 -------------------------------------------------------------------------------------------------------------
def test_m1_newest_uses_sealed_submission_number_not_time(w):
    a = w.submit(ref="bp-1")
    w.claim(a)
    w.decide(a)
    w.clock.t -= 250  # item B is stamped EARLIER than A
    b = w.submit(ref="bp-1")
    w.claim(b, "s-rev2")
    w.decide(b, "s-rev2", decision="rejected", note="no")
    w.clock.t += 250
    r = tr(w)
    assert r["items"]["blueprint_draft"]["itemId"] == b and not r["eligible"]


def test_m1_ids_are_random_not_counters(w):
    ids = {w.submit(ref=f"r{i}") for i in range(5)}
    assert len(ids) == 5 and all(len(i) == 35 and i.startswith("rq-") for i in ids)


# ---- M2 -------------------------------------------------------------------------------------------------------------
def test_m2_lock_expiry_uses_host_clock_no_early_steal_no_late_decision(w):
    iid = w.submit()
    w.claim(iid)
    w.clock.t += 1799
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-005"
    w.clock.t += 2
    assert code(lambda: w.decide(iid)) == "RQ-006"


# ---- M3 -------------------------------------------------------------------------------------------------------------
def test_m3_one_step_up_cannot_decide_twice(w):
    a, b = w.submit(ref="x1"), w.submit(ref="x2")
    c = w.claims("s-rev1")
    w.q.claim(c, tenant_id="t-a", item_id=a)
    w.q.claim(c, tenant_id="t-a", item_id=b)
    cl = {i: "pass" for i in checklist_ids("blueprint_draft")}
    w.q.decide(c, tenant_id="t-a", item_id=a, decision="approved", checklist=cl, note="", current_content=BP)
    assert code(lambda: w.q.decide(c, tenant_id="t-a", item_id=b, decision="approved", checklist=cl, note="", current_content=BP)) == "RQ-003"
    assert get(w, b)["state"] == "claimed"
    w.decide(b)  # a new MFA sign-in works


def test_m3_refused_validation_does_not_spend_the_step_up(w):
    iid = w.submit()
    c = w.claims("s-rev1")
    w.q.claim(c, tenant_id="t-a", item_id=iid)
    cl = {i: "pass" for i in checklist_ids("blueprint_draft")}
    assert code(lambda: w.q.decide(c, tenant_id="t-a", item_id=iid, decision="approved", checklist={}, note="", current_content=BP)) == "RQ-009"
    assert w.q.decide(c, tenant_id="t-a", item_id=iid, decision="approved", checklist=cl, note="", current_content=BP)["state"] == "approved"


# ---- M4 -------------------------------------------------------------------------------------------------------------
def test_m4_hold_after_approval_makes_evidence_ineligible_until_resubmit(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    assert ev(w, iid)["eligible"]
    w.q.hold_item(tenant_id="t-a", item_id=iid, reason="injection")
    e = ev(w, iid)
    assert not e["eligible"] and e["hold"] and not tr(w)["eligible"]
    assert code(lambda: w.q.hold_item(tenant_id="t-a", item_id=iid, reason="scan")) == "RQ-005"
    w.clock.t += 1
    assert w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 9}, author="agent-1", involved=[], linked_staff=[]) == 2
    w.claim(iid, "s-rev2")
    assert w.decide(iid, "s-rev2", content={**BP, "n": 9})["state"] == "approved"


def test_m4_hold_while_claimed_blocks_approval_and_validates_reason(w):
    iid = w.submit()
    w.claim(iid)
    w.q.hold_item(tenant_id="t-a", item_id=iid, reason="scan")
    assert code(lambda: w.decide(iid)) == "RQ-010"
    assert code(lambda: w.q.hold_item(tenant_id="t-a", item_id=iid, reason="because")) == "RQ-001"
    assert code(lambda: w.q.hold_item(tenant_id="t-b", item_id=iid, reason="scan")) == "RQ-004"


# ---- LOW ------------------------------------------------------------------------------------------------------------
def test_low_restart_cannot_reuse_or_corrupt_an_item():
    w = World()
    a = w.submit()
    w.claim(a)
    w.decide(a)
    q2 = ReviewQueue(w.idn, w.roles, integrity_key=b"k" * 32)  # a fresh queue over the same store contents
    q2._logs, q2._heads, q2._manifest = w.q._logs, w.q._heads, w.q._manifest
    b = q2.submit(tenant_id="t-a", kind="blueprint_draft", subject_ref="bp-1", content={**BP, "n": 2}, author="agent-1", involved=[], linked_staff=[])
    assert b != a and get(w, a)["state"] == "approved" and q2.invalid() == []


@pytest.mark.parametrize("bad", ["\ud800", "a\udc00b"])
def test_low_lone_surrogates_are_coded_and_audited(w, bad):
    assert code(lambda: w.submit(content={"k": bad})) == "RQ-001"
    assert code(lambda: w.submit(content={bad: 1})) == "RQ-001"
    iid = w.submit()
    w.claim(iid)
    assert code(lambda: w.decide(iid, note=bad)) == "RQ-014"
    assert any(e.action == "review.decide" and e.code == "RQ-014" for e in w.audit.events())
    assert any(e.action == "review.submit" and e.code == "RQ-001" for e in w.audit.events())


def test_low_staff_without_linked_ids_denied_not_crash(w):
    iid = w.submit()
    object.__setattr__(w.repo.get_staff("s-rev1"), "linked_person_ids", None)
    assert code(lambda: w.claim(iid)) == "RQ-003"


def test_low_get_and_evidence_need_a_verified_reviewer(w):
    iid = w.submit()
    for bad in (None, object()):
        assert code(lambda: w.q.get(bad, tenant_id="t-a", item_id=iid)) == "RQ-003"
        assert code(lambda: w.q.gate_evidence(bad, tenant_id="t-a", item_id=iid, current_content=BP)) == "RQ-003"
        assert code(lambda: w.q.team_reviewed_evidence(bad, tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": BP})) == "RQ-003"
    assert code(lambda: w.q.get(w.claims("s-norole"), tenant_id="t-a", item_id=iid)) == "RQ-003"
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-b", item_id=iid)) == "RQ-004"


def test_low_total_content_size_capped(w):
    big = {f"k{i}": "x" * 15000 for i in range(100)}  # 1.5M chars; each string and the node count alone are fine
    assert code(lambda: w.submit(content=big)) == "RQ-001"


def test_low_list_shows_broken_items_as_invalid(w):
    a, b = w.submit(ref="r1"), w.submit(ref="r2")
    w.q._logs[a] = [{"x": 1}]
    rows = w.q.list_items(w.claims("s-rev1"), tenant_id="t-a")
    assert {r["itemId"]: r["state"] for r in rows} == {a: "invalid", b: "pending"}
    assert [r["itemId"] for r in w.q.list_items(w.claims("s-rev1"), state="invalid")] == [a]


def test_low_resubmit_time_regression_is_rq002(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid, decision="changes_requested", note="x")
    w.clock.t -= 30
    assert code(lambda: w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 3}, author="agent-1", involved=[], linked_staff=[])) == "RQ-002"
