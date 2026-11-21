"""ERP-026, PR 126 cross-model review findings 1 to 5: one regression test per finding.

Every scenario runs twice: offline on SQLite (workers share one store, so the races are staged with events and
threads), and on MariaDB (one connection per worker) when a server is given, see test_erp_026_durable_adapter_state.
"""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from change_engine.adapter import ChangeEngineAdapter
from change_engine.adapter.mariadb_store import MariaDBAdapterStore
from change_engine.adapter.storage import SQLiteAdapterStore, TenantMismatch
from change_engine.tests.test_bpl_012_engine_adapter import _ctx, _make_initial_build
from change_engine.tests.test_erp_026_durable_adapter_state import PROVISION, MariaDBBase, mariadb_only

SYSTEM = {"kind": "system", "id": "assignments"}
FUTURE = 10_000_000  # seconds: far past any lease
M1, M2 = "m_aaaaaaaa", "m_bbbbbbbb"


def apply_input(adapter, key="apply_pr126_key_0001"):
    art = _make_initial_build()
    plan = adapter.call("plan", _ctx(), {"artifact": art})
    assert plan["ok"], plan
    return {"idempotencyKey": key, "artifact": art, "planToken": plan["result"]["planToken"],
            "approvals": {"changeApproved": "01J00000000000000000000002"}}


def sync_input(key, version, members, mode="delta"):
    return {"idempotencyKey": key, "mode": mode, "syncVersion": version,
            "members": [{"memberRef": ref, "status": status, "roleIds": []} for ref, status in members]}


class Backend:
    """Stand-in for the engine runtime: provisioning and member sync can be paused or can run a callback."""

    def __init__(self):
        self.on_provision = None
        self.on_sync = None

    def provision_tenant_site(self, tenant, inp, snapshot):
        if self.on_provision:
            self.on_provision()

    def sync_members(self, tenant, members, mode, all_members):
        if self.on_sync:
            hook, self.on_sync = self.on_sync, None
            hook()

    def persist_site_state(self, tenant, snapshot):
        pass


class Cases:
    """Scenarios shared by the SQLite and the MariaDB runs. Subclasses give worker(), a second store view and expire()."""

    def worker(self, backend=None): raise NotImplementedError
    def expire(self, adapter): raise NotImplementedError

    def provisioned(self, backend=None):
        w1 = self.worker(backend)
        self.assertTrue(w1.call("provision_site", _ctx(), PROVISION)["ok"])
        return w1, self.worker(backend)

    @staticmethod
    def executes(w):
        return [j for j in w.execution_journal() if j["phase"] == "execute"]

    def status(self, w):
        return w.call("site_status", _ctx(), {})["result"]

    def members(self, w):
        return {ref: m["status"] for ref, m in w.store.get_members("t_alpha").items()}

    def sync(self, w, key, version, members, mode="delta"):
        return w.call("sync_members", _ctx(who=SYSTEM), sync_input(key, version, members, mode))

    # ---- finding 1: the site must not be left in applying when another worker finished between the read and the acquire
    def test_site_is_not_left_applying_when_another_worker_finishes_between_read_and_acquire(self):
        w1, w2 = self.provisioned()
        inp1 = apply_input(w1, "apply_race_key_0001")
        inp2 = {**inp1, "idempotencyKey": "apply_race_key_0002"}
        inside, release, first = threading.Event(), threading.Event(), []
        w1.on_lock_held(lambda: (inside.set(), release.wait(60)))
        t1 = threading.Thread(target=lambda: first.append(w1.call("apply", _ctx(), inp1)))
        t1.start()
        self.assertTrue(inside.wait(60))
        self.assertEqual(self.status(w2)["state"], "applying")  # worker 2 reads the site now: applying, lock held by worker 1
        real = w2.store.acquire_operation

        def acquire_after_worker_1_finished(*a, **k):
            release.set()  # worker 1 finishes: its run resets the site to ready ...
            t1.join(60)
            return real(*a, **k)  # ... and only now does worker 2 acquire (ready -> applying)

        w2.store.acquire_operation = acquire_after_worker_1_finished
        second = w2.call("apply", _ctx(), inp2)
        w2.store.acquire_operation = real
        self.assertTrue(first[0]["ok"] and first[0]["result"]["status"] == "applied", first)
        self.assertTrue(second["ok"], second)
        st = self.status(w1)
        self.assertEqual((st["state"], st["lockedBy"]), ("ready", None), "site stuck in applying with no lock holder")
        self.assertEqual(len(self.executes(w1)), 1)

    def test_a_site_orphaned_in_applying_is_healed_by_the_next_apply(self):
        w1, _ = self.provisioned()
        site = w1.store.get_site("t_alpha")
        site.state = "applying"  # what the race used to leave behind: applying, no lock holder
        w1.store.save_site(site)
        res = w1.call("apply", _ctx(), apply_input(w1))
        self.assertEqual(res["result"]["status"], "applied", res)
        self.assertEqual(self.status(w1)["state"], "ready")

    def test_acquire_reports_whether_it_moved_the_site_from_ready(self):
        w1, _ = self.provisioned()
        s = w1.store
        self.assertEqual(s.acquire_operation("t_alpha", "apply", "k1", "a" * 64, "op_1", {}, {}, lock=True, lease_seconds=60),
                         ("acquired", {"ready_before": True}))
        self.assertEqual(s.acquire_operation("t_alpha", "apply", "k2", "b" * 64, "op_2", {}, {}, lock=True, lease_seconds=60),
                         ("locked", None))
        s.recover_operation({"tenant": "t_alpha", "operation": "apply", "key": "k1", "operationId": "op_1"}, {"status": "x"})
        self.assertEqual(s.get_site("t_alpha").state, "recovery_required")
        self.assertEqual(s.acquire_operation("t_alpha", "apply", "k3", "c" * 64, "op_3", {}, {}, lock=True, lease_seconds=60),
                         ("acquired", {"ready_before": False}))  # a blocked site is never put back to ready by an apply
        self.assertEqual(s.get_site("t_alpha").state, "recovery_required")

    # ---- finding 2: a lost key rolls provision_site and sync_members back; sync_members runs one at a time per tenant
    def test_provision_site_rolls_back_when_the_key_was_lost_to_lease_recovery(self):
        backend = Backend()
        w1 = self.worker(backend)

        def another_worker_recovers_our_key():
            self.expire(w1)
            self.assertEqual(w1.recover_interrupted(), 1)  # the reservation is released: our lease ran out
            self.unexpire(w1)

        backend.on_provision = another_worker_recovers_our_key
        res = w1.call("provision_site", _ctx(), PROVISION)
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["error"]["code"], "concurrent_change")
        self.assertTrue(res["error"]["retryable"])
        self.assertIsNone(w1.store.get_site("t_alpha"), "the site must not be committed without its key")
        backend.on_provision = None
        retry = w1.call("provision_site", _ctx(), PROVISION)
        self.assertTrue(retry["ok"] and not retry["replayed"], retry)

    def test_sync_members_rolls_back_when_the_key_is_lost(self):
        w1, _ = self.provisioned()
        self.assertTrue(self.sync(w1, "sync_base_key_0001", 1, [(M1, "active")])["ok"])
        real = w1.store.idem_complete
        w1.store.idem_complete = lambda *a, **k: False  # the reservation is gone (lease recovered by another worker)
        res = self.sync(w1, "sync_lost_key_0002", 2, [(M1, "disabled"), (M2, "active")])
        w1.store.idem_complete = real
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["error"]["code"], "concurrent_change")
        self.assertEqual(self.members(w1), {M1: "active"}, "members were committed without their key")
        self.assertEqual(w1.store.get_site("t_alpha").sync_version, 1)
        retry = self.sync(w1, "sync_lost_key_0002", 2, [(M1, "disabled"), (M2, "active")])
        self.assertTrue(retry["ok"] and not retry["replayed"], retry)
        self.assertEqual(self.members(w1), {M1: "disabled", M2: "active"})

    def paused_sync(self, first_key, first_version, first_members, second_key, second_version, second_members):
        """Start sync A and pause it inside the engine call (members read, nothing committed), start sync B on another
        worker and give it time, then let A finish. Returns (A result, B result, B was blocked while A was paused)."""
        backend = Backend()
        w1, _ = self.provisioned(backend)
        w2 = self.worker(backend)
        self.assertTrue(self.sync(w1, "sync_base_key_0001", 1, [(M1, "active")])["ok"])
        inside, release, out = threading.Event(), threading.Event(), {}
        backend.on_sync = lambda: (inside.set(), release.wait(60))
        ta = threading.Thread(target=lambda: out.update(a=self.sync(w1, first_key, first_version, first_members)))
        ta.start()
        self.assertTrue(inside.wait(60))
        tb = threading.Thread(target=lambda: out.update(b=self.sync(w2, second_key, second_version, second_members)))
        tb.start()
        tb.join(1.5)
        blocked = tb.is_alive()
        release.set()
        ta.join(60)
        tb.join(60)
        self.assertEqual(len(out), 2)
        return out["a"], out["b"], blocked, w1

    def test_concurrent_sync_cannot_reenable_a_member_disabled_by_a_committed_sync(self):
        # A (version 3) reads the members and pauses; B (version 2) disables m1. Without serialisation B commits and A then
        # writes its stale snapshot back (m1 active again) with both calls reporting success.
        a, b, blocked, w = self.paused_sync("sync_late_key_0003", 3, [(M2, "active")], "sync_disable_key_0002", 2, [(M1, "disabled")])
        self.assertTrue(blocked, "the second sync ran while the first held its snapshot")
        self.assertTrue(a["ok"], a)
        self.assertEqual(b["error"]["code"], "stale_sync_version")  # loud, never a silent overwrite
        self.assertEqual(self.members(w), {M1: "active", M2: "active"})
        self.assertEqual(w.store.get_site("t_alpha").sync_version, 3)

    def test_concurrent_sync_in_order_applies_both(self):
        a, b, blocked, w = self.paused_sync("sync_disable_key_0002", 2, [(M1, "disabled")], "sync_next_key_0003", 3, [(M2, "active")])
        self.assertTrue(blocked)
        self.assertTrue(a["ok"] and b["ok"], (a, b))
        self.assertEqual(self.members(w), {M1: "disabled", M2: "active"}, "the later sync must start from the earlier one's result")
        self.assertEqual(w.store.get_site("t_alpha").sync_version, 3)

    # ---- finding 3: lease and lock ownership before every step; unexpected errors unlock; recovery_required is ok: true
    def test_worker_whose_lease_expired_stops_before_the_next_step(self):
        w1, _ = self.provisioned()
        inp = apply_input(w1)
        w1.on_lock_held(lambda: self.expire(w1))
        res = w1.call("apply", _ctx(), inp)
        self.assertTrue(res["ok"] and res["replayed"], res)
        self.assertEqual(res["result"]["status"], "recovery_required")
        self.assertEqual(self.executes(w1), [], "a worker without a lease must not run a step")
        self.unexpire(w1)
        st = self.status(w1)
        self.assertEqual((st["state"], st["lockedBy"]), ("recovery_required", None))
        again = w1.call("apply", _ctx(), inp)
        self.assertTrue(again["ok"] and again["replayed"] and again["result"]["status"] == "recovery_required", again)

    def test_worker_whose_lease_expired_does_not_run_the_ddl(self):
        w1, _ = self.provisioned()
        ddl = []
        for name in ("ensure_entity_table", "ensure_field_column"):
            real = getattr(w1.store, name)
            setattr(w1.store, name, lambda *a, _real=real, _name=name, **k: (ddl.append(_name), _real(*a, **k))[1])
        real_journal = w1.store.append_journal

        def journal_then_lease_expires(*a, **k):
            real_journal(*a, **k)
            self.expire(w1)  # the engine step takes long: the lease runs out before its DDL

        w1.store.append_journal = journal_then_lease_expires
        res = w1.call("apply", _ctx(), apply_input(w1))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["result"]["status"], "recovery_required")
        self.assertEqual(ddl, [], "DDL ran after the lease expired")

    def test_unexpected_error_before_any_step_unlocks_with_failed_clean(self):
        w1, _ = self.provisioned()
        real = w1.store.save_prepare_intent
        w1.store.save_prepare_intent = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database went away"))
        inp = apply_input(w1)
        res = w1.call("apply", _ctx(), inp)
        w1.store.save_prepare_intent = real
        self.assertTrue(res["ok"], res)
        self.assertEqual((res["result"]["status"], res["result"]["error"]["code"]), ("failed_clean", "engine_unavailable"))
        st = self.status(w1)
        self.assertEqual((st["state"], st["lockedBy"]), ("ready", None), "the lock was left until the lease ended")
        self.assertEqual(self.executes(w1), [])
        self.assertEqual([e["type"] for e in w1.events() if e["type"].startswith("blueprint.")], ["blueprint.apply_failed"])
        other = w1.call("apply", _ctx(), {**inp, "idempotencyKey": "apply_after_fail_0002"})  # not stuck behind a lock
        self.assertEqual(other["result"]["status"], "applied", other)

    def test_unexpected_error_after_a_step_ends_recovery_required_and_unlocked(self):
        w1, _ = self.provisioned()
        w1._evaluate_pc = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug after the step"))
        res = w1.call("apply", _ctx(), apply_input(w1))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["result"]["status"], "recovery_required")
        st = self.status(w1)
        self.assertEqual((st["state"], st["lockedBy"]), ("recovery_required", None))
        self.assertEqual(len(self.executes(w1)), 1)


class SqliteCases(Cases, unittest.TestCase):
    """Offline: both workers share one in-memory store (one process), the races are staged with events and threads."""

    def setUp(self):
        self.store = SQLiteAdapterStore(":memory:")
        self.real_clock = self.store.clock

    def worker(self, backend=None):
        return ChangeEngineAdapter(test_hooks=True, environment="test", store=self.store, frappe_backend=backend)

    def expire(self, adapter):
        self.store.clock = lambda: time.time() + FUTURE

    def unexpire(self, adapter):
        self.store.clock = self.real_clock


@mariadb_only
class MariaCases(Cases, MariaDBBase):
    """MariaDB: one connection per worker, so the locks and the compare-and-set are the database's own."""

    def worker(self, backend=None):
        return ChangeEngineAdapter(test_hooks=True, environment="test", store=self.make_store(), frappe_backend=backend)

    def expire(self, adapter):
        adapter.store.clock = lambda: time.time() + FUTURE

    def unexpire(self, adapter):
        adapter.store.clock = time.time

    def test_sync_members_lost_key_through_real_lease_recovery(self):
        backend = Backend()
        w1, w2 = self.provisioned(backend)
        self.assertTrue(self.sync(w1, "sync_base_key_0001", 1, [(M1, "active")])["ok"])

        def other_worker_recovers():
            self.expire(w2)
            self.assertEqual(w2.recover_interrupted(), 1)  # releases the key while w1 holds its snapshot

        backend.on_sync = other_worker_recovers
        res = self.sync(w1, "sync_real_key_0002", 2, [(M1, "disabled")])
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["error"]["code"], "concurrent_change")
        self.assertEqual(self.members(w1), {M1: "active"})
        self.assertEqual(w1.store.get_site("t_alpha").sync_version, 1)
        retry = self.sync(w1, "sync_real_key_0002", 2, [(M1, "disabled")])
        self.assertTrue(retry["ok"] and not retry["replayed"], retry)
        self.assertEqual(self.members(w1), {M1: "disabled"})


# ---- finding 5: tenant binding and tenant_id on adapter_events
class TenantBinding:
    def stores(self):
        """(unbound store, store bound to t_alpha, store bound to t_beta) on the same database."""
        raise NotImplementedError

    def test_events_are_stamped_and_scoped_by_tenant(self):
        any_, alpha, beta = self.stores()
        any_.append_event("e1", "x", {"n": 1}, "t_alpha")
        any_.append_event("e2", "x", {"n": 2}, "t_beta")
        alpha.append_event("e3", "x", {"n": 3})  # a bound store stamps its own tenant
        self.assertEqual([e["eventId"] for e in alpha.events()], ["e1", "e3"])
        self.assertEqual([e["eventId"] for e in beta.events()], ["e2"])
        self.assertEqual([e["eventId"] for e in any_.events("t_beta")], ["e2"])
        self.assertEqual(len(any_.events()), 3)  # an unbound store (dev, tests) still reads the whole stream

    def test_a_bound_store_refuses_other_tenants_everywhere(self):
        _, alpha, _ = self.stores()
        site_params = {"siteClass": "production", "engineTarget": {"adapter": "frappe"}, "blueprintId": "b", "countryPack": "sa"}
        calls = {
            "get_site": lambda: alpha.get_site("t_beta"),
            "create_site": lambda: alpha.create_site("t_beta", site_params),
            "append_event": lambda: alpha.append_event("e", "x", {}, "t_beta"),
            "events": lambda: alpha.events("t_beta"),
            "idem_put": lambda: alpha.idem_put("t_beta", "apply", "k", "a" * 64, {}),
            "acquire": lambda: alpha.acquire_operation("t_beta", "apply", "k", "a" * 64, "op", {}, {}, lock=False, lease_seconds=5),
            "members": lambda: alpha.get_members("t_beta"),
            "replace_members": lambda: alpha.replace_members("t_beta", {}),
            "field_data": lambda: alpha.write_field_data("t_beta", "customer", "/f", 1),
            "audit": lambda: alpha.insert_audit({"auditId": "aud_z", "operation": "apply", "requestId": None, "correlationId": None,
                                                 "tenant": "t_beta", "service": None, "onBehalfOf": None, "inputHash": None,
                                                 "artifactId": None, "result": None}),
        }
        for name, call in calls.items():
            with self.subTest(name), self.assertRaises(TenantMismatch):
                call()
        self.assertIsNotNone(alpha.create_site("t_alpha", site_params))
        self.assertIsNone(alpha.get_site("platform"))  # the platform id is served (health, capabilities)

    def test_a_misrouted_call_gets_tenant_not_found_and_leaves_no_trace(self):
        _, alpha, _ = self.stores()
        adapter = ChangeEngineAdapter(test_hooks=True, environment="test", store=alpha)
        mine = adapter.call("provision_site", _ctx("t_alpha"), PROVISION)
        self.assertTrue(mine["ok"], mine)
        other = adapter.call("provision_site", _ctx("t_beta"), {**PROVISION, "idempotencyKey": "prov_other_0001"})
        self.assertEqual(other["error"]["code"], "tenant_not_found")
        self.assertEqual({e["tenant"] for e in alpha.audit_log()}, {"t_alpha"})
        raw = self.stores()[0]
        self.assertIsNone(raw.get_site("t_beta"))
        self.assertEqual(raw.events("t_beta"), [])
        self.assertEqual({e["tenant"] for e in raw.audit_log()} - {None}, {"t_alpha"})


class SqliteTenantBinding(TenantBinding, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = str(Path(self._dir.name) / "state.sqlite")

    def stores(self):
        return (SQLiteAdapterStore(self.path), SQLiteAdapterStore(self.path, tenant_id="t_alpha"),
                SQLiteAdapterStore(self.path, tenant_id="t_beta"))


@mariadb_only
class MariaTenantBinding(TenantBinding, MariaDBBase):
    def stores(self):
        return (MariaDBAdapterStore(self._connect(self.db)), MariaDBAdapterStore(self._connect(self.db), tenant_id="t_alpha"),
                MariaDBAdapterStore(self._connect(self.db), tenant_id="t_beta"))


if __name__ == "__main__":
    unittest.main()
