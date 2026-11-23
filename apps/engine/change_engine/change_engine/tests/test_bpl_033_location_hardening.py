"""BPL-033 (PR #150 follow-ups), backend side: kind-aware locations, warehouse retry and disable, readiness check.

Fake engine only (no bench); the live read-back stays with the bench suite. Findings: Gemini review of PR #150 item 7
(`frappe_backend.py:605-658`) and the Codex review's open item `frappe_backend.py:619-648`. Synthetic data only.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from change_engine.adapter import FrappeBackendError, make_frappe_adapter

_ENV_PATCH = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})


def setUpModule():
    _ENV_PATCH.start()  # ERP-027: the offline DDL simulator is refused unless CHANGE_ENGINE_ENV is dev or test


def tearDownModule():
    _ENV_PATCH.stop()


TENANT = "t_bpl033"


class FakeDb:
    def __init__(self, engine: "FakeEngine") -> None:
        self.engine = engine
        self.commits = 0
        self.rollbacks = 0
        self.unreachable = False

    def sql(self, *args, **kwargs):
        if self.unreachable:
            raise OSError("database gone")
        return [(1,)]

    def exists(self, doctype, name):
        return any(w["name"] == name for w in self.engine.warehouses) if doctype == "Warehouse" else False

    def get_value(self, doctype, flt, field):
        assert doctype == "Warehouse"
        for w in self.engine.warehouses:
            if all(w.get(k) == v for k, v in flt.items()):
                return w["name"]
        return None

    def set_value(self, doctype, name, field, value):
        assert doctype == "Warehouse"
        next(w for w in self.engine.warehouses if w["name"] == name)[field] = value
        self.engine.writes.append(("set_value", name, field, value))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeEngine:
    """The slice of the Frappe module that location steps touch: Company, Warehouse, meta."""

    def __init__(self, companies=("Synthetic Co",)) -> None:
        self.companies = list(companies)
        self.warehouses: list[dict] = []
        self.writes: list[tuple] = []
        self.db = FakeDb(self)
        self.defaults = SimpleNamespace(get_global_default=lambda key: None)

    def get_meta(self, doctype):
        return SimpleNamespace(get_field=lambda name: SimpleNamespace(fieldname=name) if name == "company" else None)

    def get_all(self, doctype, **kwargs):
        return list(self.companies) if doctype == "Company" else []

    def get_doc(self, payload):
        engine = self

        class Doc:
            def insert(self, **kwargs):
                abbr = "".join(w[0] for w in payload["company"].split())
                engine.warehouses.append({"name": f"{payload['warehouse_name']} - {abbr}", "warehouse_name": payload["warehouse_name"],
                                          "company": payload["company"], "disabled": payload["disabled"]})
                engine.writes.append(("insert", payload["warehouse_name"]))

        return Doc()


def make_backend(engine: FakeEngine):
    backend = make_frappe_adapter(simulated=True).frappe_backend
    backend._frappe_factory = lambda: engine
    return backend


def loc_step(kind_step: str, loc_id: str, loc_kind: str | None, *, with_definition: bool = True) -> dict:
    params: dict = {}
    if with_definition:
        params["definition"] = {"id": loc_id, "labels": {"en": loc_id, "ar": loc_id}, **({"kind": loc_kind} if loc_kind else {})}
    return {"seq": 1, "kind": kind_step, "pointer": f"/locations/{loc_id}", "subject": {"kind": "location", "id": loc_id},
            "params": params}


class TestKindAwareLocations(unittest.TestCase):
    def test_branch_and_department_upsert_touch_no_warehouse_even_without_a_company(self) -> None:
        for kind in ("branch", "department"):
            engine = FakeEngine(companies=())  # a warehouse step would be refused here; a branch has no company need
            make_backend(engine).execute_step(TENANT, loc_step("location.upsert", "loc_x", kind))
            self.assertEqual(engine.writes, [], kind)
            self.assertEqual(engine.warehouses, [], kind)

    def test_an_unknown_location_kind_is_refused_before_any_write(self) -> None:
        engine = FakeEngine()
        for step in (loc_step("location.upsert", "loc_x", "annex"), loc_step("location.upsert", "loc_x", None),
                     loc_step("location.disable", "loc_x", "annex")):
            with self.assertRaises(FrappeBackendError) as err:
                make_backend(engine).execute_step(TENANT, step)
            self.assertEqual(err.exception.code, "invalid_request")
            self.assertTrue(err.exception.side_effect_free)
        self.assertEqual(engine.writes, [])

    def test_disabling_a_branch_never_touches_a_warehouse_with_the_same_id(self) -> None:
        engine = FakeEngine()
        backend = make_backend(engine)
        backend.execute_step(TENANT, loc_step("location.upsert", "riyadh", "warehouse"))
        engine.writes.clear()
        for kind in ("branch", "department"):
            backend.execute_step(TENANT, loc_step("location.disable", "riyadh", kind))
        self.assertEqual(engine.writes, [], "an id collision with a branch must not disable the warehouse")
        self.assertEqual(engine.warehouses[0]["disabled"], 0)

    def test_disabling_a_branch_needs_no_company(self) -> None:
        engine = FakeEngine(companies=("Alpha Co", "Beta Co"))  # ambiguous company: refuses a warehouse, not a branch
        make_backend(engine).execute_step(TENANT, loc_step("location.disable", "riyadh", "branch"))
        self.assertEqual(engine.writes, [])


class TestWarehouseRetryAndDisable(unittest.TestCase):
    def test_upsert_twice_inserts_once_and_a_retry_after_disable_re_enables_the_same_warehouse(self) -> None:
        engine = FakeEngine()
        backend = make_backend(engine)
        up = loc_step("location.upsert", "wh_a", "warehouse")
        backend.execute_step(TENANT, up)
        backend.execute_step(TENANT, up)  # a retry of the same step
        self.assertEqual([w for w in engine.writes if w[0] == "insert"], [("insert", "wh_a")])
        self.assertEqual(len(engine.warehouses), 1)
        self.assertEqual(engine.warehouses[0]["name"], "wh_a - SC")

        backend.execute_step(TENANT, loc_step("location.disable", "wh_a", "warehouse"))
        self.assertEqual(engine.warehouses[0]["disabled"], 1)
        backend.execute_step(TENANT, loc_step("location.disable", "wh_a", "warehouse"))  # disabling twice is harmless
        self.assertEqual(engine.warehouses[0]["disabled"], 1)

        backend.execute_step(TENANT, up)
        self.assertEqual(engine.warehouses[0]["disabled"], 0)
        self.assertEqual(len(engine.warehouses), 1, "re-enable, never a second warehouse")

    def test_disable_without_a_kind_is_refused_and_never_defaults_to_a_warehouse(self) -> None:
        """Review of PR #301, finding 1: a schema-valid disable whose definition omits `kind` must not reach a Warehouse
        (the Blueprint location may be a branch with the same id)."""
        for step in (loc_step("location.disable", "wh_a", None),  # definition present, kind omitted
                     loc_step("location.disable", "wh_a", None, with_definition=False)):  # no definition at all
            engine = FakeEngine()
            backend = make_backend(engine)
            backend.execute_step(TENANT, loc_step("location.upsert", "wh_a", "warehouse"))
            engine.writes.clear()
            with self.assertRaises(FrappeBackendError) as err:
                backend.execute_step(TENANT, step)
            self.assertEqual(err.exception.code, "invalid_request")
            self.assertTrue(err.exception.side_effect_free)
            self.assertEqual(engine.writes, [])
            self.assertEqual(engine.warehouses[0]["disabled"], 0, "the same-id warehouse stays enabled")

    def test_check_ready_refuses_a_disable_step_without_a_kind_before_any_write(self) -> None:
        engine = FakeEngine()
        backend = make_backend(engine)
        with self.assertRaises(FrappeBackendError) as err:
            backend.check_ready(TENANT, [loc_step("location.disable", "wh_a", None)])
        self.assertEqual(err.exception.code, "invalid_request")
        self.assertTrue(err.exception.side_effect_free)
        backend.check_ready(TENANT, [loc_step("location.disable", "wh_a", "branch"),
                                     loc_step("location.disable", "wh_a", "warehouse")])  # a recognised kind passes

    def test_disabling_an_unknown_warehouse_is_a_no_op_that_commits_nothing(self) -> None:
        engine = FakeEngine()
        make_backend(engine).execute_step(TENANT, loc_step("location.disable", "wh_never", "warehouse"))
        self.assertEqual(engine.writes, [])

    def test_a_failed_insert_rolls_the_engine_back_and_a_retry_inserts_once(self) -> None:
        engine = FakeEngine()
        backend = make_backend(engine)
        real_get_doc = engine.get_doc
        boom = {"left": 1}

        def flaky_get_doc(payload):
            if boom["left"]:
                boom["left"] -= 1
                raise RuntimeError("engine hiccup")
            return real_get_doc(payload)

        engine.get_doc = flaky_get_doc
        up = loc_step("location.upsert", "wh_a", "warehouse")
        with self.assertRaises(FrappeBackendError):
            backend.execute_step(TENANT, up)
        self.assertGreaterEqual(engine.db.rollbacks, 1)
        self.assertEqual(engine.warehouses, [])
        backend.execute_step(TENANT, up)
        self.assertEqual(len(engine.warehouses), 1)


class TestCheckReady(unittest.TestCase):
    def wh(self, loc_id="wh_a", company=None) -> dict:
        step = loc_step("location.upsert", loc_id, "warehouse")
        if company:
            step["params"]["definition"]["company"] = company
        return step

    def refused(self, backend, steps) -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            backend.check_ready(TENANT, steps)
        self.assertTrue(err.exception.side_effect_free)
        return err.exception

    def test_a_warehouse_step_on_a_site_without_a_company_is_refused_before_execute(self) -> None:
        self.assertEqual(self.refused(make_backend(FakeEngine(companies=())), [self.wh()]).code, "site_not_ready")

    def test_a_warehouse_step_on_a_multi_company_site_needs_a_named_company(self) -> None:
        backend = make_backend(FakeEngine(companies=("Alpha Co", "Beta Co")))
        self.assertEqual(self.refused(backend, [self.wh()]).code, "site_not_ready")
        self.assertEqual(self.refused(backend, [self.wh(company="Gamma Co")]).code, "site_not_ready")
        backend.check_ready(TENANT, [self.wh(company="Beta Co")])

    def test_the_check_writes_nothing_and_passes_for_a_ready_site(self) -> None:
        engine = FakeEngine()
        make_backend(engine).check_ready(TENANT, [self.wh()])
        self.assertEqual((engine.writes, engine.db.commits), ([], 0))

    def test_branch_department_and_non_location_steps_need_no_company(self) -> None:
        backend = make_backend(FakeEngine(companies=()))
        backend.check_ready(TENANT, [loc_step("location.upsert", "b1", "branch"), loc_step("location.upsert", "d1", "department"),
                                     {"seq": 3, "kind": "settings.set", "pointer": "/company", "subject": {}, "params": {}}])

    def test_an_unreachable_engine_database_is_not_ready(self) -> None:
        engine = FakeEngine()
        engine.db.unreachable = True
        self.assertEqual(self.refused(make_backend(engine), []).code, "engine_unavailable")


if __name__ == "__main__":
    unittest.main()
