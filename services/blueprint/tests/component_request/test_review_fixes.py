"""Regression tests for every probe of the PR 216 review (H1 to H3, M1 to M7, L1 to L6)."""
import copy

import pytest
from cr_support import ask, forge, AGENT, CLERK, REVIEWER, T0, T1, T2, T3, TEN, TEN2, FakeLibrary, build, gap, good_draft

from component_request import Actor, RequestError, codes, policy, validate_draft
from component_request.draft import classify_draft
from component_request.text import scope_hits

FIX = {"owner": {"github": "example-owner"}, "licence": {"spdx": "LicenseRef-Proprietary"}}


def draft_for(entity, artifact_extra=None, cap="sales.visit_checklist.manage"):
    d = good_draft()
    d["manifest"]["provides"][0]["artifacts"][0] = {"type": "entity", "ref": entity, **(artifact_extra or {})}
    d["spec"]["fields"] = [{"entity": entity, "name": "result", "type": "text", "required": True}]
    return d


def code_of(d, library=None):
    with pytest.raises(RequestError) as e:
        validate_draft(d, "CR-1", FIX, library)
    return e.value.code


# H1: the class is derived, never taken from the model
@pytest.mark.parametrize("ent", ["credit_note", "payment_entry", "sales_invoice", "stock_entry", "bank_transaction", "user_role_grant",
                                 "debit_note", "expense_claim"])
@pytest.mark.parametrize("risk", [None, "plain"])
def test_non_plain_or_unknown_entities_refused_whatever_the_model_claims(ent, risk):
    extra = {"riskClass": risk} if risk else {}
    assert code_of(draft_for(ent, extra)) in (codes.FORBIDDEN_SCOPE, codes.DRAFT_RISK)


@pytest.mark.parametrize("ent", ["credit_note", "payment_entry", "sales_invoice", "stock_entry", "bank_transaction", "user_role_grant"])
def test_these_needs_are_refused_at_intake_before_the_model_is_called(system, ent):
    s, d = system()
    r = ask(s, gap(ref=ent), T0, TEN)["request"]
    assert r["status"] == "refused" and r["refusal"]["code"] == codes.FORBIDDEN_SCOPE and d.briefs == []


def test_risk_class_is_set_by_policy_not_the_model():
    d = good_draft()
    del d["manifest"]["provides"][0]["artifacts"][0]["riskClass"]
    assert validate_draft(d, "CR-1", FIX)["manifest"]["provides"][0]["artifacts"][0]["riskClass"] == "plain"
    d["manifest"]["provides"][0]["artifacts"][0]["riskClass"] = "ledger"
    assert code_of(d) in (codes.FORBIDDEN_SCOPE, codes.DRAFT_RISK)


def test_derive_class_unit():
    assert policy.derive_class("entity", "visit_checklist")[0] == "plain"
    assert policy.derive_class("entity", "sales_quote") == ("plain", "reviewed_table")
    assert policy.derive_class("entity", "credit_note")[0] is None and policy.derive_class("entity", "stock_entry")[0] is None
    assert policy.classify("entity", "zzz_thing") == ("unproven", "not_all_benign")
    assert policy.derive_class("entity", "user_role_grant")[1] == "identity_domain"


# H2
@pytest.mark.parametrize("typ", ["role_template", "function", "notification", "event", "workflow", "metric", "tool", "scheduled_job"])
def test_artifact_kinds_off_the_allow_list_refused(typ):
    d = good_draft()
    d["manifest"]["provides"][0]["artifacts"][1] = {"type": typ, "ref": "visit_checklist_x"}
    assert code_of(d) == codes.DRAFT_RISK


@pytest.mark.parametrize("role", ["platform_admin", "component_reviewer", "tenant_admin", "superuser", "agent_runner", "approver"])
def test_platform_roles_refused_in_permissions(role):
    d = good_draft()
    d["spec"]["permissions"][0]["role"] = role
    assert code_of(d) == codes.DRAFT_RISK


def test_requires_default_deny_and_library_check():
    plain = {"id": "sales.visit_notes", "version": "1.0.0", "provides": [
        {"capability": "sales.visit_notes.manage", "artifacts": [{"type": "entity", "ref": "visit_note"}]}]}
    ledger = {"id": "finance.payment_post", "version": "1.0.0", "provides": [
        {"capability": "finance.payment.post", "artifacts": [{"type": "entity", "ref": "payment_entry"}]}]}
    lib = FakeLibrary([plain, ledger])
    d = good_draft()
    d["manifest"]["requires"] = [{"capability": "finance.payment.post", "versionRange": "^1.0.0"}]
    assert code_of(d, lib) == codes.DRAFT_RISK
    d["manifest"]["requires"] = [{"component": "finance.payment_post", "versionRange": "^1.0.0"}]
    assert code_of(d, lib) == codes.DRAFT_RISK
    d["manifest"]["requires"] = [{"component": "unknown.thing", "versionRange": "^1.0.0"}]
    assert code_of(d, lib) == codes.DRAFT_RISK
    assert code_of(d, None) == codes.DRAFT_RISK
    d["manifest"]["requires"] = [{"component": "sales.visit_notes", "versionRange": "^1.0.0"}]
    assert validate_draft(d, "CR-1", FIX, lib)["manifest"]["requires"]


# H3
@pytest.mark.parametrize("text", [
    "payrolls", "pay_roll", "pay slip", "wages", "remuneration", "gross_pay", "net_pay", "EOSB", "bookkeeping", "chart of accounts",
    "trial balance", "withholding", "excise", "salestax", "taxcode", "tаx", "pаyroll", "p4yroll", "ضـريبة",
    "ضَريبة", "الأجور", "محاسبة", "الفوترة",
    "قيد", "دفتر الأستاذ", "SalesTax", "VATReturn", "e-invoice", "E Invoicing",
])
def test_scope_words_survive_normalisation(text):
    assert scope_hits(text), text


@pytest.mark.parametrize("text", ["syntax", "private", "visit_checklist", "sales_quote", "قائمة فحص"])
def test_scope_words_do_not_overmatch(text):
    assert scope_hits(text) == []


@pytest.mark.parametrize("field", ["pay_roll", "wages", "gross_pay", "bookkeeping", "tax_code", "ledger_ref", "entry_date"])
def test_identifiers_in_a_draft_checked_structurally(field):
    d = good_draft()
    d["spec"]["fields"][0]["name"] = field
    assert code_of(d) == codes.FORBIDDEN_SCOPE


def test_look_alike_letters_in_a_draft_are_hostile():
    d = good_draft()
    d["spec"]["capabilities"][0]["summary"] = "Create and edit уisit lists for sales teams"
    assert code_of(d) == codes.HOSTILE_DRAFT


def test_an_unlisted_synonym_is_still_refused_by_structure():
    # no word list knows "stipend"; the entity has no benign scope word, so default deny decides
    d = draft_for("zzz_run")                       # accepted by the draft check, but not provably plain: a human must classify
    assert validate_draft(d, "CR-1", FIX) and not classify_draft(validate_draft(d, "CR-1", FIX))["proven"]


# M1
def test_key_bound_to_need_so_a_refused_need_cannot_poison_another(system):
    s, _ = system()
    poisoned = gap(ref="payroll_run")
    poisoned["request_key"] = gap()["request_key"]
    with pytest.raises(RequestError) as e:
        ask(s, poisoned, T0, TEN)
    assert e.value.code == codes.MALFORMED_INTAKE
    assert ask(s, gap(), T0, TEN)["outcome"] == "created"


# M2
def test_closed_records_are_not_touched_by_a_duplicate(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    s.submit_for_review(rid, T2, CLERK)
    s.approve(rid, REVIEWER, T3)
    before = s.get(rid)
    out = ask(s, gap(evidence=[{"kind": "blueprint", "id": "/x/1"}]), "2026-11-20T11:00:00Z", TEN2)
    assert out["outcome"] == "duplicate" and out["request"] == before


def test_duplicate_with_other_need_under_same_id_is_refused(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    forge(s, rid, lambda x: x["need"].update(ref="something_else"), reseal=True)
    with pytest.raises(RequestError):
        ask(s, gap(), T1, TEN2)


# M4 / M5
def test_generalisation_is_deterministic_not_the_models_word(system):
    s, _ = system(min_tenants=2)
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    s.submit_for_review(rid, T2, CLERK)
    with pytest.raises(RequestError) as e:                       # one tenant, model says tenant_specific false: not enough
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.NO_GENERALISATION
    ask(s, gap(), T3, TEN2)                             # a second tenant raises the same gap
    assert s.approve(rid, REVIEWER, "2026-11-20T10:20:00Z")["status"] == "approved"


def test_human_attestation_replaces_tenant_count(system):
    s, _ = system(min_tenants=3)
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    with pytest.raises(RequestError):
        s.attest_generalisable(rid, Actor("human", "h", ("component_reviewer",), False), T2)
    s.attest_generalisable(rid, REVIEWER, T2)
    s.submit_for_review(rid, T2, CLERK)
    done = s.approve(rid, Actor("human", "founder-c", ("platform_admin",), True), T3)
    assert done["generalisation"]["attested_by"] == "founder-b" and done["status"] == "approved"


def test_exclusive_for_one_client_rationale_is_caught():
    d = good_draft()
    d["generalisation"]["rationale"] = "Built exclusively for the Jeddah branch workflow of one firm."
    assert code_of(d) == codes.PER_CLIENT


# M6
def test_stored_record_is_validated_on_read(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    pristine = s.get(rid)
    for mutate in (lambda r: r.update(status="approved"), lambda r: r.update(status="bogus"), lambda r: r["history"].pop(),
                   lambda r: r.pop("tenants"), lambda r: r.update(requested_by=5)):
        s._records[rid] = copy.deepcopy(pristine)
        mutate(s._records[rid])
        with pytest.raises(RequestError) as e:
            s.get(rid)
        assert e.value.code == codes.RECORD_INVALID


def test_keyed_digest_stops_a_store_writer_who_swaps_in_a_valid_draft(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    from component_request import digest

    def swap(rec):
        other = copy.deepcopy(rec["draft"])
        other["spec"]["permissions"].append({"role": "sales_rep", "action": "read"})
        rec["draft"], rec["draft_digest"] = other, digest(other)         # attacker recomputes the unkeyed digest
    forge(s, rid, swap)
    with pytest.raises(RequestError) as e:
        s.submit_for_review(rid, T2, CLERK)
    assert e.value.code in (codes.INTEGRITY, codes.DRAFT_TAMPERED)


def test_approve_rechecks_the_need(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    s.submit_for_review(rid, T2, CLERK)
    forge(s, rid, lambda x: x["need"].update(ref="payroll_run"), reseal=True)
    with pytest.raises(RequestError) as e:
        s.approve(rid, REVIEWER, T3)
    assert e.value.code == codes.DRAFT_TAMPERED


# M7
def test_quality_rejection_can_be_reopened_scope_refusal_cannot(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    s.draft(rid, T1, AGENT)
    s.submit_for_review(rid, T2, CLERK)
    s.reject(rid, REVIEWER, T3, "quality")
    assert s.reopen(rid, REVIEWER, "2026-11-20T10:20:00Z")["status"] == "requested"
    refused = ask(s, gap(ref="payroll_run"), T0, TEN)["request"]["id"]
    with pytest.raises(RequestError):
        s.reopen(refused, REVIEWER, T3)


# L1
def test_clock_far_future_cannot_lock_a_record(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    for bad in ("9999-12-31T23:59:59Z", "2030-01-01T00:00:00Z"):
        with pytest.raises(RequestError) as e:
            ask(s, gap(), bad, TEN2)
        assert e.value.code == codes.BAD_CLOCK
    assert s.draft(rid, T1, AGENT)["status"] == "drafted"


# L2
def test_the_human_who_ran_the_draft_may_not_approve_and_ids_are_case_insensitive(system):
    s, _ = system()
    rid = ask(s, gap(), T0, TEN)["request"]["id"]
    drafter = Actor("human", "Founder-B", ("component_reviewer",), True)
    s.draft(rid, T1, drafter)
    s.submit_for_review(rid, T2, CLERK)
    for who in (REVIEWER, drafter, Actor("human", "FOUNDER-A", ("component_reviewer",), True)):
        with pytest.raises(RequestError) as e:
            s.approve(rid, who, T3)
        assert e.value.code == codes.SELF_APPROVAL


# L3
@pytest.mark.parametrize("path", ["tests/./.git/hooks/pre-commit", "tests//x.py", "tests/.hidden/x.py", "other/x.py", "tests", ".git/x",
                                  "tests/../x.py"])
def test_test_paths(path):
    d = good_draft()
    d["manifest"]["tests"][0]["path"] = path
    assert code_of(d) == codes.MALFORMED_DRAFT


# L4
def test_library_dedupe_ignores_draft_level_and_factory_manifests_and_odd_shapes(system):
    def m(level, origin=None, provides=None):
        return {"id": "sales.visit_checklist", "version": "1.0.0", "certification": {"level": level}, "origin": origin or {},
                "provides": provides or [{"capability": "x.y", "artifacts": [{"type": "entity", "ref": "visit_checklist"}]}]}
    for lib in ([m("draft")], [m("certified", {"source": "component_factory"})], [m("certified", provides=[{"artifacts": [5]}])]):
        s, _ = system(library=lib)
        assert ask(s, gap(), T0, TEN)["outcome"] == "created"


# L5, L6
def test_error_messages_do_not_echo_model_values():
    d = good_draft()
    d["manifest"]["provides"][0]["artifacts"][1]["type"] = "SECRET_MODEL_TYPE"
    d["spec"]["permissions"][0]["action"] = "SECRET_ACTION"
    for dd in (d, ):
        with pytest.raises(RequestError) as e:
            validate_draft(dd, "CR-1", FIX)
        assert "SECRET" not in str(e.value)
    d2 = good_draft()
    d2["spec"]["permissions"][0]["action"] = "SECRET_ACTION"
    with pytest.raises(RequestError) as e:
        validate_draft(d2, "CR-1", FIX)
    assert "SECRET" not in str(e.value)
