"""Regression tests for the PR 216 re-review: N1 (structural plain), N2 (tenant from the principal), N3 (whole-record seal)."""
import copy

import pytest
from cr_support import AGENT, CLERK, REVIEWER, T0, T1, T2, T3, TEN, TEN2, Prin, ask, forge, gap, good_draft

from component_request import Actor, RequestError, codes, policy, validate_draft
from component_request.draft import classify_draft
from component_request.text import scope_hits, sensitive_hits

FIX = {"owner": {"github": "example-owner"}, "licence": {"spdx": "LicenseRef-Proprietary"}}
LATER = "2026-11-20T10:30:00Z"

NAMES = ["booking_deposit", "loyalty_wallet", "loyalty_cashback", "booking_prepayment", "ticket_commission", "training_allowance",
         "visit_overtime", "booking_bonus", "complaint_compensation", "booking_loan", "booking_advance", "ticket_receivable",
         "accounts_payable_note", "project_cost", "maintenance_charge", "course_fees", "booking_tills", "booking_cashbox",
         "booking_refunds", "booking_payouts", "booking_debits", "booking_settlements", "booking_transfers", "booking_adjustments",
         "booking_shipments", "booking_stocks", "booking_vats", "booking_gls", "equipment_depreciations", "booking_zakah",
         "booking_t_a_x", "tag_users", "acme_visit", "almarai_ticket", "ahmed_alharbi_visit", "booking_zzz"]


def draft_for(entity, fields=None):
    d = good_draft()
    d["manifest"]["provides"][0]["artifacts"][0] = {"type": "entity", "ref": entity}
    d["spec"]["fields"] = fields or [{"entity": entity, "name": "result", "type": "text", "required": True}]
    return d


def money(entity, typ="money"):
    return [{"entity": entity, "name": "score", "type": typ, "required": True}]


# N1: nothing is "plain" because of its name
@pytest.mark.parametrize("name", NAMES)
def test_names_are_never_proven_plain_by_a_benign_word(name):
    assert policy.classify("entity", name)[0] in ("refuse", "unproven"), name


@pytest.mark.parametrize("name", NAMES)
def test_these_needs_never_reach_the_model_without_a_human(system, name):
    s, d = system()
    out = ask(s, gap(ref=name), T0, TEN)
    assert out["request"]["status"] in ("refused", "needs_human_classification") and d.briefs == []
    with pytest.raises(RequestError):
        s.draft(out["request"]["id"], T1, AGENT)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("with_money", [False, True])
def test_drafts_for_these_names_are_refused_or_unproven_with_and_without_money_fields(name, with_money):
    d = draft_for(name, money(name) if with_money else None)
    try:
        clean = validate_draft(d, "CR-1", FIX)
    except RequestError as e:
        assert e.code in (codes.FORBIDDEN_SCOPE, codes.DRAFT_RISK)
        return
    cls = classify_draft(clean)
    assert not cls["proven"] and cls["has_money_field"] is with_money


@pytest.mark.parametrize("typ", ["money", "decimal", "percent", "currency", "quantity", "rate"])
def test_money_typed_fields_make_a_draft_unproven_never_plain(typ):
    cls = classify_draft(validate_draft(draft_for("visit_checklist", money("visit_checklist", typ)), "CR-1", FIX))
    assert not cls["proven"] and cls["has_money_field"] and "money_field" in cls["reasons"]


@pytest.mark.parametrize("typ", ["integer", "boolean"])
def test_other_types_outside_the_allow_list_are_unproven(typ):
    cls = classify_draft(validate_draft(draft_for("visit_checklist", money("visit_checklist", typ)), "CR-1", FIX))
    assert not cls["proven"] and not cls["has_money_field"]


def test_good_draft_is_proven_and_allow_listed_types_pass():
    d = good_draft()
    d["spec"]["fields"] += [{"entity": "visit_checklist", "name": "visited_on", "type": "date", "required": False},
                            {"entity": "visit_checklist", "name": "done", "type": "checkbox", "required": False},
                            {"entity": "visit_checklist", "name": "photo", "type": "attachment", "required": False},
                            {"entity": "visit_checklist", "name": "outcome", "type": "select", "required": False,
                             "options": ["good", "bad"]}]
    assert classify_draft(validate_draft(d, "CR-1", FIX))["proven"]


@pytest.mark.parametrize("field,why", [
    ({"name": "kind", "type": "select", "required": True}, "malformed"),                     # open select
    ({"name": "kind", "type": "text", "required": True, "options": ["a"]}, "malformed"),
    ({"name": "owner_ref", "type": "link", "required": True}, "malformed"),                  # link without target
])
def test_select_and_link_shapes(field, why):
    d = good_draft()
    d["spec"]["fields"][0] = {"entity": "visit_checklist", **field}
    with pytest.raises(RequestError) as e:
        validate_draft(d, "CR-1", FIX)
    assert e.value.code == codes.MALFORMED_DRAFT


@pytest.mark.parametrize("target,outcome", [("payment_entry", "refuse"), ("stock_entry", "refuse"), ("user_role_grant", "refuse"),
                                            ("mystery_thing", "unproven"), ("customer", "plain"), ("visit_checklist", "plain")])
def test_link_target_must_be_plain(target, outcome):
    d = good_draft()
    d["spec"]["fields"][1]["target"] = target
    if outcome == "refuse":
        with pytest.raises(RequestError) as e:
            validate_draft(d, "CR-1", FIX)
        assert e.value.code == codes.FORBIDDEN_SCOPE
    else:
        assert classify_draft(validate_draft(d, "CR-1", FIX))["proven"] is (outcome == "plain")


@pytest.mark.parametrize("field", ["iban", "national_id", "passport_number", "password", "bank_account_number", "card_number",
                                   "date_of_birth", "api_key", "health_condition", "salary", "secret_note"])
def test_sensitive_field_names_refused(field):
    d = good_draft()
    d["spec"]["fields"][0]["name"] = field
    with pytest.raises(RequestError) as e:
        validate_draft(d, "CR-1", FIX)
    assert e.value.code == codes.FORBIDDEN_SCOPE


@pytest.mark.parametrize("name", ["training_passport", "survey_national_id", "visit_iban"])
def test_sensitive_entity_names_refused(name):
    assert policy.classify("entity", name) == ("refuse", "sensitive")


def test_arabic_sensitive_and_broken_plural_and_split_letters():
    assert sensitive_hits("رقم الهوية") and sensitive_hits("كلمة السر") and sensitive_hits("رقم الايبان")
    for t in ("ضرائب", "الضرائب", "المرتبات", "الأجر", "ترحيل", "ذمم", "t a x", "v.a.t", "jour nal", "sal ary", "payroII"):
        assert scope_hits(t), t


# the human path for what is not provably plain
def parked(system, **kw):
    s, d = system(**kw)
    rid = ask(s, gap(ref="booking_zzz"), T0, TEN)["request"]["id"]
    return s, d, rid


def test_unproven_need_is_parked_then_attested_plain_by_a_human_and_proceeds(system):
    s, d, rid = parked(system, result=draft_for("booking_zzz"))
    assert s.get(rid)["status"] == "needs_human_classification" and d.briefs == []
    for who in (AGENT, Actor("human", "h", ("component_reviewer",), False), Actor("human", "discovery-agent", ("component_reviewer",), True)):
        with pytest.raises(RequestError):
            s.attest_risk_class(rid, who, "plain", T1)
    s.attest_risk_class(rid, REVIEWER, "plain", T1)
    out = s.draft(rid, T2, AGENT)                      # the draft is judged again: its entity name is still unproven
    assert out["status"] == "needs_human_classification" and out["classification"]["draft"]["reasons"] == ["artifact_name"]
    s.attest_risk_class(rid, REVIEWER, "plain", T2)
    assert s.get(rid)["classification"]["draft_attested_digest"] == s.get(rid)["draft_digest"]
    s.submit_for_review(rid, T3, CLERK)
    done = s.approve(rid, Actor("human", "founder-z", ("component_reviewer",), True), LATER)
    assert done["status"] == "approved" and done["classification"]["need_attested_by"] == "founder-b"


def test_human_attesting_a_non_plain_class_routes_to_the_human_built_path(system):
    s, _, rid = parked(system)
    out = s.attest_risk_class(rid, REVIEWER, "ledger", T1)
    assert out["status"] == "refused" and out["refusal"]["route"] == "human_built"


def test_human_can_never_attest_plain_for_a_draft_with_a_money_field(system):
    s, _, rid = parked(system, result=draft_for("booking_zzz", money("booking_zzz")))
    s.attest_risk_class(rid, REVIEWER, "plain", T1)                       # the need itself
    out = s.draft(rid, T2, AGENT)
    assert out["status"] == "needs_human_classification" and out["classification"]["draft"]["has_money_field"]
    with pytest.raises(RequestError) as e:
        s.attest_risk_class(rid, Actor("human", "founder-z", ("component_reviewer",), True), "plain", T3)
    assert e.value.code == codes.MONEY_FIELD
    assert s.attest_risk_class(rid, Actor("human", "founder-z", ("component_reviewer",), True), "ledger", T3)["status"] == "refused"


def test_money_field_cannot_be_approved_even_if_the_store_says_attested(system):
    s, _ = system(result=draft_for("visit_checklist", money("visit_checklist")))
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    assert s.draft(rid, T1, AGENT)["status"] == "needs_human_classification"
    forge(s, rid, lambda x: (x.update(status="in_review", submitted_by="x"), x["history"].append(
        {"seq": len(x["history"]) + 1, "at": T2, "actor": "x", "actor_kind": "human", "event": "submitted", "from": None,
         "to": "in_review", "code": None, "detail": {}}),
        x["classification"].update(draft_attested_by="h", draft_attested_digest=x["draft_digest"])), reseal=True)
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.MONEY_FIELD


def test_attestation_is_bound_to_the_draft_digest_and_cleared_on_reopen(system):
    s, d, rid = parked(system, result=draft_for("booking_zzz"))
    s.attest_risk_class(rid, REVIEWER, "plain", T1)
    s.draft(rid, T2, AGENT)
    s.attest_risk_class(rid, REVIEWER, "plain", T2)
    s.attest_generalisable(rid, REVIEWER, T3)
    s.submit_for_review(rid, T3, CLERK)
    s.reject(rid, Actor("human", "founder-z", ("component_reviewer",), True), T3, "quality")
    out = s.reopen(rid, REVIEWER, LATER)
    assert out["status"] == "requested" and out["classification"]["need_attested_by"] is None \
        and out["generalisation"]["attested_by"] is None
    assert s.draft(rid, LATER, AGENT)["status"] == "needs_human_classification"      # the need is re-judged, not trusted


def test_workflow_and_component_needs_are_not_draftable(system):
    s, d = system()
    for kind in ("workflow", "component"):
        out = ask(s, gap(ref="visit_flow", kind=kind), T0, TEN)
        assert out["request"]["status"] == "refused" and d.briefs == []


def test_draft_must_provide_the_need(system):
    s, _ = system(result=good_draft())
    rid = ask(s, gap(ref="visit_inspection"), T0, TEN)["request"]["id"]
    out = s.draft(rid, T1, AGENT)
    assert out["status"] == "requested" and out["history"][-1]["code"] == codes.MALFORMED_DRAFT


# N2: the tenant comes from the principal
def test_one_session_cannot_present_two_tenants(system):
    s, _ = system(min_tenants=2)
    ask(s, gap(), T0, "tenant-aaa1", session="sess-1")
    with pytest.raises(RequestError) as e:
        ask(s, gap(evidence=[{"kind": "blueprint", "id": "/x/1"}]), T1, "tenant-fake9", session="sess-1")
    assert e.value.code == codes.TENANT_MISMATCH
    assert len(s.list()[0]["tenants"]) == 1


def test_a_tenant_without_evidence_does_not_count(system):
    s, _ = system(min_tenants=2)
    rid = ask(s, gap(), T0, "tenant-aaa1")["request"]["id"]
    ask(s, gap(evidence=[]), T1, "tenant-bbb2")
    assert len(s.get(rid)["tenants"]) == 1
    s.draft(rid, T2, AGENT)
    s.submit_for_review(rid, T3, CLERK)
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, LATER)
    assert e.value.code == codes.NO_GENERALISATION


def test_two_real_tenants_in_two_sessions_count_and_raw_ids_are_not_stored(system):
    s, _ = system(min_tenants=2)
    rid = ask(s, gap(), T0, "tenant-aaa1", session="s1")["request"]["id"]
    ask(s, gap(), T1, "tenant-bbb2", session="s2")
    r = s.get(rid)
    assert len(r["tenants"]) == 2 and "tenant-aaa1" not in str(r)
    assert any("tenant" in h["detail"] for h in r["history"])                      # the tenant ref is on the event, auditable
    s.draft(rid, T2, AGENT)
    s.submit_for_review(rid, T3, CLERK)
    assert s.approve(rid, REVIEWER, LATER)["status"] == "approved"


# N3: whole-record seal
def approved(system, **kw):
    s, _ = system(**kw)
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    s.submit_for_review(rid, T2, CLERK)
    return s, rid


def test_forged_approved_status_is_caught(system):
    s, rid = approved(system)

    def forge_approval(x):
        x["status"] = "approved"
        x["history"].append({"seq": len(x["history"]) + 1, "at": T3, "actor": "x", "actor_kind": "human", "event": "approved",
                             "from": "in_review", "to": "approved", "code": None, "detail": {}})
        x["decision"] = {"by": "x", "at": T3, "outcome": "approved"}
    forge(s, rid, forge_approval)
    with pytest.raises(RequestError) as e:
        s.get(rid)
    assert e.value.code == codes.INTEGRITY
    assert rid in [b[0] for b in s.invalid()] and s.list() == []


@pytest.mark.parametrize("what", ["attestation", "tenants", "history", "classification", "requested_by"])
def test_forged_fields_are_caught(system, what):
    s, rid = approved(system, min_tenants=2)
    fns = {"attestation": lambda x: x["generalisation"].update(attested_by="me"),
           "tenants": lambda x: x["tenants"].update({"fake" * 6: [{"kind": "blueprint", "id": "/x/1"}]}),
           "history": lambda x: x["history"][0].update(actor="someone-else"),
           "classification": lambda x: x["classification"].update(need_attested_by="me"),
           "requested_by": lambda x: x.update(requested_by="other")}
    forge(s, rid, fns[what])
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.INTEGRITY


def test_without_a_key_nothing_is_trusted_as_approved(system):
    s, rid = approved(system, integrity_key=None)
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.INTEGRITY
    forge(s, rid, lambda x: (x.update(status="approved"), x["history"].append(
        {"seq": len(x["history"]) + 1, "at": T3, "actor": "x", "actor_kind": "human", "event": "approved", "from": "in_review",
         "to": "approved", "code": None, "detail": {}})))
    with pytest.raises(RequestError) as e:
        s.get(rid)
    assert e.value.code == codes.INTEGRITY


def test_a_key_rotation_breaks_one_record_not_the_listing(system):
    s, _ = system()
    a = ask(s, gap(), T0, TEN)["request"]["id"]
    b = ask(s, gap(ref="visit_survey"), T0, TEN)["request"]["id"]
    s._records[a]["seal"] = "0" * 64
    assert [r["id"] for r in s.list()] == [b] and s.invalid() == [(a, codes.INTEGRITY)]


# mediums
def test_evidence_without_kind_does_not_crash(system):
    s, _ = system()
    out = ask(s, gap(evidence=[{"id": "/x/1"}, {"kind": "blueprint"}, 5, None]), T0, TEN)
    assert out["request"]["tenants"] == {} and codes.UNTRUSTED_TEXT in out["request"]["flags"]


def test_schema_and_flags_are_checked_on_read(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    for mut in (lambda x: x.update(schema="9"), lambda x: x.update(flags=None), lambda x: x.update(decision=5)):
        saved = copy.deepcopy(s._records[rid])
        forge(s, rid, mut, reseal=True)
        with pytest.raises(RequestError) as e:
            s.get(rid)
        assert e.value.code == codes.RECORD_INVALID
        s._records[rid] = saved


def test_clock_bounds(system):
    s, _ = system(host_now=lambda: T1)
    with pytest.raises(RequestError):                                           # ahead of the host clock
        ask(s, gap(), "2026-11-20T11:00:00Z", TEN)
    s2, _ = system()
    rid = ask(s2, gap(), T0, TEN)["request"]["id"]
    for _i in range(3):                                                         # a failed call never moves the clock
        with pytest.raises(RequestError):
            s2.reject(rid, REVIEWER, "2026-11-20T10:50:00Z", "quality")
    with pytest.raises(RequestError):                                           # more than an hour past what was seen
        s2.draft(rid, "2026-11-20T12:00:00Z", AGENT)
    assert s2.draft(rid, T1, AGENT)["status"] == "drafted"
