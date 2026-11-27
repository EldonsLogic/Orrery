"""BPL-044 (#310 re-review N2): the fields of a type the adapter made are DocField rows, not Custom Field rows, so the
before-step read of a later step that touches one must read both.

Offline, on the case-insensitive simulated engine. The shared simulator does not answer `tabDocField` reads, so this
file answers them from the document type definitions the simulator holds. Whether a real bench stores and returns the
rows the same way is UNVERIFIED here. Synthetic data only.
"""
from __future__ import annotations

import unittest

from change_engine.adapter import FrappeBackendError
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine
from change_engine.tests.test_bpl_031_entity_add_existing_doctype import (
    TENANT,
    backend_for,
    custom_fields,
    engine,
    entity,
    entity_add,
    field_add_step,
    setUpModule,  # noqa: F401  (starts the test environment patch)
    tearDownModule,  # noqa: F401
)

MADE = "Vendor Ref"  # the adapter-made type of the unmapped entity vendor_ref


def with_docfields(eng: CaseInsensitiveEngine) -> CaseInsensitiveEngine:
    """Answer `tabDocField` reads like the engine: one row per field a document type definition declares."""
    real_sql = eng.db.sql

    def sql(query, params=None, *args, **kwargs):
        if "`TABDOCFIELD`" in str(query).upper():
            parent, fieldname = params
            fields = eng.current_site_db().doctype_meta.get(parent, {}).get("fields", [])
            return [(f["fieldname"],) for f in fields if f["fieldname"].casefold() == fieldname.casefold()]
        return real_sql(query, params, *args, **kwargs)

    eng.db.sql = sql
    return eng


def fail_reads_of(eng: CaseInsensitiveEngine, table: str) -> None:
    real_sql = eng.db.sql

    def sql(query, *args, **kwargs):
        if f"`{table.upper()}`" in str(query).upper():
            raise RuntimeError("database unavailable")
        return real_sql(query, *args, **kwargs)

    eng.db.sql = sql


def made_engine(*fields: tuple[str, str]) -> CaseInsensitiveEngine:
    """A site on which an earlier entity.add made Vendor Ref, so its fields are DocFields."""
    eng = with_docfields(engine())
    entity_add(backend_for(eng), entity("vendor_ref", *(fields or (("code", "string"),))))
    return eng


def definition(field_id: str, **extra) -> dict:
    return {"id": field_id, "type": "string", "labels": {"en": field_id, "ar": field_id}, **extra}


def relation_add_step(entity_id: str, defn: dict) -> dict:
    return {"seq": 1, "kind": "relation.add", "pointer": f"/entities/{entity_id}/relations/{defn['id']}",
            "subject": {"kind": "relation", "id": defn["id"], "parents": [{"kind": "entity", "id": entity_id}]},
            "params": {"definition": defn}}


def touch_step(kind: str, entity_id: str, field_id: str, **params) -> dict:
    return {"seq": 1, "kind": kind, "pointer": f"/entities/{entity_id}/fields/{field_id}",
            "subject": {"kind": "field", "id": field_id, "parents": [{"kind": "entity", "id": entity_id}]},
            "params": params}


def written(eng: CaseInsensitiveEngine) -> tuple:
    """What a step may change: field metadata, property setters, deployment journal, type definitions and DDL."""
    site = eng.current_site_db()
    return (eng.rows("Custom Field"), eng.rows("Property Setter"), eng.rows("Change Engine Audit"),
            repr(site.doctype_meta), repr(site.table_columns), list(site.ddl_statements))


def setters(eng: CaseInsensitiveEngine, doctype: str, fieldname: str) -> dict:
    return {r["property"]: int(r["value"]) for r in eng.rows("Property Setter")
            if r["doc_type"] == doctype and r["field_name"] == fieldname}


class TestDocFieldOfAnAdapterMadeType(unittest.TestCase):
    def assert_restored_in_place(self, eng: CaseInsensitiveEngine, step: dict, fieldname: str, reqd: int = 0) -> None:
        ddl = list(eng.current_site_db().ddl_statements)
        backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(setters(eng, MADE, fieldname), {"hidden": 0, "reqd": reqd, "read_only": 0})
        self.assertEqual(custom_fields(eng, MADE), set(), "a DocField must not get a Custom Field twin")
        self.assertEqual(eng.current_site_db().ddl_statements, ddl)

    def test_a_later_field_add_on_it_is_not_recovery_required(self) -> None:
        eng = made_engine()
        self.assert_restored_in_place(eng, field_add_step("vendor_ref", definition("code", required=True)),
                                      "custom_code", reqd=1)

    def test_a_later_relation_add_on_it_is_not_recovery_required(self) -> None:
        eng = made_engine(("owner", "link"))
        self.assert_restored_in_place(eng, relation_add_step("vendor_ref", {"id": "owner", "target": "customer"}),
                                      "custom_owner")

    def test_a_quarantined_one_is_restored_by_a_later_field_add(self) -> None:
        eng = made_engine()
        backend_for(eng).execute_step(TENANT, touch_step("field.quarantine", "vendor_ref", "code"))
        self.assertEqual(setters(eng, MADE, "custom_code")["hidden"], 1)
        self.assert_restored_in_place(eng, field_add_step("vendor_ref", definition("code")), "custom_code")

    def test_a_later_set_property_on_it_applies(self) -> None:
        eng = made_engine()
        backend_for(eng).execute_step(
            TENANT, touch_step("field.set_property", "vendor_ref", "code", property="/required", after=True))
        self.assertEqual(setters(eng, MADE, "custom_code"), {"reqd": 1})

    def test_a_unique_request_on_it_is_still_refused(self) -> None:
        eng = made_engine()
        before = written(eng)
        with self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, field_add_step("vendor_ref", definition("code", unique=True)))
        self.assertEqual((err.exception.code, err.exception.details.get("reasonCode")), ("plan_rejected", "unique_or_index"))
        self.assertEqual(written(eng), before)


class TestCustomFieldAsBefore(unittest.TestCase):
    def test_a_custom_field_on_a_built_in_type_is_restored(self) -> None:
        eng = with_docfields(engine())
        step = field_add_step("customer", definition("vat_number"))
        backend_for(eng).execute_step(TENANT, step)
        backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(custom_fields(eng, "Customer"), {"custom_vat_number"})
        self.assertEqual(setters(eng, "Customer", "custom_vat_number"), {"hidden": 0, "reqd": 0, "read_only": 0})

    def test_a_custom_field_on_an_adapter_made_type_is_added_then_restored(self) -> None:
        eng = made_engine()
        step = field_add_step("vendor_ref", definition("note"))
        backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(custom_fields(eng, MADE), {"custom_note"})
        self.assertEqual(eng.rows("Property Setter"), [], "a new field is created, not restored")
        backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(setters(eng, MADE, "custom_note"), {"hidden": 0, "reqd": 0, "read_only": 0})


class TestFailClosed(unittest.TestCase):
    def assert_stops(self, eng: CaseInsensitiveEngine, step: dict, code: str) -> None:
        before = written(eng)
        with self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(err.exception.code, code)
        self.assertFalse(err.exception.side_effect_free)
        self.assertEqual(written(eng), before)

    def test_a_custom_field_and_a_docfield_of_one_name_are_refused_as_ambiguous(self) -> None:
        eng = made_engine()
        eng.get_doc({"doctype": "Custom Field", "dt": MADE, "fieldname": "custom_code", "fieldtype": "Data"}).insert(
            ignore_permissions=True)
        self.assert_stops(eng, field_add_step("vendor_ref", definition("code")), "recovery_required")

    def test_a_docfield_on_a_type_the_adapter_did_not_make_stays_recovery_required(self) -> None:
        eng = with_docfields(engine())
        eng.add_field("Customer", "custom_native")
        eng.get_doc({"doctype": "Custom Field", "dt": "Customer", "fieldname": "custom_other", "fieldtype": "Data"}).insert(
            ignore_permissions=True)  # gives the simulated table its columns
        columns = eng.current_site_db().table_columns["tabCustomer"]
        columns.append(type(columns[-1])("custom_native", "varchar(140)"))
        self.assert_stops(eng, field_add_step("customer", definition("native")), "recovery_required")

    def test_a_docfield_without_its_column_is_a_divergence(self) -> None:
        eng = made_engine()
        site = eng.current_site_db()
        site.table_columns[f"tab{MADE}"] = [c for c in site.table_columns[f"tab{MADE}"] if c.name != "custom_code"]
        self.assert_stops(eng, field_add_step("vendor_ref", definition("code")), "recovery_required")

    def test_a_failed_docfield_read_is_never_taken_as_absent(self) -> None:
        for field_id in ("code", "brand_new"):  # a field the type holds, and one it does not
            with self.subTest(field=field_id):
                eng = made_engine()
                fail_reads_of(eng, "tabDocField")
                self.assert_stops(eng, field_add_step("vendor_ref", definition(field_id)), "engine_unavailable")

    def test_a_failed_custom_field_read_stays_engine_unavailable(self) -> None:
        eng = made_engine()
        fail_reads_of(eng, "tabCustom Field")
        self.assert_stops(eng, field_add_step("vendor_ref", definition("code")), "engine_unavailable")


if __name__ == "__main__":
    unittest.main()
