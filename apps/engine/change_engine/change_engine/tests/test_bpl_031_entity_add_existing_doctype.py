"""BPL-031: entity.add on an existing engine document type applies the Blueprint's fields, and never makes a custom
twin of a built-in type.

Offline, on the case-insensitive simulated engine seeded with every built-in document type the mapping contract names
(contracts/examples/engine-mapping-*.json). The bench read-back is test_05 in test_bpl_027_fixture_real_adapter.py;
both use `entity_gaps`, which derives its expectations from the contract and not from the adapter's mapper.
Synthetic data only.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from change_engine.adapter import FrappeBackendError, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine
from change_engine.tests.test_bpl_027_fixture_real_adapter import (
    MAPPINGS,
    TENANT,
    entity_gaps,
    expected_engine_config,
    load_fixture,
    without_attachments,
)

_ENV = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})  # ERP-027: the offline DDL simulator needs dev or test


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()


def contract_doctypes() -> dict[str, str]:
    """{Blueprint entity: engine document type} straight from the mapping contract examples."""
    out = {}
    for path in MAPPINGS:
        for ent in json.loads(path.read_text(encoding="utf-8"))["entities"]:
            out[ent["blueprintEntity"]] = ent["engineDocType"]
    return out


def engine() -> CaseInsensitiveEngine:
    """A simulated site on which every document type the contract names exists as a built-in (custom=0), as on a real
    site with the commerce app installed."""
    eng = CaseInsensitiveEngine("bpl031.localhost")
    for dt in sorted(set(contract_doctypes().values())):
        if not eng.db.exists("DocType", dt):
            eng.add_doctype(dt, module="Selling", custom=0)
    return eng


def drop_doctype(eng: CaseInsensitiveEngine, doctype: str) -> None:
    site = eng.current_site_db()
    for store in (site.rows, site.table_columns):
        store.pop(f"tab{doctype}", None)
    site.rows["tabDocType"].pop(doctype, None)


def backend_for(eng: CaseInsensitiveEngine) -> FrappeRuntimeBackend:
    return FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: "bpl031.localhost"}),
                                frappe_factory=lambda: eng, offline_ddl_simulator=True)


def entity_add(backend: FrappeRuntimeBackend, definition: dict) -> None:
    backend.execute_step(TENANT, {"seq": 1, "kind": "entity.add", "pointer": f"/entities/{definition['id']}",
                                  "subject": {"kind": "entity", "id": definition["id"]}, "params": {"definition": definition}})


def entity(entity_id: str, *fields: tuple[str, str]) -> dict:
    return {"id": entity_id, "kind": "master", "labels": {"en": entity_id, "ar": entity_id},
            "fields": [{"id": fid, "type": ftype, "labels": {"en": fid, "ar": fid}} for fid, ftype in fields]}


def custom_fields(eng: CaseInsensitiveEngine, doctype: str) -> set[str]:
    return {r["fieldname"] for r in eng.rows("Custom Field") if r.get("dt") == doctype}


def doctype_names(eng: CaseInsensitiveEngine) -> set[str]:
    return {r["name"] for r in eng.rows("DocType")}


class TestEntityAddExistingDoctype(unittest.TestCase):
    def test_fields_are_added_to_a_mapped_built_in_type(self) -> None:
        eng = engine()
        before = doctype_names(eng)
        entity_add(backend_for(eng), entity("customer", ("vat_number", "string"), ("credit_limit", "money")))
        self.assertEqual(custom_fields(eng, "Customer"), {"custom_vat_number", "custom_credit_limit"})
        self.assertEqual(doctype_names(eng), before, "a built-in type must not be replaced or duplicated")
        self.assertEqual(eng.db.get_value("DocType", "Customer", "custom"), 0)
        self.assertEqual(eng.get_meta("Customer").get_field("custom_credit_limit").fieldtype, "Currency")

    def test_a_native_field_with_the_blueprint_name_is_not_twinned(self) -> None:
        eng = engine()  # the simulated Customer holds customer_name natively
        entity_add(backend_for(eng), entity("customer", ("customer_name", "string"), ("vat_number", "string")))
        self.assertEqual(custom_fields(eng, "Customer"), {"custom_vat_number"})

    def test_reapply_adds_nothing_more(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("vat_number", "string"))
        entity_add(backend, definition)
        snapshot = (eng.rows("Custom Field"), eng.rows("Property Setter"), doctype_names(eng))
        entity_add(backend, definition)
        self.assertEqual((eng.rows("Custom Field"), eng.rows("Property Setter"), doctype_names(eng)), snapshot)

    def test_child_and_price_entities_use_the_built_in_type_the_contract_names(self) -> None:
        """purchase_order_line is "Purchase Order Item" and price_list_item is "Item Price" in the contract; deriving
        the name from the id made "Purchase Order Line" and "Price List Item" beside them."""
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("purchase_order_line", ("quantity", "decimal"), ("line_note", "string")))
        entity_add(backend, entity("price_list_item", ("min_quantity", "decimal")))
        self.assertIn("custom_line_note", custom_fields(eng, "Purchase Order Item"))
        self.assertIn("custom_min_quantity", custom_fields(eng, "Item Price"))
        self.assertFalse({"Purchase Order Line", "Price List Item"} & doctype_names(eng))

    def test_a_mapped_type_missing_from_the_engine_is_refused_not_created(self) -> None:
        eng = engine()
        drop_doctype(eng, "Purchase Order Item")
        before = doctype_names(eng)
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), entity("purchase_order_line", ("line_note", "string")))
        self.assertEqual(err.exception.details.get("reasonCode"), "subject_missing")
        self.assertTrue(err.exception.side_effect_free)
        self.assertEqual(doctype_names(eng), before)
        self.assertEqual(eng.rows("Custom Field"), [])

    def test_an_unmapped_entity_becomes_one_adapter_owned_type(self) -> None:
        """ADR-0051 item 3: no mapping, no built-in of that name, so the adapter makes its own custom type, once."""
        eng, definition = engine(), entity("payment", ("amount", "money"), ("reference", "string"))
        backend = backend_for(eng)
        entity_add(backend, definition)
        row = eng.db.get_value("DocType", "Payment", ["custom", "module"])
        self.assertEqual((int(row[0]), row[1]), (1, "Custom"))
        self.assertEqual({f.fieldname for f in eng.get_meta("Payment").fields}, {"custom_amount", "custom_reference"})
        entity_add(backend, definition)  # a re-apply keeps the one type
        self.assertEqual([r["name"] for r in eng.rows("DocType") if r["name"] == "Payment"], ["Payment"])

    def test_an_unmapped_entity_named_like_an_engine_type_is_refused(self) -> None:
        """No mapping and the derived name is a type the adapter did not make: nothing may be written to it, and the
        step must not report success while applying no fields."""
        eng = engine()
        eng.add_doctype("Legacy Thing", module="Selling", custom=0)
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), entity("legacy_thing", ("note", "string")))
        self.assertEqual(err.exception.details.get("reasonCode"), "protected_subject")
        self.assertTrue(err.exception.side_effect_free)
        self.assertEqual(eng.rows("Custom Field"), [])

    def test_an_unsupported_field_type_is_refused_before_any_write(self) -> None:
        eng = engine()
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), entity("customer", ("vat_number", "string"), ("scan", "attachment")))
        self.assertEqual(err.exception.details.get("reasonCode"), "unsupported_value_type")
        self.assertEqual(eng.rows("Custom Field"), [])


class TestFixtureReadBack(unittest.TestCase):
    """The offline twin of bench test_05: apply every fixture entity, then read the engine back."""

    @staticmethod
    def apply_fixture(eng: CaseInsensitiveEngine) -> dict:
        bp = without_attachments(load_fixture())
        backend = backend_for(eng)
        for elem in bp["entities"]:
            entity_add(backend, elem)
        return expected_engine_config(bp)

    def test_expected_types_come_from_the_contract(self) -> None:
        exp = expected_engine_config(without_attachments(load_fixture()))
        self.assertEqual(exp["entities"]["purchase_order_line"], "Purchase Order Item")
        self.assertEqual(exp["entities"]["price_list_item"], "Item Price")
        self.assertEqual(exp["entities"]["customer"], "Customer")
        self.assertEqual(exp["custom_entities"], ["Credit Note", "Credit Note Line", "Payment", "Sales Quote", "Sales Quote Line",
                                                  "Stock Transfer", "Stock Transfer Line"])
        self.assertEqual(set(exp["entities"]) - set(contract_doctypes()), {"sales_quote", "sales_quote_line", "credit_note",
                                                                         "credit_note_line", "payment", "stock_transfer",
                                                                         "stock_transfer_line"})

    def test_05_offline_entities_and_fields(self) -> None:
        eng = engine()
        exp = self.apply_fixture(eng)
        self.assertEqual(entity_gaps(eng, exp), {"missing": [], "duplicates": []})
        # not vacuous: Blueprint fields really reached built-in types, and the custom types are the unmapped entities only
        self.assertIn("custom_vat_number", custom_fields(eng, "Customer"))
        self.assertTrue(custom_fields(eng, "Sales Invoice"))
        made = sorted(r["name"] for r in eng.rows("DocType") if r.get("custom") == 1)
        self.assertEqual(made, exp["custom_entities"])

    def test_the_read_back_reports_the_gap_and_duplicates(self) -> None:
        """Without the fix, or with a custom twin on the engine, the check fails: it is not tuned to pass."""
        bare = engine()
        exp = expected_engine_config(without_attachments(load_fixture()))
        gaps = entity_gaps(bare, exp)
        self.assertIn("Customer.vat_number", gaps["missing"])
        self.assertIn("doctype Payment (payment)", gaps["missing"])
        twin = engine()
        self.apply_fixture(twin)
        twin.add_doctype("Purchase Order Line", module="Custom", custom=1)
        self.assertEqual(entity_gaps(twin, exp), {"missing": [], "duplicates": ["Purchase Order Line"]})


if __name__ == "__main__":
    unittest.main()
