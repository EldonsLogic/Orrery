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
    apply_ready,
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


def role_step(definition: dict) -> dict:
    return {"seq": 1, "kind": "role.upsert", "pointer": f"/roles/{definition['id']}",
            "subject": {"kind": "role", "id": definition["id"]}, "params": {"definition": definition}}


def role(role_id: str, entity_id: str, *hidden: str, scope: str = "own_records") -> dict:
    return {"id": role_id, "labels": {"en": role_id, "ar": role_id}, "scope": {"type": scope},
            "permissions": [{"entity": entity_id, "actions": ["read"], "hiddenFields": list(hidden)}]}


def can_read(eng: CaseInsensitiveEngine, role_name: str, doctype: str, fieldname: str) -> bool:
    """Independent read-back: does a Custom DocPerm rule of the role read the field at the level the field now sits on?"""
    level = int(getattr(eng.get_meta(doctype).get_field(fieldname), "permlevel", 0) or 0)
    return any(r.get("role") == role_name and r.get("parent") == doctype and int(r.get("permlevel") or 0) == level
               and int(r.get("read") or 0) for r in eng.rows("Custom DocPerm"))


def provision_cost_mask(eng: CaseInsensitiveEngine) -> None:
    """Tenant provisioning (E0-7 item 4) puts Item.valuation_rate on permission level 1."""
    eng.make_property_setter({"doctype": "Item", "fieldname": "valuation_rate", "property": "permlevel", "value": 1,
                              "property_type": "Int"})


def contract_native_fields() -> dict[tuple[str, str], str | None]:
    """{(entity, field): native engine field, or None when the data is stored on another record} for every field the
    contract maps to a name other than its own (written from the contract files, not from the adapter)."""
    out = {}
    for path in MAPPINGS:
        for ent in json.loads(path.read_text(encoding="utf-8"))["entities"]:
            for fld in ent["fields"]:
                if fld.get("engineField") != fld["blueprintField"]:
                    out[(ent["blueprintEntity"], fld["blueprintField"])] = fld.get("engineField")
    return out


class TestReviewFixesHiddenFieldMask(unittest.TestCase):
    """Review finding 1 (high, security): a hidden field must be masked on the engine field that holds the data."""

    def test_sales_rep_cannot_read_native_valuation_rate(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("item", ("cost_price", "money")))
        backend.execute_step(TENANT, role_step(role("sales_rep", "item", "cost_price")))
        self.assertFalse(can_read(eng, "bp-sales_rep", "Item", "valuation_rate"), "the native cost field is readable")
        self.assertFalse(can_read(eng, "bp-sales_rep", "Item", "custom_cost_price"))

    def test_with_the_native_cost_field_on_a_protected_level_the_grant_applies(self) -> None:
        eng = engine()
        provision_cost_mask(eng)
        backend = backend_for(eng)
        entity_add(backend, entity("item", ("cost_price", "money")))
        backend.execute_step(TENANT, role_step(role("sales_rep", "item", "cost_price")))
        self.assertTrue(can_read(eng, "bp-sales_rep", "Item", "item_name"), "the grant must apply, or this test proves nothing")
        self.assertFalse(can_read(eng, "bp-sales_rep", "Item", "valuation_rate"))
        self.assertEqual(int(eng.get_meta("Item").get_field("valuation_rate").permlevel), 1)

    def test_a_field_stored_on_another_record_cannot_be_masked_on_the_type_so_the_grant_is_withheld(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("item", ("selling_price", "money")))  # the engine keeps the price on Item Price (contract)
        backend.execute_step(TENANT, role_step(role("sales_rep", "item", "selling_price")))
        self.assertFalse([r for r in eng.rows("Custom DocPerm") if r.get("role") == "bp-sales_rep"])

    def test_an_unmapped_hidden_field_is_still_masked_on_its_custom_field(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("customer", ("credit_limit", "money")))
        backend.execute_step(TENANT, role_step(role("sales_rep", "customer", "credit_limit")))
        self.assertTrue(can_read(eng, "bp-sales_rep", "Customer", "customer_name"))
        self.assertFalse(can_read(eng, "bp-sales_rep", "Customer", "custom_credit_limit"))

    def test_the_adapter_table_matches_the_contract(self) -> None:
        from change_engine.adapter.mapping import CONTRACT_NATIVE_FIELDS

        self.assertEqual(dict(CONTRACT_NATIVE_FIELDS), contract_native_fields())


class TestReviewFixesUniqueAndIndexed(unittest.TestCase):
    """Review finding 2 (high): a unique or indexed Blueprint field is never applied without its constraint."""

    def refuse(self, eng: CaseInsensitiveEngine, definition: dict) -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), definition)
        self.assertEqual(err.exception.code, "plan_rejected")
        self.assertEqual(err.exception.details.get("reasonCode"), "unique_or_index")
        self.assertTrue(err.exception.side_effect_free)
        return err.exception

    def test_a_unique_field_on_a_built_in_type_is_refused_before_any_write(self) -> None:
        eng = engine()
        definition = entity("customer", ("vat_number", "string"), ("customer_code", "string"))
        definition["fields"][1]["unique"] = True
        self.refuse(eng, definition)
        self.assertEqual(eng.rows("Custom Field"), [], "the refusal must come before the first write")
        self.assertEqual(eng.rows("Property Setter"), [])

    def test_an_indexed_field_is_refused_too(self) -> None:
        eng = engine()
        definition = entity("supplier", ("supplier_code", "string"))
        definition["fields"][0]["indexed"] = True
        self.refuse(eng, definition)
        self.assertEqual(eng.rows("Custom Field"), [])

    def test_a_unique_field_the_type_already_holds_needs_no_ddl_and_is_not_refused(self) -> None:
        eng = engine()  # Item.item_code is native: nothing is added, so no constraint is dropped
        definition = entity("item", ("item_code", "string"))
        definition["fields"][0]["unique"] = True
        entity_add(backend_for(eng), definition)
        self.assertEqual(eng.rows("Custom Field"), [])


def item_review_artifacts():
    """Artifact pair for the public-API rollback tests: v1 adds Customer fields, v2 adds Item with a review note."""
    from change_engine.tests.test_bpl_008_blueprint_rollback import _load_example, _make_artifact

    bp = _load_example("blueprint-trading-minimal.json")
    rev1 = {"hash": "sha256:" + ("1" * 64), "revision": 1}
    rev2 = {"hash": "sha256:" + ("2" * 64), "revision": 2}
    note_item = entity("item", ("review_note", "string"))

    def step(kind: str, ent: dict, impact: str, ddl: str) -> dict:
        return {"seq": 1, "phase": 16 if kind.endswith(".quarantine") else 4, "kind": kind, "subject": {"kind": "entity", "id": ent["id"], "parents": []},
                "pointer": f"/entities/{ent['id']}", "impact": impact, "ddlImpact": ddl, "reversible": True,
                "params": {"definition": ent}, "sourceOps": [f"/entities/{ent['id']}"]}

    customer = entity("customer", ("vat_number", "string"))
    v1 = _make_artifact(bp_id="example-trading-001", kind="forward", base=None, target=rev1,
                        steps=[step("entity.add", customer, "data_shape", "additive")],
                        post_conditions=[{"id": "pc_001", "check": "exists", "pointer": "/entities/customer"}])
    v2_inv = _make_artifact(bp_id="example-trading-001", kind="inverse", base=rev2, target=rev1, diff_hash="sha256:" + ("a" * 64),
                            steps=[step("entity.quarantine", note_item, "destructive", "none")],
                            post_conditions=[{"id": "pc_001", "check": "quarantined", "pointer": "/entities/item"}])
    v2 = _make_artifact(bp_id="example-trading-001", kind="forward", base=rev1, target=rev2, diff_hash="sha256:" + ("b" * 64),
                        steps=[step("entity.add", note_item, "data_shape", "additive")],
                        post_conditions=[{"id": "pc_001", "check": "exists", "pointer": "/entities/item"}], inverse=v2_inv)
    return v1, v2, bp


class TestReviewFixesQuarantine(unittest.TestCase):
    """Review finding 3 (medium): rolling back an entity.add hides exactly the fields it added, re-apply restores them."""

    def hidden(self, eng: CaseInsensitiveEngine, doctype: str, fieldname: str) -> int:
        return int(getattr(eng.get_meta(doctype).get_field(fieldname), "hidden", 0) or 0)

    def quarantine(self, backend: FrappeRuntimeBackend, definition: dict) -> None:
        backend.execute_step(TENANT, {"seq": 1, "kind": "entity.quarantine", "pointer": f"/entities/{definition['id']}",
                                      "subject": {"kind": "entity", "id": definition["id"]}, "params": {"definition": definition}})

    def test_quarantine_hides_only_the_fields_entity_add_introduced_and_reapply_restores_them(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        # a custom field that is already there (added earlier by field.add) is not this entity.add's to hide
        backend.execute_step(TENANT, {"seq": 1, "kind": "field.add", "pointer": "/entities/customer/fields/earlier",
                                      "subject": {"kind": "field", "id": "earlier", "parents": [{"kind": "entity", "id": "customer"}]},
                                      "params": {"definition": {"id": "earlier", "type": "string"}}})
        definition = entity("customer", ("earlier", "string"), ("review_note", "string"), ("customer_name", "string"))
        entity_add(backend, definition)
        self.assertEqual(self.hidden(eng, "Customer", "custom_review_note"), 0)
        self.quarantine(backend, definition)
        self.assertEqual(self.hidden(eng, "Customer", "custom_review_note"), 1)
        self.assertEqual(self.hidden(eng, "Customer", "custom_earlier"), 0, "a pre-existing custom field must stay visible")
        self.assertEqual(self.hidden(eng, "Customer", "customer_name"), 0, "a native field must never be hidden")
        self.assertEqual({r["field_name"] for r in eng.rows("Property Setter") if r["property"] == "hidden"}, {"custom_review_note"})
        entity_add(backend, definition)  # re-apply
        self.assertEqual(self.hidden(eng, "Customer", "custom_review_note"), 0)
        self.assertEqual(len([r for r in eng.rows("Custom Field") if r["fieldname"] == "custom_review_note"]), 1)

    def test_a_quarantine_with_nothing_journaled_changes_nothing(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        self.quarantine(backend, entity("customer", ("vat_number", "string")))
        self.assertEqual(eng.rows("Property Setter"), [])

    def test_public_api_rollback_hides_and_reapply_restores_the_added_field(self) -> None:
        from change_engine.adapter import ADAPTER_ID, ChangeEngineAdapter, SimulatedFrappeRuntime
        from change_engine.api.endpoints import FrappeDeploymentAdapter
        from change_engine.tests.test_bpl_008_blueprint_rollback import _apply, _ctx, _k

        FrappeDeploymentAdapter.reset_in_memory_state()
        self.addCleanup(FrappeDeploymentAdapter.reset_in_memory_state)
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True, offline_ddl_simulator=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        tenant = "t_alpha"
        prov = adapter.call("provision_site", _ctx(tenant), {"idempotencyKey": _k("prov_bpl031"),
                            "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
                            "blueprintId": "example-trading-001", "siteClass": "production", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        v1, v2, _bp = item_review_artifacts()
        for art, key in ((v1, "bpl031_v1"), (v2, "bpl031_v2")):
            res = _apply(adapter, tenant, art, key)
            self.assertTrue(res["ok"] and res["result"]["status"] == "applied", res)
        self.assertEqual(self.hidden(sim, "Item", "custom_review_note"), 0)
        rb = adapter.call("rollback", _ctx(tenant), {"idempotencyKey": _k("bpl031_rb"), "forwardArtifact": v2, "reason": "owner_request",
                                                     "approvals": {"rollbackApproved": "01J00000000000000000000021"}})
        self.assertTrue(rb["ok"] and rb["result"]["status"] == "applied", rb)
        self.assertEqual(self.hidden(sim, "Item", "custom_review_note"), 1, "the rolled-back field must be hidden")
        self.assertEqual(self.hidden(sim, "Customer", "custom_vat_number"), 0, "fields of the still-applied version stay visible")
        again = _apply(adapter, tenant, v2, "bpl031_v2_again")
        self.assertTrue(again["ok"] and again["result"]["status"] == "applied", again)
        self.assertEqual(self.hidden(sim, "Item", "custom_review_note"), 0, "re-apply must restore the field")


class TestFixtureReadBack(unittest.TestCase):
    """The offline twin of bench test_05: apply every fixture entity, then read the engine back."""

    @staticmethod
    def apply_fixture(eng: CaseInsensitiveEngine) -> dict:
        bp = apply_ready(load_fixture())  # Q-603: no new unique or indexed field on a built-in type
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
