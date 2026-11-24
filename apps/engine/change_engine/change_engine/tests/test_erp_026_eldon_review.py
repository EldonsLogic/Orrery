"""ERP-026: deterministic two-worker regressions for Eldon's Tier 3 review.

Every lifecycle test runs against SQLite offline and MariaDB in the required CI job.
Events coordinate the exact stale-read interleavings; no timing sleeps are used.
"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from change_engine.adapter import ChangeEngineAdapter
from change_engine.adapter.storage import SQLiteAdapterStore
from change_engine.tests.test_bpl_012_engine_adapter import _ctx
from change_engine.tests.test_erp_026_durable_adapter_state import CONF, MARIA_SKIP, PROVISION, MariaDBBase, pymysql
from change_engine.tests.test_erp_026_review_fixes import _apply_input


def sync_input(version, members=None, mode="delta"):
    """Valid shadow-member synchronization request with a distinct key per version."""
    return {"idempotencyKey": f"sync_review_key_{version:04}", "syncVersion": version,
            "mode": mode, "members": members or []}


MEMBER = {"memberRef": "m_review0001", "status": "active", "roleIds": [], "displayName": "Synthetic"}


class ReviewRegressions:
    """Shared assertions against two independent connections to the same database."""

    def workers(self):
        a = ChangeEngineAdapter(store=self.make_store(), test_hooks=True, environment="test")
        self.assertTrue(a.call("provision_site", _ctx(), PROVISION)["ok"])
        b = ChangeEngineAdapter(store=self.make_store(), test_hooks=True, environment="test")
        return a, b

    def assert_recovery(self, a, inp, result):
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["status"], "recovery_required")
        site = a.store.get_site("t_alpha")
        self.assertEqual((site.state, site.lock), ("recovery_required", None))
        replay = a.call("apply", _ctx(), inp)
        self.assertTrue(replay["ok"] and replay["replayed"], replay)
        self.assertEqual(replay["result"], result["result"])

    def test_stale_applying_snapshot_before_acquire_does_not_strand_site(self):
        a, b = self.workers()
        inp = _apply_input(a)
        stale, finished, output, errors = threading.Event(), threading.Event(), [], []
        acquire = b._acquire

        def pause_acquire(*args, **kwargs):
            stale.set()  # worker 2 has observed worker 1's applying site
            if not finished.wait(10):
                raise RuntimeError("worker 1 did not finish")
            return acquire(*args, **kwargs)

        def second():
            try:
                output.append(b.call("apply", _ctx(), {**inp, "idempotencyKey": "apply_stale_snapshot_0002"}))
            except BaseException as exc:
                errors.append(exc)

        b._acquire = pause_acquire
        thread = threading.Thread(target=second)

        def start_second():
            thread.start()
            self.assertTrue(stale.wait(10))

        a.on_lock_held(start_second)
        try:
            first = a.call("apply", _ctx(), inp)
        finally:
            finished.set()
            if thread.ident is not None:
                thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(first["result"]["status"], "applied", first)
        self.assertEqual(output[0]["result"]["status"], "already_applied", output)
        site = a.store.get_site("t_alpha")
        self.assertEqual((site.state, site.lock), ("ready", None))

    def test_provision_new_site_rolls_back_when_key_completion_loses_lease(self):
        a = ChangeEngineAdapter(store=self.make_store(), test_hooks=True, environment="test")
        with patch.object(a.store, "idem_complete", return_value=False):
            result = a.call("provision_site", _ctx(), PROVISION)
        self.assertFalse(result["ok"], result)
        self.assertIsNone(a.store.get_site("t_alpha"))
        self.assertIsNone(a.store.idem_get("t_alpha", "provision_site", PROVISION["idempotencyKey"]))

    def test_provision_existing_site_checks_key_completion(self):
        a, _ = self.workers()
        with patch.object(a.store, "idem_complete", return_value=False):
            result = a.call("provision_site", _ctx(), {**PROVISION, "idempotencyKey": "prov_existing_review_0002"})
        self.assertFalse(result["ok"], result)
        self.assertEqual(a.store.get_site("t_alpha").state, "ready")

    def test_sync_rolls_back_members_version_and_lock_when_completion_fails(self):
        a, b = self.workers()
        inp = sync_input(1, [MEMBER])
        with patch.object(a.store, "idem_complete", return_value=False):
            result = a.call("sync_members", _ctx(), inp)
        self.assertFalse(result["ok"], result)
        self.assertEqual(b.store.get_members("t_alpha"), {})
        site = b.store.get_site("t_alpha")
        self.assertEqual((site.sync_version, site.state, site.lock), (0, "ready", None))
        self.assertIsNone(b.store.idem_get("t_alpha", "sync_members", inp["idempotencyKey"]))
        self.assertTrue(b.call("sync_members", _ctx(), inp)["ok"])

    def test_concurrent_sync_disable_cannot_be_overwritten_by_stale_delta(self):
        a, b = self.workers()
        self.assertTrue(a.call("sync_members", _ctx(), sync_input(1, [MEMBER]))["ok"])
        seen = []
        read = a.store.get_members

        def interleave(tenant):
            snapshot = read(tenant)
            seen.append(b.call("sync_members", _ctx(), sync_input(3)))
            return snapshot

        with patch.object(a.store, "get_members", side_effect=interleave):
            disabled = a.call("sync_members", _ctx(), sync_input(2, [{**MEMBER, "status": "disabled"}]))
        self.assertTrue(disabled["ok"], disabled)
        self.assertFalse(seen[0]["ok"], seen)
        self.assertEqual(seen[0]["error"]["code"], "concurrent_change")
        self.assertTrue(b.call("sync_members", _ctx(), sync_input(3))["ok"])
        self.assertEqual(b.store.get_member("t_alpha", MEMBER["memberRef"])["status"], "disabled")
        self.assertEqual(b.store.get_site("t_alpha").state, "ready")

    def test_expired_lease_stops_before_ddl_without_another_worker_recovering(self):
        a, _ = self.workers()
        inp = _apply_input(a)
        now = a.store.clock()
        a.on_lock_held(lambda: setattr(a.store, "clock", lambda: now + 10000))
        with patch.object(a.store, "ensure_entity_table", wraps=a.store.ensure_entity_table) as ddl:
            result = a.call("apply", _ctx(), inp)
        self.assert_recovery(a, inp, result)
        ddl.assert_not_called()

    def test_recovered_lease_returns_stored_outcome_and_stops_all_effects(self):
        a, b = self.workers()
        inp = _apply_input(a)

        def recover():
            b.store.clock = lambda: a.store.clock() + 10000
            self.assertEqual(b.recover_interrupted(), 1)

        a.on_lock_held(recover)
        with patch.object(a.store, "ensure_entity_table", wraps=a.store.ensure_entity_table) as ddl:
            result = a.call("apply", _ctx(), inp)
        self.assert_recovery(a, inp, result)
        ddl.assert_not_called()

    def exception_cleanup(self, method):
        """A transient in-process failure must not require waiting for lease recovery."""
        a, _ = self.workers()
        inp = _apply_input(a)
        original = getattr(a.store, method)
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic failure")
            return original(*args, **kwargs)

        with patch.object(a.store, method, side_effect=fail_once):
            result = a.call("apply", _ctx(), inp)
        self.assertTrue(result["ok"], result)
        self.assertIn(result["result"]["status"], ("failed_clean", "recovery_required"))
        site = a.store.get_site("t_alpha")
        self.assertIsNone(site.lock)
        self.assertNotEqual(site.state, "applying")
        self.assertEqual(a.call("apply", _ctx(), inp)["result"], result["result"])

    def test_unexpected_prepare_exception_unlocks(self):
        self.exception_cleanup("save_prepare_intent")

    def test_unexpected_journal_exception_unlocks(self):
        self.exception_cleanup("append_journal")

    def test_unexpected_finalize_exception_unlocks(self):
        self.exception_cleanup("save_site")

    def test_unexpected_event_exception_unlocks(self):
        self.exception_cleanup("append_event")


class SQLiteReview(ReviewRegressions, unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = str(Path(directory.name) / "review.sqlite")

    def make_store(self):
        store = SQLiteAdapterStore(self.path)
        self.addCleanup(store.conn.close)
        return store


@unittest.skipUnless(pymysql and CONF.count(":") == 3, MARIA_SKIP)
class MariaDBReview(ReviewRegressions, MariaDBBase):
    pass
