"""Module validator rules (ADR-0079, contracts/blueprint-modules.md): each case mutates the valid modules example."""
import copy
import json

import pytest

from fixture_registry import REPO
from validator import validate

EXAMPLE = REPO / "contracts" / "examples" / "blueprint-modules-minimal.json"
TRADING = REPO / "services" / "blueprint" / "fixtures" / "trading-distribution.blueprint.json"
MOD_CODES = {"BP-MOD-001", "BP-MOD-002", "BP-MOD-003", "BP-MOD-004", "BP-MOD-005"}


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def entity(bp, ident):
    return next(e for e in bp["entities"] if e["id"] == ident)


def field(fid, ftype="decimal"):
    return {"id": fid, "type": ftype, "labels": {"ar": "حقل", "en": "Field"}}


def codes(bp):
    return validate(bp).codes() & MOD_CODES


def test_example_has_no_module_errors():
    assert codes(example()) == set()


def bind_child(bp, parent, child_id, fields, rel_id="lines"):
    """Add a child entity reached from `parent` through a child_table relation."""
    bp["entities"].append({"id": child_id, "kind": "child", "labels": {"ar": "بند", "en": "Line"},
                           "fields": fields, "provenance": copy.deepcopy(entity(bp, parent)["provenance"])})
    entity(bp, parent).setdefault("relations", []).append(
        {"id": rel_id, "target": child_id, "cardinality": "many", "kind": "child_table"})


# Engine rigid-zone fields (contracts/engine-rigid-fields.json): a Blueprint may not declare or override them.
def m_timesheet_billing_rate(bp):          # Timesheet Detail row field, declared inline on the timesheet
    entity(bp, "timesheet")["fields"].append(field("billing_rate", "money"))


def m_timesheet_base_costing_rate(bp):
    entity(bp, "timesheet")["fields"].append(field("base_costing_rate", "money"))


def m_timesheet_sales_invoice(bp):
    entity(bp, "timesheet")["fields"].append(field("sales_invoice", "string"))


def m_activity_type_rate(bp):
    bp["entities"].append({"id": "activity_type", "labels": {"ar": "نوع", "en": "Activity type"},
                           "fields": [field("activity_type_name", "string"), field("billing_rate", "money")],
                           "components": [{"component": "projects.core", "mode": "implements"}],
                           "provenance": copy.deepcopy(entity(bp, "timesheet")["provenance"])})
    bp["modules"]["projects"]["entities"]["activity_type"] = "activity_type"


def m_customer_tax_category(bp):
    entity(bp, "customer")["fields"].append(field("tax_category", "string"))


def m_customer_receivable_account(bp):     # Party Account row field
    entity(bp, "customer")["fields"].append(field("advance_account", "string"))


def m_project_cost_center(bp):
    entity(bp, "project")["fields"].append(field("cost_center", "string"))


def m_customer_parameter_override(bp):     # setting the engine field through component parameters
    entity(bp, "customer")["components"][0]["parameters"] = {"tax_withholding_category": "wht_default"}


def m_timesheet_line_child(bp):            # child_table rows of a bound entity are followed
    bind_child(bp, "timesheet", "timesheet_line", [field("hours", "decimal"), field("costing_amount", "money")])


def m_timesheet_line_nested_child(bp):     # and so are rows of those rows
    bind_child(bp, "timesheet", "timesheet_line", [field("hours", "decimal")])
    bind_child(bp, "timesheet_line", "timesheet_line_split", [field("base_billing_rate", "money")], "splits")


@pytest.mark.parametrize("mutate", [m_timesheet_billing_rate, m_timesheet_base_costing_rate, m_timesheet_sales_invoice,
                                    m_activity_type_rate, m_customer_tax_category, m_customer_receivable_account,
                                    m_project_cost_center, m_customer_parameter_override, m_timesheet_line_child,
                                    m_timesheet_line_nested_child])
def test_engine_rigid_field_on_bound_entity_is_refused(mutate):
    bp = example()
    mutate(bp)
    assert "BP-MOD-001" in codes(bp)


def test_child_row_error_points_at_the_child_field():
    bp = example()
    m_timesheet_line_child(bp)
    i = next(k for k, e in enumerate(bp["entities"]) if e["id"] == "timesheet_line")
    assert f"/entities/{i}/fields/1/id" in [e.path for e in validate(bp).errors if e.code == "BP-MOD-001"]


# Custom fields with any name stay plain data (they never feed posting, valuation or tax), money-typed included.
@pytest.mark.parametrize("ent,fid,ftype", [
    ("customer", "account_manager", "string"), ("customer", "tax_id", "string"), ("customer", "rate_limit", "integer"),
    ("customer", "accountability", "string"), ("customer", "taxonomy", "string"), ("opportunity", "amount", "money"),
    ("opportunity", "opportunity_amount", "money"), ("opportunity", "rated", "boolean"),
    ("crm_activity", "tax_template", "string"), ("opportunity", "posting_account", "string"),
    ("timesheet", "amount", "money"), ("timesheet", "billed_value", "money"), ("project", "budget_amount", "money"),
])
def test_custom_field_with_any_name_validates(ent, fid, ftype):
    bp = example()
    entity(bp, ent)["fields"].append(field(fid, ftype))
    assert codes(bp) == set()


def test_unbound_entity_may_carry_an_amount():
    bp = example()
    bp["entities"].append({"id": "expense_note", "labels": {"ar": "ملاحظة", "en": "Expense note"},
                           "fields": [field("amount", "money"), field("valuation_rate", "money")],
                           "provenance": copy.deepcopy(entity(bp, "timesheet")["provenance"])})
    assert "BP-MOD-001" not in codes(bp)


def test_reference_relation_is_not_followed():
    bp = example()
    bind_child(bp, "timesheet", "rate_card", [field("billing_rate", "money")])
    entity(bp, "timesheet")["relations"][-1]["kind"] = "reference"
    assert "BP-MOD-001" not in codes(bp)


# A Blueprint field never carries computation (schema): no formula, expression, fetch-from, depends-on or
# default expression, on any entity, bound or not.
@pytest.mark.parametrize("key,value", [
    ("formula", "qty * rate"), ("expression", "qty * rate"), ("fetch_from", "item.valuation_rate"),
    ("fetchFrom", "item.valuation_rate"), ("depends_on", "eval:doc.is_billable"), ("dependsOn", "is_billable"),
    ("default", "eval:doc.qty * doc.rate"), ("default", "=qty*rate"), ("default", " :Company"),
])
def test_field_computation_keys_are_refused(key, value):
    bp = example()
    f = entity(bp, "customer")["fields"][0]
    f[key] = value
    assert "BP-SCHEMA-001" in validate(bp).codes()


def test_literal_default_is_allowed():
    bp = example()
    entity(bp, "customer")["fields"].append(dict(field("credit_days", "integer"), default=30))
    entity(bp, "customer")["fields"].append(dict(field("segment", "string"), default="retail"))
    assert "BP-SCHEMA-001" not in validate(bp).codes()


def test_rigid_list_missing_fails_closed(monkeypatch):
    import validator.rules_modules as rm
    monkeypatch.setattr(rm, "load_rigid_fields", lambda ctx=None: None)
    assert "BP-MOD-001" in codes(example())


def _view(bp, kind):
    return next(v for v in bp["modules"]["projects"]["views"] if v["kind"] == kind)


@pytest.mark.parametrize("kind,key,value", [
    ("timeline", "startField", "subject"),      # a string field, not a date
    ("timeline", "endField", "no_such_field"),  # does not resolve
    ("calendar", "startField", "project"),      # a link field
])
def test_view_date_fields(kind, key, value):
    bp = example()
    _view(bp, kind)[kind][key] = value
    assert "BP-MOD-002" in codes(bp)


def test_billable_needs_listed_invoicing_component():
    bp = example()
    bp["modules"]["projects"]["timesheets"] = {"enabled": True, "billable": True, "invoicingComponent": "core.sales_invoice"}
    assert "BP-MOD-003" in codes(bp)
    bp["components"].append({"id": "core.sales_invoice", "versionRange": "^0.1.0"})
    assert "BP-MOD-003" not in codes(bp)


def test_invoicing_component_missing_from_known_registry_fails_closed():
    from validator.report import ValidationContext
    bp = example()
    bp["modules"]["projects"]["timesheets"] = {"enabled": True, "billable": True, "invoicingComponent": "core.sales_invoice"}
    bp["components"].append({"id": "core.sales_invoice", "versionRange": "^0.1.0"})
    errs = [e for e in validate(bp, ValidationContext(registry={})).errors if e.code == "BP-MOD-003"]
    assert errs and "not in the component registry" in errs[0].message


# Manufacturing (#397 re-review): the engine's own valuation, costing, tax and ledger fields on item, BOM and every
# manufacturing-bound entity are refused; ordinary item master data is not.
@pytest.mark.parametrize("eid,fid", [
    ("item", "valuation_rate"), ("item", "valuation_method"), ("item", "item_tax_template"),  # Item Tax row
    ("item", "income_account"),                                                              # Item Default row
    ("bom", "rm_cost_as_per"), ("bom", "operating_cost"), ("bom", "rate"),                   # BOM Item row inline
    ("work_order", "total_operating_cost"), ("work_order", "wip_warehouse"), ("job_card", "hour_rate"),
    ("workstation", "hour_rate_electricity"), ("subcontracting_order", "service_cost_per_qty"),
    ("subcontracting_receipt", "expense_account"),
])
def test_engine_rigid_field_on_manufacturing_entity(eid, fid):
    bp = example()
    entity(bp, eid)["fields"].append(field(fid, "money"))
    assert "BP-MOD-001" in codes(bp)


def test_bom_line_child_rows_are_followed():
    """BOM lines are the real costing carrier: a child_table row entity of the bound BOM may not declare rate or amount."""
    bp = example()
    bind_child(bp, "bom", "bom_line", [field("component_item", "string"), field("qty"), field("rate", "money"),
                                       field("base_amount", "money")], "items")
    i = next(k for k, e in enumerate(bp["entities"]) if e["id"] == "bom_line")
    paths = {e.path for e in validate(bp).errors if e.code == "BP-MOD-001"}
    assert paths == {f"/entities/{i}/fields/2/id", f"/entities/{i}/fields/3/id"}


def test_bom_line_with_plain_fields_passes():
    bp = example()
    bind_child(bp, "bom", "bom_line", [field("component_item", "string"), field("qty"), field("scrap_note", "text")], "items")
    assert codes(bp) == set()


def test_trading_fixture_plus_manufacturing_validates():
    """The standard trading item keeps cost_price, selling_price and vat_rate (custom master data, never posting)."""
    mods = example()
    bp = json.loads(TRADING.read_text(encoding="utf-8"))
    mfg = copy.deepcopy(mods["modules"]["manufacturing"])
    mfg["warehouses"] = {"workInProgress": "wh_riyadh", "finishedGoods": "wh_jeddah"}
    bp["modules"] = {"manufacturing": mfg}
    bp["components"].append({"id": "manufacturing.core", "versionRange": "^0.1.0"})
    bp["entities"] += [copy.deepcopy(e) for e in mods["entities"] if e["id"] in set(mfg["entities"].values()) - {"item"}]
    assert {"cost_price", "selling_price", "vat_rate"} <= {f["id"] for f in entity(bp, "item")["fields"]}
    rep = validate(bp)
    assert not {e.code for e in rep.errors} & (MOD_CODES | {"BP-SCHEMA-001"}), [str(e) for e in rep.errors]


def _wh(bp):
    return bp["modules"]["manufacturing"]["warehouses"]


def _add_store(bp, ident, kind="warehouse"):
    bp["locations"].append({"id": ident, "kind": kind, "parent": "hq", "labels": {"ar": "مخزن", "en": "Store"}})


@pytest.mark.parametrize("update", [
    {"finishedGoods": "wip_store"},                 # WIP and finished goods are the same warehouse
    {"scrap": "wip_store"},                         # scrap equals WIP
    {"scrap": "fg_store"},                          # scrap equals finished goods
    {"workInProgress": "hq"},                       # a branch, not a warehouse
    {"scrap": "no_such_store"},                     # does not resolve
])
def test_manufacturing_warehouses(update):
    bp = example()
    _wh(bp).update(update)
    assert "BP-MOD-004" in codes(bp)


@pytest.mark.parametrize("connector", ["messaging.meta_business", "msg.telegram", "file.excel_upload"])
def test_marketing_messaging_needs_a_dsc022_connector(connector):
    """#398 review: channels.messaging.integration resolves to an integration on a DSC-022 connector id."""
    bp = example()
    ref = bp["modules"]["marketing"]["channels"]["messaging"]["integration"]
    next(i for i in bp["integrations"] if i["id"] == ref)["connector"] = connector
    assert "BP-MOD-005" in codes(bp)


def test_marketing_messaging_integration_must_resolve():
    bp = example()
    bp["modules"]["marketing"]["channels"]["messaging"]["integration"] = "no_such_integration"
    assert "BP-MOD-005" in codes(bp)


def test_distinct_scrap_warehouse_passes():
    bp = example()
    _add_store(bp, "scrap_store")
    _wh(bp)["scrap"] = "scrap_store"
    assert codes(bp) == set()
