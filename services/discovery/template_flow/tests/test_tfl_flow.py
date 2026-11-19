"""DSC-004 template-first flow. Fictional data only. No model, no network."""
import copy
import json
from pathlib import Path

import pytest

import instantiate
from template_flow import FlowError, TemplateFlow, digest, load_registry

DISC = Path(__file__).resolve().parents[2]
TEMPLATE = DISC / "templates" / "trading-distribution" / "blueprint.template.json"
NOW = "2026-11-19T10:00:00Z"
AR_NAME = "شركة النور للتجارة"
ANSW = {"country": "sa", "name_ar": AR_NAME, "name_en": "Al Noor Trading", "branches": 2,
        "vat_registered": True, "vat_number": "300000000000003"}
_n = iter(range(10**6))


def eid():
    return "edit-%06d" % next(_n)


def draft():
    return instantiate.instantiate(TEMPLATE, ANSW)


def flow(**kw):
    return TemplateFlow(draft(), clock=lambda: NOW, **kw)


def E(pointer, value, **kw):
    return {"id": eid(), "pointer": pointer, "value": value, **kw}


def code(f, edits):
    with pytest.raises(FlowError) as ei:
        f.apply(edits)
    return ei.value.code


# ---- summary ------------------------------------------------------------------------------
def test_summary_is_owner_readable_and_keyed():
    s = flow().summary()
    assert s["final"] is False and s["buildState"] == "draft" and s["noticeKey"] == "tpl.notice.draft"
    secs = {x["id"]: x for x in s["sections"]}
    assert {"company", "compliance", "locations", "roles", "approvals", "entities"} <= set(secs)
    name = next(i for i in secs["company"]["items"] if i["pointer"] == "/company/legalName/ar")
    assert name["value"] == AR_NAME and name["untrustedText"] is True and name["editable"]
    cr = next(i for i in secs["company"]["items"] if i["key"] == "company.cr_number")
    assert cr["value"] is None  # offered empty
    thr = [i for i in secs["approvals"]["items"] if i["key"] == "approval.threshold"]
    assert thr and thr[0]["value"] == 50000 and thr[0]["subject"]["id"] == "large_sales_order_approval"
    assert s["confirm"]["questions"] and all({"ar", "en"} <= set(q["text"]) for q in s["confirm"]["questions"])
    assert {c["key"] for c in s["counts"]} >= {"entities", "workflows"}


def test_every_summary_pointer_is_accepted_by_the_flow_and_every_label_key_exists():
    f = flow()
    s = f.summary()
    labels = json.loads((DISC / "template_flow" / "labels.json").read_text(encoding="utf-8"))
    assert set(labels["ar"]) == set(labels["en"])
    keys = {s["titleKey"], s["noticeKey"], s["confirm"]["titleKey"]}
    for sec in s["sections"]:
        keys.add(sec["labelKey"])
        for it in sec["items"]:
            keys.add(it["labelKey"])
            keys.update(o["labelKey"] for o in it.get("options", []))
    keys.update(c["labelKey"] for c in s["counts"])
    assert keys <= set(labels["en"])
    blob = json.dumps(labels).lower()
    assert "frappe" not in blob and "erpnext" not in blob
    from template_flow import errors
    codes = {v for k, v in vars(errors).items() if isinstance(v, str) and v.startswith("TFL-")}
    assert {"tpl.error." + c for c in codes} <= set(labels["en"]) and {"tpl.error." + c for c in codes} <= set(labels["ar"])


def test_summary_does_not_mutate_or_leak_internal_state():
    f = flow()
    s = f.summary()
    s["sections"][0]["items"][0]["value"] = "x"
    assert f.summary()["sections"][0]["items"][0]["value"] != "x"


# ---- happy path and history -----------------------------------------------------------------
def test_arabic_edit_applies_and_revises_draft_never_final():
    f = flow()
    d0 = f.draft_hash
    rev = f.apply([E("/company/legalName/ar", "  مؤسسة الأمل التجارية  ", baseHash=d0)])
    assert rev.blueprint["company"]["legalName"]["ar"] == "مؤسسة الأمل التجارية"
    assert rev.final is False and rev.needs_human_approval and rev.blueprint["meta"]["buildState"] == "draft"
    assert rev.revision == 2 and rev.base_hash == d0 and rev.draft_hash == f.draft_hash != d0
    h = f.history
    assert len(h) == 1 and h[0]["before"] == AR_NAME and h[0]["actor"] == "owner" and h[0]["at"] == NOW
    TemplateFlow.verify_history(h)


def test_arabic_indic_digits_numbers_and_yes_no():
    f = flow()
    r = f.apply([
        E("/approvals/large_sales_order_approval/conditions/total_amount|gt/value", "٧٥٬٠٠٠"),
        E("/company/crNumber", "١٠١٠٢٣٤٥٦٧"),
        E("/compliance/vat/pricesIncludeVat", "نعم"),
        E("/compliance/vat/filingPeriod", "Quarterly"),
    ]).blueprint
    ap = next(a for a in r["approvals"] if a["id"] == "large_sales_order_approval")
    assert ap["conditions"][0]["value"] == 75000
    assert r["company"]["crNumber"] == "1010234567" and r["compliance"]["vat"]["pricesIncludeVat"] is True
    assert r["compliance"]["vat"]["filingPeriod"] == "quarterly"
    assert ap["provenance"]["humanEdited"] is True and ap["provenance"]["editedBy"] == "owner"


def test_input_draft_and_returned_revision_are_not_aliased():
    d = draft()
    f = TemplateFlow(d, clock=lambda: NOW)
    d["company"]["legalName"]["en"] = "tampered"
    assert f.draft["company"]["legalName"]["en"] == "Al Noor Trading"
    rev = f.apply([E("/company/legalName/en", "Al Amal Trading")])
    rev.blueprint["company"]["legalName"]["en"] = "tampered"
    assert f.draft["company"]["legalName"]["en"] == "Al Amal Trading"


def test_batch_is_atomic():
    f = flow()
    before = f.draft_hash
    assert code(f, [E("/company/legalName/en", "Fine Name"), E("/company/country", "AE")]) == "TFL-PATH-002"
    assert f.draft_hash == before and f.history == []


def test_history_chain_detects_tampering_and_restores():
    f = flow()
    f.apply([E("/company/legalName/en", "Name One")])
    f.apply([E("/company/legalName/en", "Name Two")])
    h = f.history
    f2 = TemplateFlow(f.draft, clock=lambda: NOW, history=h)
    assert len(f2.history) == 2
    bad = copy.deepcopy(h)
    bad[0]["after"] = "forged"
    with pytest.raises(FlowError) as ei:
        TemplateFlow.verify_history(bad)
    assert ei.value.code == "TFL-HIST-001"
    with pytest.raises(FlowError):
        TemplateFlow(draft(), clock=lambda: NOW, history=h)  # history does not end at this draft
    with pytest.raises(FlowError):
        TemplateFlow.verify_history(h[::-1])


# ---- replay and staleness -------------------------------------------------------------------
def test_replay_of_old_edit_id_is_refused_even_with_other_content():
    f = flow()
    e = E("/company/legalName/en", "Name One")
    f.apply([e])
    assert code(f, [e]) == "TFL-REPLAY-001"
    assert code(f, [{**e, "value": "Different"}]) == "TFL-REPLAY-001"
    f2 = TemplateFlow(f.draft, clock=lambda: NOW, history=f.history)  # restored history keeps the ids
    assert code(f2, [e]) == "TFL-REPLAY-001"
    assert f.history[0]["after"] == "Name One" and len(f.history) == 1


def test_duplicate_id_inside_one_call_and_stale_base():
    f = flow()
    a = E("/company/legalName/en", "Name One")
    assert code(f, [a, {**a, "pointer": "/company/legalName/ar", "value": AR_NAME + "ي"}]) == "TFL-BATCH-001"
    f.apply([E("/company/legalName/en", "Name One")])
    stale = E("/company/legalName/en", "Name Two", baseHash=digest(draft()))
    assert code(f, [stale]) == "TFL-STALE-001"


def test_rejected_edit_does_not_burn_its_id():
    f = flow()
    e = E("/company/legalName/en", "")
    assert code(f, [e]) == "TFL-VALUE-002"
    f.apply([{**e, "value": "Good Name"}])


# ---- hostile paths ----------------------------------------------------------------------------
@pytest.mark.parametrize("ptr", [
    "/company/../meta/buildState", "/company/legalName/..", "/../../etc/passwd", "company/legalName/en",
    "/company//legalName/en", "/company/legalName/en/", "/__proto__/polluted", "/company/__proto__/x",
    "/company/constructor/prototype/x", "/company/legalName/%65n", "/company/legalName/e~1n", "/company\\legalName/en",
    "/company/legalName/عربي", "/" + "a/" * 20 + "b", "/" + "a" * 300, "", "/", "/company/legalName/en\x00",
    "/company/legalName/ar\n", "/company/legalName/__class__", "/constructor",
])
def test_hostile_pointers_refused(ptr):
    f = flow()
    h = f.draft_hash
    assert code(f, [E(ptr, "x")]) in ("TFL-PATH-001", "TFL-PATH-002", "TFL-PATH-003")
    assert f.draft_hash == h and f.history == []


def test_non_string_pointer_and_prototype_keys_in_value():
    f = flow()
    assert code(f, [E(["company"], "x")]) == "TFL-PATH-001"
    assert code(f, [E("/company/legalName/en", {"__proto__": {"x": 1}})]) == "TFL-VALUE-001"
    assert code(f, [E("/company/legalName/en", ["a"])]) == "TFL-VALUE-001"
    assert code(f, [E("/company/legalName/en", None)]) == "TFL-VALUE-001"


@pytest.mark.parametrize("ptr", [
    "/meta/buildState", "/meta/revision", "/company/country", "/compliance/country", "/compliance/vat/registered",
    "/compliance/eInvoicing/mode", "/compliance/eInvoicing/componentId", "/entities/customer/provenance/humanEdited",
    "/approvals/large_sales_order_approval/steps/general_manager/approverRole", "/roles/owner/isAdmin",
    "/roles/owner/permissions", "/company", "/company/legalName", "/branding/displayName/ar", "/components",
])
def test_non_editable_paths_refused(ptr):
    f = flow()
    assert code(f, [E(ptr, "x")]) == "TFL-PATH-002"


def test_missing_and_ambiguous_targets_and_indexes_refused():
    f = flow()
    assert code(f, [E("/roles/ghost_role/labels/en", "Ghost")]) == "TFL-PATH-003"
    assert code(f, [E("/roles/0/labels/en", "Index")]) == "TFL-PATH-003"
    d = draft()
    d["roles"].append(copy.deepcopy(d["roles"][0]))  # duplicate id: ambiguous
    f2 = TemplateFlow(d, clock=lambda: NOW)
    assert code(f2, [E("/roles/owner/labels/en", "Boss")]) == "TFL-PATH-003"


def test_cannot_unset_or_create_non_optional_values():
    f = flow()
    assert code(f, [{"id": eid(), "pointer": "/company/legalName/en", "value": "x", "op": "remove"}]) == "TFL-EDIT-001"
    assert code(f, [E("/company/legalName/fr", "x")]) == "TFL-PATH-002"
    d = draft()
    del d["compliance"]["vat"]["filingPeriod"]
    f2 = TemplateFlow(d, clock=lambda: NOW)
    assert code(f2, [E("/compliance/vat/filingPeriod", "monthly")]) == "TFL-PATH-003"  # not creatable


# ---- hostile values ------------------------------------------------------------------------------
@pytest.mark.parametrize("val", ["a" * 201, "x" * 5000, "‮evil", "zero​width", "tag\U000e0041", "nul\x00", "{{company.name}}", "<script>", "a\nb"])
def test_hostile_text_values(val):
    f = flow()
    assert code(f, [E("/company/legalName/en", val)]) in ("TFL-VALUE-002", "TFL-VALUE-003", "TFL-VALUE-004")
    assert f.history == []


def test_oversized_edit_batch_and_big_numbers():
    f = flow()
    assert code(f, [E("/company/legalName/en", "n%d" % i) for i in range(51)]) == "TFL-BATCH-001"
    assert code(f, []) == "TFL-BATCH-001" and code(f, "nope") == "TFL-BATCH-001"
    p = "/approvals/large_sales_order_approval/conditions/total_amount|gt/value"
    for v in (0, -5, 10**13, float("inf"), float("nan"), True, "1e9", "abc", "9" * 60, 5.00001, "٠"):
        assert code(f, [E(p, v)]) in ("TFL-VALUE-001", "TFL-VALUE-002", "TFL-VALUE-003"), v


def test_enum_bool_digits_ranges():
    f = flow()
    assert code(f, [E("/compliance/vat/filingPeriod", "weekly")]) == "TFL-VALUE-002"
    assert code(f, [E("/compliance/vat/pricesIncludeVat", "maybe")]) == "TFL-VALUE-002"
    assert code(f, [E("/compliance/vat/pricesIncludeVat", 1)]) == "TFL-VALUE-001"
    assert code(f, [E("/company/vatNumber", "123")]) == "TFL-VALUE-002"
    assert code(f, [E("/company/crNumber", "12345678ab")]) == "TFL-VALUE-002"


def test_required_fields_cannot_be_blanked_and_noop_refused():
    f = flow()
    for v in ("", "   ", " "):
        assert code(f, [E("/company/legalName/ar", v)]) == "TFL-VALUE-002"
    assert code(f, [E("/company/legalName/ar", AR_NAME)]) == "TFL-EDIT-002"


# ---- schema and semantic validation ----------------------------------------------------------------
def test_edit_that_would_violate_schema_is_refused_by_the_schema_step():
    # A registry that is looser than the Blueprint contract: the schema step is the backstop.
    loose = load_registry()
    for r in loose:
        if r["key"] == "company.legal_name":
            r["maxLength"] = 500
    f = TemplateFlow(draft(), clock=lambda: NOW, registry=loose)
    assert code(f, [E("/company/legalName/en", "x" * 250)]) == "TFL-SCHEMA-001"
    assert f.history == []


def test_existing_schema_errors_do_not_block_unrelated_edits_but_new_ones_do():
    d = draft()
    d["company"]["languages"]["primary"] = "klingon-too-long"  # preexisting defect
    f = TemplateFlow(d, clock=lambda: NOW)
    f.apply([E("/company/legalName/en", "Fine Name")])


def test_semantic_port_is_injected_and_can_refuse():
    def sem(bp):
        return ["BAD"] if bp["company"]["legalName"]["en"] == "Forbidden Co" else []
    f = flow(semantic=sem)
    assert code(f, [E("/company/legalName/en", "Forbidden Co")]) == "TFL-SEM-001"
    f.apply([E("/company/legalName/en", "Allowed Co")])


def test_real_blueprint_validator_as_semantic_port():
    from validator import validate, ValidationContext  # services/blueprint
    from helpers_registry import load_registry_dir
    ctx = ValidationContext(registry=load_registry_dir())
    def sem(bp):
        return [i.code for i in validate(bp, ctx).errors]
    f = flow(semantic=sem)
    r = f.apply([E("/compliance/vat/filingPeriod", "quarterly")])
    assert r.blueprint["compliance"]["vat"]["filingPeriod"] == "quarterly"


# ---- state, determinism, hygiene ----------------------------------------------------------------------
@pytest.mark.parametrize("state", ["owner_approved", "team_reviewed", "built_in_sandbox", "simulated", "live"])
def test_only_drafts_can_be_corrected(state):
    d = draft()
    d["meta"]["buildState"] = state
    with pytest.raises(FlowError) as ei:
        TemplateFlow(d, clock=lambda: NOW)
    assert ei.value.code == "TFL-STATE-001"


def test_unknown_edit_keys_and_bad_ids():
    f = flow()
    assert code(f, [{**E("/company/legalName/en", "Name One"), "actor": "admin"}]) == "TFL-EDIT-001"
    assert code(f, [{"id": "short", "pointer": "/company/legalName/en", "value": "Name One"}]) == "TFL-EDIT-001"
    assert code(f, [{"id": "../../../etc/passwd", "pointer": "/company/legalName/en", "value": "N"}]) == "TFL-EDIT-001"
    assert code(f, ["string"]) == "TFL-EDIT-001"
    assert code(f, [E("/company/legalName/en", "Name One", baseHash="zz")]) == "TFL-EDIT-001"
    with pytest.raises(FlowError):
        TemplateFlow(draft(), clock=lambda: NOW, actor="root")


def test_deterministic_same_inputs_same_output_and_error_messages_do_not_echo_input():
    a, b = flow(), flow()
    edits = [{"id": "edit-fixed01", "pointer": "/company/legalName/ar", "value": "مؤسسة الأمل"}]
    assert a.apply(edits).draft_hash == b.apply(edits).draft_hash
    marker = "PRIVATE-OWNER-TEXT-" + "x" * 300
    with pytest.raises(FlowError) as ei:
        flow().apply([E("/company/legalName/en", marker)])
    assert "PRIVATE" not in str(ei.value)


def test_no_model_or_network_imports():
    src = "".join(p.read_text(encoding="utf-8") for p in (DISC / "template_flow").glob("*.py"))
    for bad in ("import requests", "urllib", "socket", "anthropic", "openai", "subprocess", "os.system", "eval(", "exec("):
        assert bad not in src
