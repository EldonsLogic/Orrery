"""BPL-031 review fixes (PR #302): protected and reserved entities are refused by the backend itself, before any write.

Offline, on the simulated engine. Synthetic data only. Refusals use the existing `protected_subject` reason and must not
name the engine or an engine document type.
"""
from __future__ import annotations

import unittest

from change_engine.adapter import FrappeBackendError
from change_engine.adapter.mapping import ENTITY_TO_DOCTYPE, PROTECTED_ENTITY_IDS, is_protected_entity
from change_engine.tests.test_bpl_031_entity_add_existing_doctype import (
    backend_for,
    engine,
    entity,
    entity_add,
    field_add_step,
    setUpModule,  # noqa: F401  (starts the test environment patch)
    tearDownModule,  # noqa: F401
)
from change_engine.tests.test_bpl_027_fixture_real_adapter import TENANT

PROTECTED = sorted(PROTECTED_ENTITY_IDS)  # the five protected entities, every one a mapped built-in type
RESERVED = ["change_engine_entity_field", "change_engine_audit", "change_engine_blueprint_state",
            "change_engine_element", "change_engine_event_outbox", "change_engine_event_subject"]


def seeded_engine():
    """The usual simulated site plus every protected built-in type, as on a real site."""
    eng = engine()
    for entity_id in PROTECTED:
        if not eng.db.exists("DocType", ENTITY_TO_DOCTYPE[entity_id]):
            eng.add_doctype(ENTITY_TO_DOCTYPE[entity_id], module="Core", custom=0)
    return eng


def written(eng) -> tuple:
    return (eng.rows("Custom Field"), eng.rows("Property Setter"), sorted(r["name"] for r in eng.rows("DocType")))


class TestProtectedEntityAdd(unittest.TestCase):
    def assert_refused(self, err: FrappeBackendError) -> None:
        self.assertEqual(err.details.get("reasonCode"), "protected_subject")
        self.assertTrue(err.side_effect_free)
        self.assertNotIn("frappe", str(err).lower())
        self.assertNotIn("erpnext", str(err).lower())

    def test_entity_add_on_a_protected_entity_is_refused_before_any_write(self) -> None:
        for entity_id in PROTECTED:
            with self.subTest(entity=entity_id):
                eng = seeded_engine()
                before = written(eng)
                with self.assertRaises(FrappeBackendError) as err:
                    entity_add(backend_for(eng), entity(entity_id, ("note", "string")))
                self.assert_refused(err.exception)
                self.assertEqual(written(eng), before)

    def test_field_add_on_a_protected_entity_is_refused_before_any_write(self) -> None:
        for entity_id in PROTECTED:
            with self.subTest(entity=entity_id):
                eng = seeded_engine()
                before = written(eng)
                step = field_add_step(entity_id, {"id": "note", "type": "string", "labels": {"en": "n", "ar": "n"}})
                with self.assertRaises(FrappeBackendError) as err:
                    backend_for(eng).execute_step(TENANT, step)
                self.assert_refused(err.exception)
                self.assertEqual(written(eng), before)

    def test_relation_add_on_a_protected_entity_is_refused_before_any_write(self) -> None:
        for entity_id in PROTECTED:
            with self.subTest(entity=entity_id):
                eng = seeded_engine()
                before = written(eng)
                step = {"seq": 1, "kind": "relation.add", "pointer": f"/entities/{entity_id}/relations/owner",
                        "subject": {"kind": "relation", "id": "owner", "parents": [{"kind": "entity", "id": entity_id}]},
                        "params": {"definition": {"id": "owner", "target": "customer"}}}
                with self.assertRaises(FrappeBackendError) as err:
                    backend_for(eng).execute_step(TENANT, step)
                self.assert_refused(err.exception)
                self.assertEqual(written(eng), before)


class TestReservedInternalNames(unittest.TestCase):
    def test_internal_table_names_are_protected_entities(self) -> None:
        for entity_id in RESERVED:
            with self.subTest(entity=entity_id):
                self.assertTrue(is_protected_entity(entity_id))

    def test_entity_add_with_an_internal_table_name_is_refused_and_leaves_the_table_alone(self) -> None:
        for entity_id in RESERVED:
            with self.subTest(entity=entity_id):
                eng = seeded_engine()
                before = written(eng)
                with self.assertRaises(FrappeBackendError) as err:
                    entity_add(backend_for(eng), entity(entity_id, ("note", "string")))
                self.assertEqual(err.exception.details.get("reasonCode"), "protected_subject")
                self.assertTrue(err.exception.side_effect_free)
                self.assertEqual(written(eng), before)

    def test_field_add_on_an_internal_table_name_is_refused(self) -> None:
        eng = seeded_engine()
        before = written(eng)
        step = field_add_step("change_engine_entity_field", {"id": "note", "type": "string", "labels": {"en": "n", "ar": "n"}})
        with self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, step)
        self.assertEqual(err.exception.details.get("reasonCode"), "protected_subject")
        self.assertEqual(written(eng), before)

    def test_an_ordinary_unmapped_entity_is_still_allowed(self) -> None:
        eng = seeded_engine()
        entity_add(backend_for(eng), entity("payment", ("amount", "money")))
        self.assertTrue(eng.db.exists("DocType", "Payment"))


if __name__ == "__main__":
    unittest.main()
