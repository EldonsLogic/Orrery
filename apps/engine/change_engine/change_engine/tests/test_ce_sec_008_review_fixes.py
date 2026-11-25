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


if __name__ == "__main__":
    unittest.main()
