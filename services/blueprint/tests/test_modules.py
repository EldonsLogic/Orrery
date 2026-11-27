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
