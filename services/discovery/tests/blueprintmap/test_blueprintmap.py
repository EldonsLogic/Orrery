import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

import blueprintmap as B
from blueprintmap import table
from connectors.odoo import mapping as odoo

PKG = Path(B.__file__).resolve().parent
REPO = PKG.parents[2]
SCHEMA = json.loads((REPO / "contracts" / "blueprint.schema.json").read_text(encoding="utf-8"))


def _validator(ref):
    return jsonschema.Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{ref}"})


ENTITY, LOCATION = _validator("entity"), _validator("location")
TYPES = {"char": "char", "text": "text", "integer": "integer", "float": "float", "monetary": "monetary",
         "boolean": "boolean", "date": "date", "datetime": "datetime", "selection": "selection",
         "many2one": "many2one", "one2many": "one2many", "binary": "binary"}


def model(name, fields, records=(), **kw):
    """fields: {name: odoo type}. A raw connector model item with synthetic data."""
    fm = {f: {"type": t, "string": f, "required": False, "relation": "", "selection": [], "translate": False}
          for f, t in fields.items()}
    return {"type": "model", "model": name, "unavailable": False, "fields": fm, "withheld": [], "binary": [],
            "records": list(records), "count": len(records), "pages": 1, "truncated": "", **kw}


def source_types(mdl):
    """Odoo type for each field of a model, taken from the neutral type in the export table."""
    inv = {"text": "char", "integer": "integer", "decimal": "float", "boolean": "boolean", "date": "date",
           "datetime": "datetime", "enum": "selection", "reference": "many2one", "reference_list": "one2many"}
    return {f: inv[nt] for f, (n, nt) in odoo.MAPPING[mdl].items()}


def full(mdl, records=()):
    return model(mdl, source_types(mdl), records)


def run(items):
    return B.map_records(copy.deepcopy(items))


def mapped(res, mdl):
    return {(m["field"], m["target"]) for m in res["report"]["mapped"] if m["model"] == mdl}


def test_table_resolves_in_template():
    ent = B.load_entities()
    assert B.check_table(ent) == []
    assert set(table.MODELS) == set(odoo.DEFAULT_MODELS)
    for mdl, fields in odoo.MAPPING.items():
        for _f, (neutral, _t) in fields.items():
            assert neutral in table.FIELDS, neutral


def test_every_mapped_model_yields_valid_entities():
    items = [full(m) for m in odoo.DEFAULT_MODELS]
    res = run(items)
    ids = {e["id"] for e in res["fragment"]["entities"]}
    assert {"customer", "supplier", "item", "sales_order", "sales_order_line", "purchase_order",
            "purchase_order_line", "sales_invoice", "purchase_invoice", "credit_note", "sales_invoice_line",
            "purchase_invoice_line", "credit_note_line", "payment"} <= ids
    template = B.load_entities()
    for e in res["fragment"]["entities"]:
        assert not list(ENTITY.iter_errors(e)), e["id"]
        assert e["provenance"]["source"] == "imported" and e["provenance"]["humanEdited"] is False
        for f in e["fields"]:  # only vocabulary the template already has
            assert f in template[e["id"]]["fields"]


@pytest.mark.parametrize("mdl,pairs", [
    ("res.partner", {("name", "customer.customer_name"), ("name", "supplier.supplier_name"),
                     ("vat", "customer.vat_number"), ("city", "supplier.city")}),
    ("product.template", {("name", "item.item_name"), ("list_price", "item.selling_price"),
                          ("standard_price", "item.cost_price"), ("uom_id", "item.unit")}),
    ("sale.order", {("partner_id", "sales_order.customer"), ("amount_total", "sales_order.total_amount"),
                    ("order_line", "sales_order#lines")}),
    ("sale.order.line", {("price_unit", "sales_order_line.unit_price"), ("product_uom_qty", "sales_order_line.quantity")}),
    ("purchase.order", {("partner_id", "purchase_order.supplier")}),
    ("purchase.order.line", {("price_unit", "purchase_order_line.unit_cost")}),
    ("account.move", {("partner_id", "purchase_invoice.supplier"), ("invoice_date", "credit_note.credit_date")}),
    ("account.move.line", {("price_unit", "purchase_invoice_line.unit_cost")}),
    ("account.payment", {("amount", "payment.amount"), ("date", "payment.posting_date")}),
])
def test_mapped_models(mdl, pairs):
    assert pairs <= mapped(run([full(mdl)]), mdl)


def test_active_maps_inverted_to_disabled():
    m = full("res.partner")
    m["fields"]["active"] = dict(m["fields"]["name"], type="boolean")
    res = run([m])
    inv = [m for m in res["report"]["mapped"] if m["field"] == "active"]
    assert {m["target"] for m in inv} == {"customer.disabled", "supplier.disabled"}
    assert all(m["inverted"] for m in inv)


def test_warehouse_company_and_reference_data():
    res = run([
        full("res.company", [{"id": 1, "name": "Sample Trading", "vat": "300000000000003", "currency_id": [2, "SAR"]}]),
        model("stock.warehouse", {"name": "char", "code": "char", "lot_stock_id": "many2one"},
              [{"id": 7, "name": "المستودع الرئيسي", "code": "WH1"}, {"id": 8, "name": "Second", "code": "مخزن"}]),
        full("account.tax", [{"id": 3, "name": "VAT standard", "amount": 17.5}]),
        full("uom.uom", [{"id": 1, "name": "Units"}]),
    ])
    f = res["fragment"]
    assert f["company"] == {"legalName": {"ar": "Sample Trading", "en": "Sample Trading"},
                            "vatNumber": "300000000000003", "locale": {"currency": "SAR"}}
    assert [x["id"] for x in f["locations"]] == ["wh1", "wh_8"]
    assert all(not list(LOCATION.iter_errors(x)) and x["kind"] == "warehouse" for x in f["locations"])
    assert f["reference_data"]["taxes"] == [{"model": "account.tax", "source_id": 3, "label": "VAT standard"}]
    assert "17" not in json.dumps(f["reference_data"])  # the rate is not interpreted
    codes = {(h["model"], h["code"]) for h in res["report"]["needs_human"]}
    assert ("account.tax", "tax_semantics") in codes
    assert ("res.company", "label_locale_unverified") in codes


def test_invalid_company_values_need_a_person():
    res = run([model("res.company", {"vat": "char", "currency_id": "many2one"},
                     [{"id": 1, "vat": "12345", "currency_id": [1, "sar!"]}])])
    assert res["fragment"]["company"] == {}
    assert sum(h["code"] == "invalid_value" for h in res["report"]["needs_human"]) == 2


def test_unmapped_field_with_reason_never_dropped():
    m = model("res.partner", {"name": "char", "x_studio_note": "char", "street": "char", "payment_blob": "binary"})
    m["fields"]["property_payment_term_id"] = dict(m["fields"]["name"], type="many2one")
    res = run([m])
    un = {u["field"]: u["reason"] for u in res["report"]["unmapped_field"]}
    assert un == {"x_studio_note": "no_neutral_name", "street": "no_blueprint_home",
                  "payment_blob": "binary_not_fetched", "property_payment_term_id": "semantic_mismatch"}
    mp = {x["field"] for x in res["report"]["mapped"]}
    assert mp | set(un) == set(m["fields"])
    assert all(u["reason_key"].startswith("bmp.reason.") for u in res["report"]["unmapped_field"])


def test_unmapped_models():
    res = run([model("hr.employee", {"name": "char"}), model("stock.location", {"name": "char"}),
               model("sale.order.template", {"name": "char"}, unavailable=True) | {"unavailable": True}])
    um = {u["model"]: u["reason"] for u in res["report"]["unmapped_model"]}
    assert um == {"hr.employee": "no_neutral_name", "stock.location": "no_blueprint_entity",
                  "sale.order.template": "model_unavailable"}


def test_needs_human_ledger_tax_stock_posted():
    res = run([
        full("account.move", [{"id": 1, "state": "posted", "move_type": "out_invoice"},
                              {"id": 2, "state": "posted", "move_type": "entry"},
                              {"id": 3, "state": "draft", "move_type": "in_invoice"}]),
        full("account.move.line"),
        full("account.account", [{"id": 1, "code": "1000", "name": "Cash"}]),
        full("stock.quant", [{"id": 1, "quantity": 5.0}]),
        full("account.payment", [{"id": 1, "state": "paid"}]),
    ])
    nh = {(h["model"], h["code"], h["field"]): h["count"] for h in res["report"]["needs_human"]}
    assert nh[("account.move", "posted_entries", "state")] == 2
    assert nh[("account.move", "journal_entry_not_mapped", "move_type")] == 1
    assert nh[("account.payment", "posted_entries", "state")] == 1
    assert ("stock.quant", "stock_semantics", "") in nh and ("account.account", "ledger_semantics", "") in nh
    assert ("account.move.line", "ledger_semantics", "debit") in nh
    mp = {(m["model"], m["field"]) for m in res["report"]["mapped"]}
    assert ("account.move.line", "debit") not in mp and ("account.move.line", "credit") not in mp
    assert ("account.move", "journal_id") not in mp
    un = {(u["model"], u["field"]) for u in res["report"]["unmapped_field"]}
    assert ("account.move.line", "debit") in un
    # ledger numbers never reach the fragment, nor does the stock quantity model
    assert all(e["id"] != "stock_level" for e in res["fragment"]["entities"])


def test_enum_targets_need_review():
    res = run([full("account.payment")])
    assert ("account.payment", "enum_values_review", "payment_type") in {
        (h["model"], h["code"], h["field"]) for h in res["report"]["needs_human"]}


def test_conflicts():
    res = run([model("res.partner", {"phone": "char", "mobile": "char"}),
               full("product.template"), full("product.product")])
    c = {(x["model"], x["field"], x["reason"]) for x in res["report"]["conflicts"]}
    assert ("res.partner", "mobile", "target_taken") in c
    assert ("product.product", "barcode", "target_taken") in c
    res = run([model("res.partner", {"name": "integer"})])  # wrong type for the target
    assert {x["reason"] for x in res["report"]["conflicts"]} == {"type_mismatch"}
    assert res["fragment"]["entities"] == []


def test_duplicate_location_id_is_a_conflict():
    res = run([model("stock.warehouse", {"name": "char", "code": "char"},
                     [{"id": 1, "name": "A", "code": "WH"}, {"id": 2, "name": "B", "code": "WH"}])])
    assert [x["id"] for x in res["fragment"]["locations"]] == ["wh"]
    assert [x["reason"] for x in res["report"]["conflicts"]] == ["duplicate_id"]


HOSTILE = "<script>alert(1)</script>‮evil\x00\x1b[31m'; DROP TABLE x;--{{7*7}}${jndi:x}" + "A" * 500


def test_hostile_strings_are_inert():
    m = model("res.partner", {"name": "char", "x'; DROP": "char", "__import__('os')": "char"}, [{"id": 1, "name": HOSTILE}])
    res = run([m, model("res.currency", {"name": "char"}, [{"id": 1, "name": HOSTILE}]),
               model("stock.warehouse", {"name": "char", "code": "char"}, [{"id": 1, "name": HOSTILE, "code": HOSTILE}]),
               model("evil'; model", {"name": "char"})])
    blob = json.dumps(res, ensure_ascii=False)
    assert "\x00" not in blob and "‮" not in blob and "\x1b" not in blob
    assert {u["reason"] for u in res["report"]["unmapped_field"]} == {"invalid_name"}
    assert [u["reason"] for u in res["report"]["unmapped_model"]] == ["invalid_name"]
    assert len(res["fragment"]["locations"][0]["labels"]["en"]) <= 120
    assert res["fragment"]["locations"][0]["id"] == "wh_1"  # hostile code is not an id
    assert all(len(r["label"]) <= 120 for r in res["fragment"]["reference_data"]["currencies"])
    assert B.clean("a‮b\x00c‍") == "abc‍" and B.clean(None) == ""
    assert not any(t in blob for t in ("‮",))


def test_deterministic_and_input_not_mutated():
    items = [full(m) for m in odoo.DEFAULT_MODELS]
    before = copy.deepcopy(items)
    a = B.map_records(items)
    b = B.map_records(list(reversed(items)))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert items == before


def test_refusals():
    for bad in ("x", None, 5, {"models": "x"}):
        with pytest.raises(B.BlueprintMapError) as e:
            B.map_records(bad)
        assert e.value.code == "BMP-E01"
    with pytest.raises(B.BlueprintMapError) as e:
        B.map_records([model(f"a.m{i}", {}) for i in range(201)])
    assert e.value.code == "BMP-E02"
    ent = B.load_entities()
    del ent["item"]
    with pytest.raises(B.BlueprintMapError) as e:
        B.map_records([], ent)
    assert e.value.code == "BMP-E04"


def test_cli(tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps([full("sale.order")]), encoding="utf-8")
    p = subprocess.run([sys.executable, "-W", "ignore", "-m", "blueprintmap", str(f)], cwd=PKG.parent,
                       capture_output=True, text=True)
    assert p.returncode in (0, 1) and json.loads(p.stdout)["fragment"]["entities"][0]["id"] == "sales_order"
    f.write_text("{", encoding="utf-8")
    p = subprocess.run([sys.executable, "-m", "blueprintmap", str(f)], cwd=PKG.parent, capture_output=True, text=True)
    assert p.returncode == 2 and "BMP-E01" in p.stderr


def test_files_stay_small():
    for f in list(PKG.glob("*.py")):
        assert len(f.read_text(encoding="utf-8").splitlines()) < 500
