"""ERP-026 review fixes (PR 126): atomic key reservation, transactional finalize, crash recovery, production guard.

Guard tests need nothing. Multi-worker tests need a MariaDB server (see test_erp_026_durable_adapter_state).
"""
from __future__ import annotations

import os
import threading
import time
import unittest

from change_engine.adapter import ChangeEngineAdapter, HooksDisabled
from change_engine.adapter.mariadb_store import MariaDBAdapterStore
from change_engine.adapter.storage import SQLiteAdapterStore
from change_engine.adapter.store_api import StoreRefused, is_production
from change_engine.tests.test_bpl_012_engine_adapter import _ctx, _make_initial_build
from change_engine.tests.test_erp_026_durable_adapter_state import PROVISION, MariaDBBase, mariadb_only



class _Env:
    def __init__(self, value):
        self.value, self.old = value, os.environ.get("CHANGE_ENGINE_ENV")

    def __enter__(self):
        if self.value is None:
            os.environ.pop("CHANGE_ENGINE_ENV", None)
        else:
            os.environ["CHANGE_ENGINE_ENV"] = self.value

    def __exit__(self, *_):
        if self.old is None:
            os.environ.pop("CHANGE_ENGINE_ENV", None)
        else:
            os.environ["CHANGE_ENGINE_ENV"] = self.old


class ProductionGuardTable(unittest.TestCase):
    def test_is_production_table(self):
        rows = [  # (test_hooks, environment arg, CHANGE_ENGINE_ENV, expected production)
            (False, None, None, True), (True, None, None, False),
            (True, "dev", None, False), (True, " Development ", None, False), (True, "TEST", None, False),
            (True, "production", None, True), (True, "PRODUCTION ", None, True), (True, "prod", None, True),
            (True, "staging", None, True), (True, "", None, True), (True, "   ", None, True),
            (True, "", "dev", True),  # an empty argument must not fall back to the variable
            (True, None, "production", True), (True, None, "", True), (True, None, "  ", True),
            (True, None, "prod", True), (True, None, "staging", True), (True, None, "DEV", False),
            (False, "dev", None, False),
        ]
        for hooks, arg, var, expected in rows:
            with self.subTest(hooks=hooks, environment=arg, var=var), _Env(var):
                self.assertEqual(is_production(hooks, arg), expected)

    def test_test_hooks_default_off_and_refused_in_production(self):
        with _Env(None):
            self.assertFalse(ChangeEngineAdapter(environment="dev").test_hooks)
        for env in ("production", "PRODUCTION ", "prod", "staging", "", "  "):
            with self.subTest(environment=env), self.assertRaises(StoreRefused):
                ChangeEngineAdapter(test_hooks=True, environment=env, store=_FakeDurable())
        with _Env("production"), self.assertRaises(StoreRefused):
            ChangeEngineAdapter(test_hooks=True, store=_FakeDurable())
        with _Env("dev"), self.assertRaises(StoreRefused):  # empty argument beats the variable
            ChangeEngineAdapter(test_hooks=True, environment="", store=_FakeDurable())
        ChangeEngineAdapter(environment="production", store=_FakeDurable(tenant_id="t_alpha"))

    def test_production_refuses_unbound_production_grade_store(self):
        for arg, var in (("production", None), ("", "dev"), (None, ""), (None, None)):
            with self.subTest(environment=arg, environment_variable=var), _Env(var):
                with self.assertRaisesRegex(StoreRefused, "tenant-bound"):
                    ChangeEngineAdapter(environment=arg, store=_FakeDurable())

    def test_production_accepts_bound_production_grade_store(self):
        store = _FakeDurable(tenant_id="t_alpha")
        self.assertIs(ChangeEngineAdapter(environment="production", store=store).store, store)

    def test_test_environment_accepts_unbound_store(self):
        store = _FakeDurable()
        self.assertIs(ChangeEngineAdapter(environment="test", store=store).store, store)

    def test_reset_needs_hooks(self):
        a = ChangeEngineAdapter(test_hooks=False, environment="dev")
        with self.assertRaises(HooksDisabled):
            a.reset()

    def test_sqlite_store_is_not_production_grade(self):
        self.assertFalse(SQLiteAdapterStore(":memory:").production_grade)


class _FakeDurable(SQLiteAdapterStore):
    """A durable, production-grade stand-in so the guard tests reach the hooks check."""
    production_grade = True

    def __init__(self, tenant_id=None):
        super().__init__(":memory:", tenant_id=tenant_id)
        self.volatile = False


def _apply_input(adapter, key="apply_race_key_0001", approvals=None):
    art = _make_initial_build()
    plan = adapter.call("plan", _ctx(), {"artifact": art})
    assert plan["ok"], plan
    return {"idempotencyKey": key, "artifact": art, "planToken": plan["result"]["planToken"],
            "approvals": approvals or {"changeApproved": "01J00000000000000000000002"}}


@mariadb_only
class MultiWorker(MariaDBBase):
    def worker(self, **kw):
        return ChangeEngineAdapter(test_hooks=True, environment="test", store=self.make_store(), **kw)

    def provisioned(self, **kw):
        w1 = self.worker(**kw)
        self.assertTrue(w1.call("provision_site", _ctx(), PROVISION)["ok"])
        return w1, self.worker(**kw)  # w2 opens after provisioning, as a second process would

    def executes(self, w):
        return [j for j in w.execution_journal() if j["phase"] == "execute"]

    # ---- Critical: the key is reserved atomically before the effect
    def test_same_key_from_second_worker_while_first_runs_is_in_progress_not_a_second_effect(self):
        w1, w2 = self.provisioned()
        inp, seen = _apply_input(w1), []
        w1.on_lock_held(lambda: seen.append(w2.call("apply", _ctx(), inp)))
        first = w1.call("apply", _ctx(), inp)
        self.assertTrue(first["ok"] and first["result"]["status"] == "applied", first)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0]["ok"], seen[0])
        self.assertEqual(seen[0]["result"]["status"], "in_progress")
        self.assertEqual(seen[0]["result"]["operationId"], first["result"]["operationId"])
        self.assertEqual(len(self.executes(w1)), 1)
        done = w2.call("apply", _ctx(), inp)  # after completion: the stored outcome
        self.assertTrue(done["ok"] and done["replayed"] and done["result"]["status"] == "applied", done)
        self.assertEqual(len(self.executes(w2)), 1)

    def test_other_key_or_other_input_while_locked_is_refused_by_the_database_lock(self):
        w1, w2 = self.provisioned()
        inp, seen = _apply_input(w1), []
        w1.on_lock_held(lambda: seen.extend([
            w2.call("apply", _ctx(), {**inp, "idempotencyKey": "apply_other_key_0002"}),
            w2.call("apply", _ctx(), {**inp, "approvals": {"changeApproved": "01J00000000000000000000009"}}),
        ]))
        self.assertTrue(w1.call("apply", _ctx(), inp)["ok"])
        self.assertEqual(seen[0]["error"]["code"], "concurrent_change")
        self.assertEqual(seen[1]["error"]["code"], "idempotency_conflict")  # key binding is checked before the lock
        self.assertEqual(len(self.executes(w1)), 1)

    def test_two_threads_two_connections_same_key_run_the_effect_once(self):
        w1, w2 = self.provisioned()
        inp, out, gate = _apply_input(w1), [], threading.Barrier(2)

        def go(w):
            gate.wait()
            out.append(w.call("apply", _ctx(), inp))

        threads = [threading.Thread(target=go, args=(w,)) for w in (w1, w2)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(len(out), 2)
        self.assertTrue(all(r["ok"] for r in out), out)
        self.assertEqual(len(self.executes(w1)), 1, "second worker must not run the step again")
        self.assertEqual(sum(1 for r in out if r["result"]["status"] == "applied" and not r["replayed"]), 1)
        self.assertEqual(len(w1.store.events()), 1 + sum(1 for e in w1.store.events() if e["type"] != "blueprint.applied"))

    def test_idem_put_never_rewrites_the_bound_input_hash(self):
        s = self.make_store()
        s.idem_put("t", "apply", "k", "a" * 64, {"status": "applied"})
        with self.assertRaises(Exception):
            s.idem_put("t", "apply", "k", "b" * 64, {"status": "other"})
        self.assertEqual(s.idem_get("t", "apply", "k")[0], "a" * 64)

    # ---- High: effect state, event and key commit together; a crash leaves a recoverable state
    def test_crash_between_state_write_and_key_write_is_recoverable_and_never_reruns(self):
        for broken in ("save_site", "append_event", "idem_complete"):
            with self.subTest(broken=broken):
                self.setUp_clean()
                w1, w2 = self.provisioned()
                inp = _apply_input(w1)

                def boom(*a, **k):
                    raise RuntimeError("process died")

                setattr(w1.store, broken, boom)
                crashed = w1.call("apply", _ctx(), inp)
                self.assertFalse(crashed["ok"])
                self.assertEqual(len(self.executes(w2)), 1)
                st = w2.call("site_status", _ctx(), {})["result"]
                self.assertEqual(st["state"], "applying")  # nothing half-written: still the acquire state
                self.assertIsNone(st["applied"])
                busy = w2.call("apply", _ctx(), {**inp, "idempotencyKey": "apply_other_key_0003"})
                self.assertEqual(busy["error"]["code"], "concurrent_change")  # lease still valid
                w2.store.clock = lambda: time.time() + 10_000_000  # lease expired
                self.assertEqual(w2.recover_interrupted(), 1)
                st = w2.call("site_status", _ctx(), {})["result"]
                self.assertEqual((st["state"], st["lockedBy"]), ("recovery_required", None))
                again = w2.call("apply", _ctx(), inp)
                self.assertTrue(again["ok"] and again["replayed"], again)
                self.assertEqual(again["result"]["status"], "recovery_required")
                self.assertEqual(len(self.executes(w2)), 1)  # never a second blind run

    def test_expired_lock_is_recovered_lazily_by_a_different_key_instead_of_blocking_forever(self):
        w1, w2 = self.provisioned()
        inp = _apply_input(w1)
        w1.store.append_event = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("died"))
        w1.call("apply", _ctx(), inp)
        w2.store.clock = lambda: time.time() + 10_000_000
        got = w2.call("apply", _ctx(), {**inp, "idempotencyKey": "apply_other_key_0004"})
        self.assertNotEqual(got.get("error", {}).get("code"), "concurrent_change", got)
        self.assertEqual(w2.call("site_status", _ctx(), {})["result"]["state"], "recovery_required")

    def test_worker_that_lost_its_lease_cannot_overwrite_the_recovered_site(self):
        w1, w2 = self.provisioned()
        inp = _apply_input(w1)

        def other_worker_recovers():
            w2.store.clock = lambda: time.time() + 10_000_000
            self.assertEqual(w2.recover_interrupted(), 1)

        w1.on_lock_held(other_worker_recovers)
        res = w1.call("apply", _ctx(), inp)
        # the operation record exists, so the stored recovery_required outcome comes back as ok: true (contract 5.6.1),
        # and the worker that lost its lease stopped before running a single step
        self.assertTrue(res["ok"] and res["replayed"], res)
        self.assertEqual((res["result"]["status"], res["result"]["error"]["code"]), ("recovery_required", "recovery_required"))
        self.assertEqual(self.executes(w2), [])
        st = w2.call("site_status", _ctx(), {})["result"]
        self.assertEqual((st["state"], st["applied"]), ("recovery_required", None))

    # ---- High: audit and operation ids are unique across workers
    def test_audit_and_operation_ids_unique_across_two_store_instances(self):
        w1, w2 = self.provisioned()
        ids = []
        for w in (w1, w2, w1, w2):
            r = w.call("site_status", _ctx(), {})
            self.assertTrue(r["ok"], r)
            ids.append(r["auditId"])
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual(len({a["auditId"] for a in w1.audit_log()}), len(w1.audit_log()))

    # ---- Medium: transaction hazards, tenant width, charset
    def test_inner_failure_caught_inside_a_transaction_does_not_roll_back_earlier_writes(self):
        s = self.make_store()
        with s.transaction():
            s.idem_put("t", "apply", "k", "a" * 64, {"status": "applied"})
            try:
                with s.conn:
                    s.conn.execute("INSERT INTO adapter_events (event_id) VALUES ('x')")  # fails: missing columns
            except Exception:
                pass
            s.append_event("e1", "t", {})
        s = self.reopen(s)
        self.assertEqual(s.idem_get("t", "apply", "k")[0], "a" * 64)
        self.assertEqual(len(s.events()), 1)

    def test_ddl_inside_a_transaction_is_refused_not_silently_committed(self):
        s = self.make_store()
        with self.assertRaises(RuntimeError):
            with s.transaction():
                s.idem_put("t", "apply", "k", "a" * 64, {})
                s.write_field_data("t", "customer", "/f", 1)
        self.assertIsNone(self.reopen(s).idem_get("t", "apply", "k"))

    def test_site_reads_come_from_the_database_not_a_stale_cache(self):
        a, b = self.make_store(), self.make_store()
        params = {"siteClass": "production", "engineTarget": {"adapter": "frappe"}, "blueprintId": "b", "countryPack": "sa"}
        with self.assertRaises(RuntimeError):
            with a.transaction():
                a.create_site("t", params)
                raise RuntimeError("rolled back")
        self.assertIsNone(a.get_site("t"))
        a.create_site("t", params)
        self.assertEqual(b.get_site("t").blueprint_id, "b")

    def test_autocommit_connection_is_refused(self):
        with self.assertRaises(ValueError):
            MariaDBAdapterStore(self._connect(self.db, autocommit=True))

    def test_max_length_tenant_id_fits(self):
        t = "t_" + "a" * 63  # 65 chars, valid per common.schema.json
        s = self.make_store()
        s.idem_put(t, "apply", "k", "a" * 64, {})
        s.insert_audit({"auditId": "aud_x1", "operation": "apply", "requestId": None, "correlationId": None, "tenant": t,
                        "service": None, "onBehalfOf": None, "inputHash": None, "artifactId": None, "result": None})
        self.assertIsNotNone(s.idem_get(t, "apply", "k"))

    def setUp_clean(self):
        """Fresh database for each subTest."""
        if getattr(self, "_used", False):
            self._drop()
            self.db = "erp026_" + os.urandom(5).hex()
            self._admin = self._connect(None, autocommit=True)
            self._admin.cursor().execute(f"CREATE DATABASE {self.db} CHARACTER SET utf8mb4")
        self._used = True


@mariadb_only
class Latin1Database(MariaDBBase):
    DB_CHARSET = "latin1"

    def test_entity_tables_are_utf8mb4_even_in_a_latin1_database(self):
        s = self.make_store()
        tbl = s.ensure_entity_table("t_alpha", "customer")
        s.write_field_data("t_alpha", "customer", "/f", "مرحبا 🕌")
        cur = self._admin.cursor()
        cur.execute(f"SHOW CREATE TABLE {self.db}.`{tbl}`")
        self.assertIn("utf8mb4", cur.fetchone()[1])
        self.assertEqual(s.read_field_data("t_alpha", "customer", "/f"), "مرحبا 🕌")


class SqliteSingleProcess(unittest.TestCase):
    def test_same_key_during_run_is_in_progress_on_the_sqlite_dev_store_too(self):
        a = ChangeEngineAdapter(test_hooks=True, environment="test")
        self.assertTrue(a.call("provision_site", _ctx(), PROVISION)["ok"])
        inp, seen = _apply_input(a), []
        a.on_lock_held(lambda: seen.append(a.call("apply", _ctx(), inp)))
        first = a.call("apply", _ctx(), inp)
        self.assertEqual(first["result"]["status"], "applied")
        self.assertEqual(seen[0]["result"]["status"], "in_progress")
        self.assertEqual(len([j for j in a.execution_journal() if j["phase"] == "execute"]), 1)


if __name__ == "__main__":
    unittest.main()
