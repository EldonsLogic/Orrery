"""BPL-041: the BPL-031 refusals (`protected_subject`, `subject_missing`, `unique_or_index`) are found by `check_ready`.

A plan the backend would refuse at step N is refused before step 1 runs, with the same error type and reason code the
execute path raises, so no earlier step has written (contract 5.6.1). The execute-time checks stay as a second line.
The REQUIRE flag of the bench test_05 (BPL-027) is tested here too. Offline, on the simulated engine. Synthetic data only.
"""
from __future__ import annotations

import contextlib
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
    seed_constraint,
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


def site_state(eng) -> str:
    """Everything the simulated site holds (rows, schema, DDL log, singles, locks, queues), as one comparable string."""
    return repr({k: v for k, v in sorted(vars(eng.current_site_db()).items()) if k != "runtime"})


@contextlib.contextmanager
def no_writes(test: unittest.TestCase, eng):
    """Fails the test on ANY write while it runs: a document or DocType insert (get_doc), set_value, commit, DDL helper, or
    a db.sql that is not a read; and when the whole site state differs afterwards (BPL-041 review round 1, R4)."""
    calls: list[str] = []
    before = site_state(eng)

    def spy(name: str, target, owner):
        real = getattr(target, name)
        setattr(owner, name, lambda *a, **kw: (calls.append(f"{name}{a[:1]}"), real(*a, **kw))[1])

    for name in ("commit", "sql_ddl", "set_value"):
        if hasattr(eng.db, name):
            spy(name, eng.db, eng.db)
    spy("get_doc", eng, eng)
    real_sql = eng.db.sql

    def sql(query, *a, **kw):
        if str(query).lstrip().upper().split(" ", 1)[0] not in ("SELECT", "SHOW"):
            calls.append(f"sql {str(query)[:40]}")
        return real_sql(query, *a, **kw)

    eng.db.sql = sql
    try:
        yield
    finally:
        for owner in (eng.db, eng):
            for name in ("commit", "sql_ddl", "set_value", "get_doc", "sql"):
                owner.__dict__.pop(name, None)
    test.assertEqual(calls, [], "check_ready must not write")
    test.assertEqual(site_state(eng), before, "check_ready is read-only")


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
                with no_writes(self, eng):
                    got = self.refusal(backend_for(eng), [entity_step(1, VALID), step])
                self.assertEqual(got.details.get("reasonCode"), reason, step)

    def test_a_clean_plan_passes_the_check(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        owner = {"id": "owner", "target": "customer"}
        item = entity("item", ("item_code", "string"))
        item["fields"][0]["unique"] = True  # Item.item_code is native and unique: nothing is added, nothing is dropped
        plan = [entity_step(1, VALID), entity_step(2, entity("payment", ("amount", "money"))), entity_step(3, item),
                field_add_step("customer", {"id": "note", "type": "string"}) | {"seq": 4}, relation_step(5, "customer", owner)]
        with no_writes(self, eng):
            backend.check_ready(TENANT, plan)
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


def field_step(seq: int, entity_id: str, definition: dict) -> dict:
    return field_add_step(entity_id, definition) | {"seq": seq}


class TestEarlierStepsOfTheSamePlan(unittest.TestCase):
    """Review round 1, R1 and R2: each step is judged against the engine plus what the steps before it will create."""

    def execute_all(self, eng, plan: list[dict]) -> None:
        backend = backend_for(eng)
        for step in plan:
            backend.execute_step(TENANT, step)

    def assert_refused_up_front_as_execute_does(self, maker, plan: list[dict], reason: str) -> None:
        eng = maker()
        with no_writes(self, eng):
            with self.assertRaises(FrappeBackendError) as err:
                backend_for(eng).check_ready(TENANT, plan)
        self.assertEqual((err.exception.code, err.exception.details.get("reasonCode")), ("plan_rejected", reason))
        self.assertTrue(err.exception.side_effect_free)
        with self.assertRaises(FrappeBackendError) as ran:  # execute really does refuse this plan, after step 1 has written
            self.execute_all(maker(), plan)
        self.assertEqual((ran.exception.code, ran.exception.details.get("reasonCode")), ("plan_rejected", reason))

    def test_an_index_asked_of_a_field_an_earlier_step_adds_without_one_is_refused_up_front(self) -> None:
        plan = [field_step(1, "customer", {"id": "note", "type": "string"}),
                relation_step(2, "customer", {"id": "note", "target": "customer", "indexed": True})]
        self.assert_refused_up_front_as_execute_does(engine, plan, "unique_or_index")

    def test_a_unique_asked_of_a_field_an_earlier_entity_add_creates_without_one_is_refused_up_front(self) -> None:
        plan = [entity_step(1, entity("customer", ("review_code", "string"))),
                field_step(2, "customer", {"id": "review_code", "type": "string", "unique": True})]
        self.assert_refused_up_front_as_execute_does(engine, plan, "unique_or_index")

    def test_a_field_asked_for_twice_without_a_constraint_passes_and_runs(self) -> None:
        plan = [field_step(1, "customer", {"id": "note", "type": "string"}),
                relation_step(2, "customer", {"id": "note", "target": "customer"}),
                entity_step(3, entity("customer", ("note", "string")))]
        eng = engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, plan)
        self.execute_all(eng, plan)

    def test_an_entity_add_that_creates_a_type_lets_a_later_step_use_it(self) -> None:
        plan = [entity_step(1, entity("purchase_order_item", ("note", "string"))),
                entity_step(2, entity("purchase_order_line", ("line_note", "string")))]
        eng = missing_engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, plan)
        self.execute_all(eng, plan)  # the plan the check lets through runs to the end
        self.assertIn("custom_line_note", {r["fieldname"] for r in eng.rows("Custom Field")})

    def test_a_field_add_that_creates_a_type_lets_a_later_entity_add_use_it(self) -> None:
        plan = [field_step(1, "purchase_order_item", {"id": "note", "type": "string"}),
                entity_step(2, entity("purchase_order_line", ("line_note", "string")))]
        eng = missing_engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, plan)
        self.execute_all(eng, plan)

    def test_a_type_created_after_the_step_that_needs_it_does_not_help(self) -> None:
        plan = [entity_step(1, entity("purchase_order_line", ("line_note", "string"))),
                entity_step(2, entity("purchase_order_item", ("note", "string")))]
        self.assert_refused_up_front_as_execute_does(missing_engine, plan, "subject_missing")

    def test_an_entity_add_of_another_type_does_not_help(self) -> None:
        plan = [entity_step(1, entity("payment", ("amount", "money"))),
                entity_step(2, entity("purchase_order_line", ("line_note", "string")))]
        self.assert_refused_up_front_as_execute_does(missing_engine, plan, "subject_missing")

    def test_fields_of_one_entity_add_are_judged_against_the_state_before_that_step(self) -> None:
        """Re-review N1: `note` and `custom_note` in one entity.add both become new fields (custom_note and
        custom_custom_note), because execute judges each against the metadata before the step; a later unique on
        custom_custom_note must then be refused up front, not after step 1 has written."""
        plan = [entity_step(1, entity("customer", ("note", "string"), ("custom_note", "string"))),
                field_step(2, "customer", {"id": "custom_note", "type": "string", "unique": True})]
        self.assert_refused_up_front_as_execute_does(engine, plan, "unique_or_index")

    def test_a_unique_field_in_a_type_an_earlier_entity_add_creates_is_refused(self) -> None:
        """BPL-043: an adapter-made type never carries a constraint, so a plan that creates a unique field in a new custom
        type is refused up front (the earlier step used to be projected as creating it unique)."""
        made = entity("vendor_ref", ("code", "string"))
        made["fields"][0]["unique"] = True
        plan = [entity_step(1, made), field_step(2, "vendor_ref", {"id": "code", "type": "string", "unique": True})]
        self.assert_refused_up_front_as_execute_does(engine, plan, "unique_or_index")


class TestConstraintOnAFieldNoEngineFieldHolds(unittest.TestCase):
    """Review round 3, M1: unique or indexed asked of a field no existing engine field holds is refused before any write.

    The field would be added without its constraint (Q-603), so readiness refuses it up front instead of letting step 1
    write and the DDL gate fail step 2 as engine_unavailable. The execute path refuses it too, before its first write."""

    def assert_refused(self, eng, steps: list[dict]) -> None:
        with no_writes(self, eng):
            with self.assertRaises(FrappeBackendError) as err:
                backend_for(eng).check_ready(TENANT, steps)
        self.assertEqual((err.exception.code, err.exception.details.get("reasonCode")), ("plan_rejected", "unique_or_index"))
        self.assertTrue(err.exception.side_effect_free)

    def assert_execute_refuses_without_writing(self, eng, step: dict) -> None:
        before = site_state(eng)
        with self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, step)
        self.assertEqual((err.exception.code, err.exception.details.get("reasonCode")), ("plan_rejected", "unique_or_index"))
        self.assertTrue(err.exception.side_effect_free)
        self.assertEqual(site_state(eng), before, "execute must refuse before its first write")

    def test_the_reviewers_two_step_probe_is_refused_at_readiness_with_nothing_written(self) -> None:
        plan = [field_step(1, "customer", {"id": "a", "type": "string"}),
                relation_step(2, "customer", {"id": "owner", "target": "customer", "indexed": True})]
        self.assert_refused(engine(), plan)

    def test_a_unique_field_add_on_a_missing_table_is_refused(self) -> None:
        step = field_step(1, "purchase_order_line", {"id": "code", "type": "string", "unique": True})
        self.assert_refused(missing_engine(), [step])
        self.assert_execute_refuses_without_writing(missing_engine(), step)

    def test_an_indexed_relation_add_is_refused(self) -> None:
        step = relation_step(1, "customer", {"id": "owner", "target": "customer", "indexed": True})
        self.assert_refused(engine(), [step])
        self.assert_execute_refuses_without_writing(engine(), step)

    def test_a_unique_field_add_on_an_existing_table_is_refused_on_both_paths(self) -> None:
        step = field_step(1, "customer", {"id": "fresh_code", "type": "string", "unique": True})
        self.assert_refused(engine(), [step])
        self.assert_execute_refuses_without_writing(engine(), step)

    def test_a_truthy_non_bool_value_counts_as_asking_for_the_constraint(self) -> None:
        for prop in ("unique", "indexed"):
            step = field_step(1, "customer", {"id": "fresh_code", "type": "string", prop: "1"})
            self.assert_refused(engine(), [step])
            self.assert_execute_refuses_without_writing(engine(), step)

    def test_a_falsy_constraint_on_a_new_field_still_passes_and_runs(self) -> None:
        step = field_step(1, "customer", {"id": "fresh_note", "type": "string", "unique": False, "indexed": 0})
        eng = engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, [step])
        backend_for(eng).execute_step(TENANT, step)

    def test_a_held_field_that_already_carries_the_constraint_keeps_its_behaviour(self) -> None:
        eng = held_engine()
        seed_constraint(eng, "Customer", "custom_review_code", unique=1)
        step = field_step(1, "customer", {"id": "review_code", "type": "string", "unique": True, "indexed": True})
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, [step])
        backend_for(eng).execute_step(TENANT, step)


class TestUnsupportedTypeAndMalformedSteps(unittest.TestCase):
    def test_a_field_type_the_adapter_does_not_know_is_refused_with_nothing_written(self) -> None:
        step = entity_step(2, entity("customer", ("vat_number", "no_such_type")))
        eng = engine()
        with no_writes(self, eng):
            with self.assertRaises(FrappeBackendError) as err:
                backend_for(eng).check_ready(TENANT, [entity_step(1, VALID), step])
        self.assertEqual((err.exception.code, err.exception.details.get("reasonCode")), ("plan_rejected", "unsupported_value_type"))
        self.assertTrue(err.exception.side_effect_free)
        with self.assertRaises(FrappeBackendError) as ran:
            backend_for(engine()).execute_step(TENANT, step)
        self.assertEqual(ran.exception.details.get("reasonCode"), "unsupported_value_type")

    def test_a_malformed_step_is_a_side_effect_free_invalid_request(self) -> None:
        good = field_add_step("customer", {"id": "note", "type": "string"})
        malformed = {
            "not a step": "text",
            "subject not a dict": entity_step(1, VALID) | {"subject": ["customer"]},
            "params not a dict": entity_step(1, VALID) | {"params": "x"},
            "definition not a dict": entity_step(1, VALID) | {"params": {"definition": ["customer"]}},
            "fields not a list": entity_step(1, VALID) | {"params": {"definition": {"id": "customer", "fields": 5}}},
            "fields not dicts": entity_step(1, VALID) | {"params": {"definition": {"id": "customer", "fields": ["a"]}}},
            "parents not a list": good | {"subject": {"kind": "field", "id": "note", "parents": "customer"}},
            "parent not a dict": good | {"subject": {"kind": "field", "id": "note", "parents": ["customer"]}},
            "parent without id": good | {"subject": {"kind": "field", "id": "note", "parents": [{"kind": "entity"}]}},
        }
        for label, step in malformed.items():
            eng = engine()
            with no_writes(self, eng):
                with self.assertRaises(FrappeBackendError, msg=label) as err:
                    backend_for(eng).check_ready(TENANT, [entity_step(1, VALID), step])
            self.assertEqual(err.exception.code, "invalid_request", label)
            self.assertTrue(err.exception.side_effect_free, label)
            self.assertTrue(err.exception.details.get("fields"), label)

    def test_a_step_without_a_subject_or_params_is_not_malformed(self) -> None:
        eng = engine()
        backend_for(eng).check_ready(TENANT, [{"seq": 1, "kind": "field.add", "pointer": "/entities/customer/fields/note"}])


class TestRequireFlagOfTheBenchTest(unittest.TestCase):
    """BPL-041: REQUIRE_BPL027_LIVE=1 (to be set by real-bench CI, slice 2) turns test_05's skip into a failure."""

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

    def test_a_missing_prerequisite_fails_with_the_flag_and_skips_without_it(self) -> None:
        """Review round 1, R3: need() skipped the rest of the class when an earlier step had not run, even with the flag."""
        try:
            bpl027.missing_prerequisite({bpl027.REQUIRE_LIVE_ENV: "1"}, {}, "plan")
        except unittest.SkipTest:  # SkipTest is not an AssertionError: without this catch a skip would pass for a failure
            self.fail("with the flag a missing prerequisite must fail, not skip")
        except AssertionError:
            pass
        else:
            self.fail("with the flag a missing prerequisite must raise")
        with self.assertRaises(unittest.SkipTest):
            bpl027.missing_prerequisite({}, {}, "plan")
        with self.assertRaises(unittest.SkipTest):
            bpl027.missing_prerequisite({bpl027.REQUIRE_LIVE_ENV: "true"}, {}, "plan")
        for env in ({}, {bpl027.REQUIRE_LIVE_ENV: "1"}):
            bpl027.missing_prerequisite(env, {"plan": 1}, "plan")  # a reached prerequisite is neither

    def test_need_uses_the_environment(self) -> None:
        stub = unittest.TestCase()
        stub.state = {}
        with mock.patch.dict(bpl027.os.environ, {bpl027.REQUIRE_LIVE_ENV: "1"}):
            try:
                bpl027.TestBpl027FixtureRealAdapter.need(stub, "plan")
            except unittest.SkipTest:
                self.fail("with the flag need() must fail, not skip")
            except AssertionError:
                pass
            else:
                self.fail("with the flag need() must raise")
        with mock.patch.dict(bpl027.os.environ, {}, clear=False):
            bpl027.os.environ.pop(bpl027.REQUIRE_LIVE_ENV, None)
            with self.assertRaises(unittest.SkipTest):
                bpl027.TestBpl027FixtureRealAdapter.need(stub, "plan")


if __name__ == "__main__":
    unittest.main()
