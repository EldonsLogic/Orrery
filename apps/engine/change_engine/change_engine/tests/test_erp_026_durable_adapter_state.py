"""ERP-026: durable adapter state (ADR-0041): store conformance, production guard, restart and restore.

MariaDB tests run only when a throwaway server is given (otherwise skipped with the reason):
  docker run -d --name erp026-mdb -e MARIADB_ROOT_PASSWORD=pw -p 127.0.0.1:33726:3306 mariadb:10.6
  ERP026_MARIADB=127.0.0.1:33726:root:pw  ERP026_MARIADB_CONTAINER=erp026-mdb   (container only for the restore test)
Needs pymysql. Each test uses its own database, dropped afterwards.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from change_engine.adapter import ChangeEngineAdapter
from change_engine.adapter.mariadb_store import MariaDBAdapterStore
from change_engine.adapter.storage import SQLiteAdapterStore
from change_engine.adapter.store_api import AdapterStore, StoreRefused
from change_engine.tests.test_bpl_012_engine_adapter import _ctx

try:
    import pymysql
except ImportError:  # pragma: no cover
    pymysql = None

CONF = os.environ.get("ERP026_MARIADB", "")
CONTAINER = os.environ.get("ERP026_MARIADB_CONTAINER", "")
MARIA_SKIP = "needs pymysql and ERP026_MARIADB=host:port:user:password (see module docstring)"
PROVISION = {
    "idempotencyKey": "prov_durable_0001",
    "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
    "countryPack": "sa",
    "siteClass": "production",
    "blueprintId": "example-trading-001",
}
AUDIT = {"auditId": "aud_1", "operation": "apply", "requestId": "r1", "correlationId": "c1", "tenant": "t_alpha",
         "service": "control_plane", "onBehalfOf": {"kind": "user", "id": "u"}, "inputHash": "h" * 64,
         "artifactId": "art1", "result": "in_progress"}


class StoreConformance:
    """Contract every AdapterStore passes. Subclasses provide make_store() and reopen() (a new connection to the same data)."""

    def make_store(self) -> AdapterStore: raise NotImplementedError
    def reopen(self, store: AdapterStore) -> AdapterStore: raise NotImplementedError

    def test_idempotency_roundtrip_and_overwrite_survive_reopen(self):
        s = self.make_store()
        self.assertIsNone(s.idem_get("t", "apply", "k1"))
        s.idem_put("t", "apply", "k1", "a" * 64, {"status": "applied"})
        s.idem_put("t", "apply", "k1", "b" * 64, {"status": "rejected"})
        s.idem_put("u", "apply", "k1", "c" * 64, {"status": "other-tenant"})
        s = self.reopen(s)
        self.assertEqual(s.idem_get("t", "apply", "k1"), ("b" * 64, {"status": "rejected"}))
        self.assertEqual(s.idem_get("u", "apply", "k1")[1], {"status": "other-tenant"})
        self.assertIsNone(s.idem_get("t", "rollback", "k1"))

    def test_tokens_evidence_journal_audit_events_members_survive_reopen(self):
        s = self.make_store()
        s.save_token("t", "tok", 5)
        s.save_evidence("t", "ev1", ["ALTER ..."])
        s.save_prepare_intent("op1", "t", "art1", {"x": 1})
        s.append_journal("t", "art1", 1, "execute")
        s.append_journal("t", "art1", 2, "compensate")
        s.insert_audit(AUDIT)
        s.update_audit({**AUDIT, "result": "applied"})
        s.append_event("e1", "apply.done", {"n": 1})
        s.replace_members("t", {"m1": {"status": "active", "roleIds": ["r"], "displayName": "ن"}})
        s = self.reopen(s)
        self.assertEqual(s.get_token_issued_at("t", "tok"), 5)
        self.assertIsNone(s.get_token_issued_at("t", "nope"))
        self.assertEqual(s.get_evidence("t", "ev1"), ["ALTER ..."])
        with self.assertRaises(KeyError):
            s.get_evidence("t", "missing")
        self.assertEqual(s.execution_journal(), [{"artifactId": "art1", "seq": 1, "phase": "execute"},
                                                 {"artifactId": "art1", "seq": 2, "phase": "compensate"}])
        self.assertEqual(s.audit_log(), [{**AUDIT, "result": "applied"}])
        self.assertEqual(s.events(), [{"eventId": "e1", "type": "apply.done", "data": {"n": 1}}])
        self.assertEqual(s.get_member("t", "m1")["displayName"], "ن")
        self.assertFalse(s.get_members("t")["m1"]["canAuthenticate"])

    def test_site_and_tenant_field_data_survive_reopen(self):
        s = self.make_store()
        site = s.create_site("t", {"siteClass": "production", "engineTarget": {"adapter": "frappe"},
                                   "blueprintId": "b", "countryPack": "sa"})
        site.sync_version = 3
        site.applied_ids.add("art1")
        s.save_site(site)
        self.assertEqual(s.write_field_data("t", "customer", "/f", {"v": 42}), {"v": 42})
        s = self.reopen(s)
        got = s.get_site("t")
        self.assertEqual((got.sync_version, got.applied_ids, got.site_class), (3, {"art1"}, "production"))
        self.assertEqual(s.read_field_data("t", "customer", "/f"), {"v": 42})
        self.assertIsNone(s.read_field_data("t", "customer", "/other"))
        s.reset()
        self.assertIsNone(self.reopen(s).get_site("t"))

    def test_restart_replays_stored_result_without_second_effect(self):
        s = self.make_store()
        first = ChangeEngineAdapter(test_hooks=True, store=s).call("provision_site", _ctx(), PROVISION)
        self.assertTrue(first["ok"], first)
        events, audit = len(s.events()), len(s.audit_log())
        again = ChangeEngineAdapter(test_hooks=True, store=self.reopen(s))  # "restarted process"
        replay = again.call("provision_site", _ctx(), PROVISION)
        self.assertTrue(replay["ok"] and replay["replayed"], replay)
        self.assertEqual(replay["result"], first["result"])
        self.assertEqual(len(again.store.events()), events)
        conflict = again.call("provision_site", _ctx(), {**PROVISION, "countryPack": "ae"})
        self.assertEqual(conflict["error"]["code"], "idempotency_conflict")
        self.assertEqual(len(again.store.events()), events)
        self.assertGreaterEqual(len(again.store.audit_log()), audit)


class SQLiteConformance(StoreConformance, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = str(Path(self._dir.name) / "state.sqlite")

    def make_store(self): return SQLiteAdapterStore(self.path)
    def reopen(self, store):
        store.conn.close()
        return SQLiteAdapterStore(self.path)


class ProductionGuard(unittest.TestCase):
    def test_production_refuses_in_memory_store(self):
        for kwargs in ({"test_hooks": False}, {"test_hooks": True, "environment": "production"},
                       {"test_hooks": True, "environment": "staging"}, {"test_hooks": False, "db_path": ""}):
            with self.assertRaises(StoreRefused, msg=str(kwargs)):
                ChangeEngineAdapter(**kwargs)

    def test_env_variable_sets_production_and_dev_flag_allows_memory(self):
        old = os.environ.get("CHANGE_ENGINE_ENV")
        self.addCleanup(lambda: os.environ.pop("CHANGE_ENGINE_ENV", None) if old is None else os.environ.update(CHANGE_ENGINE_ENV=old))
        os.environ["CHANGE_ENGINE_ENV"] = "production"
        with self.assertRaises(StoreRefused):
            ChangeEngineAdapter(test_hooks=True)
        os.environ["CHANGE_ENGINE_ENV"] = "test"
        ChangeEngineAdapter(test_hooks=False)
        ChangeEngineAdapter(test_hooks=True, environment="dev")

    def test_production_accepts_durable_store(self):
        with tempfile.TemporaryDirectory() as d:
            ChangeEngineAdapter(test_hooks=False, db_path=str(Path(d) / "s.sqlite"))


@unittest.skipUnless(pymysql and CONF.count(":") == 3, MARIA_SKIP)
class MariaDBConformance(StoreConformance, unittest.TestCase):
    def setUp(self):
        self.host, port, self.user, self.pw = CONF.split(":")
        self.port, self.db, self._open = int(port), "erp026_" + uuid.uuid4().hex[:10], []
        admin = self._connect(None, autocommit=True)
        admin.cursor().execute(f"CREATE DATABASE {self.db} CHARACTER SET utf8mb4")
        self.addCleanup(self._drop)
        self._admin = admin

    def _connect(self, db, autocommit=False):
        c = pymysql.connect(host=self.host, port=self.port, user=self.user, password=self.pw, database=db,
                            charset="utf8mb4", autocommit=autocommit)
        self._open.append(c)
        return c

    def _drop(self):
        self._admin.cursor().execute(f"DROP DATABASE IF EXISTS {self.db}")
        for c in self._open:
            try:
                c.close()
            except Exception:
                pass

    def make_store(self): return MariaDBAdapterStore(self._connect(self.db))
    def reopen(self, store):
        store.conn.close()
        return MariaDBAdapterStore(self._connect(self.db))

    def test_transaction_rolls_back_effect_and_idempotency_record_together(self):
        s = self.make_store()
        with self.assertRaises(RuntimeError):
            with s.transaction():
                s.idem_put("t", "apply", "k", "a" * 64, {"status": "applied"})
                s.append_event("e1", "apply.done", {})
                raise RuntimeError("effect failed")
        s = self.reopen(s)
        self.assertIsNone(s.idem_get("t", "apply", "k"))
        self.assertEqual(s.events(), [])

    def test_production_accepts_mariadb_store(self):
        ChangeEngineAdapter(test_hooks=False, store=self.make_store())

    @unittest.skipUnless(CONTAINER, "restore test needs ERP026_MARIADB_CONTAINER (docker exec mariadb-dump/mariadb)")
    def test_dump_and_restore_of_tenant_database_keeps_keys_and_effects_consistent(self):
        s = self.make_store()
        ChangeEngineAdapter(test_hooks=True, store=s).call("provision_site", _ctx(), PROVISION)
        s.write_field_data("t_alpha", "customer", "/f", 42)
        dump = subprocess.run(["docker", "exec", CONTAINER, "mariadb-dump", f"-u{self.user}", f"-p{self.pw}", "--single-transaction",
                               self.db], capture_output=True, check=True).stdout
        later = ChangeEngineAdapter(test_hooks=True, store=self.reopen(s))  # work after the dump is lost by the restore
        later.store.idem_put("t_alpha", "apply", "after_dump", "d" * 64, {"status": "applied"})
        later.store.write_field_data("t_alpha", "customer", "/f", 99)
        self._admin.cursor().execute(f"DROP DATABASE {self.db}")
        self._admin.cursor().execute(f"CREATE DATABASE {self.db} CHARACTER SET utf8mb4")
        subprocess.run(["docker", "exec", "-i", CONTAINER, "mariadb", f"-u{self.user}", f"-p{self.pw}", self.db],
                       input=dump, capture_output=True, check=True)
        restored = ChangeEngineAdapter(test_hooks=True, store=self.reopen(later.store))
        replay = restored.call("provision_site", _ctx(), PROVISION)
        self.assertTrue(replay["ok"] and replay["replayed"], replay)
        self.assertEqual(restored.store.read_field_data("t_alpha", "customer", "/f"), 42)
        self.assertIsNone(restored.store.idem_get("t_alpha", "apply", "after_dump"))  # key and effect rolled back together


if __name__ == "__main__":
    unittest.main()
