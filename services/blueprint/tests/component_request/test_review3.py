"""Regression tests for the third review of PR 216 (R1 to R6, Q-432)."""
import sys
from dataclasses import dataclass

import pytest
from cr_support import AGENT, CLERK, REVIEWER, T0, T1, T2, T3, TEN, FakeLibrary, ask, build, gap, good_draft

from component_request import Actor, RequestError, codes, policy, validate_draft
from component_request.draft import classify_draft

FIX = {"owner": {"github": "example-owner"}, "licence": {"spdx": "LicenseRef-Proprietary"}}
LATER = "2026-11-20T10:30:00Z"


def human(i):
    return Actor("human", i, ("component_reviewer",), True)


def in_review(system, **kw):
    s, _ = system(**kw)
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    return s, rid


# R1: separation of duties across requester, drafter, submitter, attesters and approver
@pytest.mark.parametrize("what", ["generalisation", "need", "draft"])
def test_an_attester_may_not_approve(system, what):
    s, rid = in_review(system, min_tenants=2)
    if what == "generalisation":
        s.attest_generalisable(rid, human("attester-1"), T2)
    else:
        s.attest_generalisable(rid, human("someone"), T2)
    s.submit_for_review(rid, T2, CLERK)

    if what != "generalisation":
        s._records[rid]["classification"]["need_attested_by" if what == "need" else "draft_attested_by"] = "attester-1"
        s._seal(s._records[rid])
    with pytest.raises(RequestError) as e:
        s.approve(rid, human("attester-1"), T3)
    assert e.value.code == codes.SELF_APPROVAL
    assert s.approve(rid, human("a-fourth-person"), T3)["status"] == "approved"


# R2: money hidden in allowed field types
def fields(*fs):
    d = good_draft()
    d["spec"]["fields"] = [{"entity": "visit_checklist", "required": False, **f} for f in fs]
    return d


@pytest.mark.parametrize("f", [
    {"name": "outcome", "type": "select", "options": ["good", "points", "bad"]},
    {"name": "status", "type": "select", "options": ["paid", "open"]},
    {"name": "state", "type": "select", "options": ["refunded", "open"]},
    {"name": "is_paid", "type": "checkbox"}, {"name": "refunded", "type": "checkbox"}, {"name": "settled", "type": "checkbox"},
    {"name": "points", "type": "text"}, {"name": "loyalty_points", "type": "long_text"}, {"name": "redeemed", "type": "checkbox"},
])
def test_financial_words_in_allowed_types_park_the_draft_as_money(f):
    d = fields(f)
    try:
        cls = classify_draft(validate_draft(d, "CR-1", FIX))
    except RequestError as e:                                      # the stricter list may refuse outright: also fine
        assert e.code == codes.FORBIDDEN_SCOPE
        return
    assert not cls["proven"] and cls["has_money_field"]


def test_arabic_financial_words():
    for t in ("رصيد", "نقاط الولاء", "مدفوع", "مسترد"):
        assert policy.financial_hit(t), t
    assert not policy.financial_hit("visit result")


def test_a_human_cannot_attest_plain_over_hidden_money(system):
    s, _ = system(result=fields({"name": "is_paid", "type": "checkbox"}))
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    out = s.draft(rid, T1, AGENT)
    assert out["status"] == "needs_human_classification" and out["classification"]["draft"]["has_money_field"]
    with pytest.raises(RequestError) as e:
        s.attest_risk_class(rid, REVIEWER, "plain", T2)
    assert e.value.code == codes.MONEY_FIELD


# R3
def test_link_target_declared_ledger_or_stock_in_the_library_is_refused():
    lib = FakeLibrary([{"id": "x.wallet", "version": "1.0.0", "provides": [
        {"capability": "x.wallet.manage", "artifacts": [{"type": "entity", "ref": "gift_card", "riskClass": "ledger"}]}]}])
    d = good_draft()
    d["spec"]["fields"][1]["target"] = "gift_card"
    with pytest.raises(RequestError) as e:
        validate_draft(d, "CR-1", FIX, lib)
    assert e.value.code == codes.FORBIDDEN_SCOPE
    d["spec"]["fields"][1]["target"] = "mystery"                       # not declared anywhere: unproven, not refused
    assert not classify_draft(validate_draft(d, "CR-1", FIX, lib), lib)["proven"]


@pytest.mark.parametrize("name", ["bank_visit", "warehouse_visit", "account_visit", "bank_account_visit", "price_list_visit"])
def test_words_of_the_reviewed_table_do_not_make_a_name_plain(name):
    assert policy.classify("entity", name)[0] != "plain"


def test_reviewed_plain_names_still_plain_by_table():
    assert policy.classify("entity", "sales_quote")[0] == "plain" and policy.classify("entity", "warehouse")[0] == "plain"


# R4
def test_only_the_real_principal_type_is_accepted(system):
    @dataclass(frozen=True)
    class Fake:
        tenant_id: str = "tenant-aaa1"
        subject: str = "agent"
        role_ids: tuple = ()
        session_id: str = "s1"
    s, _ = system()
    with pytest.raises(RequestError) as e:
        s.intake(gap(), Fake(), T0)
    assert e.value.code == codes.MALFORMED_INTAKE


# R5: separate derived keys, key ids, rotation
def test_keys_are_separated_and_rotate(system):
    s, rid = in_review(system, integrity_keys={"k1": b"first-master-key"}, integrity_key=None, key_id="k1")
    assert s._derived("k1", b"record-seal") != s._derived("k1", b"draft-digest") != s._derived("k1", b"tenant-ref")
    assert s.get(rid)["key_id"] == "k1" and s.get(rid)["draft_key_id"] == "k1"
    s._keys["k2"] = b"second-master-key"
    s._active = "k2"
    assert s.get(rid)["key_id"] == "k1"                                   # old record still verifies under its own key id
    s.submit_for_review(rid, T2, CLERK)
    r = s.get(rid)
    assert r["key_id"] == "k2" and r["draft_key_id"] == "k1"              # resealed under the new key, draft digest keeps its key
    assert s.approve(rid, REVIEWER, T3)["status"] == "approved"
    del s._keys["k1"]                                                      # key withdrawn: the draft can no longer be trusted
    with pytest.raises(RequestError):
        s.get(rid)


def test_unknown_active_key_id_is_refused():
    with pytest.raises(ValueError):
        build(integrity_keys={"k1": b"x" * 16}, integrity_key=None, key_id="nope")


# R6
def test_approval_needs_a_host_clock(system):
    s, rid = in_review(system, host_now=None)
    s.submit_for_review(rid, T2, CLERK)
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.BAD_CLOCK


# Q-432
def test_operate_paths_are_appended_not_inserted_first():
    ops = [i for i, p in enumerate(sys.path) if p.endswith("services/operate") or p.endswith("blueprint/events")]
    assert ops and all(i > 0 for i in ops)
