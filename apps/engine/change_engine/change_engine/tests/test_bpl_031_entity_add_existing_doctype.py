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


def field_add_step(entity_id: str, definition: dict) -> dict:
    return {"seq": 1, "kind": "field.add", "pointer": f"/entities/{entity_id}/fields/{definition['id']}",
            "subject": {"kind": "field", "id": definition["id"], "parents": [{"kind": "entity", "id": entity_id}]},
            "params": {"definition": definition}}


def set_property_step(entity_id: str, field_id: str, prop: str, before: object, after: object) -> dict:
    return {"seq": 1, "kind": "field.set_property", "pointer": f"/entities/{entity_id}/fields/{field_id}",
            "subject": {"kind": "field", "id": field_id, "parents": [{"kind": "entity", "id": entity_id}]},
            "params": {"property": prop, "before": before, "after": after}}


def has_grant(eng: CaseInsensitiveEngine, role_name: str, doctype: str) -> bool:
    """Does the role hold a level-0 read rule on the type at all (the grant applied rather than withheld)?"""
    return any(r.get("role") == role_name and r.get("parent") == doctype and int(r.get("permlevel") or 0) == 0
               and int(r.get("read") or 0) for r in eng.rows("Custom DocPerm"))


def permlevel(eng: CaseInsensitiveEngine, doctype: str, fieldname: str) -> int:
    return int(getattr(eng.get_meta(doctype).get_field(fieldname), "permlevel", 0) or 0)


def seed_constraint(eng: CaseInsensitiveEngine, doctype: str, fieldname: str, *, unique: int = 0, search_index: int = 0) -> None:
    """Set unique and search_index on a field the engine already holds, native or custom (read back through its meta)."""
    site = eng.current_site_db()
    custom = site.rows["tabCustom Field"].get(f"{doctype}-{fieldname}")
    target = custom if custom is not None else next(f for f in site.doctype_meta[doctype]["fields"] if f["fieldname"] == fieldname)
    target.update(unique=unique, search_index=search_index)


def written_state(eng: CaseInsensitiveEngine) -> tuple:
    return tuple(eng.rows(t) for t in ("Custom Field", "Property Setter", "Custom DocPerm", "Change Engine Entity Field"))


class TestRereviewMaskEveryRepresentation(unittest.TestCase):
    """Re-review finding 1 (high, security): a hidden field is masked on EVERY engine representation (the contract's native
    field, same-name or not, and the custom twin), or the grant is withheld."""

    def test_cost_price_is_masked_on_the_native_field_and_on_the_custom_twin(self) -> None:
        eng = engine()
        provision_cost_mask(eng)  # valuation_rate on level 1, as tenant provisioning leaves it
        backend = backend_for(eng)
        entity_add(backend, entity("item", ("cost_price", "money")))
        backend.execute_step(TENANT, role_step(role("sales_rep", "item", "cost_price")))
        self.assertTrue(can_read(eng, "bp-sales_rep", "Item", "item_name"), "the grant must apply, or this test proves nothing")
        self.assertFalse(can_read(eng, "bp-sales_rep", "Item", "valuation_rate"), "native cost field readable")
        self.assertGreaterEqual(permlevel(eng, "Item", "custom_cost_price"), 1)
        self.assertFalse(can_read(eng, "bp-sales_rep", "Item", "custom_cost_price"), "the custom twin leaks the cost")

    def test_vat_number_is_masked_on_tax_id_and_on_the_custom_twin(self) -> None:
        eng = engine()
        eng.add_field("Supplier", "tax_id", 1)  # the native field already sits on a protected level
        backend = backend_for(eng)
        entity_add(backend, entity("supplier", ("vat_number", "string")))
        backend.execute_step(TENANT, role_step(role("buyer", "supplier", "vat_number")))
        self.assertTrue(has_grant(eng, "bp-buyer", "Supplier"), "the grant must apply, or this test proves nothing")
        self.assertFalse(can_read(eng, "bp-buyer", "Supplier", "tax_id"))
        self.assertFalse(can_read(eng, "bp-buyer", "Supplier", "custom_vat_number"), "the custom twin leaks the VAT number")

    def test_vat_number_with_tax_id_on_level_zero_withholds_the_grant(self) -> None:
        eng = engine()
        eng.add_field("Supplier", "tax_id", 0)
        backend = backend_for(eng)
        entity_add(backend, entity("supplier", ("vat_number", "string")))
        backend.execute_step(TENANT, role_step(role("buyer", "supplier", "vat_number")))
        self.assertFalse(has_grant(eng, "bp-buyer", "Supplier"))
        self.assertFalse(can_read(eng, "bp-buyer", "Supplier", "tax_id"))
        self.assertFalse(can_read(eng, "bp-buyer", "Supplier", "custom_vat_number"))

    def test_a_same_name_native_field_on_level_zero_withholds_the_grant_even_with_a_custom_twin(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        backend.execute_step(TENANT, field_add_step("customer", {"id": "customer_name", "type": "string"}))  # makes the twin
        self.assertIn("custom_customer_name", custom_fields(eng, "Customer"))
        backend.execute_step(TENANT, role_step(role("clerk", "customer", "customer_name")))
        self.assertFalse(can_read(eng, "bp-clerk", "Customer", "customer_name"), "the native customer_name is readable")
        self.assertFalse(can_read(eng, "bp-clerk", "Customer", "custom_customer_name"))
        self.assertFalse(has_grant(eng, "bp-clerk", "Customer"), "the native field cannot be masked, so no grant")

    def test_a_same_name_native_field_on_a_protected_level_and_its_twin_are_both_masked(self) -> None:
        eng = engine()
        eng.make_property_setter({"doctype": "Customer", "fieldname": "customer_name", "property": "permlevel", "value": 1,
                                  "property_type": "Int"})
        backend = backend_for(eng)
        backend.execute_step(TENANT, field_add_step("customer", {"id": "customer_name", "type": "string"}))
        backend.execute_step(TENANT, role_step(role("clerk", "customer", "customer_name")))
        self.assertTrue(has_grant(eng, "bp-clerk", "Customer"), "the grant must apply, or this test proves nothing")
        self.assertFalse(can_read(eng, "bp-clerk", "Customer", "customer_name"))
        self.assertFalse(can_read(eng, "bp-clerk", "Customer", "custom_customer_name"))

    def test_a_hidden_field_with_no_engine_representation_withholds_the_grant(self) -> None:
        eng = engine()  # no custom field and no native field of that name
        backend_for(eng).execute_step(TENANT, role_step(role("sales_rep", "customer", "credit_limit")))
        self.assertFalse(has_grant(eng, "bp-sales_rep", "Customer"))


class TestRereviewExistingFieldConstraints(unittest.TestCase):
    """Re-review finding 2 (high): an existing field is never accepted without a unique or index constraint the definition
    asks for; a unique or index property change the backend cannot deploy is refused, never reported as applied."""

    def refused(self, step_or_definition: dict, backend: FrappeRuntimeBackend, *, add: bool = True) -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            if add:
                entity_add(backend, step_or_definition)
            else:
                backend.execute_step(TENANT, step_or_definition)
        self.assertEqual(err.exception.code, "plan_rejected")
        self.assertEqual(err.exception.details.get("reasonCode"), "unique_or_index")
        self.assertTrue(err.exception.side_effect_free)
        return err.exception

    def test_reapplying_a_constrained_entity_over_an_unconstrained_custom_field_is_refused(self) -> None:
        for key in ("unique", "indexed"):  # no subTest: pytest without a plugin does not report a failing one
            eng = engine()
            backend = backend_for(eng)
            definition = entity("customer", ("review_code", "string"))
            entity_add(backend, definition)
            before = written_state(eng)
            definition["fields"][0][key] = True
            self.refused(definition, backend)
            self.assertEqual(written_state(eng), before, key)

    def test_a_constrained_definition_over_a_native_field_that_is_not_constrained_is_refused(self) -> None:
        for key in ("unique", "indexed"):
            eng = engine()  # the simulated Customer.customer_name is neither unique nor indexed
            definition = entity("customer", ("customer_name", "string"))
            definition["fields"][0][key] = True
            self.refused(definition, backend_for(eng))
            self.assertEqual(written_state(eng), written_state(engine()), key)

    def test_an_existing_field_that_already_holds_the_constraint_is_accepted(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_code", "string"), ("customer_name", "string"), ("note_ref", "string"))
        entity_add(backend, entity("customer", ("review_code", "string"), ("note_ref", "string")))
        seed_constraint(eng, "Customer", "custom_review_code", unique=1)
        seed_constraint(eng, "Customer", "custom_note_ref", search_index=1)
        seed_constraint(eng, "Customer", "customer_name", search_index=1)
        definition["fields"][0]["unique"] = True
        definition["fields"][1]["indexed"] = True
        definition["fields"][2]["indexed"] = True
        before = written_state(eng)
        entity_add(backend, definition)
        self.assertEqual(written_state(eng), before)

    def test_a_unique_engine_field_satisfies_an_index_request(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_code", "string"))
        entity_add(backend, definition)
        seed_constraint(eng, "Customer", "custom_review_code", unique=1)
        definition["fields"][0]["indexed"] = True
        entity_add(backend, definition)  # a unique index is an index

    def test_item_code_is_refused_when_the_engine_does_not_report_it_unique(self) -> None:
        eng = engine()
        seed_constraint(eng, "Item", "item_code", unique=0)
        definition = entity("item", ("item_code", "string"))
        definition["fields"][0]["unique"] = True
        self.refused(definition, backend_for(eng))

    def test_field_add_over_an_existing_unconstrained_field_is_refused(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("customer", ("review_code", "string")))
        before = written_state(eng)
        step = field_add_step("customer", {"id": "review_code", "type": "string", "unique": True})
        self.refused(step, backend, add=False)
        self.assertEqual(written_state(eng), before)

    def test_set_property_unique_or_indexed_on_an_unconstrained_field_is_refused(self) -> None:
        for prop in ("/unique", "/indexed"):
            eng = engine()
            backend = backend_for(eng)
            entity_add(backend, entity("customer", ("review_code", "string")))
            before = written_state(eng)
            self.refused(set_property_step("customer", "review_code", prop, False, True), backend, add=False)
            self.assertEqual(written_state(eng), before, prop)

    def test_set_property_unique_on_a_native_field_without_a_twin_is_refused(self) -> None:
        eng = engine()
        self.refused(set_property_step("customer", "customer_name", "/unique", False, True), backend_for(eng), add=False)

    def test_set_property_that_the_engine_already_reflects_is_accepted_and_writes_nothing(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("customer", ("review_code", "string"), ("plain", "string")))
        seed_constraint(eng, "Customer", "custom_review_code", unique=1)
        before = written_state(eng)
        backend.execute_step(TENANT, set_property_step("customer", "review_code", "/unique", False, True))
        backend.execute_step(TENANT, set_property_step("customer", "review_code", "/indexed", False, True))  # unique implies index
        backend.execute_step(TENANT, set_property_step("customer", "plain", "/unique", True, False))
        self.assertEqual(written_state(eng), before)

    def test_set_property_that_would_remove_an_enforced_constraint_is_refused(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        entity_add(backend, entity("customer", ("review_code", "string")))
        seed_constraint(eng, "Customer", "custom_review_code", unique=1)
        self.refused(set_property_step("customer", "review_code", "/unique", True, False), backend, add=False)

    def test_public_api_set_property_unique_is_not_reported_applied(self) -> None:
        from change_engine.adapter import ADAPTER_ID, ChangeEngineAdapter, SimulatedFrappeRuntime
        from change_engine.api.endpoints import FrappeDeploymentAdapter
        from change_engine.tests.test_bpl_008_blueprint_rollback import _apply, _ctx, _k, _make_artifact

        FrappeDeploymentAdapter.reset_in_memory_state()
        self.addCleanup(FrappeDeploymentAdapter.reset_in_memory_state)
        sim = SimulatedFrappeRuntime()
        backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True, offline_ddl_simulator=True)
        adapter = ChangeEngineAdapter(test_hooks=True, frappe_backend=backend)
        tenant = "t_alpha"
        prov = adapter.call("provision_site", _ctx(tenant), {"idempotencyKey": _k("prov_bpl031_u"),
                            "engineTarget": {"adapter": ADAPTER_ID, "versionSet": "set-example"},
                            "blueprintId": "example-trading-001", "siteClass": "production", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        v1, _v2, _bp = item_review_artifacts()
        first = _apply(adapter, tenant, v1, "bpl031_u_v1")
        self.assertTrue(first["ok"] and first["result"]["status"] == "applied", first)
        pointer = "/entities/customer/fields/vat_number"

        def step(before: bool, after: bool) -> dict:
            return {"seq": 1, "phase": 6, "kind": "field.set_property", "pointer": pointer, "impact": "data_shape", "ddlImpact": "semantic",
                    "subject": {"kind": "field", "id": "vat_number", "parents": [{"kind": "entity", "id": "customer"}]},
                    "reversible": True, "params": {"property": "/unique", "before": before, "after": after},
                    "sourceOps": [pointer + "/unique"]}

        post = [{"id": "pc_001", "check": "exists", "pointer": pointer}]
        rev2 = {"hash": "sha256:" + ("2" * 64), "revision": 2}
        inverse = _make_artifact(bp_id="example-trading-001", kind="inverse", base=rev2, target=v1["blueprint"]["target"],
                                 steps=[step(True, False)], post_conditions=post, diff_hash="sha256:" + ("c" * 64))
        v2 = _make_artifact(bp_id="example-trading-001", kind="forward", base=v1["blueprint"]["target"], target=rev2,
                            steps=[step(False, True)], post_conditions=post, diff_hash="sha256:" + ("b" * 64), inverse=inverse)
        res = _apply(adapter, tenant, v2, "bpl031_u_v2")
        self.assertFalse(res["ok"] and res["result"]["status"] == "applied", "an unenforced unique property was reported applied")
        with backend._site_session(tenant):
            self.assertFalse(getattr(sim.get_meta("Customer").get_field("custom_vat_number"), "unique", 0))
        fields = adapter.store.get_site(tenant).config["entities"][0]["fields"]
        self.assertFalse(next(f for f in fields if f["id"] == "vat_number").get("unique"), "the exported config claims unique")


class TestRereviewJournalOwnership(unittest.TestCase):
    """Re-review finding 3 (medium): a journal row is intent (pending) until this adapter has created the field (created);
    only created rows are quarantined or restored, and a field that appears without our creation is never ours."""

    def hidden(self, eng: CaseInsensitiveEngine, fieldname: str) -> int:
        return int(getattr(eng.get_meta("Customer").get_field(fieldname), "hidden", 0) or 0)

    def failing_creation(self, backend: FrappeRuntimeBackend, definition: dict) -> None:
        with mock.patch.object(backend, "_apply_or_restore_custom_field", side_effect=RuntimeError("field creation failed")):
            with self.assertRaises(FrappeBackendError):
                entity_add(backend, definition)

    def test_the_row_is_pending_until_the_field_is_created(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_note", "string"))
        self.failing_creation(backend, definition)
        self.assertEqual({(r["fieldname"], r.get("status")) for r in eng.rows("Change Engine Entity Field")},
                         {("custom_review_note", "pending")})
        entity_add(backend, definition)
        self.assertEqual({(r["fieldname"], r.get("status")) for r in eng.rows("Change Engine Entity Field")},
                         {("custom_review_note", "created")})

    def test_an_independent_field_after_a_failed_creation_is_never_quarantined(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_note", "string"))
        self.failing_creation(backend, definition)  # the intent is journaled, the field is not created
        backend.execute_step(TENANT, field_add_step("customer", definition["fields"][0]))  # someone else creates it
        entity_add(backend, definition)  # the retry finds the field already there
        TestReviewFixesQuarantine().quarantine(backend, definition)
        self.assertEqual(self.hidden(eng, "custom_review_note"), 0, "the independently created field was hidden")
        self.assertEqual(eng.rows("Property Setter"), [])
        self.assertEqual([r for r in eng.rows("Change Engine Entity Field") if r.get("status") == "pending"], [],
                         "a stale pending row must not outlive the field that appeared without us")

    def test_a_field_created_independently_between_the_journal_and_our_creation_is_not_adopted(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_note", "string"))
        record = backend._record_entity_fields

        def record_then_race(*args, **kwargs):
            record(*args, **kwargs)
            backend.execute_step(TENANT, field_add_step("customer", definition["fields"][0]))

        with mock.patch.object(backend, "_record_entity_fields", side_effect=record_then_race):
            entity_add(backend, definition)
        TestReviewFixesQuarantine().quarantine(backend, definition)
        self.assertEqual(self.hidden(eng, "custom_review_note"), 0)

    def test_a_pending_row_is_not_restored_or_quarantined(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        definition = entity("customer", ("review_note", "string"))
        backend.execute_step(TENANT, field_add_step("customer", definition["fields"][0]))
        backend.execute_step(TENANT, {"seq": 1, "kind": "field.quarantine", "pointer": "/entities/customer/fields/review_note",
                                      "subject": {"kind": "field", "id": "review_note", "parents": [{"kind": "entity", "id": "customer"}]},
                                      "params": {}})
        eng.db.sql("CREATE TABLE IF NOT EXISTS `tabChange Engine Entity Field` (doctype VARCHAR(140), fieldname VARCHAR(140), status VARCHAR(16))")
        eng.db.sql("INSERT IGNORE INTO `tabChange Engine Entity Field` (doctype, fieldname, status) VALUES (%s, %s, 'pending')",
                   ("Customer", "custom_review_note"))
        self.assertEqual(self.hidden(eng, "custom_review_note"), 1)
        entity_add(backend, definition)  # a hidden field with only a pending row is not ours to restore
        self.assertEqual(self.hidden(eng, "custom_review_note"), 1)


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
