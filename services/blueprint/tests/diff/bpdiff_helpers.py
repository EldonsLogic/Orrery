"""Shared builders for the Blueprint diff tests. Fictional data only."""
import copy
import json
from pathlib import Path

BLUEPRINT = Path(__file__).resolve().parents[2]
REPO = BLUEPRINT.parents[1]
FIXTURE = BLUEPRINT / "fixtures" / "trading-distribution.blueprint.json"
TEMPLATE = REPO / "services" / "discovery" / "templates" / "trading-distribution" / "blueprint.template.json"
DIFF_SCHEMA = BLUEPRINT / "diff" / "diff.schema.json"


def base():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def by_id(items, ident, key="id"):
    return next(x for x in items if x[key] == ident)


def lt(text):
    return {"ar": "اختبار", "en": text}


def two_steps(bp):
    ap = by_id(bp["approvals"], "large_sales_order_approval")
    ap["steps"].append({"order": 2, "approverRole": "owner", "mode": "any_one"})


def _add_entity(bp):
    bp["entities"].append({"id": "warranty_claim", "labels": lt("Warranty claim"), "kind": "document",
                           "fields": [{"id": "claim_no", "type": "string", "labels": lt("Claim no")}],
                           "provenance": {"source": "manual", "humanEdited": False}})


def _remove_entity(bp):
    bp["entities"].pop()


def _rename_entity_id(bp):
    by_id(bp["entities"], "item")["id"] = "product"


def _rename_entity_label(bp):
    by_id(bp["entities"], "item")["labels"]["en"] = "Product"


def _add_field(bp):
    by_id(bp["entities"], "customer")["fields"].append({"id": "nickname", "type": "string", "labels": lt("Nickname")})


def _add_required_field(bp):
    by_id(bp["entities"], "customer")["fields"].append(
        {"id": "tax_class", "type": "string", "required": True, "labels": lt("Tax class")})


def _field_type(bp):
    f = next(f for f in by_id(bp["entities"], "customer")["fields"] if f["type"] == "string")
    f["type"] = "text"
    f.pop("maxLength", None)


def _remove_field(bp):
    by_id(bp["entities"], "customer")["fields"].pop()


def _remove_state(bp):
    st = by_id(bp["workflows"], "sales_order_flow")["states"]
    st.remove(by_id(st, "cancelled"))


def _role_scope(bp):
    by_id(bp["roles"], "sales_rep")["scope"] = {"type": "company"}


def _colour(bp):
    bp["branding"]["primaryColour"] = "#0A6B61"


def _compliance(bp):
    bp["compliance"]["eInvoicing"]["mode"] = "zatca_phase1"


def _reorder_steps(bp):
    by_id(bp["approvals"], "large_sales_order_approval")["steps"].reverse()


def _locale(bp):
    bp["company"]["locale"]["timezone"] = "Asia/Dubai"


def _locales(bp):
    bp["meta"]["locales"].append("fr")


def _vat(bp):
    bp["company"]["vatNumber"] = "300000000000011"


def _remove_option(bp):
    f = next(f for e in bp["entities"] for f in e["fields"] if f["type"] == "select")
    f["options"].pop()


def _threshold(bp):
    by_id(bp["approvals"], "large_sales_order_approval")["conditions"][0]["value"] = 60000


def _add_role(bp):
    bp["roles"].append({"id": "viewer", "labels": lt("Viewer"), "function": "read_only", "scope": {"type": "company"},
                        "permissions": [{"entity": "customer", "actions": ["read"]}],
                        "homeView": {"layout": "task_list"}, "provenance": {"source": "manual", "humanEdited": False}})


def _remove_role(bp):
    bp["roles"].pop()


def _add_report(bp):
    bp["reports"].append({"id": "stock_value", "kind": "report", "labels": lt("Stock value"),
                          "metrics": [{"ref": "stock.value"}], "visibleToRoles": ["owner"],
                          "provenance": {"source": "manual", "humanEdited": False}})


def _remove_integration(bp):
    bp["integrations"].pop()


def _provenance(bp):
    by_id(bp["entities"], "customer")["provenance"]["humanEdited"] = not by_id(bp["entities"], "customer")["provenance"]["humanEdited"]


def _revision(bp):
    bp["meta"]["revision"] += 1
    bp["meta"]["updatedAt"] = "2026-11-02T08:00:00Z"


def _remove_workflow(bp):
    bp["workflows"].pop()


def _transition_roles(bp):
    by_id(by_id(bp["workflows"], "sales_order_flow")["transitions"], "draft_to_pending_approval"
          if any(t["id"] == "draft_to_pending_approval" for t in by_id(bp["workflows"], "sales_order_flow")["transitions"])
          else by_id(bp["workflows"], "sales_order_flow")["transitions"][0]["id"])["allowedRoles"].append("auditor")


def _field_visibility(bp):
    by_id(by_id(bp["entities"], "customer")["fields"], "customer_name"
          if any(f["id"] == "customer_name" for f in by_id(bp["entities"], "customer")["fields"])
          else by_id(bp["entities"], "customer")["fields"][0]["id"])["visibleToRoles"] = ["owner"]


def _remove_location(bp):
    bp["locations"].pop()


def _add_component(bp):
    bp["components"].append({"id": "core.fixture_extra", "versionRange": "^0.1.0"})


def _poweredby(bp):
    bp["branding"]["poweredBy"]["show"] = not bp["branding"]["poweredBy"]["show"]


def _currency(bp):
    bp["company"]["locale"]["currency"] = "AED"


# name -> (prep applied to both revisions or None, mutation, expected {(op, code, impact)})
CASES = {
    "add_entity": (None, _add_entity, {("add", "BPD-ENTITY-ADDED", "data_shape")}),
    "remove_entity": (None, _remove_entity, {("remove", "BPD-ENTITY-REMOVED", "destructive")}),
    "rename_entity_id": (None, _rename_entity_id,
                         {("remove", "BPD-ENTITY-REMOVED", "destructive"), ("add", "BPD-ENTITY-ADDED", "data_shape")}),
    "rename_entity_label": (None, _rename_entity_label, {("replace", "BPD-ENTITY-LABEL-CHANGED", "cosmetic")}),
    "add_field": (None, _add_field, {("add", "BPD-FIELD-ADDED", "data_shape")}),
    "add_required_field": (None, _add_required_field, {("add", "BPD-FIELD-ADDED", "data_shape")}),
    "change_field_type": (None, _field_type, {("replace", "BPD-FIELD-TYPE-CHANGED", "data_shape"),
                                              ("remove", "BPD-FIELD-CHANGED", "data_shape")}),
    "remove_field": (None, _remove_field, {("remove", "BPD-FIELD-REMOVED", "destructive")}),
    "remove_workflow_state": (None, _remove_state, {("remove", "BPD-STATE-REMOVED", "destructive")}),
    "remove_workflow": (None, _remove_workflow, {("remove", "BPD-WORKFLOW-REMOVED", "destructive")}),
    "change_role_scope": (None, _role_scope, {("replace", "BPD-ROLE-SCOPE-CHANGED", "access")}),
    "change_branding_colour": (None, _colour, {("replace", "BPD-BRANDING-COLOUR-CHANGED", "branding")}),
    "toggle_powered_by": (None, _poweredby, {("replace", "BPD-BRANDING-CHANGED", "branding")}),
    "change_compliance": (None, _compliance, {("replace", "BPD-COMPLIANCE-CHANGED", "compliance")}),
    "reorder_approval_steps": (two_steps, _reorder_steps, {("reorder", "BPD-STEP-REORDERED", "access")}),
    "change_locale_timezone": (None, _locale, {("replace", "BPD-COMPANY-CHANGED", "config")}),
    "change_meta_locales": (None, _locales, {("replace", "BPD-META-CHANGED", "config")}),
    "change_vat_number": (None, _vat, {("replace", "BPD-COMPANY-CHANGED", "compliance")}),
    "change_currency": (None, _currency, {("replace", "BPD-COMPANY-CHANGED", "compliance")}),
    "remove_select_option": (None, _remove_option, {("remove", "BPD-OPTION-REMOVED", "destructive")}),
    "change_approval_threshold": (None, _threshold, {("replace", "BPD-CONDITION-CHANGED", "access")}),
    "add_role": (None, _add_role, {("add", "BPD-ROLE-ADDED", "access")}),
    "remove_role": (None, _remove_role, {("remove", "BPD-ROLE-REMOVED", "access")}),
    "add_report": (None, _add_report, {("add", "BPD-REPORT-ADDED", "config")}),
    "remove_integration": (None, _remove_integration, {("remove", "BPD-INTEGRATION-REMOVED", "config")}),
    "change_provenance": (None, _provenance, {("replace", "BPD-ENTITY-CHANGED", "cosmetic")}),
    "bump_revision": (None, _revision, {("replace", "BPD-META-CHANGED", "cosmetic")}),
    "transition_allowed_roles": (None, _transition_roles, {("replace", "BPD-TRANSITION-CHANGED", "access")}),
    "field_visible_to_roles": (None, _field_visibility, {("add", "BPD-FIELD-CHANGED", "access")}),
    "remove_location": (None, _remove_location, {("remove", "BPD-LOCATION-REMOVED", "destructive")}),
    "add_component": (None, _add_component, {("add", "BPD-COMPONENT-ADDED", "config")}),
}


def make_pair(name):
    prep, mutate, _ = CASES[name]
    a = base()
    if prep:
        prep(a)
    b = copy.deepcopy(a)
    mutate(b)
    return a, b
