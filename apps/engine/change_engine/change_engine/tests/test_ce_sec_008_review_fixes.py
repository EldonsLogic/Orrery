"""CE-SEC-008 part 1, revision round 1: one test group per finding of the independent review.

Reuses the transactional, fault-injecting live database double of
``test_ce_sec_008_deploy_path_durability``. Synthetic data only.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.api import endpoints  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.schema_reconciler import (  # noqa: E402
    ExhaustiveSnapshot,
    IdempotencyConflictError,
    execute_single_field_deployment,
    reconcile_exhaustive_snapshot,
)
from change_engine.tests.test_ce_sec_008_deploy_path_durability import (  # noqa: E402
    FIELD,
    STMT,
    _Bench,
    _Crash,
    _DbDown,
    _DurableDb,
)
from change_engine.tests.test_erp_027_decimal_drift import _T  # noqa: E402

SECRET = "SECRET-dsn host=db-internal-7 user=svc"
ADMIN = ["System Manager"]


def _record(**over):
    rec = {"deployment_id": "dep_1", "idempotency_key": "key-1", "payload_hash": "hash-1", "site_id": "site-a",
           "doctype": "Item", "fieldname": None, "base_revision_hash": "r1", "status": "PREPARED"}
    rec.update(over)
    return rec


def _entry_points(bench: _Bench):
    """The three non-DDL entry points, each bound to a live adapter on ``bench``."""
    from change_engine.tests import test_phase3_workflow, test_phase4_report  # lazily: their TestCases must not be collected here

    TestPhase3WorkflowEngine = test_phase3_workflow.TestPhase3WorkflowEngine
    TestPhase4ReportEngine = test_phase4_report.TestPhase4ReportEngine
    bench.module.make_property_setter = lambda *a, **k: None
    wf = TestPhase3WorkflowEngine("test_11_api_endpoints_and_proposal")._build_valid_2_stage_workflow("Sales Order")
    rd = TestPhase4ReportEngine("test_11_end_to_end_api_calls")._build_valid_report_def("Sales Order")
    adapter = bench.new_adapter()
    return {
        "property_setter": lambda dep="dep_ps", **kw: endpoints.apply_property_setter_change(
            doctype="Item", deployment_id=dep, fieldname="note", property_name="label", value="X",
            adapter=adapter, user_roles=ADMIN, **kw),
        "workflow": lambda dep="dep_wf", **kw: endpoints.apply_workflow_change(
            doctype="Sales Order", deployment_id=dep, workflow_def=wf.model_dump(),
            adapter=adapter, user_roles=ADMIN, **kw),
        "report": lambda dep="dep_rp", **kw: endpoints.apply_report_change(
            doctype="Sales Order", deployment_id=dep, report_def=rd.model_dump(),
            adapter=adapter, user_roles=["Sales Manager"], **kw),
    }, adapter


# ===========================================================================================
class TestFinding1BaselineOnlyForPhysicalDdl(unittest.TestCase):
    def test_all_three_non_ddl_entry_points_prepare_on_a_live_adapter(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(entry_point=name):
                bench = _Bench()
                calls, _adapter = _entry_points(bench)
                out = calls[name]()
                self.assertNotEqual(out.get("disposition"), "AUDIT_PREPARE_FAILED", out)
                self.assertNotEqual(out.get("stage"), "PREPARE", out)
                rows = [r for r in bench.db.committed.values() if r["deployment_id"].startswith("dep_")]
                self.assertTrue(rows, "the intent is committed")
                self.assertFalse(bench.db.evidence(rows[0]["deployment_id"]), "no DDL baseline for a non-DDL deployment")

    def test_physical_ddl_still_requires_a_baseline(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        with self.assertRaises(endpoints.DurableEvidenceError):
            adapter.persist_prepare_and_audit_intent(_record(ddl_plan_statements=[STMT]))
        self.assertEqual(bench.db.committed, {})

    def test_non_ddl_record_without_a_plan_key_prepares_strictly(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.persist_prepare_and_audit_intent(_record())
        with self.assertRaises(endpoints.DeploymentIntentConflictError):
            adapter.persist_prepare_and_audit_intent(_record(idempotency_key="key-2"))


# ===========================================================================================
class TestFinding2EvidenceNamespaceIsNotCallerReachable(unittest.TestCase):
    def _deployed(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self.assertEqual(bench.deploy(adapter)["status"], "APPLIED")
        return bench, adapter

    def test_ids_that_could_collide_with_the_evidence_namespace_are_rejected_before_any_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        for dep in ("dep_1#baseline", "x#d0001", "#", "", "a" * 129, None, 7):
            with self.subTest(dep=dep):
                out = execute_single_field_deployment(
                    adapter, dep, "key-1", "site-a", "Item", "rev", dict(FIELD))
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["stage"], "VALIDATE")
                self.assertEqual(out["reason_code"], "invalid_deployment_id")
        out = execute_single_field_deployment(adapter, "dep_1", "key#evidence", "site-a", "Item", "rev", dict(FIELD))
        self.assertEqual(out["reason_code"], "invalid_idempotency_key")
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.committed, {})
        with self.assertRaises(endpoints.InvalidDeploymentIdError):
            adapter.persist_prepare_and_audit_intent(_record(deployment_id="dep_1#baseline"))
        with self.assertRaises(endpoints.InvalidDeploymentIdError):
            FrappeDeploymentAdapter(in_memory=True, use_shared_state=False).persist_prepare_and_audit_intent(
                _record(deployment_id="dep_1#baseline"))

    def test_the_rpc_boundary_rejects_a_colliding_deployment_id(self):
        bench = _Bench()
        calls, adapter = _entry_points(bench)
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(entry_point=name):
                out = calls[name](dep="dep_1#baseline")
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["disposition"], "INVALID_DEPLOYMENT_ID")
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="dep_1#d0001", field_def=dict(FIELD), adapter=adapter, user_roles=ADMIN)
        self.assertEqual(out["disposition"], "INVALID_DEPLOYMENT_ID")
        self.assertEqual(bench.db.committed, {})

    def test_rollback_does_not_accept_evidence_rows_as_deployments(self):
        bench, adapter = self._deployed()
        evidence = {k: dict(v) for k, v in bench.db.committed.items() if "#" in k}
        self.assertTrue(evidence)
        for name in evidence:
            with self.subTest(name=name):
                self.assertIsNone(adapter.get_deployment_record(name))
                out = endpoints.revert_configuration_change(deployment_id=name, adapter=adapter, user_roles=ADMIN)
                self.assertEqual(out["disposition"], "DEPLOYMENT_NOT_FOUND")
        self.assertEqual({k: v for k, v in bench.db.committed.items() if "#" in k}, evidence)

    def test_no_finalizer_can_touch_an_evidence_row(self):
        bench, adapter = self._deployed()
        evidence = {k: dict(v) for k, v in bench.db.committed.items() if "#" in k}
        for name in evidence:
            with self.subTest(name=name):
                with self.assertRaises(endpoints.InvalidDeploymentIdError):
                    adapter.persist_final_outcome_and_audit(name, {"outcome": {"status": "APPLIED"}})
                with self.assertRaises(endpoints.InvalidDeploymentIdError):
                    adapter.mark_recovery_required(name, "x")
                with self.assertRaises(endpoints.InvalidDeploymentIdError):
                    adapter.update_deployment_status(name, "ROLLED_BACK")
        self.assertEqual({k: v for k, v in bench.db.committed.items() if "#" in k}, evidence)

    def test_every_audit_statement_is_restricted_to_main_rows(self):
        bench, adapter = self._deployed()
        bench.db.sql_log.clear()
        adapter.get_existing_deployment_by_idempotency("site-a", "key-1")
        adapter.is_target_in_recovery_required("site-a", "Item")
        adapter.get_deployment_record("dep_1")
        adapter.persist_final_outcome_and_audit("dep_1", {"outcome": {"status": "APPLIED"}})
        adapter.mark_recovery_required("dep_1", "x")
        audit_sql = [q for q in bench.db.sql_log
                     if "Change Engine Audit" in q and q.lstrip().upper().startswith(("SELECT", "UPDATE"))]
        self.assertEqual(len(audit_sql), 5)
        for q in audit_sql:
            self.assertIn("NOT IN ('EVIDENCE_BASELINE'", q.replace("\n", " "), q)


# ===========================================================================================
class TestFinding3ReadsAreFreshAfterTheLock(unittest.TestCase):
    def test_a_prepared_row_committed_while_waiting_for_the_lock_blocks_the_deployment(self):
        bench = _Bench()
        adapter = bench.new_adapter()

        def other_session_commits(lock_name):
            if "committed_by_other" not in bench.db.committed:
                bench.db.committed["committed_by_other"] = {
                    "name": "committed_by_other", "deployment_id": "committed_by_other",
                    "idempotency_key": "key-other", "payload_hash": "h-other", "site_id": "site-a",
                    "doctype": "Item", "fieldname": "custom_o", "base_revision_hash": "r",
                    "ddl_plan_statements": "[]", "status": "PREPARED", "outcome_json": None}

        base_rev = adapter.get_doctype_revision_hash("Item")  # a read before the lock opens the view
        bench.db.on_lock = other_session_commits
        out = execute_single_field_deployment(adapter, "dep_1", "key-1", "site-a", "Item", base_rev, dict(FIELD))
        self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertEqual(bench.db.altered(), [])

    def test_the_order_is_lock_then_fresh_view_then_lookups_then_snapshot(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        order = []
        for name in ("acquire_advisory_lock", "begin_fresh_read_view", "get_existing_deployment_by_idempotency",
                     "is_target_in_recovery_required", "take_snapshot", "release_advisory_lock"):
            original = getattr(adapter, name)
            setattr(adapter, name, (lambda n, f: lambda *a, **k: (order.append(n), f(*a, **k))[1])(name, original))
        bench.deploy(adapter)
        first = {n: order.index(n) for n in set(order)}
        self.assertLess(first["acquire_advisory_lock"], first["begin_fresh_read_view"])
        self.assertLess(first["begin_fresh_read_view"], first["get_existing_deployment_by_idempotency"])
        self.assertLess(first["begin_fresh_read_view"], first["is_target_in_recovery_required"])
        self.assertLess(first["begin_fresh_read_view"], first["take_snapshot"])

    def test_a_fresh_view_that_cannot_be_opened_blocks_with_no_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.begin_fresh_read_view = lambda: (_ for _ in ()).throw(_DbDown("connection lost"))
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["reason_code"], "engine_unavailable")
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.locks, set())


# ===========================================================================================
class TestFinding4ProvenanceAndHolds(unittest.TestCase):
    def _crash(self, how):
        bench = _Bench()
        adapter = bench.new_adapter()
        if how == "before_ddl":
            bench.db.crash_before_ddl = True
        elif how == "during_ddl":
            bench.db.crash_after_ddl = True
        else:
            adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter)
        bench.db.crash()
        bench.db.crash_before_ddl = bench.db.crash_after_ddl = False
        return bench

    def test_provenance_is_computed_and_a_restart_never_vouches_for_it(self):
        for how in ("during_ddl", "before_finalize"):
            with self.subTest(how=how):
                bench = self._crash(how)
                restarted = bench.new_adapter()
                before = restarted.load_durable_evidence("dep_1")["baseline"]
                self.assertIsNotNone(before)
                snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
                self.assertFalse(snap.provenance_matches)
                outcome = reconcile_exhaustive_snapshot(
                    "dep_1", "Item", "custom_x", ExhaustiveSnapshot(False, False), snap, None)
                self.assertEqual(outcome["status"], "RECOVERY_REQUIRED", "never APPLIED from a restart")

    def test_a_normal_in_process_apply_has_matching_provenance_and_applies(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self.assertEqual(bench.deploy(adapter)["status"], "APPLIED")
        self.assertTrue(adapter.take_snapshot("Item", "custom_x", "dep_1").provenance_matches)

    def test_a_dispatched_statement_that_never_returned_breaks_provenance(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.crash_after_ddl = True
        orig = bench.db.sql

        def swallow(q, *a, **k):  # the engine swallows the crash exception: the statement took effect, but never "returned"
            try:
                return orig(q, *a, **k)
            except _Crash:
                raise RuntimeError("connection reset") from None

        bench.db.sql = swallow
        out = bench.deploy(adapter)
        self.assertEqual(adapter._dispatched_ddl["dep_1"], [STMT])
        self.assertEqual(adapter._executed_ddl["dep_1"], [])
        self.assertNotEqual(out["status"], "APPLIED")
        self.assertFalse(adapter.take_snapshot("Item", "custom_x", "dep_1").provenance_matches)

    def test_an_intent_row_alone_is_never_executed_evidence(self):
        bench = self._crash("before_ddl")
        restarted = bench.new_adapter()
        ev = restarted.load_durable_evidence("dep_1")
        self.assertEqual(ev["dispatched"], [STMT])
        self.assertEqual(ev["completed"], [])
        self.assertEqual(restarted._executed_ddl, {}, "nothing is recorded executed from an intent row")
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertFalse(snap.has_col)
        self.assertEqual(restarted._executed_ddl, {})

    def test_a_prepared_deployment_holds_the_target_and_is_never_re_run(self):
        for how in ("before_ddl", "during_ddl", "before_finalize"):
            with self.subTest(how=how):
                bench = self._crash(how)
                sent = len(bench.db.altered())
                for n in range(2):  # across two further restarts
                    adapter = bench.new_adapter()
                    for dep, key in (("dep_1", "key-1"), ("dep_2", "key-1"), ("dep_3", "key-3")):
                        out = bench.deploy(adapter, dep=dep, key=key)
                        self.assertEqual(out["status"], "RECOVERY_REQUIRED", (dep, key, out))
                self.assertEqual(len(bench.db.altered()), sent)
                self.assertEqual(bench.db.row("dep_1")["status"], "PREPARED")


# ===========================================================================================
class TestFinding5LookupsRequireTheExpectedShape(unittest.TestCase):
    def test_an_empty_recovery_count_is_not_clear(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        real = bench.db._audit
        for bad in ((), ((),), ((None,),), (("1",),), ((True,),), ((-1,),)):
            with self.subTest(bad=bad):
                bench.db._audit = lambda q, p, a, bad=bad: bad if "SELECT COUNT(*)" in q else real(q, p, a)
                with self.assertRaises(endpoints.DurableEvidenceError):
                    adapter.is_target_in_recovery_required("site-a", "Item")

    def test_a_malformed_stored_outcome_is_never_absent_and_never_a_replay(self):
        for stored in ("", "   ", "[]", "42", "null", '"done"', "true", "{not json"):
            with self.subTest(stored=stored):
                bench = _Bench()
                adapter = bench.new_adapter()
                bench.db.committed["x"] = {
                    "name": "x", "deployment_id": "x", "idempotency_key": "key-1", "payload_hash": "h",
                    "site_id": "site-a", "doctype": "Item", "fieldname": "f", "base_revision_hash": "r",
                    "ddl_plan_statements": "[]", "status": "APPLIED", "outcome_json": stored}
                with self.assertRaises(Exception) as cm:
                    adapter.get_existing_deployment_by_idempotency("site-a", "key-1")
                self.assertNotIsInstance(cm.exception, KeyboardInterrupt)
                out = execute_single_field_deployment(adapter, "dep_9", "key-1", "site-a", "Item",
                                                      adapter.get_doctype_revision_hash("Item"), dict(FIELD))
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["reason_code"], "engine_unavailable")
                self.assertEqual(bench.db.altered(), [])

    def test_a_valid_outcome_object_is_replayed(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.committed["x"] = {
            "name": "x", "deployment_id": "x", "idempotency_key": "key-1", "payload_hash": "h", "site_id": "site-a",
            "doctype": "Item", "fieldname": "f", "base_revision_hash": "r", "ddl_plan_statements": "[]",
            "status": "APPLIED", "outcome_json": json.dumps({"status": "APPLIED"})}
        self.assertEqual(adapter.get_existing_deployment_by_idempotency("site-a", "key-1"),
                         {"payload_hash": "h", "outcome": {"status": "APPLIED"}})

    def test_the_deployment_record_lookup_reports_unavailable_instead_of_not_found(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.fail("WHERE DEPLOYMENT_ID = %S", _DbDown(SECRET))
        with self.assertRaises(endpoints.DurableEvidenceError) as cm:
            adapter.get_deployment_record("dep_1")
        self.assertNotIn("SECRET", str(cm.exception))
        out = endpoints.revert_configuration_change(deployment_id="dep_1", adapter=adapter, user_roles=ADMIN)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["reason_code"], "engine_unavailable")
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertNotEqual(out.get("disposition"), "DEPLOYMENT_NOT_FOUND")

    def test_an_absent_deployment_record_is_still_not_found(self):
        bench = _Bench()
        out = endpoints.revert_configuration_change(deployment_id="dep_none", adapter=bench.new_adapter(), user_roles=ADMIN)
        self.assertEqual(out["disposition"], "DEPLOYMENT_NOT_FOUND")


# ===========================================================================================
class TestFinding6IdempotencyAcrossTargets(unittest.TestCase):
    def _other_target_row(self, bench, *, outcome=None, status="PREPARED"):
        bench.db.committed["other"] = {
            "name": "other", "deployment_id": "other", "idempotency_key": "key-1", "payload_hash": "h-other-target",
            "site_id": "site-a", "doctype": "Customer", "fieldname": "custom_o", "base_revision_hash": "r",
            "ddl_plan_statements": "[]", "status": status, "outcome_json": outcome}

    @staticmethod
    def _back_to_baseline(bench):
        del bench.db.schema["columns"]["custom_x"]
        bench.db.schema["order"].remove("custom_x")
        bench.db.inserted.discard("custom_x")

    def test_a_site_scoped_idempotency_lock_is_taken_before_the_target_lock_and_both_are_released(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        acquired, released = [], []
        a, r = adapter.acquire_advisory_lock, adapter.release_advisory_lock
        adapter.acquire_advisory_lock = lambda k, wait_seconds: (acquired.append(k), a(k, wait_seconds))[1]
        adapter.release_advisory_lock = lambda k: (released.append(k), r(k))[1]
        bench.deploy(adapter)
        self.assertEqual(len(acquired), 2)
        self.assertNotEqual(acquired[0], acquired[1])
        self.assertTrue(all(len(k) <= 64 for k in acquired))
        self.assertEqual(sorted(released), sorted(acquired))
        self.assertEqual(bench.db.locks, set())

    def test_the_same_key_cannot_reserve_a_second_target(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self._other_target_row(bench)  # the key is already held by an unfinished deployment on another target
        with self.assertRaises(IdempotencyConflictError):
            bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(len([r for r in bench.db.committed.values() if r["idempotency_key"] == "key-1"]), 1)

    def test_a_key_reserved_while_waiting_for_the_idempotency_lock_is_seen(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        base_rev = adapter.get_doctype_revision_hash("Item")
        bench.db.on_lock = lambda name: self._other_target_row(bench) if "other" not in bench.db.committed else None
        with self.assertRaises(IdempotencyConflictError):
            execute_single_field_deployment(adapter, "dep_1", "key-1", "site-a", "Item", base_rev, dict(FIELD))
        self.assertEqual(bench.db.altered(), [])

    def test_an_unfinished_deployment_with_the_same_key_and_payload_is_returned_as_a_hold(self):
        bench = _Bench()
        crashed = bench.new_adapter()
        crashed.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(crashed)
        bench.db.crash()
        held = bench.new_adapter().get_existing_deployment_by_idempotency("site-a", "key-1")
        self.assertEqual(held["outcome"]["status"], "RECOVERY_REQUIRED")
        self.assertEqual(held["outcome"]["reason_code"], "idempotency_key_held")
        out = bench.deploy(bench.new_adapter(), dep="dep_2")
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")
        self.assertEqual(out["reason_code"], "idempotency_key_held")

    def test_already_recorded_replays_the_stored_outcome(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        first = bench.deploy(adapter)
        self._back_to_baseline(bench)  # the field looks absent again, so the request reaches Stage 3
        lookups = {"n": 0}
        real = adapter.get_existing_deployment_by_idempotency

        def blind_once(site, key):  # as if the lookup ran before the competing commit
            lookups["n"] += 1
            return None if lookups["n"] == 1 else real(site, key)

        adapter.get_existing_deployment_by_idempotency = blind_once
        adapter.is_target_in_recovery_required = lambda *a: False
        out = bench.deploy(adapter)  # same deployment id, key and payload
        self.assertEqual(out, first)
        self.assertEqual(len(bench.db.altered()), 1)

    def test_already_recorded_on_an_unfinished_intent_returns_the_hold(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.take_snapshot("Item", "custom_x", "dep_1")
        adapter.persist_prepare_and_audit_intent(_record(
            payload_hash=__import__("change_engine.guarded_apply.schema_reconciler", fromlist=["x"])
            .compute_canonical_payload_hash("site-a", "Item", dict(FIELD)),
            fieldname="custom_x", ddl_plan_statements=[STMT]))
        real = adapter.get_existing_deployment_by_idempotency
        calls = {"n": 0}

        def blind_once(site, key):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(site, key)

        adapter.get_existing_deployment_by_idempotency = blind_once
        adapter.is_target_in_recovery_required = lambda *a: False
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")
        self.assertEqual(bench.db.altered(), [])


# ===========================================================================================
class TestFinding7StableErrorCodes(unittest.TestCase):
    def _assert_clean(self, out):
        self.assertNotIn("SECRET", json.dumps(out, default=str), out)

    def test_lookup_failures_reach_every_rpc_as_stable_codes_only(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(entry_point=name):
                bench = _Bench()
                calls, _ = _entry_points(bench)
                bench.db.fail("SELECT PAYLOAD_HASH", _DbDown(SECRET))
                out = calls[name]()
                self._assert_clean(out)
                self.assertEqual(out["reason_code"], "engine_unavailable", out)
        bench = _Bench()
        bench.db.fail("SELECT PAYLOAD_HASH", _DbDown(SECRET))
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="dep_1", field_def=dict(FIELD), adapter=bench.new_adapter(), user_roles=ADMIN)
        self._assert_clean(out)

    def test_recovery_lookup_failures_are_stable_too(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(entry_point=name):
                bench = _Bench()
                calls, _ = _entry_points(bench)
                bench.db.fail("SELECT COUNT(*)", _DbDown(SECRET))
                out = calls[name]()
                self._assert_clean(out)
                self.assertEqual(out["reason_code"], "engine_unavailable", out)

    def test_prepare_failures_do_not_leak_database_text(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(entry_point=name):
                bench = _Bench()
                calls, _ = _entry_points(bench)
                bench.db.fail("INSERT INTO", _DbDown(SECRET))
                out = calls[name]()
                self._assert_clean(out)
        bench = _Bench()
        bench.db.fail("INSERT INTO", _DbDown(SECRET))
        self._assert_clean(bench.deploy(bench.new_adapter()))

    def test_reconciler_outcomes_carry_no_exception_text(self):
        # lock timeout setter, dispatch failure, finalization failure, intent conflict
        bench = _Bench()
        bench.db.fail("SET SESSION LOCK_WAIT_TIMEOUT", _DbDown(SECRET))
        self._assert_clean(bench.deploy(bench.new_adapter()))

        bench = _Bench()
        bench.db.fail("ALTER TABLE", _DbDown(SECRET))
        out = bench.deploy(bench.new_adapter())
        self._assert_clean(out)

        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))
        out = bench.deploy(adapter)
        self._assert_clean(out)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")

        bench = _Bench()
        adapter = bench.new_adapter()
        bench.deploy(adapter)
        out = bench.deploy(adapter, dep="dep_1", key="key-9")
        self._assert_clean(out)

    def test_a_failing_lock_release_cannot_escape_the_response(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.release_advisory_lock = lambda k: (_ for _ in ()).throw(_DbDown(SECRET))
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "APPLIED")
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="dep_9", field_def={**FIELD, "fieldname": "custom_q"},
            adapter=adapter, user_roles=ADMIN)
        self._assert_clean(out)


# ===========================================================================================
class TestFinding8TimeoutIsValidatedAndVerifiedWhereDdlIsDispatched(unittest.TestCase):
    def test_the_rpc_validates_the_timeout_before_any_database_call(self):
        for bad in ("abc", "3.5", 3.5, True, 0, -1, "0", 10 ** 12, "", [3], {"a": 1}):
            with self.subTest(bad=bad):
                bench = _Bench()
                adapter = bench.new_adapter()
                before = len(bench.db.sql_log)
                out = endpoints.apply_configuration_change(
                    doctype="Item", deployment_id="dep_1", field_def=dict(FIELD), adapter=adapter,
                    user_roles=ADMIN, lock_wait_seconds=bad)
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["stage"], "VALIDATE")
                self.assertEqual(out["disposition"], "INVALID_LOCK_WAIT_SECONDS")
                self.assertEqual(len(bench.db.sql_log), before, "nothing was read or written")

    def test_a_valid_timeout_in_either_rpc_form_is_accepted(self):
        for ok in (3, "3"):
            with self.subTest(ok=ok):
                bench = _Bench(statements=[_T + "ADD COLUMN `custom_xyz` varchar(140)"])
                out = endpoints.apply_configuration_change(
                    doctype="Item", deployment_id="dep_1", field_def={**FIELD, "fieldname": "custom_xyz"},
                    adapter=bench.new_adapter(), user_roles=ADMIN, lock_wait_seconds=ok)
                self.assertEqual(out["status"], "APPLIED", out)
                self.assertEqual(bench.db.lock_wait_timeout, 3)

    def test_the_timeout_is_re_verified_on_the_session_that_dispatches_ddl(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        out = None
        bench.db.readback_values = [3, 50]  # verified when set; the session is back to 50 when DDL is about to go
        out = bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [], "no statement is sent on an unverified session")
        self.assertNotEqual(out["status"], "APPLIED")

    def test_an_unset_timeout_does_not_block_a_direct_adapter_use(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.take_snapshot("Item", "custom_x", "dep_1")
        adapter.persist_prepare_and_audit_intent(_record(fieldname="custom_x", ddl_plan_statements=[STMT]))
        adapter.apply_native_custom_field("dep_1", "Item", dict(FIELD))
        self.assertEqual(bench.db.altered(), [STMT])


# ===========================================================================================
# Revision round 2
# ===========================================================================================
def _crashed(bench: _Bench, dep="dep_1", key="key-1", site="site-a"):
    """Leave ``dep`` PREPARED: the process dies after the DDL, before finalization."""
    adapter = bench.new_adapter()
    adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
    try:
        bench.deploy(adapter, dep=dep, key=key, site=site)
    except _Crash:
        pass
    bench.db.crash()


class TestN1FreshViewNeverCommitsTheCallersWork(unittest.TestCase):
    CALLER_ROW = {
        "name": "caller_row", "deployment_id": "caller_row", "idempotency_key": "caller", "payload_hash": "h",
        "site_id": "other", "doctype": "Other", "fieldname": "", "base_revision_hash": "r",
        "ddl_plan_statements": "[]", "status": "CALLER", "outcome_json": None}

    def test_pending_caller_writes_survive_a_rejection_uncommitted(self):
        for rejection in ("replay", "preflight"):
            with self.subTest(rejection=rejection):
                bench = _Bench()
                adapter = bench.new_adapter()
                first = bench.deploy(adapter)
                base_rev = adapter.get_doctype_revision_hash("Item")
                bench.db.pending.append(("insert", "caller_row", dict(self.CALLER_ROW)))
                commits = bench.db.commits
                out = execute_single_field_deployment(
                    adapter, "dep_2", "key-1" if rejection == "replay" else "key-2", "site-a", "Item", base_rev, dict(FIELD))
                self.assertNotEqual(out, first, "the engine refuses to run over uncommitted caller writes")
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["reason_code"], "engine_unavailable")
                self.assertEqual(bench.db.commits, commits, "nothing was committed on the caller's behalf")
                self.assertIn(("insert", "caller_row", self.CALLER_ROW), bench.db.pending, "and nothing was rolled back")
                self.assertNotIn("caller_row", bench.db.committed)
                self.assertEqual(len(bench.db.altered()), 1)

    def test_a_replay_with_no_pending_writes_commits_nothing(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        first = bench.deploy(adapter)
        adapter = bench.new_adapter()
        commits = bench.db.commits
        self.assertEqual(bench.deploy(adapter, dep="dep_2"), first)
        self.assertEqual(bench.db.commits, commits, "the fresh read view is opened without a commit")

    def test_begin_fresh_read_view_refuses_over_pending_writes_and_ends_a_clean_transaction(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.pending.append(("insert", "caller_row", dict(self.CALLER_ROW)))
        with self.assertRaises(endpoints.DurableEvidenceError):
            adapter.begin_fresh_read_view()
        bench.db.pending.clear()
        bench.db.view = {}
        adapter.begin_fresh_read_view()
        self.assertIsNone(bench.db.view)


class TestN2OneEqualityForLocksLookupsAndUniqueness(unittest.TestCase):
    def test_lock_names_follow_the_collation_equality(self):
        from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key, make_idempotency_lock_key

        self.assertEqual(make_idempotency_lock_key("site-a", "KEY-1"), make_idempotency_lock_key("site-a", "key-1"))
        self.assertEqual(make_idempotency_lock_key("site-a", "key-1  "), make_idempotency_lock_key("site-a", "key-1"))
        self.assertEqual(make_idempotency_lock_key("SITE-A ", "key-1"), make_idempotency_lock_key("site-a", "key-1"))
        self.assertNotEqual(make_idempotency_lock_key("site-a", "key-1"), make_idempotency_lock_key("site-a", "key-2"))
        self.assertEqual(make_bounded_lock_key("Site-A", "Item "), make_bounded_lock_key("site-a", "item"))
        self.assertNotEqual(make_bounded_lock_key("site-a", "Item"), make_bounded_lock_key("site-a", "Customer"))

    def test_keys_that_are_not_canonical_are_refused_before_any_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        for key in ("key-1 ", " key-1", "key 1", "kéy", "كلمة", "key/1", "k" * 129):
            with self.subTest(key=key):
                out = execute_single_field_deployment(adapter, "dep_1", key, "site-a", "Item", "rev", dict(FIELD))
                self.assertEqual(out["reason_code"], "invalid_idempotency_key")
        for dep in ("dep 1", "dep_1 ", "dép", "d" * 101):
            with self.subTest(dep=dep):
                out = execute_single_field_deployment(adapter, dep, "key-1", "site-a", "Item", "rev", dict(FIELD))
                self.assertEqual(out["reason_code"], "invalid_deployment_id")
        self.assertEqual(bench.db.committed, {})

    def test_a_key_differing_only_in_case_waits_on_the_same_lock(self):
        from change_engine.guarded_apply.schema_reconciler import make_idempotency_lock_key

        bench = _Bench()
        adapter = bench.new_adapter()
        base_rev = adapter.get_doctype_revision_hash("Item")
        bench.db.locks.add(make_idempotency_lock_key("site-a", "KEY-1"))  # another session holds the key
        out = execute_single_field_deployment(adapter, "dep_1", "key-1", "site-a", "Item", base_rev, dict(FIELD))
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["stage"], "ACQUIRE")
        self.assertEqual(bench.db.altered(), [])

    def test_the_lookup_and_the_lock_agree_for_case_and_padding(self):
        bench = _Bench()
        _crashed(bench, key="KEY-1")
        for key in ("key-1", "Key-1"):
            with self.subTest(key=key):
                held = bench.new_adapter().get_existing_deployment_by_idempotency("site-a", key)
                self.assertEqual(held["outcome"]["reason_code"], "idempotency_key_held")
        self.assertIsNotNone(bench.new_adapter().get_existing_deployment_by_idempotency("site-a", "key-1  "))


class TestN3LocksAreAlwaysReleased(unittest.TestCase):
    def test_a_target_lock_acquire_that_raises_still_releases_the_idempotency_lock(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        released, calls = [], []
        real_acquire, real_release = adapter.acquire_advisory_lock, adapter.release_advisory_lock

        def acquire(key, wait_seconds):
            calls.append(key)
            if len(calls) == 2:
                raise _DbDown(SECRET)
            return real_acquire(key, wait_seconds)

        adapter.acquire_advisory_lock = acquire
        adapter.release_advisory_lock = lambda k: (released.append(k), real_release(k))[1]
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["stage"], "ACQUIRE")
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertEqual(released, [calls[0]])
        self.assertEqual(bench.db.locks, set())
        self.assertEqual(bench.db.altered(), [])

    def test_a_first_lock_acquire_that_raises_is_a_stable_rejection(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.acquire_advisory_lock = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))
        out = bench.deploy(adapter)
        self.assertEqual((out["status"], out["stage"]), ("REJECTED", "ACQUIRE"))
        self.assertNotIn("SECRET", json.dumps(out))

    def test_a_failed_release_makes_the_session_unusable_and_discards_it(self):
        for fault in ("raises", "not_held"):
            with self.subTest(fault=fault):
                bench = _Bench()
                adapter = bench.new_adapter()
                if fault == "raises":
                    bench.db.fail("SELECT RELEASE_LOCK", _DbDown(SECRET))
                else:
                    bench.db.release_result = 0
                out = bench.deploy(adapter)
                self.assertEqual(out["status"], "APPLIED", "the applied outcome is still reported")
                self.assertTrue(bench.db.closed, "the connection that may still hold a lock is discarded")
                again = bench.deploy(adapter, dep="dep_2", key="key-2", field={**FIELD, "fieldname": "custom_y"})
                self.assertEqual((again["status"], again["stage"]), ("REJECTED", "ACQUIRE"))
                self.assertEqual(len(bench.db.altered()), 1)

    def test_the_reconciler_marks_an_adapter_whose_release_raises_unusable(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        marked = []
        adapter.release_advisory_lock = lambda k: (_ for _ in ()).throw(_DbDown(SECRET))
        adapter.mark_session_unusable = lambda: marked.append(True)
        self.assertEqual(bench.deploy(adapter)["status"], "APPLIED")
        self.assertTrue(marked)


class TestN4IdLengthsAndExistingRows(unittest.TestCase):
    def test_every_derived_name_of_a_maximum_length_id_fits_the_columns(self):
        bench = _Bench(statements=[_T + "ADD COLUMN `custom_xyz` varchar(140)"])
        dep = "d" * 100
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id=dep, field_def={**FIELD, "fieldname": "custom_xyz"},
            adapter=bench.new_adapter(), user_roles=ADMIN)
        self.assertEqual(out["status"], "APPLIED", out)
        for row in bench.db.committed.values():
            self.assertLessEqual(max(len(row["name"]), len(row["deployment_id"]), len(row["idempotency_key"])), 140)

    def test_a_longer_id_is_refused_for_a_new_deployment_at_the_rpc(self):
        bench = _Bench()
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="d" * 101, field_def=dict(FIELD), adapter=bench.new_adapter(), user_roles=ADMIN)
        self.assertEqual(out["disposition"], "INVALID_DEPLOYMENT_ID")

    def test_existing_long_ids_still_look_up_finalize_and_revert(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        old = "o" * 135
        bench.db.committed[old] = {
            "name": old, "deployment_id": old, "idempotency_key": "idemp-old", "payload_hash": "h", "site_id": "site-a",
            "doctype": "Item", "fieldname": "custom_old", "base_revision_hash": "r", "ddl_plan_statements": "[]",
            "status": "APPLIED", "outcome_json": json.dumps({"status": "APPLIED"})}
        self.assertEqual(adapter.get_deployment_record(old)["deployment_id"], old)
        adapter.persist_final_outcome_and_audit(old, {"outcome": {"status": "ROLLED_BACK"}})
        self.assertEqual(bench.db.committed[old]["status"], "ROLLED_BACK")
        out = endpoints.revert_configuration_change(deployment_id=old, adapter=adapter, user_roles=ADMIN)
        self.assertNotIn(out.get("disposition"), ("DEPLOYMENT_NOT_FOUND", "INVALID_DEPLOYMENT_ID", "ENGINE_UNAVAILABLE"))


class TestN5NoOrphanMetadataWhenNoDdlWasSent(unittest.TestCase):
    def _field_state(self, bench):
        return {"pending": set(bench.db.meta_pending), "committed": "custom_x" in bench.db.inserted}

    def test_the_timeout_is_re_checked_before_the_metadata_insert(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        bench.db.readback_values = [3, 50]
        out = bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(self._field_state(bench), {"pending": set(), "committed": False})
        self.assertEqual(out["status"], "FAILED_CLEAN", out)

    def test_a_refusal_at_dispatch_rolls_the_pending_metadata_back(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        bench.db.readback_values = [3, 3, 50]  # fine before the insert, drifted when the statement is admitted
        out = bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(self._field_state(bench), {"pending": set(), "committed": False}, "no orphan Custom Field")
        self.assertEqual(out["status"], "FAILED_CLEAN", out)
        self.assertEqual(bench.db.row("dep_1")["status"], "FAILED_CLEAN")

    def test_a_journal_write_failure_before_dispatch_rolls_the_metadata_back_too(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        orig = bench.db._audit
        n = {"i": 0}

        def flaky(q, p, as_dict):
            if q.startswith("INSERT INTO"):
                n["i"] += 1
                if n["i"] == 3:
                    raise _DbDown("journal unavailable")
            return orig(q, p, as_dict)

        bench.db._audit = flaky
        out = bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(self._field_state(bench), {"pending": set(), "committed": False})
        self.assertNotEqual(out["status"], "APPLIED")

    def test_the_normal_apply_still_commits_the_metadata(self):
        bench = _Bench(meta_first=True)
        self.assertEqual(bench.deploy(bench.new_adapter())["status"], "APPLIED")
        self.assertTrue(self._field_state(bench)["committed"])


class TestRemaindersFromRound1(unittest.TestCase):
    def test_the_internal_main_row_lookup_carries_the_evidence_filter(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self.assertEqual(bench.deploy(adapter)["status"], "APPLIED")
        bench.db.sql_log.clear()
        adapter.load_durable_evidence("dep_1")
        with self.assertRaises(endpoints.DeploymentIntentConflictError):
            adapter.take_snapshot("Item", "custom_x", "dep_1")
            adapter.persist_prepare_and_audit_intent(_record(ddl_plan_statements=[STMT], fieldname="custom_x"))
        by_id = [q for q in bench.db.sql_log if "WHERE deployment_id" in q]
        self.assertTrue(by_id)
        for q in by_id:
            self.assertIn("NOT IN ('EVIDENCE_BASELINE'", q.replace("\n", " "), q)

    def test_an_ordinary_revert_cannot_clear_a_hold(self):
        for status in ("PREPARED", "RECOVERY_REQUIRED"):
            with self.subTest(status=status):
                bench = _Bench()
                _crashed(bench)
                if status == "RECOVERY_REQUIRED":
                    bench.new_adapter().mark_recovery_required("dep_1", "x")
                row = dict(bench.db.row("dep_1"))
                bench.db.sql_log.clear()
                out = endpoints.revert_configuration_change(
                    deployment_id="dep_1", adapter=bench.new_adapter(), user_roles=ADMIN)
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["disposition"], "DEPLOYMENT_ON_HOLD")
                self.assertEqual(out["reason_code"], "recovery_hold")
                self.assertEqual(bench.db.row("dep_1"), row)
                self.assertFalse([q for q in bench.db.sql_log if q.lstrip().upper().startswith("UPDATE")])

    def test_replay_and_rollback_require_a_real_outcome_object(self):
        for stored in ("{}", '{"deployment_id": "x"}', '{"status": ""}', '{"status": 3}', "[]", "42", "", "null"):
            with self.subTest(stored=stored):
                bench = _Bench()
                adapter = bench.new_adapter()
                bench.db.committed["x"] = {
                    "name": "x", "deployment_id": "x", "idempotency_key": "key-1", "payload_hash": "h",
                    "site_id": "site-a", "doctype": "Item", "fieldname": "f", "base_revision_hash": "r",
                    "ddl_plan_statements": "[]", "status": "APPLIED", "outcome_json": stored}
                with self.assertRaises(endpoints.DurableEvidenceError):
                    adapter.get_existing_deployment_by_idempotency("site-a", "key-1")
                with self.assertRaises(endpoints.DurableEvidenceError):
                    adapter.get_deployment_record("x")
                out = endpoints.revert_configuration_change(deployment_id="x", adapter=adapter, user_roles=ADMIN)
                self.assertEqual(out["disposition"], "ENGINE_UNAVAILABLE")

    def test_a_revision_read_failure_returns_a_stable_code(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.get_doctype_revision_hash = lambda dt: (_ for _ in ()).throw(endpoints.RevisionHashError(SECRET))
        out = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="dep_1", field_def={**FIELD, "fieldname": "custom_xyz"},
            adapter=adapter, user_roles=ADMIN)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["reason_code"], "revision_unavailable")
        self.assertNotIn("SECRET", json.dumps(out))


# ===========================================================================================
# Revision round 3
# ===========================================================================================
class _NoCounterDb(_DurableDb):
    @property
    def transaction_writes(self):
        raise AttributeError("transaction_writes")


class _BadCounterDb(_DurableDb):
    counter = None

    @property
    def transaction_writes(self):
        return self.counter


class _NoRollbackDb(_DurableDb):
    rollback = None


class TestR3FreshViewFailsClosed(unittest.TestCase):
    def test_a_missing_or_invalid_write_counter_is_a_refusal_not_zero(self):
        cases = [("missing", _Bench(_NoCounterDb()))]
        for bad in (None, "0", True, -1, 1.5):
            db = _BadCounterDb()
            db.counter = bad
            cases.append((f"invalid {bad!r}", _Bench(db)))
        for name, bench in cases:
            with self.subTest(counter=name):
                adapter = bench.new_adapter()
                with self.assertRaises(endpoints.DurableEvidenceError):
                    adapter.begin_fresh_read_view()
                commits = bench.db.commits
                out = bench.deploy(adapter)
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["reason_code"], "engine_unavailable")
                self.assertEqual(bench.db.altered(), [])
                self.assertEqual(bench.db.committed, {})
                self.assertEqual(bench.db.commits, commits)

    def test_there_is_no_commit_fallback_without_a_rollback(self):
        bench = _Bench(_NoRollbackDb())
        adapter = bench.new_adapter()
        commits = bench.db.commits
        with self.assertRaises(endpoints.DurableEvidenceError):
            adapter.begin_fresh_read_view()
        self.assertEqual(bench.db.commits, commits, "nothing was committed to get a fresh view")

    def test_a_zero_counter_opens_the_view_with_a_rollback_only(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.view = {}
        commits = bench.db.commits
        adapter.begin_fresh_read_view()
        self.assertIsNone(bench.db.view)
        self.assertEqual(bench.db.commits, commits)


def _frappe_stub(site):
    """A Frappe runtime that resolves ``site`` and an authenticated administrator."""
    from types import SimpleNamespace

    return SimpleNamespace(local=SimpleNamespace(site=site), session=SimpleNamespace(user="admin@example.test"),
                           get_roles=lambda user: ["System Manager", "Sales Manager"])


class TestR3SiteIdentityIsTrustedAndCanonical(unittest.TestCase):
    def test_a_site_that_is_not_canonical_is_refused_before_any_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        for site in ("sité", "موقع", "site-a ", "site a", "s" * 141, "", None):
            with self.subTest(site=site):
                out = execute_single_field_deployment(adapter, "dep_1", "key-1", site, "Item", "rev", dict(FIELD))
                self.assertEqual(out["reason_code"], "invalid_site_id")
        self.assertEqual(bench.db.committed, {})
        with self.assertRaises(endpoints.InvalidDeploymentIdError):
            adapter.persist_prepare_and_audit_intent(_record(site_id="sité"))

    def test_the_resolved_site_is_used_and_a_caller_site_that_differs_is_refused(self):
        from types import SimpleNamespace
        from unittest import mock

        bench = _Bench(statements=[_T + "ADD COLUMN `custom_xyz` varchar(140)"])
        adapter = bench.new_adapter()
        field = {**FIELD, "fieldname": "custom_xyz"}
        with mock.patch.object(endpoints, "frappe", _frappe_stub("Site-A")):
            out = endpoints.apply_configuration_change(
                doctype="Item", deployment_id="dep_1", field_def=field, adapter=adapter, user_roles=ADMIN,
                site_id="other.site")
            self.assertEqual(out["disposition"], "SITE_MISMATCH")
            self.assertEqual(bench.db.altered(), [])
            out = endpoints.apply_configuration_change(
                doctype="Item", deployment_id="dep_1", field_def=field, adapter=adapter, user_roles=ADMIN,
                site_id="site-a ")
            self.assertEqual(out["disposition"], "SITE_MISMATCH", "a collation-equal spelling is still not the resolved site")
            out = endpoints.apply_configuration_change(
                doctype="Item", deployment_id="dep_1", field_def=field, adapter=adapter, user_roles=ADMIN)
            self.assertEqual(out["status"], "APPLIED", out)
            self.assertEqual(bench.db.row("dep_1")["site_id"], "Site-A", "the resolved identity, verbatim")

    def test_a_resolved_site_that_is_not_canonical_is_refused_at_every_rpc(self):
        from types import SimpleNamespace
        from unittest import mock

        bench = _Bench()
        calls, adapter = _entry_points(bench)
        with mock.patch.object(endpoints, "frappe", _frappe_stub("sit\u00e9")):
            for name in ("property_setter", "workflow", "report"):
                with self.subTest(entry_point=name):
                    out = calls[name]()
                    self.assertEqual(out["disposition"], "INVALID_SITE_ID", out)
            out = endpoints.apply_configuration_change(
                doctype="Item", deployment_id="dep_1", field_def={**FIELD, "fieldname": "custom_xyz"},
                adapter=adapter, user_roles=ADMIN)
            self.assertEqual(out["disposition"], "INVALID_SITE_ID")
        self.assertEqual(bench.db.committed, {})


class TestR3FailedRollbackHoldsTheDeployment(unittest.TestCase):
    def _run(self, drift):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        bench.db.readback_values = drift

        def arm():  # the rollback breaks after the engine's own fresh read view was opened
            bench.db.rollback_error = _DbDown(SECRET)

        bench.db.on_set_timeout = arm
        return bench, adapter, bench.deploy(adapter)

    def test_a_rollback_that_fails_holds_the_deployment_and_discards_the_session(self):
        for name, drift in (("at dispatch", [3, 3, 50]), ("before the insert", [3, 50])):
            with self.subTest(drift=name):
                bench, adapter, out = self._run(drift)
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
                self.assertNotEqual(out["status"], "FAILED_CLEAN")
                self.assertNotIn("SECRET", json.dumps(out))
                self.assertEqual(bench.db.altered(), [])
                self.assertTrue(bench.db.closed, "the connection with the unrolled metadata is discarded")
                self.assertTrue(adapter.session_unusable)
                self.assertNotIn("custom_x", bench.db.inserted, "the orphan metadata was never committed")
                row = bench.db.row("dep_1")
                self.assertEqual(row["status"], "PREPARED", "no finalization ran: the hold stands")
                self.assertIsNone(row["outcome_json"])

    def test_the_hold_survives_for_every_later_request(self):
        bench, adapter, _ = self._run([3, 3, 50])
        again = bench.deploy(adapter, dep="dep_2", key="key-2")
        self.assertEqual((again["status"], again["stage"]), ("REJECTED", "ACQUIRE"))
        bench.db.rollback_error = None
        bench.db.closed = False
        fresh = bench.deploy(bench.new_adapter(), dep="dep_3", key="key-3")
        self.assertEqual(fresh["status"], "RECOVERY_REQUIRED")
        self.assertEqual(bench.db.altered(), [])

    def test_a_failed_journal_rollback_before_dispatch_holds_too(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        orig = bench.db._audit
        n = {"i": 0}

        def flaky(q, p, as_dict):
            if q.startswith("INSERT INTO"):
                n["i"] += 1
                if n["i"] == 3:
                    bench.db.rollback_error = _DbDown(SECRET)
                    raise _DbDown("journal unavailable")
            return orig(q, p, as_dict)

        bench.db._audit = flaky
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertTrue(adapter.session_unusable)
        self.assertEqual(bench.db.altered(), [])


class TestR3RevertHoldCheckComesAfterAuthorization(unittest.TestCase):
    def test_an_unauthorised_caller_learns_nothing_about_a_held_deployment(self):
        bench = _Bench()
        _crashed(bench)
        adapter = bench.new_adapter()
        reads = []
        real = adapter.get_deployment_record
        adapter.get_deployment_record = lambda dep: (reads.append(dep), real(dep))[1]
        held = endpoints.revert_configuration_change(deployment_id="dep_1", adapter=adapter, user_roles=["Guest"])
        other = endpoints.revert_configuration_change(deployment_id="dep_unknown", adapter=adapter, user_roles=["Guest"])
        for out in (held, other):
            out.pop("execution_time_ms")
            out.pop("deployment_id")
        self.assertEqual(held, other, "the same refusal as for any other unauthorised revert")
        self.assertEqual(held["disposition"], "UNAUTHORIZED_ROLE")
        self.assertNotIn("Item", json.dumps(held))
        self.assertEqual(reads, [], "the record is not even read for an unauthorised caller")

    def test_an_authorised_caller_still_gets_the_hold(self):
        bench = _Bench()
        _crashed(bench)
        out = endpoints.revert_configuration_change(deployment_id="dep_1", adapter=bench.new_adapter(), user_roles=ADMIN)
        self.assertEqual(out["disposition"], "DEPLOYMENT_ON_HOLD")


# ===========================================================================================
# Revision round 4
# ===========================================================================================
TENANT = "t_alpha"  # what the runtime backend binds as ``site_id`` (the tenant id), not the Frappe host name
HOST = "t-alpha.localhost"
XYZ = {**FIELD, "fieldname": "custom_xyz"}
XYZ_STMT = _T + "ADD COLUMN `custom_xyz` varchar(140)"


class TestR4SiteIdentityIsTheOneTheBackendBinds(unittest.TestCase):
    def _rpc(self, bench, adapter, **kw):
        from unittest import mock

        with mock.patch.object(endpoints, "frappe", _frappe_stub(HOST)):
            return endpoints.apply_configuration_change(
                doctype="Item", field_def=dict(XYZ), adapter=adapter, user_roles=ADMIN, **kw)

    def test_a_replay_record_written_under_the_tenant_id_is_found_through_the_rpc(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        first = bench.deploy(adapter, key="idemp-dep_1", site=TENANT, field=XYZ)  # as the backend writes it
        self.assertEqual(first["status"], "APPLIED")
        out = self._rpc(bench, bench.new_adapter(), deployment_id="dep_2", idempotency_key="idemp-dep_1", site_id=TENANT)
        for key in ("execution_time_ms", "success"):
            out.pop(key, None)
        self.assertEqual(out, first)
        self.assertEqual(len(bench.db.altered()), 1, "no second statement")

    def test_a_hold_written_under_the_tenant_id_is_found_through_the_rpc(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter, key="idemp-dep_1", site=TENANT, field=XYZ)
        bench.db.crash()
        sent = len(bench.db.altered())
        out = self._rpc(bench, bench.new_adapter(), deployment_id="dep_2", idempotency_key="idemp-other", site_id=TENANT)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertEqual(len(bench.db.altered()), sent)

    def test_the_identity_must_belong_to_the_resolved_site_and_be_canonical(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        for site in ("t_beta", "t_alpha ", "other.site", "t_alphà", HOST + "x"):
            with self.subTest(site=site):
                out = self._rpc(bench, adapter, deployment_id="dep_1", site_id=site)
                self.assertIn(out["disposition"], ("SITE_MISMATCH", "INVALID_SITE_ID"))
                self.assertEqual(bench.db.committed, {})
        out = self._rpc(bench, adapter, deployment_id="dep_1", site_id=TENANT)
        self.assertEqual(out["status"], "APPLIED", "the tenant id the backend binds is the identity")


class TestR5OneAuthoritativeSiteIdentity(unittest.TestCase):
    """Round 5 (High): every spelling of one site must map to ONE lock and audit scope, or be refused."""

    _rpc = TestR4SiteIdentityIsTheOneTheBackendBinds._rpc

    def test_aliases_of_the_same_site_are_refused(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        for site in ("t-alpha", HOST, "T_ALPHA", "t-alpha.localhost.", "talpha"):
            with self.subTest(site=site):
                out = self._rpc(bench, adapter, deployment_id="dep_1", site_id=site)
                self.assertIn(out["disposition"], ("SITE_MISMATCH", "INVALID_SITE_ID"), out)
                self.assertEqual(bench.db.committed, {})

    def test_no_caller_identity_uses_the_tenant_id_so_holds_and_replays_still_apply(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter, key="idemp-dep_1", site=TENANT, field=XYZ)
        bench.db.crash()
        sent = len(bench.db.altered())
        out = self._rpc(bench, bench.new_adapter(), deployment_id="dep_2", idempotency_key="idemp-other")
        self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertEqual(len(bench.db.altered()), sent)

    def test_a_legacy_hold_stored_under_the_host_name_still_blocks(self):
        # Round 6 (High): rows written before this change under the host name must stay visible (read-only alias).
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter, key="idemp-dep_1", site=HOST, field=XYZ)
        bench.db.crash()
        sent = len(bench.db.altered())
        for kw in ({}, {"site_id": TENANT}):
            with self.subTest(**kw):
                out = self._rpc(bench, bench.new_adapter(), deployment_id="dep_2", idempotency_key="idemp-other", **kw)
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertEqual(len(bench.db.altered()), sent)

    def test_a_legacy_replay_record_stored_under_the_host_name_still_holds_its_key(self):
        # The legacy row is found, so the key can not run again. Its payload hash was taken with the host name,
        # so the request is refused as a conflict (fail closed), not replayed; no second statement is sent.
        bench = _Bench(statements=[XYZ_STMT])
        first = bench.deploy(bench.new_adapter(), key="idemp-dep_1", site=HOST, field=XYZ)
        self.assertEqual(first["status"], "APPLIED")
        out = self._rpc(bench, bench.new_adapter(), deployment_id="dep_2", idempotency_key="idemp-dep_1")
        self.assertEqual((out["status"], out.get("disposition")), ("REJECTED", "IDEMPOTENCY_CONFLICT"), out)
        self.assertEqual(len(bench.db.altered()), 1, "no second statement")

    def test_the_legacy_alias_never_reaches_another_tenant(self):
        bench = _Bench(statements=[XYZ_STMT])
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter, key="idemp-dep_1", site="t-beta.localhost", field=XYZ)
        bench.db.crash()
        from unittest import mock

        with mock.patch.object(endpoints, "frappe", _frappe_stub(HOST)):
            fresh = bench.new_adapter()
            self.assertFalse(fresh.is_target_in_recovery_required(TENANT, "Item"),
                             "a hold of another site is not this site's hold")
            self.assertIsNone(fresh.get_existing_deployment_by_idempotency(TENANT, "idemp-dep_1"))

    def test_the_legacy_alias_comes_from_an_injected_runtime_too(self):
        # Round 7 (Medium): an adapter with its own Frappe runtime must see the alias even if the global differs.
        from types import SimpleNamespace
        from unittest import mock

        runtime = SimpleNamespace(local=SimpleNamespace(site=HOST))
        with mock.patch.object(endpoints, "frappe", _frappe_stub("other.localhost")):
            self.assertEqual(endpoints._read_site_ids(TENANT, runtime), (TENANT, HOST))
            self.assertEqual(endpoints._read_site_ids("t_beta", runtime), ("t_beta",))
        self.assertEqual(endpoints._read_site_ids(TENANT, SimpleNamespace()), (TENANT,))

    def test_the_offline_simulator_reads_the_alias_list(self):
        # Round 7 (Medium): the simulator answers the three-parameter ``site_id IN (%s, %s)`` replay lookup.
        from change_engine.adapter.simulated_frappe import SimulatedFrappeRuntime

        rt = SimulatedFrappeRuntime()
        rt.ensure_site(HOST)
        rt.connect(HOST)
        rt.local.site = HOST
        adapter = endpoints.FrappeDeploymentAdapter(frappe_module=rt)
        rt.db.sql(f"INSERT INTO `{adapter.audit_table}` VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  ("dep_1", "dep_1", "idemp-dep_1", "h", HOST, "Item", "custom_x", "r", "[]", "APPLIED"))
        rt.db.sql(f"UPDATE `{adapter.audit_table}` SET status = %s, outcome_json = %s WHERE deployment_id = %s",
                  ("APPLIED", '{"status": "APPLIED"}', "dep_1"))
        found = adapter.get_existing_deployment_by_idempotency(TENANT, "idemp-dep_1")
        self.assertEqual(found, {"payload_hash": "h", "outcome": {"status": "APPLIED"}})

    def test_a_site_that_is_not_a_tenant_site_keeps_its_own_name_as_the_only_identity(self):
        from unittest import mock

        bench = _Bench(statements=[XYZ_STMT])
        with mock.patch.object(endpoints, "frappe", _frappe_stub("bench.localhost")):
            ok = endpoints.apply_configuration_change(doctype="Item", field_def=dict(XYZ), adapter=bench.new_adapter(),
                                                      user_roles=ADMIN, deployment_id="dep_1")
            bad = endpoints.apply_configuration_change(doctype="Item", field_def=dict(XYZ), adapter=bench.new_adapter(),
                                                       user_roles=ADMIN, deployment_id="dep_2", site_id="t_bench")
        self.assertEqual(ok["status"], "APPLIED", ok)
        self.assertEqual(bad["disposition"], "SITE_MISMATCH", bad)


def _decimal_style(bench: _Bench, adapter, dep="dep_1", key="idemp-dep_1", site="site-a"):
    """The adapter calls ``FrappeRuntimeBackend._execute_six_stage_field`` makes, in its order."""
    from change_engine.guarded_apply.schema_reconciler import (
        compute_canonical_payload_hash, make_bounded_lock_key, reconcile_exhaustive_snapshot as reconcile)

    adapter.acquire_advisory_lock(make_bounded_lock_key(site, "Item"), wait_seconds=5)
    before = adapter.take_snapshot("Item", "custom_x", expected_deployment_id=dep)
    adapter.persist_prepare_and_audit_intent({
        "deployment_id": dep, "idempotency_key": key, "payload_hash": compute_canonical_payload_hash(site, "Item", FIELD),
        "site_id": site, "doctype": "Item", "fieldname": "custom_x",
        "base_revision_hash": before.revision_hash, "ddl_plan_statements": [STMT], "status": "PREPARED"})
    adapter.set_lock_wait_timeout(3)
    apply_error = None
    try:
        adapter.apply_native_custom_field(dep, "Item", dict(FIELD))
    except Exception as exc:
        apply_error = str(exc)
    after = adapter.take_snapshot("Item", "custom_x", expected_deployment_id=dep)
    outcome = reconcile(dep, "Item", "custom_x", before, after, apply_error)
    adapter.persist_final_outcome_and_audit(dep, {"payload_hash": "h", "outcome": outcome})
    return outcome


def _break_completion_journal(bench: _Bench):
    """The completion journal write fails and the rollback after it fails too (the reviewer's scenario)."""
    orig = bench.db._audit
    n = {"i": 0}

    def flaky(q, p, as_dict):
        if q.startswith("INSERT INTO"):
            n["i"] += 1
            if n["i"] == 4:  # main, baseline, dispatch intent, then the completion row
                bench.db.rollback_error = _DbDown(SECRET)
                raise _DbDown("journal unavailable")
        return orig(q, p, as_dict)

    bench.db._audit = flaky


class TestR4NothingCommitsOnADiscardedSession(unittest.TestCase):
    def test_native_apply_does_not_commit_or_finalize_after_the_session_is_discarded(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        _break_completion_journal(bench)
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
        self.assertEqual(out["reason_code"], "session_discarded")
        self.assertTrue(bench.db.closed)
        self.assertEqual(bench.db.commits, bench.db.commits_at_close, "no commit after the connection was discarded")
        row = bench.db.row("dep_1")
        self.assertEqual(row["status"], "PREPARED")
        self.assertIsNone(row["outcome_json"])

    def test_the_decimal_path_cannot_finalize_over_a_discarded_session(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        _break_completion_journal(bench)
        with self.assertRaises(endpoints.SessionDiscardedError):
            _decimal_style(bench, adapter)
        self.assertEqual(bench.db.commits, bench.db.commits_at_close)
        row = bench.db.row("dep_1")
        self.assertEqual((row["status"], row["outcome_json"]), ("PREPARED", None), "the hold stands")

    def test_every_commit_finalize_and_write_refuses_on_a_discarded_session(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.mark_session_unusable()
        for call in (
            lambda: adapter.persist_final_outcome_and_audit("dep_1", {"outcome": {"status": "APPLIED"}}),
            lambda: adapter.mark_recovery_required("dep_1", "x"),
            lambda: adapter.persist_prepare_and_audit_intent(_record(ddl_plan_statements=[STMT])),
            lambda: adapter.apply_native_custom_field("dep_1", "Item", dict(FIELD)),
            lambda: adapter._commit_durable(),
        ):
            with self.assertRaises(endpoints.SessionDiscardedError):
                call()
        self.assertEqual(bench.db.altered(), [])

    def test_native_apply_refuses_to_commit_when_the_lock_is_no_longer_held(self):
        from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

        bench = _Bench()
        adapter = bench.new_adapter()
        key = make_bounded_lock_key("site-a", "Item")
        self.assertEqual(adapter.acquire_advisory_lock(key, wait_seconds=5), 1)
        adapter.take_snapshot("Item", "custom_x", "dep_1")
        adapter.persist_prepare_and_audit_intent(_record(fieldname="custom_x", ddl_plan_statements=[STMT]))
        bench.db.locks.clear()  # the server dropped the lock before the apply
        commits = bench.db.commits
        with self.assertRaises(endpoints.SessionDiscardedError):
            adapter.apply_native_custom_field("dep_1", "Item", dict(FIELD))
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.commits, commits)


class TestR4AFailedCloseNeverReportsASuccessfulRelease(unittest.TestCase):
    def test_release_is_unverified_while_the_discard_has_not_worked(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.close_error = _DbDown(SECRET)
        adapter.mark_session_unusable()
        self.assertTrue(adapter.session_unusable)
        self.assertFalse(adapter.release_advisory_lock("ce:v1:any"), "the lock may still be held")
        bench.db.close_error = None
        self.assertTrue(adapter.release_advisory_lock("ce:v1:any"), "the retried close worked: the lock is freed")

    def test_a_deployment_whose_close_failed_stays_unusable_on_hold_and_retries_the_discard(self):
        bench = _Bench(meta_first=True)
        adapter = bench.new_adapter()
        _break_completion_journal(bench)
        bench.db.close_error = _DbDown(SECRET)
        results = []
        real = adapter.release_advisory_lock
        adapter.release_advisory_lock = lambda k: (results.append(real(k)), results[-1])[1]
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertTrue(results and not any(results), "no release is reported as successful")
        self.assertTrue(adapter.session_unusable)
        self.assertEqual(bench.db.row("dep_1")["status"], "PREPARED")
        again = bench.deploy(adapter, dep="dep_2", key="key-2")
        self.assertEqual((again["status"], again["stage"]), ("REJECTED", "ACQUIRE"))


if __name__ == "__main__":
    unittest.main()
