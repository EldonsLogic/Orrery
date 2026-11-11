"""Checks the draft Blueprint-to-engine mapping (contracts/engine-mapping.schema.json, BPL-029).

The mapping must stay consistent with the fixture Blueprint it targets, and the computed-field contract must
reproduce the golden path numbers (docs/specs/golden-path-trading-sale.md). The formulas here only document
and check the contract; the engine stays the authority for real totals.
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "contracts" / "engine-mapping.schema.json").read_text(encoding="utf-8"))
MAPPING_PATH = ROOT / "contracts" / "examples" / "engine-mapping-golden-path.json"
MAPPING = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
BLUEPRINT = json.loads((ROOT / MAPPING["blueprintRef"]["fixture"]).read_text(encoding="utf-8"))
ENTITIES = {e["id"]: e for e in BLUEPRINT["entities"]}
ROLES = {r["id"]: r for r in BLUEPRINT["roles"]}
MAPPED = {e["blueprintEntity"]: e for e in MAPPING["entities"]}


def test_schema_is_valid_and_example_validates():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.Draft202012Validator(SCHEMA).validate(MAPPING)


def test_draft_mapping_never_claims_to_be_verified():
    assert MAPPING["status"] == "draft"
    assert MAPPING["verification"]["benchRun"] == "none"
    assert "UNVERIFIED" in MAPPING["engine"]["versionSet"]


def test_every_mapped_entity_and_field_exists_in_the_blueprint_with_the_same_type():
    for name, em in MAPPED.items():
        assert name in ENTITIES, f"entity {name} is not in the Blueprint"
        by_id = {f["id"]: f for f in ENTITIES[name]["fields"]}
        for fm in em["fields"]:
            assert fm["blueprintField"] in by_id, f"{name}.{fm['blueprintField']} is not in the Blueprint"
            assert by_id[fm["blueprintField"]]["type"] == fm["blueprintType"], f"{name}.{fm['blueprintField']} type differs"


def test_child_entities_point_at_a_real_child_table_relation():
    for name, em in MAPPED.items():
        if em["kind"] != "child":
            continue
        parent = em["parent"]
        rels = {r["id"]: r for r in ENTITIES[parent["blueprintEntity"]].get("relations", [])}
        assert parent["relation"] in rels and rels[parent["relation"]]["target"] == name
        assert parent["blueprintEntity"] in MAPPED


def test_link_fields_name_the_engine_document_they_link_to():
    for em in MAPPED.values():
        for fm in em["fields"]:
            if fm["blueprintType"] == "link":
                assert fm.get("engineLinkDoctype"), f"{em['blueprintEntity']}.{fm['blueprintField']} needs engineLinkDoctype"


def test_role_grants_never_exceed_the_blueprint_role_and_masks_name_real_fields():
    for rm in MAPPING["roles"]:
        assert rm["blueprintRole"] in ROLES
        perms = {p["entity"]: set(p["actions"]) for p in ROLES[rm["blueprintRole"]]["permissions"]}
        for g in rm["grants"]:
            assert g["blueprintEntity"] in ENTITIES
            assert set(g["actions"]) <= perms.get(g["blueprintEntity"], set()), f"{rm['blueprintRole']} grant exceeds the Blueprint"
            fields = {f["id"] for f in ENTITIES[g["blueprintEntity"]]["fields"]}
            for mask in g.get("fieldMasks", []):
                assert mask["blueprintField"] in fields


def test_engine_roles_are_adapter_owned_not_built_in():
    for rm in MAPPING["roles"]:
        assert rm["engineRole"].startswith("platform_")


def test_operations_reference_mapped_entities_and_use_the_human_floor_for_ledger_effects():
    for op in MAPPING["operations"]:
        for key in ("fromEntity", "toEntity"):
            if key in op:
                assert op[key] in MAPPED
    posting = {"submit_delivery", "post_invoice"}
    for op in MAPPING["operations"]:
        if op["id"] in posting:
            assert op["humanFloor"] is True
    docs = {e["engineDocType"]: e for e in MAPPING["entities"]}
    assert docs["Delivery Note"]["ledgerEffect"] == "stock_and_gl" and docs["Sales Invoice"]["ledgerEffect"] == "gl"
    invoice_op = [o for o in MAPPING["operations"] if o["id"] == "create_invoice_draft_from_delivery"][0]
    assert any("not move stock again" in p for p in invoice_op["preconditions"])


def test_mapping_does_not_name_the_engine_product():
    text = MAPPING_PATH.read_text(encoding="utf-8").lower()
    assert "frappe" not in text and "erpnext" not in text


def _q(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _evaluate(expr, **values):
    return eval(expr, {"__builtins__": {}}, {k: Decimal(str(v)) for k, v in values.items()})


def _computed(entity, field):
    return [f for f in MAPPED[entity]["fields"] if f["blueprintField"] == field][0]["computed"]


@pytest.mark.parametrize("entity", ["sales_order_line", "sales_invoice_line"])
def test_line_total_formula_reproduces_the_golden_numbers(entity):
    expr = _computed(entity, "line_total")["expression"]
    assert _q(_evaluate(expr, quantity=10, unit_price="15.00", discount_percent=0)) == Decimal("150.00")
    assert _q(_evaluate(expr, quantity=3, unit_price="0.335", discount_percent=0)) == Decimal("1.01")


@pytest.mark.parametrize("entity", ["sales_order", "sales_invoice"])
def test_total_formula_gives_150_and_135_with_a_ten_percent_document_discount(entity):
    sub = _computed(entity, "subtotal")
    assert sub["aggregation"] == {"over": "lines", "function": "sum", "field": "line_total"}
    expr = _computed(entity, "total_amount")["expression"]
    assert _q(_evaluate(expr, subtotal="150.00", discount_percent=0, vat_amount=0)) == Decimal("150.00")
    assert _q(_evaluate(expr, subtotal="150.00", discount_percent=10, vat_amount=0)) == Decimal("135.00")


def test_every_computed_field_is_marked_engine_authoritative_with_rounding():
    for em in MAPPING["entities"]:
        for fm in em["fields"]:
            if "computed" in fm:
                assert fm["computed"]["authority"] == "engine"
                assert fm["computed"]["rounding"]["precision"] == 2
