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
EXAMPLES = ROOT / "contracts" / "examples"
MAPPING_PATH = EXAMPLES / "engine-mapping-golden-path.json"
MAPPING = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
PURCHASING_PATH = EXAMPLES / "engine-mapping-purchasing.json"  # BPL-034
PURCHASING = json.loads(PURCHASING_PATH.read_text(encoding="utf-8"))
ALL_PATHS = sorted(EXAMPLES.glob("engine-mapping-*.json"))
BLUEPRINT = json.loads((ROOT / MAPPING["blueprintRef"]["fixture"]).read_text(encoding="utf-8"))
ENTITIES = {e["id"]: e for e in BLUEPRINT["entities"]}
ROLES = {r["id"]: r for r in BLUEPRINT["roles"]}
MAPPED = {e["blueprintEntity"]: e for e in MAPPING["entities"]}
P_MAPPED = {e["blueprintEntity"]: e for e in PURCHASING["entities"]}
EVERY = pytest.mark.parametrize("m", [json.loads(p.read_text(encoding="utf-8")) for p in ALL_PATHS],
                                ids=[p.stem for p in ALL_PATHS])


def test_every_mapping_targets_the_same_fixture_blueprint():
    assert {PURCHASING_PATH, MAPPING_PATH} <= set(ALL_PATHS)
    for path in ALL_PATHS:
        assert json.loads(path.read_text(encoding="utf-8"))["blueprintRef"] == MAPPING["blueprintRef"]


@EVERY
def test_schema_is_valid_and_example_validates(m):
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.Draft202012Validator(SCHEMA).validate(m)


@EVERY
def test_draft_mapping_never_claims_to_be_verified(m):
    assert m["status"] == "draft"
    assert m["verification"]["benchRun"] == "none"
    assert "UNVERIFIED" in m["engine"]["versionSet"]


@EVERY
def test_every_mapped_entity_and_field_exists_in_the_blueprint_with_the_same_type(m):
    for em in m["entities"]:
        name = em["blueprintEntity"]
        assert name in ENTITIES, f"entity {name} is not in the Blueprint"
        by_id = {f["id"]: f for f in ENTITIES[name]["fields"]}
        for fm in em["fields"]:
            assert fm["blueprintField"] in by_id, f"{name}.{fm['blueprintField']} is not in the Blueprint"
            assert by_id[fm["blueprintField"]]["type"] == fm["blueprintType"], f"{name}.{fm['blueprintField']} type differs"


@EVERY
def test_child_entities_point_at_a_real_child_table_relation(m):
    mapped = {e["blueprintEntity"] for e in m["entities"]}
    for em in m["entities"]:
        name = em["blueprintEntity"]
        if em["kind"] != "child":
            continue
        parent = em["parent"]
        rels = {r["id"]: r for r in ENTITIES[parent["blueprintEntity"]].get("relations", [])}
        assert parent["relation"] in rels and rels[parent["relation"]]["target"] == name
        assert parent["blueprintEntity"] in mapped


@EVERY
def test_link_fields_name_the_engine_document_they_link_to(m):
    for em in m["entities"]:
        for fm in em["fields"]:
            if fm["blueprintType"] == "link":
                assert fm.get("engineLinkDoctype"), f"{em['blueprintEntity']}.{fm['blueprintField']} needs engineLinkDoctype"


@EVERY
def test_role_grants_never_exceed_the_blueprint_role_and_masks_name_real_fields(m):
    mapped = {e["blueprintEntity"] for e in m["entities"]}
    for rm in m["roles"]:
        assert rm["blueprintRole"] in ROLES
        perms = {p["entity"]: set(p["actions"]) for p in ROLES[rm["blueprintRole"]]["permissions"]}
        for g in rm["grants"]:
            assert g["blueprintEntity"] in ENTITIES and g["blueprintEntity"] in mapped
            assert set(g["actions"]) <= perms.get(g["blueprintEntity"], set()), f"{rm['blueprintRole']} grant exceeds the Blueprint"
            fields = {f["id"] for f in ENTITIES[g["blueprintEntity"]]["fields"]}
            for mask in g.get("fieldMasks", []):
                assert mask["blueprintField"] in fields


@EVERY
def test_engine_roles_are_adapter_owned_not_built_in(m):
    for rm in m["roles"]:
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


@pytest.mark.parametrize("path", ALL_PATHS, ids=[p.stem for p in ALL_PATHS])
def test_mapping_does_not_name_the_engine_product(path):
    text = path.read_text(encoding="utf-8").lower()
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


@EVERY
def test_every_computed_field_is_marked_engine_authoritative_with_rounding(m):
    for em in m["entities"]:
        for fm in em["fields"]:
            if "computed" in fm:
                assert fm["computed"]["authority"] == "engine"
                assert fm["computed"]["rounding"]["precision"] == 2


# BPL-034: purchasing and price-list mapping (contracts/examples/engine-mapping-purchasing.json).
def test_purchasing_maps_the_entities_the_fixture_roles_grant():
    granted = {p["entity"] for r in BLUEPRINT["roles"] for p in r["permissions"]}
    covered = set(MAPPED) | set(P_MAPPED)
    for name in ("supplier", "price_list", "purchase_order", "purchase_receipt", "purchase_invoice"):
        assert name in granted and name in P_MAPPED
    assert not set(MAPPED) & set(P_MAPPED), "an entity is mapped twice"
    assert granted - covered <= {"sales_quote", "credit_note", "payment", "stock_transfer"}


def test_purchasing_ledger_effects_and_human_floor_on_every_posting_submit():
    effects = {e["blueprintEntity"]: e["ledgerEffect"] for e in PURCHASING["entities"]}
    assert effects["supplier"] == effects["price_list"] == effects["purchase_order"] == "none"
    assert effects["purchase_receipt"] == "stock_and_gl" and effects["purchase_invoice"] == "gl"
    for op in PURCHASING["operations"]:
        if "toEntity" in op:
            assert op["toEntity"] in P_MAPPED
        if "fromEntity" in op:
            assert op["fromEntity"] in P_MAPPED
        if op["blueprintAction"] == "submit":
            assert op["humanFloor"] is (effects[op["toEntity"]] != "none"), op["id"]
    pinv = [o for o in PURCHASING["operations"] if o["toEntity"] == "purchase_invoice" and o["blueprintAction"] == "create"][0]
    assert any("not move stock again" in p for p in pinv["preconditions"])


def test_purchasing_unmapped_fields_are_real_and_not_also_mapped():
    for u in PURCHASING["unmapped"]:
        fields = {f["id"] for f in ENTITIES[u["blueprintEntity"]]["fields"]}
        assert u["blueprintField"] in fields
        assert u["blueprintField"] not in {f["blueprintField"] for f in P_MAPPED[u["blueprintEntity"]]["fields"]}


@pytest.mark.parametrize("entity", ["purchase_order_line", "purchase_invoice_line"])
def test_purchase_line_and_document_totals_reproduce_the_golden_numbers(entity):
    expr = [f for f in P_MAPPED[entity]["fields"] if f["blueprintField"] == "line_total"][0]["computed"]["expression"]
    assert _q(_evaluate(expr, quantity=10, unit_cost="10.00", discount_percent=0)) == Decimal("100.00")
    assert _q(_evaluate(expr, quantity=3, unit_cost="0.335", discount_percent=0)) == Decimal("1.01")
    doc = P_MAPPED[entity]["parent"]["blueprintEntity"]
    tot = [f for f in P_MAPPED[doc]["fields"] if f["blueprintField"] == "total_amount"][0]["computed"]["expression"]
    assert _q(_evaluate(tot, subtotal="100.00", discount_percent=10, vat_amount=0)) == Decimal("90.00")


def _unmapped(m):
    return {(u["blueprintEntity"], u["blueprintField"]) for u in m.get("unmapped", [])}


# Scoped to the purchasing example: the golden-path example (BPL-029) is not edited by BPL-034.
def test_purchasing_every_blueprint_field_of_a_mapped_entity_is_mapped_or_listed_unmapped():
    listed = _unmapped(PURCHASING)
    for name, em in P_MAPPED.items():
        mapped = {f["blueprintField"] for f in em["fields"]}
        for f in ENTITIES[name]["fields"]:
            assert f["id"] in mapped or (name, f["id"]) in listed, f"{name}.{f['id']} is neither mapped nor unmapped"
            assert not (f["id"] in mapped and (name, f["id"]) in listed), f"{name}.{f['id']} is both"
    assert all(u["reason"].strip() for u in PURCHASING["unmapped"])


# Scoped to purchasing: the golden-path example maps sales_invoice.outstanding_amount as a plain field (BPL-029, not edited here).
def test_purchasing_blueprint_computed_field_is_never_mapped_as_a_plain_field():
    m = PURCHASING
    listed = _unmapped(m)
    for em in m["entities"]:
        name = em["blueprintEntity"]
        computed_ids = {f["id"] for f in ENTITIES[name]["fields"] if f.get("computed")}
        for fm in em["fields"]:
            if fm["blueprintField"] in computed_ids:
                assert fm.get("computed", {}).get("authority") == "engine", \
                    f"{name}.{fm['blueprintField']} is computed in the Blueprint but mapped as a plain field"
                assert (name, fm["blueprintField"]) not in listed
