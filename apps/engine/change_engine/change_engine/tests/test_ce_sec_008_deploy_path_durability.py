"""CE-SEC-008 part 1: durability of today's guarded deploy path (Tier 3, G1).

Defects found in the #309 reviews, each pinned by a test here:
  * the baseline schema and the approved/executed statements lived only in instance dicts;
  * a statement was recorded as "executed" before it took effect;
  * the Stage 3 intent was an upsert that could overwrite an older record;
  * the idempotency and recovery lookups answered "none" on a database error;
  * the lock-timeout setter swallowed errors and never read the setting back.

The live-mode database double below models what matters for durability: writes are pending until
``commit()``, a DDL statement implicitly commits (as MariaDB does), ``crash()`` drops everything
uncommitted, and faults can be injected on any statement. Synthetic data only; no server needed.
Part 2 (deployment-id counter, adapter files) is not covered here.
"""
from __future__ import annotations

import json
import os
import re
import sys
import types
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.api import endpoints  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.ddl_plan_gate import DDLPlanInspection  # noqa: E402
from change_engine.guarded_apply.schema_reconciler import (  # noqa: E402
    IdempotencyConflictError,
    execute_single_field_deployment,
)
from change_engine.tests.test_erp_027_decimal_drift import _ADD, _T, _LiveDb, _col  # noqa: E402

STMT = _T + _ADD
FIELD = {"fieldname": "custom_x", "fieldtype": "Data", "label": "X"}
AUDIT = "tabChange Engine Audit"


class _Crash(BaseException):
    """Process death: it is not an ``Exception``, so no ``except Exception`` can absorb it."""


class _DbDown(Exception):
    pass


class _DurableDb(_LiveDb):
    """Live ``frappe.db`` double with a transactional audit table and fault injection."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.committed: dict[str, dict] = {}
        self.pending: list[tuple] = []
        self.faults: list[dict] = []
        self.before_ddl = None
        self.crash_before_ddl = False
        self.crash_after_ddl = False
        self.lock_wait_timeout = 50
        self.ignore_timeout_set = False
        self.readback = "value"  # "value" | "empty"
        self.locks: set[str] = set()
        self.commits = 0

    # -- transaction model ---------------------------------------------------------------
    def commit(self):
        for op in self.pending:
            if op[0] == "insert":
                self.committed[op[1]] = op[2]
            else:
                _, dep, fields = op
                for row in self.committed.values():
                    if row["deployment_id"] == dep:
                        row.update(fields)
        self.pending = []
        self.commits += 1

    def rollback(self):
        self.pending = []

    def crash(self):
        """Process death: whatever was not committed is gone, and the server drops the session lock."""
        self.pending = []
        self.locks.clear()

    def _visible(self) -> dict[str, dict]:
        rows = {k: dict(v) for k, v in self.committed.items()}
        for op in self.pending:
            if op[0] == "insert":
                rows[op[1]] = dict(op[2])
            else:
                for row in rows.values():
                    if row["deployment_id"] == op[1]:
                        row.update(op[2])
        return rows

    # -- fault injection -----------------------------------------------------------------
    def fail(self, fragment: str, exc: Exception | None = None, times: int = 1_000_000):
        self.faults.append({"fragment": fragment.upper(), "exc": exc or _DbDown("database unavailable"), "left": times})

    def _maybe_fail(self, q: str):
        for f in self.faults:
            if f["left"] > 0 and f["fragment"] in q:
                f["left"] -= 1
                raise f["exc"]

    # -- SQL -----------------------------------------------------------------------------
    def sql(self, query, values=None, as_dict=False):
        q = " ".join(query.upper().split())
        self._maybe_fail(q)
        if "INFORMATION_SCHEMA.COLUMNS" in q and "COLUMN_NAME = %S" in q:  # does the physical column exist?
            self.sql_log.append(query)
            return ((values[1], "varchar(140)"),) if values[1] in self.schema["columns"] else ()
        if q.startswith("SELECT GET_LOCK"):
            self.sql_log.append(query)
            if values[0] in self.locks:
                return ((0,),)
            self.locks.add(values[0])
            return ((1,),)
        if q.startswith("SELECT RELEASE_LOCK"):
            self.sql_log.append(query)
            self.locks.discard(values[0])
            return ((1,),)
        if q.startswith("SET SESSION LOCK_WAIT_TIMEOUT"):
            self.sql_log.append(query)
            if not self.ignore_timeout_set:
                self.lock_wait_timeout = int(re.search(r"=\s*(\d+)", q).group(1))
            return ()
        if q.startswith("SELECT @@SESSION.LOCK_WAIT_TIMEOUT"):
            self.sql_log.append(query)
            return () if self.readback == "empty" else ((self.lock_wait_timeout,),)
        if q.startswith("CREATE TABLE IF NOT EXISTS"):
            self.sql_log.append(query)
            self.commit()  # DDL commits implicitly
            return ()
        if q.startswith("ALTER TABLE"):
            self.sql_log.append(query)
            if self.before_ddl:
                self.before_ddl(query)
            if self.crash_before_ddl:
                raise _Crash("before DDL took effect")
            self.commit()  # implicit commit
            m = re.search(r"ADD COLUMN `(\w+)`", query)
            if m:
                self.schema["columns"][m.group(1)] = _col()
                self.schema["order"].append(m.group(1))
            if self.crash_after_ddl:
                raise _Crash("after DDL took effect, before it returned")
            return ()
        if f"`{AUDIT.upper()}`" in q:
            self.sql_log.append(query)
            return self._audit(q, values, as_dict)
        return super().sql(query, values)

    def _audit(self, q, p, as_dict):
        rows = self._visible()
        if q.startswith("INSERT INTO"):
            name = p[0]
            row = {
                "name": name, "deployment_id": p[1], "idempotency_key": p[2], "payload_hash": p[3],
                "site_id": p[4], "doctype": p[5], "fieldname": p[6], "base_revision_hash": p[7],
                "ddl_plan_statements": p[8], "status": p[9], "outcome_json": None,
            }
            if name in rows:
                if "ON DUPLICATE KEY UPDATE" in q:  # the old upsert
                    self.pending.append(("update", rows[name]["deployment_id"], {
                        "idempotency_key": p[2], "payload_hash": p[3], "status": p[9]}))
                    return ()
                raise RuntimeError(f"(1062, \"Duplicate entry '{name}' for key 'PRIMARY'\")")
            self.pending.append(("insert", name, row))
            return ()
        if q.startswith("UPDATE"):
            if "SET STATUS = 'RECOVERY_REQUIRED'" in q:
                outcome_json, dep = p
                fields = {"status": "RECOVERY_REQUIRED", "outcome_json": outcome_json}
            else:
                status, outcome_json, dep = p
                fields = {"status": status, "outcome_json": outcome_json}
            self.pending.append(("update", dep, fields))
            return ()
        if "SELECT COUNT(*)" in q:
            site, doctype = p
            n = sum(1 for r in rows.values()
                    if r["site_id"] == site and r["doctype"] == doctype
                    and r["status"] in ("RECOVERY_REQUIRED", "PREPARED"))
            return ((n,),)
        if "SELECT PAYLOAD_HASH, OUTCOME_JSON" in q:
            site, key = p
            return tuple((r["payload_hash"], r["outcome_json"]) for r in rows.values()
                         if r["site_id"] == site and r["idempotency_key"] == key and r["outcome_json"] is not None)
        if "WHERE IDEMPOTENCY_KEY = %S" in q and "SELECT NAME" in q:
            hit = sorted((r for r in rows.values() if r["idempotency_key"] == p[0]), key=lambda r: r["name"])
            return tuple((r["name"], r["status"], r["ddl_plan_statements"]) for r in hit)
        if "WHERE DEPLOYMENT_ID = %S" in q:
            hit = [r for r in rows.values() if r["deployment_id"] == p[0]]
            return tuple(dict(r) for r in hit) if as_dict else tuple(tuple(r.values()) for r in hit)
        raise AssertionError(f"unmodelled audit query: {q}")

    # -- helpers for assertions ----------------------------------------------------------
    def row(self, dep: str, committed_only: bool = True) -> dict | None:
        src = self.committed if committed_only else self._visible()
        return next((r for r in src.values() if r["deployment_id"] == dep), None)

    def evidence(self, dep: str, committed_only: bool = True) -> list[dict]:
        src = self.committed if committed_only else self._visible()
        return [r for r in src.values() if r["idempotency_key"] == f"{dep}#evidence"]

    def altered(self) -> list[str]:
        return [q for q in self.sql_log if q.upper().startswith("ALTER TABLE")]


class _Bench:
    """One database that outlives adapters: ``new_adapter()`` is a process restart."""

    def __init__(self, db: _DurableDb | None = None, statements=None):
        self.db = db or _DurableDb()
        self.statements = [STMT] if statements is None else statements
        self.module = types.SimpleNamespace(db=self.db, clear_cache=lambda **kw: None, get_doc=self._get_doc)

    def _get_doc(self, args):
        field = args["fieldname"]

        def insert(ignore_permissions=True):
            for stmt in self.statements:
                self.db.sql_ddl(stmt)  # through the adapter's recorder
            self.db.inserted.add(field)

        return types.SimpleNamespace(insert=insert)

    def new_adapter(self) -> FrappeDeploymentAdapter:
        plan = DDLPlanInspection(inspectable=True, statements=list(self.statements), is_approved_additive_only=True)
        return FrappeDeploymentAdapter(frappe_module=self.module, in_memory=False, ddl_plan=plan, use_shared_state=False)

    def deploy(self, adapter, *, dep="dep_1", key="key-1", field=None):
        return execute_single_field_deployment(
            adapter, dep, key, "site-a", "Item", adapter.get_doctype_revision_hash("Item"), dict(field or FIELD))


def _stages(db: _DurableDb) -> list[str]:
    return [q for q in db.sql_log if q.upper().startswith(("ALTER", "INSERT", "SET SESSION", "SELECT @@"))]


# ===========================================================================================
class TestEvidenceIsDurableBeforeAnythingTakesEffect(unittest.TestCase):
    def test_baseline_approved_statements_and_dispatch_intent_are_committed_before_the_statement_is_sent(self):
        bench = _Bench()
        seen = {}

        def at_ddl(query):
            seen["committed"] = {k: dict(v) for k, v in bench.db.committed.items()}
            seen["executed"] = list(bench.adapter._executed_ddl.get("dep_1", []))
            seen["dispatched"] = list(bench.adapter._dispatched_ddl.get("dep_1", []))

        bench.db.before_ddl = at_ddl
        bench.adapter = bench.new_adapter()
        out = bench.deploy(bench.adapter)
        self.assertEqual(out["status"], "APPLIED", out)

        rows = list(seen["committed"].values())
        main = next(r for r in rows if r["deployment_id"] == "dep_1")
        self.assertEqual(main["status"], "PREPARED")
        self.assertEqual(json.loads(main["ddl_plan_statements"]), [STMT], "approved plan is durable first")
        kinds = {json.loads(r["ddl_plan_statements"]).get("kind") for r in rows if r["idempotency_key"] == "dep_1#evidence"}
        self.assertIn("baseline", kinds)
        self.assertIn("dispatch_intent", kinds, "the dispatch intent is committed before the statement is sent")
        self.assertNotIn("dispatch_completed", kinds, "nothing is recorded complete before it took effect")
        self.assertEqual(seen["executed"], [], "never recorded as executed before it takes effect")
        self.assertEqual(seen["dispatched"], [STMT])

    def test_statement_is_recorded_executed_only_after_it_returned(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self.assertEqual(bench.deploy(adapter)["status"], "APPLIED")
        self.assertEqual(adapter._dispatched_ddl["dep_1"], [STMT])
        self.assertEqual(adapter._executed_ddl["dep_1"], [STMT])
        kinds = [json.loads(r["ddl_plan_statements"])["kind"] for r in bench.db.evidence("dep_1")]
        self.assertEqual(sorted(kinds), ["baseline", "dispatch_completed", "dispatch_intent"])

    def test_a_statement_that_failed_is_dispatched_but_never_executed_or_completed(self):
        bench = _Bench()
        bench.db.fail("ALTER TABLE", _DbDown("metadata lock wait timeout"))
        adapter = bench.new_adapter()
        bench.deploy(adapter)
        self.assertEqual(adapter._dispatched_ddl["dep_1"], [STMT])
        self.assertEqual(adapter._executed_ddl["dep_1"], [])
        kinds = sorted(json.loads(r["ddl_plan_statements"])["kind"] for r in bench.db.evidence("dep_1"))
        self.assertEqual(kinds, ["baseline", "dispatch_intent"])

    def test_the_main_row_stays_prepared_and_carries_no_outcome_until_finalize(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("before finalize"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter)
        row = bench.db.row("dep_1")
        self.assertEqual(row["status"], "PREPARED")
        self.assertIsNone(row["outcome_json"], "intent is not completion truth")

    def test_baseline_write_failure_runs_nothing_and_leaves_no_stuck_intent(self):
        bench = _Bench()
        bench.db.fail("INSERT INTO", _DbDown("disk full"), times=1_000_000)
        adapter = bench.new_adapter()
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "FAILED_CLEAN")
        self.assertEqual(out["stage"], "PREPARE")
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.committed, {})
        self.assertNotIn("dep_1", adapter._approved_ddl)

    def test_second_evidence_row_failing_rolls_back_the_intent_too(self):
        bench = _Bench()
        calls = {"n": 0}
        orig = bench.db._audit

        def flaky(q, p, as_dict):
            if q.startswith("INSERT INTO"):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise _DbDown("connection lost mid-transaction")
            return orig(q, p, as_dict)

        bench.db._audit = flaky
        adapter = bench.new_adapter()
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "FAILED_CLEAN")
        self.assertEqual(bench.db.committed, {}, "no half-written intent may block or mislead later")
        self.assertEqual(bench.db.altered(), [])

    def test_missing_baseline_refuses_the_intent_in_live_mode(self):
        bench = _Bench()
        adapter = bench.new_adapter()  # no before-snapshot was taken
        with self.assertRaises(endpoints.DurableEvidenceError):
            adapter.persist_prepare_and_audit_intent({
                "deployment_id": "dep_1", "idempotency_key": "key-1", "payload_hash": "h", "site_id": "site-a",
                "doctype": "Item", "fieldname": "custom_x", "base_revision_hash": "r",
                "ddl_plan_statements": [STMT], "status": "PREPARED"})
        self.assertEqual(bench.db.committed, {})

    def test_dispatch_intent_write_failure_means_the_statement_is_never_sent(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        orig = bench.db._audit
        n = {"i": 0}

        def flaky(q, p, as_dict):
            if q.startswith("INSERT INTO"):
                n["i"] += 1
                if n["i"] == 3:  # main, baseline, then the dispatch intent
                    raise _DbDown("journal unavailable")
            return orig(q, p, as_dict)

        bench.db._audit = flaky
        out = bench.deploy(adapter)
        self.assertEqual(bench.db.altered(), [], "no durable intent, no statement")
        self.assertNotEqual(out["status"], "APPLIED")
        self.assertEqual(adapter._dispatched_ddl["dep_1"], [])

    def test_completion_write_failure_never_makes_a_statement_look_unrun(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        orig = bench.db._audit
        n = {"i": 0}

        def flaky(q, p, as_dict):
            if q.startswith("INSERT INTO"):
                n["i"] += 1
                if n["i"] == 4:  # the completion row
                    raise _DbDown("journal unavailable")
            return orig(q, p, as_dict)

        bench.db._audit = flaky
        bench.deploy(adapter)
        kinds = sorted(json.loads(r["ddl_plan_statements"])["kind"] for r in bench.db.evidence("dep_1"))
        self.assertEqual(kinds, ["baseline", "dispatch_intent"], "intent is durable, completion is not claimed")
        self.assertEqual(len(bench.db.altered()), 1)


class TestCrashRecoveryEvidence(unittest.TestCase):
    def _crash_at(self, how):
        bench = _Bench()
        adapter = bench.new_adapter()
        if how == "before_ddl":
            bench.db.crash_before_ddl = True
        elif how == "during_ddl":
            bench.db.crash_after_ddl = True
        elif how == "before_finalize":
            adapter.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(adapter)
        bench.db.crash()
        bench.db.crash_before_ddl = bench.db.crash_after_ddl = False
        return bench, bench.new_adapter()

    def test_crash_before_the_statement_leaves_a_blocked_prepared_target_and_a_durable_baseline(self):
        bench, restarted = self._crash_at("before_ddl")
        self.assertTrue(restarted.is_target_in_recovery_required("site-a", "Item"))
        ev = restarted.load_durable_evidence("dep_1")
        self.assertEqual(ev["approved"], [STMT])
        self.assertEqual(ev["dispatched"], [STMT], "intent was committed before the statement was sent")
        self.assertEqual(ev["completed"], [])
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertFalse(snap.has_col)
        self.assertFalse(snap.unapproved_side_effects)
        self.assertEqual(bench.db.altered(), [STMT])  # only the one attempt that crashed

    def test_crash_while_the_statement_took_effect_is_intent_without_completion(self):
        bench, restarted = self._crash_at("during_ddl")
        ev = restarted.load_durable_evidence("dep_1")
        self.assertEqual(ev["dispatched"], [STMT])
        self.assertEqual(ev["completed"], [], "the crash hid the return: completion is not claimed")
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertTrue(snap.has_col, "the physical column is there")
        self.assertFalse(snap.has_meta, "but the engine metadata is not")
        self.assertTrue(restarted.is_target_in_recovery_required("site-a", "Item"))

    def test_crash_between_ddl_and_finalize_reads_the_durable_baseline_not_the_post_ddl_schema(self):
        bench, restarted = self._crash_at("before_finalize")
        baseline_row = next(r for r in bench.db.evidence("dep_1")
                            if json.loads(r["ddl_plan_statements"])["kind"] == "baseline")
        before_blob = baseline_row["ddl_plan_statements"]
        self.assertNotIn("custom_x", before_blob, "the baseline predates the DDL")

        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertTrue(snap.has_col)
        self.assertTrue(snap.has_meta)
        self.assertTrue(snap.definition_matches)
        self.assertFalse(snap.unapproved_side_effects, "approved plan, durable baseline and live schema agree")
        self.assertEqual(baseline_row["ddl_plan_statements"], before_blob, "a restart never rewrites the baseline")
        self.assertEqual(bench.db.row("dep_1")["status"], "PREPARED")

    def test_restart_with_an_unapproved_extra_column_is_flagged_from_the_durable_baseline(self):
        bench, restarted = self._crash_at("before_finalize")
        bench.db.schema["columns"]["custom_sneaky"] = _col()
        bench.db.schema["order"].append("custom_sneaky")
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertTrue(snap.unapproved_side_effects)

    def test_baseline_roundtrips_exactly(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.take_snapshot("Item", "custom_x", "dep_1")
        original = adapter._before_schema[("Item", "dep_1")]
        adapter.persist_prepare_and_audit_intent({
            "deployment_id": "dep_1", "idempotency_key": "k", "payload_hash": "h", "site_id": "site-a",
            "doctype": "Item", "fieldname": "custom_x", "base_revision_hash": "r",
            "ddl_plan_statements": [STMT], "status": "PREPARED"})
        self.assertEqual(bench.new_adapter().load_durable_evidence("dep_1")["baseline"], original)

    def test_repeated_request_after_a_crash_is_blocked_and_sends_no_statement(self):
        bench, restarted = self._crash_at("before_finalize")
        sent = len(bench.db.altered())
        out = bench.deploy(restarted)
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")
        self.assertEqual(out["stage"], "INSPECT")
        out = bench.deploy(restarted, dep="dep_2", key="key-2")  # a different request on the same target
        self.assertEqual(out["status"], "RECOVERY_REQUIRED")
        self.assertEqual(len(bench.db.altered()), sent)

    def test_evidence_that_cannot_be_read_or_is_incomplete_fails_closed_on_restart(self):
        bench, restarted = self._crash_at("before_finalize")
        bench.db.fail("WHERE IDEMPOTENCY_KEY = %S")
        with self.assertRaises(_DbDown):
            restarted.load_durable_evidence("dep_1")
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertTrue(snap.unapproved_side_effects, "unreadable evidence is never read as clean")
        self.assertEqual(snap.revision_hash, "rev_error")

    def test_a_missing_baseline_row_fails_closed(self):
        bench, restarted = self._crash_at("before_finalize")
        for name in [k for k, r in bench.db.committed.items()
                     if r["idempotency_key"] == "dep_1#evidence"
                     and json.loads(r["ddl_plan_statements"])["kind"] == "baseline"]:
            del bench.db.committed[name]
        snap = restarted.take_snapshot("Item", "custom_x", "dep_1")
        self.assertTrue(snap.unapproved_side_effects)
        self.assertEqual(snap.revision_hash, "rev_error")

    def test_a_journal_with_a_gap_is_refused(self):
        bench, restarted = self._crash_at("before_finalize")
        for name, r in list(bench.db.committed.items()):
            if r["idempotency_key"] == "dep_1#evidence" and json.loads(r["ddl_plan_statements"])["kind"] == "dispatch_intent":
                del bench.db.committed[name]
        with self.assertRaises(endpoints.DurableEvidenceError):
            restarted.load_durable_evidence("dep_1")


class TestRepeatedAndConflictingRequests(unittest.TestCase):
    def test_identical_request_returns_the_stored_outcome_with_no_new_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        first = bench.deploy(adapter)
        self.assertEqual(first["status"], "APPLIED")
        rows = {k: dict(v) for k, v in bench.db.committed.items()}
        again = bench.deploy(bench.new_adapter(), dep="dep_2")  # also after a restart
        self.assertEqual(again, first)
        self.assertEqual(len(bench.db.altered()), 1)
        self.assertEqual(bench.db.committed, rows, "a replay writes nothing")

    def test_same_key_with_another_payload_is_a_conflict_with_no_effect(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.deploy(adapter)
        with self.assertRaises(IdempotencyConflictError):
            bench.deploy(adapter, dep="dep_2", field={**FIELD, "label": "Other"})
        self.assertEqual(len(bench.db.altered()), 1)

    def test_a_repeated_deployment_id_for_another_request_cannot_overwrite_the_old_record(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        first = bench.deploy(adapter, dep="dep_1", key="key-1")
        old = dict(bench.db.row("dep_1"))
        bench.statements = [_T + "ADD COLUMN `custom_y` varchar(140)"]
        out = execute_single_field_deployment(
            bench.new_adapter(), "dep_1", "key-2", "site-a", "Item",
            bench.new_adapter().get_doctype_revision_hash("Item"), {**FIELD, "fieldname": "custom_y"})
        self.assertNotEqual(out["status"], "APPLIED")
        self.assertEqual(out["stage"], "PREPARE")
        self.assertEqual(bench.db.row("dep_1"), old, "the older record is untouched")
        self.assertEqual(first["status"], "APPLIED")
        self.assertEqual(len(bench.db.altered()), 1, "no second statement was sent")


class TestStrictStageThreeIntent(unittest.TestCase):
    def _record(self, **over):
        rec = {"deployment_id": "dep_1", "idempotency_key": "key-1", "payload_hash": "hash-1", "site_id": "site-a",
               "doctype": "Item", "fieldname": "custom_x", "base_revision_hash": "r1",
               "ddl_plan_statements": [STMT], "status": "PREPARED"}
        rec.update(over)
        return rec

    def _live(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.take_snapshot("Item", "custom_x", "dep_1")
        return bench, adapter

    def test_live_mismatched_binding_is_rejected_and_the_older_record_is_unchanged(self):
        bench, adapter = self._live()
        adapter.persist_prepare_and_audit_intent(self._record())
        old = {k: dict(v) for k, v in bench.db.committed.items()}
        for over in ({"idempotency_key": "key-2"}, {"payload_hash": "hash-2"}, {"site_id": "site-b"},
                     {"ddl_plan_statements": [_T + "ADD COLUMN `custom_z` int"]}):
            with self.subTest(over=over):
                with self.assertRaises(endpoints.DeploymentIntentConflictError) as cm:
                    adapter.persist_prepare_and_audit_intent(self._record(**over))
                self.assertEqual(cm.exception.reason, "binding_mismatch")
                self.assertEqual(bench.db.committed, old)

    def test_live_identical_binding_is_not_a_second_intent_either(self):
        bench, adapter = self._live()
        adapter.persist_prepare_and_audit_intent(self._record())
        old = {k: dict(v) for k, v in bench.db.committed.items()}
        with self.assertRaises(endpoints.DeploymentIntentConflictError) as cm:
            adapter.persist_prepare_and_audit_intent(self._record())
        self.assertEqual(cm.exception.reason, "already_recorded")
        self.assertEqual(bench.db.committed, old)

    def test_live_intent_is_a_plain_insert_never_an_upsert(self):
        bench, adapter = self._live()
        adapter.persist_prepare_and_audit_intent(self._record())
        inserts = [q for q in bench.db.sql_log if q.lstrip().upper().startswith("INSERT")]
        self.assertTrue(inserts)
        self.assertFalse(any("ON DUPLICATE KEY" in q.upper() for q in inserts))

    def test_a_failed_conflict_lookup_still_refuses(self):
        bench, adapter = self._live()
        adapter.persist_prepare_and_audit_intent(self._record())
        bench.db.fail("WHERE DEPLOYMENT_ID = %S")
        with self.assertRaises(Exception):
            adapter.persist_prepare_and_audit_intent(self._record(idempotency_key="key-2"))
        self.assertEqual(bench.db.row("dep_1")["idempotency_key"], "key-1")

    def test_in_memory_mismatched_binding_is_rejected_and_the_older_record_is_unchanged(self):
        adapter = FrappeDeploymentAdapter(in_memory=True, use_shared_state=False)
        adapter.persist_prepare_and_audit_intent(self._record())
        old = json.loads(json.dumps(adapter.audit_journal, default=str))
        with self.assertRaises(endpoints.DeploymentIntentConflictError):
            adapter.persist_prepare_and_audit_intent(self._record(idempotency_key="key-2", payload_hash="other"))
        with self.assertRaises(endpoints.DeploymentIntentConflictError):
            adapter.persist_prepare_and_audit_intent(self._record())
        self.assertEqual(json.loads(json.dumps(adapter.audit_journal, default=str)), old)
        self.assertEqual(adapter.idempotency_store[("site-a", "key-1")]["payload_hash"], "hash-1")


class TestDatabaseErrorsBlockAndAreNeverAbsent(unittest.TestCase):
    def test_idempotency_lookup_raises_on_a_database_error(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        for exc in (_DbDown("gone away"), TimeoutError("(1205, 'Lock wait timeout exceeded')"), RuntimeError("1213")):
            with self.subTest(exc=type(exc).__name__):
                bench.db.faults.clear()
                bench.db.fail("SELECT PAYLOAD_HASH", exc)
                with self.assertRaises(type(exc)):
                    adapter.get_existing_deployment_by_idempotency("site-a", "key-1")

    def test_idempotency_lookup_answers_none_only_when_it_really_found_nothing(self):
        bench = _Bench()
        self.assertIsNone(bench.new_adapter().get_existing_deployment_by_idempotency("site-a", "never-used"))

    def test_an_unparseable_stored_outcome_blocks_instead_of_reading_as_absent(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.committed["x"] = {
            "name": "x", "deployment_id": "x", "idempotency_key": "key-1", "payload_hash": "h", "site_id": "site-a",
            "doctype": "Item", "fieldname": "f", "base_revision_hash": "r", "ddl_plan_statements": "[]",
            "status": "APPLIED", "outcome_json": "{not json"}
        with self.assertRaises(ValueError):
            adapter.get_existing_deployment_by_idempotency("site-a", "key-1")

    def test_recovery_lookup_raises_on_a_database_error(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.fail("SELECT COUNT(*)", _DbDown("gone away"))
        with self.assertRaises(_DbDown):
            adapter.is_target_in_recovery_required("site-a", "Item")

    def test_recovery_lookup_still_reports_a_blocked_target(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        self.assertFalse(adapter.is_target_in_recovery_required("site-a", "Item"))
        bench.db.committed["x"] = {
            "name": "x", "deployment_id": "x", "idempotency_key": "k", "payload_hash": "h", "site_id": "site-a",
            "doctype": "Item", "fieldname": "f", "base_revision_hash": "r", "ddl_plan_statements": "[]",
            "status": "PREPARED", "outcome_json": None}
        self.assertTrue(adapter.is_target_in_recovery_required("site-a", "Item"))

    def test_deploy_is_blocked_with_no_effect_when_the_idempotency_lookup_fails(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.fail("SELECT PAYLOAD_HASH")
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["stage"], "INSPECT")
        self.assertEqual(out["reason_code"], "engine_unavailable")
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.committed, {})
        self.assertEqual(bench.db.locks, set(), "the advisory lock is released")

    def test_deploy_is_blocked_with_no_effect_when_the_recovery_lookup_fails(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.fail("SELECT COUNT(*)")
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "REJECTED")
        self.assertEqual(out["reason_code"], "engine_unavailable")
        self.assertEqual(bench.db.altered(), [])
        self.assertEqual(bench.db.committed, {})

    def test_an_outage_never_lets_a_blocked_target_deploy(self):
        bench = _Bench()
        crashed = bench.new_adapter()
        crashed.persist_final_outcome_and_audit = lambda *a, **k: (_ for _ in ()).throw(_Crash("x"))
        with self.assertRaises(_Crash):
            bench.deploy(crashed)
        bench.db.crash()
        sent = len(bench.db.altered())
        bench.db.fail("SELECT COUNT(*)")
        out = bench.deploy(bench.new_adapter(), dep="dep_2", key="key-2")
        self.assertNotEqual(out["status"], "APPLIED")
        self.assertEqual(len(bench.db.altered()), sent)


class TestLockTimeoutSetterVerifiesTheEffectiveSetting(unittest.TestCase):
    def test_setter_applies_reads_back_and_records_the_effective_value(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        adapter.set_lock_wait_timeout(3)
        self.assertEqual(bench.db.lock_wait_timeout, 3)
        self.assertEqual(adapter.lock_wait_timeout_seconds, 3)
        self.assertTrue(any("@@SESSION.lock_wait_timeout" in q for q in bench.db.sql_log))

    def test_setter_raises_when_the_statement_fails(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.fail("SET SESSION LOCK_WAIT_TIMEOUT", _DbDown("gone away"))
        with self.assertRaises(endpoints.LockTimeoutError):
            adapter.set_lock_wait_timeout(3)
        self.assertIsNone(adapter.lock_wait_timeout_seconds, "nothing is claimed as effective")

    def test_setter_raises_when_the_read_back_differs(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.ignore_timeout_set = True  # the server kept 50
        with self.assertRaises(endpoints.LockTimeoutError):
            adapter.set_lock_wait_timeout(3)
        self.assertIsNone(adapter.lock_wait_timeout_seconds)

    def test_setter_raises_when_the_read_back_is_missing_or_fails(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.db.readback = "empty"
        with self.assertRaises(endpoints.LockTimeoutError):
            adapter.set_lock_wait_timeout(3)
        bench.db.readback = "value"
        bench.db.fail("SELECT @@SESSION")
        with self.assertRaises(endpoints.LockTimeoutError):
            adapter.set_lock_wait_timeout(3)

    def test_setter_refuses_values_that_are_not_a_positive_integer_before_any_sql(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        before = len(bench.db.sql_log)
        for bad in (0, -1, True, 3.5, "3", None, 10 ** 12):
            with self.subTest(bad=bad):
                with self.assertRaises(endpoints.LockTimeoutError):
                    adapter.set_lock_wait_timeout(bad)
        self.assertEqual(len(bench.db.sql_log), before)

    def test_deploy_sends_no_statement_and_leaves_no_intent_when_the_timeout_cannot_be_set(self):
        for fault in ("set", "mismatch"):
            with self.subTest(fault=fault):
                bench = _Bench()
                adapter = bench.new_adapter()
                if fault == "set":
                    bench.db.fail("SET SESSION LOCK_WAIT_TIMEOUT")
                else:
                    bench.db.ignore_timeout_set = True
                out = bench.deploy(adapter)
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["reason_code"], "lock_timeout_not_effective")
                self.assertEqual(bench.db.altered(), [])
                self.assertEqual(bench.db.committed, {}, "no PREPARED row is left blocking the target")
                self.assertEqual(bench.db.locks, set())

    def test_in_memory_setter_records_the_value(self):
        adapter = FrappeDeploymentAdapter(in_memory=True, use_shared_state=False)
        adapter.set_lock_wait_timeout(7)
        self.assertEqual(adapter.lock_wait_timeout_seconds, 7)


if __name__ == "__main__":
    unittest.main()
