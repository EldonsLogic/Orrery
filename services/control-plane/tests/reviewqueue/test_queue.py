import copy
import hashlib
import json

import pytest

from rq_support import BP, KEY, T0, World, code
from reviewqueue import (CODES, KINDS, ReviewError, ReviewQueue, checklist_ids, content_digest, label, label_keys)


def approved(w, **kw):
    iid = w.submit(**kw)
    w.claim(iid)
    w.decide(iid)
    return iid


def test_happy_path_and_evidence(w):
    iid = w.submit()
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "pending"
    v = w.claim(iid)
    assert v["state"] == "claimed" and v["claim"]["by"] == "s-rev1"
    v = w.decide(iid)
    assert v["state"] == "approved" and v["decisions"][0]["reviewer"] == "s-rev1"
    ev = w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-a", item_id=iid, current_content=BP)
    assert ev["eligible"] and ev["evidenceOnly"] and ev["consumer"] == "BPL-020" and ev["approvedBy"] == "s-rev1"
    assert ev["contentDigest"] == content_digest(BP)


def test_evidence_never_promotes():
    assert not any(n for n in dir(ReviewQueue) if "promote" in n or "go_live" in n or "build_state" in n)
    w = World()
    iid = approved(w)
    ev = w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-a", item_id=iid, current_content=BP)
    assert "buildState" not in ev and ev["evidenceOnly"] is True


# ---- integrity: no key, forged, edited, moved records ---------------------------------------------------------
@pytest.mark.parametrize("key", [None, b"", b"short", "k" * 32, bytearray(b"k" * 32)])
def test_no_key_or_weak_key_fails_closed(key):
    w = World()
    assert code(lambda: ReviewQueue(w.idn, w.roles, integrity_key=key)) == "RQ-012"
    assert code(lambda: ReviewQueue(w.idn, w.roles)) == "RQ-012"
    assert code(lambda: ReviewQueue(w.idn, w.roles, integrity_keys={"a": b"x" * 31})) == "RQ-012"


def test_stored_verdict_is_not_trusted(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid, decision="rejected", note="no")
    log = w.q._logs[iid]
    log[-1]["data"]["decision"] = "approved"  # flip the stored verdict
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"
    assert code(lambda: w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-a", item_id=iid, current_content=BP)) == "RQ-011"
    assert w.q.invalid() == [(iid, "RQ-011")]


def test_extra_stored_status_field_is_refused(w):
    iid = w.submit()
    w.q._logs[iid][0]["status"] = "approved"
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


def test_sha256_forged_seal_is_refused(w):
    iid = approved(w)
    log = w.q._logs[iid]
    ev = log[-1]
    ev["data"]["note"] = "forged"
    body = json.dumps({k: v for k, v in ev.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    ev["seal"] = hashlib.sha256(body.encode()).hexdigest()  # a plain-hash "seal"
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


def test_dropped_reordered_and_replayed_events(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid, decision="changes_requested", note="fix")
    good = copy.deepcopy(w.q._logs[iid])
    w.q._logs[iid] = good[:1] + good[2:]
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"
    w.q._logs[iid] = [good[0], good[2], good[1]]
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"
    w.q._logs[iid] = good + [good[1]]
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


def test_event_moved_to_another_item_or_tenant(w):
    a, b = w.submit(ref="bp-1"), w.submit(ref="bp-2", tenant="t-b")
    w.q._logs[b][0] = copy.deepcopy(w.q._logs[a][0])
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-b", item_id=b)) == "RQ-011"


def test_unknown_key_id_and_rotation():
    w = World(integrity_keys={"old": b"o" * 32, "new": b"n" * 32}, key_id="old")
    iid = w.submit()
    w.q._active = "new"
    w.claim(iid)  # new events under the new key, old ones still verify
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "claimed"
    del w.q._keys["old"]
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


def test_decision_with_forged_reviewer_conflict_is_refused_on_read(w):
    """A sealed event that breaks the rules (a decision by the author) is refused on read, not trusted."""
    iid = w.submit(author="s-rev1")
    q = w.q
    q._append(iid, "t-a", "claimed", w.clock.t, "s-rev1", {"expires_at": w.clock.t + 600})
    assert code(lambda: q.get(w.claims("s-rev2"), tenant_id="t-a", item_id=iid)) == "RQ-011"


# ---- reviewer verification ---------------------------------------------------------------------------------
def test_customer_realm_claims_refused(w):
    from identity import Membership, Person
    w.repo.put_person(Person("p-1", "p", mfa_enrolled=True))
    w.repo.put_membership(Membership("p-1", "t-a"))
    iid = w.submit()
    tok = w.idn.issue_customer_token("p-1", "t-a", mfa_satisfied=True, auth_time=w.clock.t)
    c = w.idn.verify_customer_token(tok.access_token, "t-a")
    assert code(lambda: w.q.claim(c, tenant_id="t-a", item_id=iid)) == "RQ-003"


def test_not_claims_objects_refused(w):
    iid = w.submit()
    for bad in (None, {"subject": "s-rev1"}, "s-rev1", object()):
        assert code(lambda: w.q.claim(bad, tenant_id="t-a", item_id=iid)) == "RQ-003"


def test_role_required_and_resolver_fails_closed(w):
    iid = w.submit()
    assert code(lambda: w.claim(iid, "s-norole")) == "RQ-003"
    w.roles.map["s-rev1"] = RuntimeError("boom")
    assert code(lambda: w.claim(iid)) == "RQ-003"
    w.roles.map["s-rev1"] = iter(["team_reviewer"])  # iterator result is not accepted
    assert code(lambda: w.claim(iid)) == "RQ-003"
    w.roles.map["s-rev1"] = "team_reviewer"  # a bare string is not a role list
    assert code(lambda: w.claim(iid)) == "RQ-003"
    w.roles.map["s-rev1"] = ("team_reviewer", 5)
    assert code(lambda: w.claim(iid)) == "RQ-003"


def test_needs_fresh_step_up_and_live_staff(w):
    iid = w.submit()
    stale = w.claims("s-rev1", auth_age=301)
    assert code(lambda: w.q.claim(stale, tenant_id="t-a", item_id=iid)) == "RQ-003"
    fresh = w.claims("s-rev1")
    w.idn.revoke_staff_sessions("s-rev1")
    assert code(lambda: w.q.claim(fresh, tenant_id="t-a", item_id=iid)) == "RQ-003"
    live = w.claims("s-rev2")
    w.repo.put_staff(type(w.repo.get_staff("s-rev2"))("s-rev2", "x", mfa_enrolled=True, active=False))
    assert code(lambda: w.q.claim(live, tenant_id="t-a", item_id=iid)) == "RQ-003"


def test_expired_token_refused(w):
    iid = w.submit()
    c = w.claims("s-rev1")
    w.clock.t += 10_000
    assert code(lambda: w.q.claim(c, tenant_id="t-a", item_id=iid)) == "RQ-003"


# ---- separation of duties --------------------------------------------------------------------------------------
def test_author_cannot_review_own_item(w):
    iid = w.submit(author="s-author")
    assert code(lambda: w.claim(iid, "s-author")) == "RQ-007"


def test_involved_requester_attester_signer_cannot_review(w):
    iid = w.submit(kind="component_request", involved=["s-rev1"])
    assert code(lambda: w.claim(iid, "s-rev1")) == "RQ-007"
    w.claim(iid, "s-rev2")


def test_linked_customer_person_cannot_review(w):
    iid = w.submit(kind="simulation_signoff", content=BP, involved=["p-owner"])  # owner who signed
    assert code(lambda: w.claim(iid, "s-linked")) == "RQ-007"


def test_attester_cannot_approve_even_with_a_claim_made_before(w):
    iid = w.submit(involved=[])
    w.claim(iid)
    # the host later records that s-rev1 attested: a resubmission cycle names them
    w.decide(iid, decision="changes_requested", note="classify")
    w.clock.t += 1
    w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 4}, author="agent-1", involved=["s-rev1"], linked_staff=[])
    assert code(lambda: w.claim(iid, "s-rev1")) == "RQ-007"
    w.claim(iid, "s-rev2")
    assert w.decide(iid, "s-rev2", content={**BP, "n": 4})["state"] == "approved"


def test_only_claim_holder_can_decide(w):
    iid = w.submit()
    w.claim(iid)
    assert code(lambda: w.decide(iid, "s-rev2")) == "RQ-006"
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-005"


# ---- tenant isolation ------------------------------------------------------------------------------------------
def test_cross_tenant_access_is_not_found(w):
    iid = w.submit(tenant="t-a")
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-b", item_id=iid)) == "RQ-004"
    assert code(lambda: w.claim(iid, tenant="t-b")) == "RQ-004"
    assert code(lambda: w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-b", item_id=iid, current_content=BP)) == "RQ-004"
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-b", item_id="nope")) == "RQ-004"
    assert w.q.list_items(w.claims("s-rev1"), tenant_id="t-b") == []


def test_same_subject_in_two_tenants_is_independent(w):
    a, b = w.submit(tenant="t-a"), w.submit(tenant="t-b")
    w.claim(a)
    w.decide(a)
    ev = w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-b", subject_ref="bp-1", required={"blueprint_draft": BP})
    assert not ev["eligible"] and ev["items"]["blueprint_draft"]["itemId"] == b
    ev = w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": BP})
    assert ev["eligible"]


def test_unknown_or_closed_tenant_refused(w):
    assert code(lambda: w.submit(tenant="t-zzz")) == "RQ-001"


# ---- inputs: iterators, floats, types --------------------------------------------------------------------------
def test_iterator_and_set_inputs_refused(w):
    gen = (x for x in ["a"])
    assert code(lambda: w.submit(involved=gen)) == "RQ-001"
    assert code(lambda: w.q.submit(tenant_id="t-a", kind="blueprint_draft", subject_ref="x", content=BP, author="a", involved={"a"}, linked_staff=[])) == "RQ-001"
    assert code(lambda: w.q.submit(tenant_id="t-a", kind="blueprint_draft", subject_ref="x", content=BP, author="a", involved="abc", linked_staff=[])) == "RQ-001"
    assert code(lambda: w.submit(content=(x for x in [1]))) == "RQ-001"
    assert code(lambda: w.submit(content={"a": (x for x in [1])})) == "RQ-001"
    assert code(lambda: w.submit(content={"a": {1, 2}})) == "RQ-001"
    iid = w.submit()
    w.claim(iid)
    from reviewqueue import checklist_ids
    gen_cl = ((i, "pass") for i in checklist_ids("blueprint_draft"))
    assert code(lambda: w.decide(iid, checklist=gen_cl)) == "RQ-009"
    assert code(lambda: w.decide(iid, decision=iter(["approved"]))) == "RQ-001"


def test_floats_nan_and_non_string_keys_refused(w):
    for bad in ({"a": 1.5}, {"a": float("nan")}, {1: "x"}, {"a": {"b": [0.1]}}, 5, "str", None):
        assert code(lambda: w.submit(content=bad)) == "RQ-001"
    assert code(lambda: w.submit(content={"a": [[[[[[[[[[[[[[1]]]]]]]]]]]]]]})) == "RQ-001"  # too deep


def test_tuple_and_list_content_have_one_digest():
    assert content_digest({"a": (1, 2)}) == content_digest({"a": [1, 2]})
    assert content_digest({"a": 1, "b": 2}) == content_digest({"b": 2, "a": 1})
    assert content_digest({"a": True}) != content_digest({"a": "True"})


@pytest.mark.parametrize("bad", ["", "a b", "x" * 81, "../x", None, 5, ["a"]])
def test_ids_validated(w, bad):
    assert code(lambda: w.submit(ref=bad)) == "RQ-001"
    assert code(lambda: w.submit(author=bad)) == "RQ-001"


def test_bad_kind_and_hold_type(w):
    assert code(lambda: w.submit(kind="live")) == "RQ-001"
    assert code(lambda: w.submit(hold="yes")) == "RQ-001"


# ---- time ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [1.5, True, "1900000000", None, 0, -1, 10**12])
def test_bad_host_clock_reading_fails_that_call_closed(w, bad):
    iid = w.submit()
    good = w.clock.t
    w.clock.t = bad
    assert code(lambda: w.q.get(w.claims("s-rev1") if False else _c(w, good), tenant_id="t-a", item_id=iid)) in ("RQ-002", "RQ-003")
    assert code(lambda: w.submit(ref="z")) == "RQ-002"
    w.clock.t = good
    w.claim(iid)  # the next call with a sane clock works


def _c(w, t):
    old, w.clock.t = w.clock.t, t
    try:
        return w.claims("s-rev1")
    finally:
        w.clock.t = old


def test_caller_time_is_not_a_parameter(w):
    import inspect
    from reviewqueue import ReviewQueue
    for n in ("submit", "resubmit", "claim", "release", "decide", "get", "list_items", "gate_evidence", "team_reviewed_evidence", "hold_item", "clear_hold", "verify_evidence"):
        assert "now" not in inspect.signature(getattr(ReviewQueue, n)).parameters


def test_clock_cannot_go_backwards_within_skew(w):
    iid = w.submit()
    w.clock.t += 100
    w.claim(iid)
    w.clock.t -= 50  # the host clock reads earlier than the log's last event
    assert code(lambda: w.q.release(w.claims("s-rev1", auth_age=0), tenant_id="t-a", item_id=iid)) in ("RQ-002", "RQ-003")


def test_claim_expires_and_can_be_taken(w):
    iid = w.submit()
    w.claim(iid)
    w.clock.t += 1799
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "claimed"
    w.clock.t += 2
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "pending"
    assert code(lambda: w.decide(iid)) == "RQ-006"  # lapsed claim cannot decide
    v = w.claim(iid, "s-rev2")
    assert v["claim"]["by"] == "s-rev2"
    assert code(lambda: w.decide(iid)) == "RQ-006"  # the first reviewer lost the lock


def test_claim_ttl_bounds():
    w = World()
    for bad in (59, 86_401, True, 1.5, "60"):
        assert code(lambda: ReviewQueue(w.idn, w.roles, integrity_key=KEY, claim_ttl=bad)) == "RQ-012"


def test_release(w):
    iid = w.submit()
    w.claim(iid)
    assert code(lambda: w.q.release(w.claims("s-rev2"), tenant_id="t-a", item_id=iid)) == "RQ-006"
    assert w.q.release(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["state"] == "pending"
    assert code(lambda: w.q.release(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-006"


# ---- duplicates and finality -----------------------------------------------------------------------------------
def test_duplicates(w):
    iid = w.submit()
    assert code(lambda: w.submit()) == "RQ-013"
    assert code(lambda: w.submit(involved=["a", "a"], ref="other")) == "RQ-001"
    w.claim(iid)
    assert code(lambda: w.claim(iid)) == "RQ-005"
    w.decide(iid)
    assert code(lambda: w.decide(iid)) == "RQ-006"
    assert code(lambda: w.claim(iid, "s-rev2")) == "RQ-005"
    w.submit()  # a new review of the same subject is allowed once the old one is final


def test_rejected_is_final_and_changes_requested_needs_resubmit(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid, decision="rejected", note="no")
    assert code(lambda: w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 9}, author="agent-1", involved=[], linked_staff=[])) == "RQ-005"
    j = w.submit(ref="bp-2")
    w.claim(j)
    w.decide(j, decision="changes_requested", note="fix")
    assert code(lambda: w.claim(j, "s-rev2")) == "RQ-005"
    assert code(lambda: w.q.resubmit(tenant_id="t-a", item_id=j, content=BP, author="agent-1", involved=[], linked_staff=[])) == "RQ-001"  # unchanged
    assert code(lambda: w.q.resubmit(tenant_id="t-a", item_id=j, content={**BP, "n": 9}, author="someone", involved=[], linked_staff=[])) == "RQ-003"
    assert w.q.resubmit(tenant_id="t-a", item_id=j, content={**BP, "n": 9}, author="agent-1", involved=[], linked_staff=[]) == 2
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=j)["state"] == "pending"


# ---- stale content ---------------------------------------------------------------------------------------------
def test_decision_on_changed_content_refused_and_old_approval_goes_stale(w):
    iid = w.submit()
    w.claim(iid)
    assert code(lambda: w.decide(iid, content={**BP, "n": 4})) == "RQ-008"
    w.decide(iid)
    ev = w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-a", item_id=iid, current_content={**BP, "entities": []})
    assert ev["stale"] and not ev["eligible"] and ev["state"] == "approved"
    ev = w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": {**BP, "n": 5}})
    assert not ev["eligible"] and ev["items"]["blueprint_draft"]["stale"]


def test_decision_binds_digest_of_the_item_not_the_callers_claim(w):
    iid = w.submit()
    w.claim(iid)
    w.decide(iid)
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["decisions"][0]["contentDigest"] == content_digest(BP)


# ---- hold / quarantine -----------------------------------------------------------------------------------------
def test_hold_cannot_be_approved_and_is_not_eligible(w):
    iid = w.submit(kind="component_request", hold=True)
    w.claim(iid)
    assert code(lambda: w.decide(iid, kind="component_request")) == "RQ-010"
    w.decide(iid, kind="component_request", decision="changes_requested", note="classify first")
    ev = w.q.gate_evidence(w.claims("s-rev1"), tenant_id="t-a", item_id=iid, current_content=BP)
    assert not ev["eligible"]
    w.clock.t += 1
    w.q.resubmit(tenant_id="t-a", item_id=iid, content={**BP, "n": 8}, author="agent-1", involved=[], linked_staff=[])
    assert w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)["hold"]  # a resubmission does not lift the hold
    w.clear_hold(iid)
    w.claim(iid, "s-rev2")
    assert w.decide(iid, "s-rev2", kind="component_request", content={**BP, "n": 8})["state"] == "approved"


def test_forged_approval_of_a_held_item_is_refused_on_read(w):
    iid = w.submit(hold=True)
    w.claim(iid)
    from reviewqueue import checklist_ids
    note = "x"
    w.q._append(iid, "t-a", "decided", w.clock.t, "s-rev1",
                {"revision": 1, "content_digest": content_digest(BP), "decision": "approved",
                 "checklist": {i: "pass" for i in checklist_ids("blueprint_draft")}, "note": note,
                 "note_sha256": hashlib.sha256(note.encode()).hexdigest(), "note_len": 1})
    assert code(lambda: w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)) == "RQ-011"


# ---- checklist and notes ---------------------------------------------------------------------------------------
def test_checklist_must_be_exact_and_all_pass_to_approve(w):
    iid = w.submit()
    w.claim(iid)
    ids = checklist_ids("blueprint_draft")
    assert code(lambda: w.decide(iid, checklist={})) == "RQ-009"
    assert code(lambda: w.decide(iid, checklist={i: "pass" for i in ids[:-1]})) == "RQ-009"
    assert code(lambda: w.decide(iid, checklist={**{i: "pass" for i in ids}, "extra": "pass"})) == "RQ-009"
    assert code(lambda: w.decide(iid, checklist={i: True for i in ids})) == "RQ-009"
    assert code(lambda: w.decide(iid, checklist={**{i: "pass" for i in ids}, ids[0]: "fail"})) == "RQ-009"
    v = w.decide(iid, decision="changes_requested", note="compliance", checklist={**{i: "pass" for i in ids}, ids[0]: "fail"})
    assert v["state"] == "changes_requested"


def test_checklists_cover_every_kind_with_unique_ids():
    for k in KINDS:
        ids = checklist_ids(k)
        assert ids and len(set(ids)) == len(ids)


def test_note_rules(w):
    iid = w.submit()
    w.claim(iid)
    assert code(lambda: w.decide(iid, decision="rejected", note="")) == "RQ-014"
    assert code(lambda: w.decide(iid, decision="rejected", note="   ")) == "RQ-014"
    assert code(lambda: w.decide(iid, note=5)) == "RQ-014"
    assert code(lambda: w.decide(iid, note="a\x00b")) == "RQ-014"
    assert code(lambda: w.decide(iid, note="a‮b")) == "RQ-014"
    assert code(lambda: w.decide(iid, note="x" * 2001)) == "RQ-014"
    assert code(lambda: w.decide(iid, decision="merged")) == "RQ-001"


# ---- audit, labels, aggregate gate -----------------------------------------------------------------------------
def test_audit_has_hash_and_length_never_note_text(w):
    iid = w.submit()
    w.claim(iid)
    secret = "customer IBAN SA0380000000608010167519"
    w.decide(iid, note=secret)
    blob = json.dumps([e.__dict__ for e in w.audit.events()], default=str)
    assert secret not in blob and "SA03" not in blob
    d = [e for e in w.audit.events() if e.action == "review.decide"][-1]
    assert f"note_len={len(secret)}" in d.detail and hashlib.sha256(secret.encode()).hexdigest()[:16] in d.detail


def test_denials_are_audited_with_codes(w):
    iid = w.submit(author="s-author")
    code(lambda: w.claim(iid, "s-author"))
    e = [x for x in w.audit.events() if x.action == "review.claim"][-1]
    assert e.decision == "deny" and e.code == "RQ-007" and e.subject == "s-author"


def test_view_carries_label_keys_not_text_and_both_languages_complete(w):
    iid = w.submit()
    v = w.q.get(w.claims("s-rev1"), tenant_id="t-a", item_id=iid)
    assert v["labelKeys"] == {"kind": "review.kind.blueprint_draft", "state": "review.state.pending"}
    for key in label_keys() | {f"review.error.{c}" for c in CODES}:
        for lang in ("en", "ar"):
            assert label(key, lang).strip()
    assert label("review.state.approved", "ar") != label("review.state.approved", "en")


def test_team_reviewed_evidence_needs_blueprint_and_every_required_kind(w):
    assert code(lambda: w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={})) == "RQ-001"
    assert code(lambda: w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={"component_request": BP})) == "RQ-001"
    ev = w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": BP})
    assert ev["missing"] == ["blueprint_draft"] and not ev["eligible"]
    approved(w)
    cr = {"spec": 1}
    w.submit(kind="component_request", content=cr)
    ev = w.q.team_reviewed_evidence(w.claims("s-rev1"), tenant_id="t-a", subject_ref="bp-1", required={"blueprint_draft": BP, "component_request": cr})
    assert not ev["eligible"] and ev["items"]["component_request"]["state"] == "pending"


def test_list_needs_verified_reviewer_and_returns_metadata_only(w):
    w.submit()
    rows = w.q.list_items(w.claims("s-rev1"), state="pending")
    assert len(rows) == 1 and "\"content\"" not in json.dumps(rows) and set(rows[0]) >= {"itemId", "tenantId", "state"}
    assert code(lambda: w.q.list_items(w.claims("s-norole"))) == "RQ-003"
    assert code(lambda: w.q.list_items(w.claims("s-rev1"), state="live")) == "RQ-001"
