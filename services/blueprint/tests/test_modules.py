"""Module validator rules (ADR-0079, contracts/blueprint-modules.md): each case mutates the valid modules example."""
import copy
import json

import pytest

from fixture_registry import REPO
from validator import validate

EXAMPLE = REPO / "contracts" / "examples" / "blueprint-modules-minimal.json"
MOD_CODES = {"BP-MOD-001", "BP-MOD-002", "BP-MOD-003", "BP-MOD-004"}


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


def m_timesheet_billing_rate(bp):
    entity(bp, "timesheet")["fields"].append(field("billing_rate"))


def m_timesheet_costing_rate(bp):
    entity(bp, "timesheet")["fields"].append(field("costingRate"))


def m_timesheet_amount(bp):
    entity(bp, "timesheet")["fields"].append(field("amount", "money"))


def m_timesheet_money_field(bp):
    entity(bp, "timesheet")["fields"].append(field("billed_value", "money"))


def m_activity_type_rate(bp):
    bp["entities"].append({"id": "activity_type", "labels": {"ar": "نوع", "en": "Activity type"},
                           "fields": [field("activity_type_name", "string"), field("billing_rate")],
                           "components": [{"component": "projects.core", "mode": "implements"}],
                           "provenance": copy.deepcopy(entity(bp, "timesheet")["provenance"])})
    bp["modules"]["projects"]["entities"]["activity_type"] = "activity_type"


def m_crm_activity_tax(bp):
    entity(bp, "crm_activity")["fields"].append(field("tax_template", "string"))


def m_opportunity_posting(bp):
    entity(bp, "opportunity")["fields"].append(field("posting_account", "string"))


@pytest.mark.parametrize("mutate", [m_timesheet_billing_rate, m_timesheet_costing_rate, m_timesheet_amount,
                                    m_timesheet_money_field, m_activity_type_rate, m_crm_activity_tax,
                                    m_opportunity_posting])
def test_rigid_zone_field_on_bound_entity(mutate):
    bp = example()
    mutate(bp)
    assert "BP-MOD-001" in codes(bp)


def test_unbound_entity_may_carry_an_amount():
    bp = example()
    bp["entities"].append({"id": "expense_note", "labels": {"ar": "ملاحظة", "en": "Expense note"},
                           "fields": [field("amount", "money")],
                           "provenance": copy.deepcopy(entity(bp, "timesheet")["provenance"])})
    assert "BP-MOD-001" not in codes(bp)


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


# Manufacturing (#397 review): rigid-zone fields on item, BOM and every manufacturing-bound entity.
@pytest.mark.parametrize("eid,fid", [("item", "valuation_rate"), ("bom", "rm_cost_as_per"), ("bom", "operating_cost"),
                                     ("bom", "backflush_raw_materials_based_on"), ("work_order", "total_operating_cost"),
                                     ("job_card", "hour_rate"), ("workstation", "hour_rate_electricity"),
                                     ("item", "standardRate"), ("subcontracting_order", "service_cost_per_qty")])
def test_rigid_zone_field_on_manufacturing_entity(eid, fid):
    bp = example()
    entity(bp, eid)["fields"].append(field(fid))
    assert "BP-MOD-001" in codes(bp)


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


def test_distinct_scrap_warehouse_passes():
    bp = example()
    _add_store(bp, "scrap_store")
    _wh(bp)["scrap"] = "scrap_store"
    assert codes(bp) == set()
