"""BPL-041: the BPL-031 refusals (`protected_subject`, `subject_missing`, `unique_or_index`) are found by `check_ready`.

A plan the backend would refuse at step N is refused before step 1 runs, with the same error type and reason code the
execute path raises, so no earlier step has written (contract 5.6.1). The execute-time checks stay as a second line.
The REQUIRE flag of the bench test_05 (BPL-027) is tested here too. Offline, on the simulated engine. Synthetic data only.
"""
from __future__ import annotations

import unittest
from unittest import mock

from change_engine.adapter import ADAPTER_ID, ChangeEngineAdapter, FrappeBackendError
from change_engine.adapter.mapping import PROTECTED_ENTITY_IDS
from change_engine.tests import test_bpl_027_fixture_real_adapter as bpl027
from change_engine.tests.test_bpl_031_entity_add_existing_doctype import (
    TENANT,
    backend_for,
    drop_doctype,
    engine,
    entity,
    entity_add,
    field_add_step,
    setUpModule,  # noqa: F401  (starts the test environment patch)
    tearDownModule,  # noqa: F401
    written_state,
)

VALID = entity("customer", ("vat_number", "string"))  # a clean first step: it would add custom_vat_number


def entity_step(seq: int, definition: dict) -> dict:
    return {"seq": seq, "kind": "entity.add", "pointer": f"/entities/{definition['id']}",
            "subject": {"kind": "entity", "id": definition["id"]}, "params": {"definition": definition}}


def relation_step(seq: int, entity_id: str, definition: dict) -> dict:
    return {"seq": seq, "kind": "relation.add", "pointer": f"/entities/{entity_id}/relations/{definition['id']}",
            "subject": {"kind": "relation", "id": definition["id"], "parents": [{"kind": "entity", "id": entity_id}]},
            "params": {"definition": definition}}


def unique_entity() -> dict:
    definition = entity("supplier", ("supplier_code", "string"))
    definition["fields"][0]["unique"] = True
    return definition


def clash_engine():
    """A site on which Legacy Thing is an engine type the adapter did not make, so an entity that derives that name clashes."""
    eng = engine()
    eng.add_doctype("Legacy Thing", module="Selling", custom=0)
    return eng


def held_engine():
    """A site on which an earlier apply already added Customer.custom_review_code, with no unique or index constraint."""
    eng = engine()
    entity_add(backend_for(eng), entity("customer", ("review_code", "string")))
    return eng


def missing_engine():
    eng = engine()
    drop_doctype(eng, "Purchase Order Item")
    return eng


PROTECTED_ID = sorted(PROTECTED_ENTITY_IDS)[0]


# reason -> (offending steps, the engine they are offending on); each list holds one step, and the same steps are refused
# when they run as step 2 of a plan.
OFFENDING = {
    "subject_missing": ([entity_step(2, entity("purchase_order_line", ("line_note", "string")))], missing_engine),
    "protected_subject": (
        [entity_step(2, entity("legacy_thing", ("note", "string"))),
         entity_step(2, entity(PROTECTED_ID, ("note", "string"))),
         field_add_step(PROTECTED_ID, {"id": "note", "type": "string"}) | {"seq": 2},
         relation_step(2, PROTECTED_ID, {"id": "owner", "target": "customer"})],
        clash_engine),
    "unique_or_index": ([entity_step(2, unique_entity()),
                         field_add_step("customer", {"id": "review_code", "type": "string", "unique": True}) | {"seq": 2}],
                        held_engine),
}


class TestCheckReadyRefusals(unittest.TestCase):
    def refusal(self, backend, steps: list[dict]) -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            backend.check_ready(TENANT, steps)
        self.assertEqual(err.exception.code, "plan_rejected")
        self.assertTrue(err.exception.side_effect_free)
        return err.exception

    def execute_refusal(self, eng, step: dict) -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, step)
        return err.exception

    def test_a_plan_with_an_offending_step_is_refused_with_the_reason_the_execute_path_gives(self) -> None:
        for reason, (steps, maker) in OFFENDING.items():
            for step in steps:
                eng = maker()
                got = self.refusal(backend_for(eng), [step])
                self.assertEqual(got.details.get("reasonCode"), reason, step)
                # the same step on the execute path: same error type, same reason
                ran = self.execute_refusal(maker(), step)
                self.assertEqual((ran.code, ran.details.get("reasonCode")), (got.code, got.details.get("reasonCode")), step)

    def test_an_offending_second_step_refuses_the_whole_plan_and_nothing_is_written(self) -> None:
        for reason, (steps, maker) in OFFENDING.items():
            for step in steps:
                eng = maker()
                before = written_state(eng)
                plan = [entity_step(1, VALID), step]
                got = self.refusal(backend_for(eng), plan)
                self.assertEqual(got.details.get("reasonCode"), reason, step)
                self.assertEqual(written_state(eng), before, "check_ready is read-only")

    def test_a_clean_plan_passes_the_check(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        owner = {"id": "owner", "target": "customer"}
        item = entity("item", ("item_code", "string"))
        item["fields"][0]["unique"] = True  # Item.item_code is native and unique: nothing is added, nothing is dropped
        plan = [entity_step(1, VALID), entity_step(2, entity("payment", ("amount", "money"))), entity_step(3, item),
                field_add_step("customer", {"id": "note", "type": "string"}) | {"seq": 4}, relation_step(5, "customer", owner)]
        before = written_state(eng)
        backend.check_ready(TENANT, plan)
        self.assertEqual(written_state(eng), before)
        for step in plan:  # and the plan really runs, so the check did not refuse something the execute path accepts
            backend.execute_step(TENANT, step)


class TestAppliedPlanIsRefusedBeforeAnyStepRuns(unittest.TestCase):
    """Through the engine: the second step is the offending one, the first is valid, and the first does not run."""

    def run_plan(self, eng, second: dict, approvals: dict) -> tuple[dict, list[str], tuple]:
        backend = backend_for(eng)
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)
        target = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
        res = adapter.call("provision_site", bpl027.ctx(), {"idempotencyKey": "idemp_bpl041_prov", "engineTarget": target,
                           "blueprintId": "bp-offline", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(res["ok"], res)
        before = written_state(eng)  # after the site is provisioned: provisioning itself writes
        steps = [{**entity_step(i, step["params"]["definition"]), "phase": 4, "impact": "data_shape", "ddlImpact": "additive",
                  "reversible": True, "subject": {"kind": "entity", "id": step["params"]["definition"]["id"], "parents": []},
                  "sourceOps": [step["pointer"]]} for i, step in enumerate([entity_step(1, VALID), second], start=1)]
        base = bpl027.TestBpl027Offline._two_warehouse_artifact(target)
        art = bpl027.seal({**base, "steps": steps})
        ran: list[str] = []
        real = backend.execute_step
        backend.execute_step = lambda tenant_id, step: (ran.append(step["kind"]), real(tenant_id, step))[1]
        plan = adapter.call("plan", bpl027.ctx(), {"artifact": art})
        self.assertTrue(plan["ok"], plan)
        out = adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl041_apply", "artifact": art,
                                                   "planToken": plan["result"]["planToken"], "approvals": approvals})
        self.assertTrue(out["ok"], out)
        return out["result"], ran, before

    def test_each_reason_fails_clean_with_no_step_run(self) -> None:
        approvals = {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011"}
        for reason, (steps, maker) in OFFENDING.items():
            second = steps[0]  # the entity.add the plan lets through (the engine's own state is what refuses it)
            eng = maker()
            out, ran, before = self.run_plan(eng, second, approvals)
            self.assertEqual(out["status"], "failed_clean", (reason, out))
            self.assertEqual(out["error"]["code"], "plan_rejected", (reason, out))
            self.assertEqual(ran, [], f"{reason}: no step may run before the refusal")
            self.assertEqual(written_state(eng), before)


class TestRequireFlagOfTheBenchTest(unittest.TestCase):
    """BPL-041: REQUIRE_BPL027_LIVE=1 (set by real-bench CI) turns test_05's skip into a failure."""

    def test_without_the_flag_a_missing_bench_skips(self) -> None:
        with mock.patch.object(bpl027, "BENCH_SITE", ""):
            self.assertIn("BPL027_BENCH_SITE", bpl027.live_skip_reason({}) or "")
            self.assertIsNone(bpl027.live_config_problem({}))

    def test_with_the_flag_the_class_is_not_skipped_and_a_missing_bench_is_a_failure(self) -> None:
        env = {bpl027.REQUIRE_LIVE_ENV: "1"}
        with mock.patch.object(bpl027, "BENCH_SITE", ""):
            self.assertIsNone(bpl027.live_skip_reason(env))
            self.assertIn("BPL027_BENCH_SITE", bpl027.live_config_problem(env) or "")

    def test_only_the_value_one_counts(self) -> None:
        with mock.patch.object(bpl027, "BENCH_SITE", ""):
            self.assertIsNotNone(bpl027.live_skip_reason({bpl027.REQUIRE_LIVE_ENV: "true"}))

    def test_the_flag_name_is_the_one_the_workflow_runner_sets(self) -> None:
        self.assertEqual(bpl027.REQUIRE_LIVE_ENV, "REQUIRE_BPL027_LIVE")


if __name__ == "__main__":
    unittest.main()
