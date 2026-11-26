"""BPL-043: an unmapped `entity.add` never creates a custom type whose fields carry `unique` or `indexed` (Q-603).

A gated unmapped `entity.add` used to insert a custom type with `unique` and `search_index` set, which is constraint DDL
outside the guarded DDL gate. It is refused now, with or without a gate approval, at execute, in `_ensure_doctype_exists`
and in `check_ready`, with the side-effect-free `plan_rejected` / `unique_or_index` the BPL-031 path raises. Offline, on the
simulated engine. Synthetic data only; the checks read the error code and details, never message text.
"""
from __future__ import annotations

import unittest

from change_engine.adapter import ADAPTER_ID, ChangeEngineAdapter, FrappeBackendError
from change_engine.tests import test_bpl_027_fixture_real_adapter as bpl027
from change_engine.tests.test_bpl_031_entity_add_existing_doctype import (
    TENANT,
    backend_for,
    doctype_names,
    engine,
    entity,
    entity_add,
    setUpModule,  # noqa: F401  (starts the test environment patch)
    tearDownModule,  # noqa: F401
    written_state,
)
from change_engine.tests.test_bpl_041_check_ready_refusals import VALID, entity_step, no_writes, site_state

FLAGS = ("unique", "indexed")


def constrained(flag: str, entity_id: str = "vendor_ref") -> dict:
    definition = entity(entity_id, ("vendor_code", "string"), ("note", "string"))
    definition["fields"][0][flag] = True
    return definition


def is_plain_refusal(test: unittest.TestCase, err: FrappeBackendError) -> None:
    test.assertEqual((err.code, err.details.get("reasonCode")), ("plan_rejected", "unique_or_index"))
    test.assertTrue(err.side_effect_free)
    test.assertNotIn("frappe", repr((err.code, err.details)).lower())  # the engine is invisible (ADR-0016)
    test.assertNotIn("erpnext", repr((err.code, err.details)).lower())


class TestExecuteRefusesConstraintsOnAnUnmappedEntity(unittest.TestCase):
    def test_unique_and_indexed_are_each_refused_with_nothing_written(self) -> None:
        for flag in FLAGS:  # no subTest: pytest without a plugin does not report a failing one
            eng = engine()
            types, before = doctype_names(eng), site_state(eng)
            with self.assertRaises(FrappeBackendError) as err:
                entity_add(backend_for(eng), constrained(flag))
            is_plain_refusal(self, err.exception)
            self.assertEqual(doctype_names(eng), types, f"{flag}: no DocType row")
            self.assertEqual(site_state(eng), before, f"{flag}: no row, no DDL, nothing")

    def test_a_constraint_on_a_second_field_is_refused_too(self) -> None:
        definition = entity("vendor_ref", ("code", "string"), ("note", "string"))
        definition["fields"][1]["indexed"] = True
        eng = engine()
        before = site_state(eng)
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), definition)
        is_plain_refusal(self, err.exception)
        self.assertEqual(site_state(eng), before)

    def test_a_type_the_adapter_already_made_is_refused_too(self) -> None:
        eng = engine()
        entity_add(backend_for(eng), entity("vendor_ref", ("vendor_code", "string")))
        before = site_state(eng)
        for flag in FLAGS:
            with self.assertRaises(FrappeBackendError) as err:
                entity_add(backend_for(eng), constrained(flag))
            is_plain_refusal(self, err.exception)
        self.assertEqual(site_state(eng), before)

    def test_a_false_flag_is_not_a_constraint(self) -> None:
        definition = entity("vendor_ref", ("vendor_code", "string"))
        definition["fields"][0].update(unique=False, indexed=0)
        eng = engine()
        entity_add(backend_for(eng), definition)
        self.assertIn("Vendor Ref", doctype_names(eng))

    def test_a_clean_unmapped_entity_still_applies(self) -> None:
        eng = engine()
        entity_add(backend_for(eng), entity("payment", ("amount", "money"), ("reference", "string")))
        row = eng.db.get_value("DocType", "Payment", ["custom", "module"])
        self.assertEqual((int(row[0]), row[1]), (1, "Custom"))

    def test_a_constraint_on_a_mapped_entity_keeps_its_own_refusal(self) -> None:
        definition = entity("customer", ("review_code", "string"))
        definition["fields"][0]["unique"] = True
        eng = engine()
        with self.assertRaises(FrappeBackendError) as err:
            entity_add(backend_for(eng), definition)
        is_plain_refusal(self, err.exception)


class TestEnsureDoctypeExistsRefusesConstraints(unittest.TestCase):
    """Defence in depth: the helper refuses on its own, before `get_doc` or an insert."""

    def test_a_constrained_definition_is_refused_before_get_doc(self) -> None:
        for flag in FLAGS:
            eng = engine()
            backend, before = backend_for(eng), site_state(eng)
            with no_writes(self, eng), self.assertRaises(FrappeBackendError) as err:
                backend._ensure_doctype_exists(eng, "Vendor Ref", constrained(flag))
            is_plain_refusal(self, err.exception)
            self.assertEqual(site_state(eng), before)

    def test_an_empty_or_clean_definition_is_unaffected(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        backend._ensure_doctype_exists(eng, "Vendor Ref", {})
        backend._ensure_doctype_exists(eng, "Payment", entity("payment", ("amount", "money")))
        self.assertTrue({"Vendor Ref", "Payment"} <= doctype_names(eng))


class TestCheckReadyRefusesConstraints(unittest.TestCase):
    def test_a_plan_with_such_a_second_step_is_refused_up_front_and_writes_nothing(self) -> None:
        for flag in FLAGS:
            eng = engine()
            with no_writes(self, eng), self.assertRaises(FrappeBackendError) as err:
                backend_for(eng).check_ready(TENANT, [entity_step(1, VALID), entity_step(2, constrained(flag))])
            is_plain_refusal(self, err.exception)

    def test_an_earlier_step_that_makes_the_type_does_not_launder_the_constraint(self) -> None:
        plain = entity("vendor_ref", ("vendor_code", "string"))
        for flag in FLAGS:
            eng = engine()
            with no_writes(self, eng), self.assertRaises(FrappeBackendError) as err:
                backend_for(eng).check_ready(TENANT, [entity_step(1, plain), entity_step(2, constrained(flag))])
            is_plain_refusal(self, err.exception)

    def test_a_clean_unmapped_plan_still_passes(self) -> None:
        eng = engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, [entity_step(1, VALID), entity_step(2, entity("payment", ("amount", "money")))])


class TestAppliedThroughTheEngine(unittest.TestCase):
    """Step 2 of the plan is the constrained unmapped entity; step 1 is valid and must not run."""

    def apply(self, eng, flag: str, approvals: dict) -> tuple[dict, list[str], tuple]:
        backend = backend_for(eng)
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)
        target = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
        res = adapter.call("provision_site", bpl027.ctx(), {"idempotencyKey": "idemp_bpl043_prov", "engineTarget": target,
                           "blueprintId": "bp-offline", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(res["ok"], res)
        before = written_state(eng)
        steps = [{**entity_step(i, d), "phase": 4, "impact": "data_shape", "ddlImpact": "additive", "reversible": True,
                  "subject": {"kind": "entity", "id": d["id"], "parents": []}, "sourceOps": [f"/entities/{d['id']}"]}
                 for i, d in enumerate([VALID, constrained(flag)], start=1)]
        art = bpl027.seal({**bpl027.TestBpl027Offline._two_warehouse_artifact(target), "steps": steps})
        ran: list[str] = []
        real = backend.execute_step
        backend.execute_step = lambda tenant_id, step: (ran.append(step["kind"]), real(tenant_id, step))[1]
        plan = adapter.call("plan", bpl027.ctx(), {"artifact": art})
        self.assertTrue(plan["ok"], plan)
        out = adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl043_apply", "artifact": art,
                                                   "planToken": plan["result"]["planToken"], "approvals": approvals})
        return out, ran, before

    def test_refused_with_the_gate_approval_as_failed_clean_with_no_step_run(self) -> None:
        approvals = {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011"}
        for flag in FLAGS:
            eng = engine()
            out, ran, before = self.apply(eng, flag, approvals)
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["result"]["status"], "failed_clean", (flag, out))
            self.assertEqual(out["result"]["error"]["code"], "plan_rejected", (flag, out))
            self.assertEqual(out["result"]["error"]["stage"], "prepare", "refused by the readiness check, before any step")
            self.assertEqual(ran, [], f"{flag}: no step may run before the refusal")
            self.assertEqual(written_state(eng), before)
            self.assertNotIn("Vendor Ref", doctype_names(eng))

    def test_refused_without_the_gate_approval_and_nothing_is_written(self) -> None:
        for flag in FLAGS:
            eng = engine()
            out, ran, before = self.apply(eng, flag, {"changeApproved": "01J00000000000000000000010"})
            # The DDL gate already stops an ungated apply (the backend never sees the approval); this pins that no
            # path applies the constrained entity, and the backend-level tests above refuse it with no approval at all.
            self.assertEqual((out["ok"], out["result"]["status"]), (True, "rejected"), f"{flag}: {out}")
            self.assertEqual(out["result"]["error"]["code"], "approval_missing")
            self.assertEqual(ran, [], f"{flag}: no step may run")
            self.assertEqual(written_state(eng), before)
            self.assertNotIn("Vendor Ref", doctype_names(eng))


if __name__ == "__main__":
    unittest.main()
