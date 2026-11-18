"""Security review findings T1 to T10 on the Tool API generator (OPR-003): each one reproduced, then held fixed."""
import copy

import pytest

from toolapi import check_tool_api, generate_tool_api
from toolapi import policy as P
from toolapi.result import hash_tools

L0 = "l0:platform-policy-test"


def codes(res):
    return {e.code for e in res.errors}


def tool(res, name):
    return next(t for t in res.tools if t["name"] == name)


def names(res):
    return {t["name"] for t in res.tools}


def trans(res, name):
    return {t["id"]: t for t in tool(res, name)["transitions"]}


def add_entity(b, eid, fields=None, actions=("read", "create", "update", "submit", "cancel", "delete"), kind="document"):
    b["entities"].append({"id": eid, "kind": kind, "labels": {"ar": eid, "en": eid},
                          "fields": fields or [{"id": "amount", "type": "decimal", "labels": {"en": "Amount"}}]})
    if kind != "child":
        owner = next(r for r in b["roles"] if r["id"] == "owner")
        owner["permissions"].append({"entity": eid, "actions": list(actions)})
    return b


def rechecked(defs):
    """Re-hash after tampering, so only the policy recompute can catch the change (T9)."""
    defs["contentHash"] = hash_tools(defs["tools"])
    return {i.code for i in check_tool_api(defs)}


# ---- T1: an unlisted ledger or stock entity must never fall back to plain ------------------------------------------
LEDGER_OR_STOCK = ("journal_entry", "payment_entry", "stock_entry", "stock_reconciliation", "debit_note", "pos_invoice",
                   "expense_claim", "payroll_entry", "salary_slip", "landed_cost_voucher", "period_closing_voucher",
                   "goods_receipt", "invoice", "bill", "receipt", "customer_bill", "petty_cash_voucher", "general_ledger")


@pytest.mark.parametrize("eid", LEDGER_OR_STOCK)
def test_t1_ledger_and_stock_entities_never_plain(mini, eid):
    res = generate_tool_api(add_entity(mini, eid))
    assert res.ok, [str(e) for e in res.errors]
    assert tool(res, f"{eid}.create")["entity_class"] in ("stock", "ledger")
    cancel = tool(res, f"{eid}.cancel")
    assert cancel["risk_class"] == "R4" and cancel["agent_creatable"] is False
    sub = tool(res, f"{eid}.submit")
    assert sub["effects"]["ledger"] is True and sub["approval"]["agent_required"] is True
    assert tool(res, f"{eid}.delete")["risk_class"] == "R4"


def test_t1_unknown_entity_refused(mini):
    res = generate_tool_api(add_entity(mini, "warranty_claim"))
    assert "TAPI-CLASS-001" in codes(res) and res.tools == []


def test_t1_unknown_child_entity_needs_no_class(mini):
    assert generate_tool_api(add_entity(mini, "warranty_line", kind="child")).ok


def test_t1_registry_may_classify_unknown_entity(mini):
    res = generate_tool_api(add_entity(mini, "warranty_claim"), {"source": L0, "entity_classes": {"warranty_claim": "plain"}})
    assert res.ok and tool(res, "warranty_claim.create")["entity_class"] == "plain"


def test_t1_fixture_classes(bp):
    res = generate_tool_api(bp)
    want = {"customer": "plain", "supplier": "plain", "item": "plain", "price_list": "plain", "sales_quote": "plain",
            "sales_order": "plain", "purchase_order": "plain", "delivery_note": "stock", "purchase_receipt": "stock",
            "stock_transfer": "stock", "sales_invoice": "ledger", "purchase_invoice": "ledger", "credit_note": "ledger",
            "payment": "ledger"}
    got = {t["entity"]: t["entity_class"] for t in res.tools if t["entity"]}
    assert got == want


def test_t1_child_table_cannot_carry_a_riskier_entity(mini):
    add_entity(mini, "journal_entry", kind="child")
    cust = mini["entities"][0]
    cust["relations"] = [{"id": "postings", "kind": "child_table", "target": "journal_entry"}]
    assert "TAPI-CLASS-003" in codes(generate_tool_api(mini))
    so = next(e for e in mini["entities"] if e["id"] == "sales_order")
    so["relations"][0]["target"] = "sales_invoice"  # a ledger document embedded in a plain order
    cust["relations"] = []
    assert "TAPI-CLASS-003" in codes(generate_tool_api(mini))


# ---- T2: the registry may raise, never lower -----------------------------------------------------------------------
def test_t2_registry_cannot_lower_class(bp):
    res = generate_tool_api(bp, {"source": L0, "entity_classes": {"sales_invoice": "plain"}})
    assert "TAPI-REGISTRY-002" in codes(res) and res.tools == []
    res = generate_tool_api(bp, {"source": L0, "entity_classes": {"delivery_note": "plain"}})
    assert "TAPI-REGISTRY-002" in codes(res)


def test_t2_registry_cannot_lower_effects(bp):
    res = generate_tool_api(bp, {"source": L0, "entity_effects": {"sales_invoice": {"tax": False}}})
    assert "TAPI-REGISTRY-002" in codes(res)
    res = generate_tool_api(bp, {"source": L0, "entity_effects": {"sales_invoice": {}}})  # empty adds nothing
    assert res.ok
    eff = tool(res, "sales_invoice.transition")["effects"]
    assert eff == {"ledger": True, "tax": True, "external_send": True}


def test_t2_registry_raises_and_ors_effects_and_is_recorded(bp):
    reg = {"source": L0, "entity_classes": {"customer": "ledger"}, "entity_effects": {"purchase_invoice": {"external_send": True}}}
    res = generate_tool_api(bp, reg)
    assert res.ok
    assert tool(res, "customer.create")["entity_class"] == "ledger"
    assert tool(res, "purchase_invoice.create")["effects"] == {"ledger": True, "tax": True, "external_send": True}
    meta = res.definition_set()["registry"]
    assert meta["source"] == L0 and meta["sha256"].startswith("sha256:")
    assert generate_tool_api(bp).definition_set()["registry"] is None


def test_t2_registry_needs_a_source(bp):
    assert "TAPI-REGISTRY-001" in codes(generate_tool_api(bp, {"entity_classes": {"customer": "ledger"}}))
    assert "TAPI-REGISTRY-001" in codes(generate_tool_api(bp, {"source": "", "entity_classes": {"customer": "ledger"}}))


# ---- T3: transition kind must not hinge on exact name tokens -------------------------------------------------------
@pytest.mark.parametrize("tid", ["mark_approved", "approval_step", "authorise_order", "authorize_order", "sign_off",
                                 "accept_order", "confirm_order", "release_order", "approve_large"])
def test_t3_approval_names_never_agent_creatable(mini, tid):
    t = next(t for t in mini["workflows"][0]["transitions"] if t["id"] == "approve_large")
    t["id"] = tid
    res = generate_tool_api(mini)
    assert res.ok, [str(e) for e in res.errors]
    tr = trans(res, "sales_order.transition")[tid]
    assert tr["kind"] == "approve" and tr["agent_creatable"] is False


def _invoice_wf(bp):
    return next(w for w in bp["workflows"] if w["entity"] == "sales_invoice")


@pytest.mark.parametrize("tid", ["void_invoice", "mark_cancelled", "reverse_invoice", "refund", "write_off",
                                 "return_goods", "amend_invoice", "finish"])
def test_t3_leaving_posted_state_on_ledger_is_r4(bp, tid):
    wf = _invoice_wf(bp)
    wf["states"].append({"id": "voided", "labels": {"en": "Voided"}, "kind": "final"})
    wf["transitions"].append({"id": tid, "from": "submitted", "to": "voided", "actionLabels": {"en": "x"},
                              "allowedRoles": ["accountant"]})
    res = generate_tool_api(bp)
    tr = trans(res, "sales_invoice.transition")[tid]
    assert tr["risk_class"] == "R4" and tr["agent_creatable"] is False


def test_t3_named_cancel_from_draft_into_posted_state_is_not_cheap(bp):
    _invoice_wf(bp)["transitions"].append({"id": "cancel_and_post", "from": "draft", "to": "submitted",
                                           "actionLabels": {"en": "x"}, "allowedRoles": ["accountant"]})
    tr = trans(generate_tool_api(bp), "sales_invoice.transition")["cancel_and_post"]
    assert tr["risk_class"] == "R3"


def test_t3_approval_rule_on_ledger_transition_is_approve(bp):
    _invoice_wf(bp)["transitions"].append({"id": "go_ahead", "from": "draft", "to": "submitted", "actionLabels": {"en": "x"},
                                           "allowedRoles": ["accountant"], "approval": "credit_note_approval"})
    tr = trans(generate_tool_api(bp), "sales_invoice.transition")["go_ahead"]
    assert tr["kind"] == "approve" and tr["agent_creatable"] is False


def test_t3_stock_receive_from_non_initial_is_r4(bp):
    tr = trans(generate_tool_api(bp), "stock_transfer.transition")
    assert tr["dispatch_transfer"]["risk_class"] == "R2" and tr["dispatch_transfer"]["agent_creatable"] is True
    assert tr["receive_transfer"]["risk_class"] == "R4" and tr["receive_transfer"]["agent_creatable"] is False


def test_t3_tokens_on_plain_entity_add_restriction(bp):
    so = trans(generate_tool_api(bp), "sales_order.transition")
    assert so["cancel_approved"]["agent_creatable"] is False  # "approved" token adds the approve restriction
    assert so["deliver"]["kind"] == "advance" and so["deliver"]["agent_creatable"] is True


def test_t3_explicit_kind(bp):
    wf = _invoice_wf(bp)
    wf["transitions"].append({"id": "settle", "from": "submitted", "to": "paid", "kind": "advance",
                              "actionLabels": {"en": "x"}, "allowedRoles": ["accountant"]})
    wf["transitions"].append({"id": "void_it", "from": "submitted", "to": "cancelled", "kind": "advance",
                              "actionLabels": {"en": "x"}, "allowedRoles": ["accountant"]})
    tr = trans(generate_tool_api(bp), "sales_invoice.transition")
    assert tr["settle"]["kind"] == "advance" and tr["settle"]["risk_class"] == "R3"
    assert tr["void_it"]["risk_class"] == "R4"  # name tokens only ever add restriction
    b = copy.deepcopy(bp)
    _invoice_wf(b)["transitions"][-1]["kind"] = "whatever"
    assert "TAPI-TRANS-001" in codes(generate_tool_api(b))


def test_t3_one_initial_state_only(bp):
    next(s for s in _invoice_wf(bp)["states"] if s["id"] == "submitted")["kind"] = "initial"
    assert "TAPI-TRANS-002" in codes(generate_tool_api(bp))


# ---- T4: bank, contact and permission changes are separate R4 tools ------------------------------------------------
def test_t4_bank_detail_is_its_own_r4_tool(bp):
    res = generate_tool_api(bp)
    assert "bank_iban" not in tool(res, "supplier.update")["input_schema"]["properties"]
    assert "bank_iban" not in tool(res, "supplier.create")["input_schema"]["properties"]
    bank = tool(res, "supplier.update_bank_details")
    assert set(bank["input_schema"]["properties"]) == {"id", "expected_version", "bank_iban"}
    assert bank["risk_class"] == "R4" and bank["agent_creatable"] is False and bank["kind"] == "write"
    assert "bank_iban" in tool(res, "supplier.get")["output_schema"]["properties"]


@pytest.mark.parametrize("fid", ["iban", "bank_account", "account_number", "swift_code", "payment_account", "beneficiary_name"])
def test_t4_bank_names(mini, fid):
    mini["entities"][0]["fields"].append({"id": fid, "type": "string", "labels": {"en": fid}})
    res = generate_tool_api(mini)
    assert fid not in tool(res, "customer.update")["input_schema"]["properties"]
    assert fid in tool(res, "customer.update_bank_details")["input_schema"]["properties"]


def test_t4_contact_fields(bp):
    res = generate_tool_api(bp)
    upd = tool(res, "customer.update")["input_schema"]["properties"]
    assert "email" not in upd and "phone" not in upd
    c = tool(res, "customer.update_contact_details")
    assert {"email", "phone"} <= set(c["input_schema"]["properties"]) and c["risk_class"] == "R4"
    assert c["agent_creatable"] is False
    assert "bank_reference" in tool(res, "payment.update")["input_schema"]["properties"]  # a reference, not a target


def test_t4_link_to_bank_entity_is_sensitive(mini):
    add_entity(mini, "bank_account", [{"id": "label", "type": "string", "labels": {"en": "x"}}], ("read",), "master")
    mini["entities"][0]["fields"].append({"id": "settlement", "type": "link", "target": "bank_account", "labels": {"en": "x"}})
    res = generate_tool_api(mini)
    assert "settlement" not in tool(res, "customer.update")["input_schema"]["properties"]
    assert "settlement" in tool(res, "customer.update_bank_details")["input_schema"]["properties"]


def test_t4_required_sensitive_field_makes_create_r4(mini):
    mini["entities"][0]["fields"].append({"id": "iban", "type": "string", "required": True, "labels": {"en": "x"}})
    c = tool(generate_tool_api(mini), "customer.create")
    assert "iban" in c["input_schema"]["properties"] and c["risk_class"] == "R4" and c["agent_creatable"] is False


@pytest.mark.parametrize("eid", ["user_role", "role_assignment", "user_permission", "permission_set", "grant_log",
                                 "agent_limit", "users", "custom_role"])
def test_t4_identity_domain_entities_refused(mini, eid):
    res = generate_tool_api(add_entity(mini, eid))
    assert "TAPI-DOMAIN-001" in codes(res) and res.tools == []


# ---- T5: forbidden argument names by token -------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["user", "owner", "approver", "approver_role", "approved_by", "on_behalf_of", "actor",
                                  "agent_id", "grant_id", "permissions", "role_name", "assigned_role", "tenants",
                                  "owner_ref", "created_by", "assigned_to", "caller_ref", "data_scope"])
def test_t5_forbidden_tokens(mini, name):
    mini["entities"][0]["fields"].append({"id": name, "type": "string", "labels": {"en": "x"}})
    assert "TAPI-ARG-001" in codes(generate_tool_api(mini)), name


def test_t5_checker_uses_tokens(bp):
    d = generate_tool_api(bp).definition_set()
    tool_ = next(t for t in d["tools"] if t["name"] == "customer.update")
    tool_["input_schema"]["properties"]["approved_by"] = {"type": "string"}
    assert "TAPI-ARG-001" in rechecked(d)
    d = generate_tool_api(bp).definition_set()
    next(t for t in d["tools"] if t["name"] == "customer.get")["input_schema"]["properties"]["ownerId"] = {"type": "string"}
    assert "TAPI-ARG-001" in rechecked(d)


# ---- T6: export is not a read ----------------------------------------------------------------------------------------
def test_t6_export_is_write_with_idempotency(bp):
    res = generate_tool_api(bp)
    for t in res.tools:
        if t["name"].endswith(".export"):
            assert t["kind"] == "write" and t["idempotency"] == "required" and t["approval"]["agent_required"] is True
        if t["kind"] == "read":
            assert t["risk_class"] == "R0", t["name"]


def test_t6_checker_read_implies_r0(bp):
    d = generate_tool_api(bp).definition_set()
    exp = next(t for t in d["tools"] if t["name"] == "customer.export")
    exp["kind"], exp["idempotency"] = "read", "none"
    assert "TAPI-RISK-004" in rechecked(d)


# ---- T7: hidden fields are not filterable --------------------------------------------------------------------------
def test_t7_hidden_fields_not_in_filter_or_order(bp):
    res = generate_tool_api(bp)
    for name in ("customer.list", "customer.export"):
        props = tool(res, name)["input_schema"]["properties"]
        assert "credit_limit" not in props["filter"]["items"]["properties"]["field"]["enum"], name
    lst = tool(res, "customer.list")["input_schema"]["properties"]
    assert "credit_limit" not in lst["order_by"]["properties"]["field"]["enum"]
    assert "customer_name" in lst["order_by"]["properties"]["field"]["enum"]
    it = tool(res, "item.list")["input_schema"]["properties"]["filter"]["items"]["properties"]["field"]["enum"]
    assert "cost_price" not in it and "selling_price" not in it


def test_t7_group_by_is_enum(bp):
    gb = tool(generate_tool_api(bp), "metric.query")["input_schema"]["properties"]["group_by"]
    assert gb["items"]["enum"] == ["branch", "customer", "supplier", "warehouse"]
    assert "pattern" not in gb["items"]


# ---- T8: the workflow cannot be skipped through a status field -----------------------------------------------------
@pytest.mark.parametrize("fid", ["status", "workflow_state", "docstatus", "order_status"])
def test_t8_status_fields_read_only_on_workflow_entities(mini, fid):
    so = next(e for e in mini["entities"] if e["id"] == "sales_order")
    so["fields"].append({"id": fid, "type": "string", "labels": {"en": "x"}})
    res = generate_tool_api(mini)
    for verb in ("create", "update"):
        assert fid not in tool(res, f"sales_order.{verb}")["input_schema"]["properties"]
    assert fid in tool(res, "sales_order.get")["output_schema"]["properties"]


def test_t8_engine_status_fields_read_only_everywhere(mini):
    mini["entities"][0]["fields"] += [{"id": "docstatus", "type": "integer", "labels": {"en": "x"}},
                                      {"id": "status", "type": "string", "labels": {"en": "x"}}]
    props = tool(generate_tool_api(mini), "customer.update")["input_schema"]["properties"]
    assert "docstatus" not in props and "status" in props  # a plain master's own status stays editable


# ---- T9: the checker recomputes ------------------------------------------------------------------------------------
def test_t9_checker_recomputes_risk_and_effects(bp):
    good = generate_tool_api(bp).definition_set()
    assert check_tool_api(good) == []

    d = copy.deepcopy(good)
    t = next(t for t in d["tools"] if t["name"] == "payment.submit")
    t["risk_class"], t["effects"], t["approval"]["agent_required"] = "R1", {k: False for k in P.EFFECT_KEYS}, False
    assert "TAPI-RISK-003" in rechecked(d)

    d = copy.deepcopy(good)
    t = next(t for t in d["tools"] if t["name"] == "sales_invoice.transition")
    t["entity_class"] = "plain"
    for tr in t["transitions"]:
        tr["risk_class"], tr["agent_creatable"] = "R1", True
    t["risk_class"], t["agent_creatable"] = "R1", True
    assert {"TAPI-CLASS-002", "TAPI-RISK-003"} <= rechecked(d)

    d = copy.deepcopy(good)  # relabel an approval as an advance: the id still says approve
    t = next(t for t in d["tools"] if t["name"] == "sales_order.transition")
    tr = next(x for x in t["transitions"] if x["id"] == "approve_large")
    tr["kind"], tr["agent_creatable"] = "advance", True
    assert "TAPI-RISK-003" in rechecked(d)

    d = copy.deepcopy(good)  # posted ledger transition relabelled as leaving the initial state
    t = next(t for t in d["tools"] if t["name"] == "sales_invoice.transition")
    tr = next(x for x in t["transitions"] if x["id"] == "mark_paid")
    tr["kind"], tr["risk_class"], tr["agent_creatable"] = "advance", "R3", True
    assert "TAPI-RISK-003" in rechecked(d)

    d = copy.deepcopy(good)
    next(t for t in d["tools"] if t["name"] == "approval.decide")["risk_class"] = "R0"
    assert "TAPI-RISK-003" in rechecked(d)

    d = copy.deepcopy(good)
    next(t for t in d["tools"] if t["name"] == "supplier.update_bank_details")["risk_class"] = "R1"
    next(t for t in d["tools"] if t["name"] == "supplier.update_bank_details")["agent_creatable"] = True
    assert "TAPI-RISK-003" in rechecked(d)

    d = copy.deepcopy(good)  # a sensitive field smuggled back into the generic update
    next(t for t in d["tools"] if t["name"] == "supplier.update")["input_schema"]["properties"]["bank_iban"] = {"type": "string"}
    assert "TAPI-RISK-003" in rechecked(d)


def test_t9_content_hash_mandatory(bp):
    d = generate_tool_api(bp).definition_set()
    assert "TAPI-HASH-002" in {i.code for i in check_tool_api(d["tools"])}
    d["contentHash"] = None
    assert "TAPI-HASH-002" in {i.code for i in check_tool_api(d)}


def test_t9_checker_needs_the_registry_it_was_built_with(bp):
    reg = {"source": L0, "entity_classes": {"customer": "ledger"}}
    d = generate_tool_api(bp, reg).definition_set()
    assert check_tool_api(d, reg) == []
    assert "TAPI-REGISTRY-003" in {i.code for i in check_tool_api(d)}


# ---- T10 ------------------------------------------------------------------------------------------------------------
def test_t10_report_filter_without_field_is_coded(bp):
    bp["reports"][0]["filters"].append({"type": "select"})
    res = generate_tool_api(bp)
    assert "TAPI-INPUT-003" in codes(res) and res.tools == []


def test_t10_platform_risk_from_policy(bp):
    res = generate_tool_api(bp)
    for n, r in P.PLATFORM_RISK.items():
        assert tool(res, n)["risk_class"] == r
