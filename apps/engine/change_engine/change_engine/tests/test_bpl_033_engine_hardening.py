"""BPL-033 (PR #150 follow-ups), engine side: state-persistence errors fail closed and the journal follows the effect.

Offline only (the simulated engine runtime). Findings: Gemini review of PR #150, items 2 and 10, and the Codex
review's open item `adapter/engine.py:1117,1248`. Synthetic data only.
"""
from __future__ import annotations

import copy
import os
import time
import unittest
from contextlib import contextmanager
from unittest import mock

from change_engine.adapter import ADAPTER_ID, FrappeBackendError, make_frappe_adapter
from change_engine.adapter.engine import ChangeEngineAdapter
from change_engine.tests import test_bpl_027_fixture_real_adapter as bpl027

_ENV_PATCH = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})


def setUpModule():
    _ENV_PATCH.start()  # ERP-027: the offline DDL simulator is refused unless CHANGE_ENGINE_ENV is dev or test


def tearDownModule():
    _ENV_PATCH.stop()


TARGET = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
APPROVAL = {"changeApproved": "01J00000000000000000000010"}


class Bpl033EngineBase(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = make_frappe_adapter(simulated=True, test_hooks=False)
        self.backend = self.adapter.frappe_backend
        res = self.adapter.call("provision_site", bpl027.ctx(), {
            "idempotencyKey": "idemp_bpl033_prov", "engineTarget": TARGET, "blueprintId": "bp-offline",
            "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(res["ok"], res)
        self.art = bpl027.TestBpl027Offline._two_warehouse_artifact(TARGET)

    def apply(self, key: str = "idemp_bpl033_apply") -> dict:
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        res = self.adapter.call("apply", bpl027.ctx(), {"idempotencyKey": key, "artifact": self.art,
                                                 "planToken": plan["planToken"], "approvals": APPROVAL})
        self.assertTrue(res["ok"], res)
        return res["result"]

    def journal(self) -> list[tuple[int, str]]:
        return [(j["seq"], j["phase"]) for j in self.adapter.store.execution_journal()]

    def site_state(self) -> str:
        return self.adapter.call("site_status", bpl027.ctx(), {})["result"]["state"]


class TestJournalFollowsTheEffect(Bpl033EngineBase):
    def test_a_step_that_raised_is_not_journaled_as_run(self) -> None:
        """Contract 15.1: a step that failed before taking effect is not listed. It was journaled before it ran."""
        real = self.backend.execute_step

        def boom_on_step_2(tenant_id, step):
            if step["seq"] == 2:
                raise RuntimeError("engine down")
            return real(tenant_id, step)

        self.backend.execute_step = boom_on_step_2
        out = self.apply()
        self.assertEqual(out["status"], "recovery_required", out)  # fail closed: not proven side-effect-free
        self.assertEqual(self.journal(), [(1, "execute")])

    def test_a_journal_write_that_fails_after_the_step_took_effect_fails_closed(self) -> None:
        """The step ran on the engine; recording it failed. Never report applied or clean: block the site for a human."""
        ran: list[int] = []
        real = self.backend.execute_step
        self.backend.execute_step = lambda tenant_id, step: (ran.append(step["seq"]), real(tenant_id, step))[1]
        real_append = self.adapter.store.append_journal

        def append_fails_for_step_1(tenant_id, artifact_id, seq, phase):
            if (seq, phase) == (1, "execute"):
                raise OSError("journal store unavailable")
            return real_append(tenant_id, artifact_id, seq, phase)

        self.adapter.store.append_journal = append_fails_for_step_1
        out = self.apply()
        self.assertEqual(ran, [1], "the step took effect once, and no later step ran")
        self.assertEqual(out["status"], "recovery_required", out)
        self.assertEqual(out["error"]["code"], "recovery_required", out)
        self.assertEqual(out["site"]["state"], "recovery_required", out)
        self.assertEqual(self.site_state(), "recovery_required")

    def test_a_successful_apply_journals_every_step_once_after_it_ran(self) -> None:
        order: list[str] = []
        real = self.backend.execute_step
        real_append = self.adapter.store.append_journal
        self.backend.execute_step = lambda tenant_id, step: (order.append(f"run{step['seq']}"), real(tenant_id, step))[1]
        self.adapter.store.append_journal = lambda t, a, seq, ph: (order.append(f"journal{seq}"), real_append(t, a, seq, ph))[1]
        out = self.apply()
        self.assertEqual(out["status"], "applied", out)
        self.assertEqual(order, ["run1", "journal1", "run2", "journal2"])
        self.assertEqual(self.journal(), [(1, "execute"), (2, "execute")])


class TestStatePersistenceFailsClosed(Bpl033EngineBase):
    def break_state_persistence(self) -> None:
        def refuse(tenant_id, snapshot):
            raise RuntimeError("tenant database unavailable")

        self.backend.persist_site_state = refuse

    def test_a_failed_state_write_after_apply_is_surfaced_not_swallowed(self) -> None:
        self.break_state_persistence()
        out = self.apply()
        self.assertEqual(out["status"], "recovery_required", out)
        self.assertEqual(out["error"], {**out["error"], "code": "recovery_required"}, out)
        self.assertEqual(out["error"].get("stage"), "finalize", out)
        self.assertEqual(out["site"]["state"], "recovery_required", out)
        self.assertEqual(self.site_state(), "recovery_required")
        self.assertEqual(self.journal(), [(1, "execute"), (2, "execute")], "the steps did run; the journal says so")

    def test_the_failure_reaches_the_audit_log_the_event_stream_and_the_stored_outcome(self) -> None:
        self.break_state_persistence()
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        inp = {"idempotencyKey": "idemp_bpl033_apply_audit", "artifact": self.art, "planToken": plan["planToken"],
               "approvals": APPROVAL}
        out = self.adapter.call("apply", bpl027.ctx(), inp)["result"]
        self.assertEqual(self.adapter.store.audit_log()[-1]["result"], "recovery_required")
        types = [e["type"] for e in self.adapter.store.events()]
        self.assertIn("blueprint.apply_failed", types)
        self.assertNotIn("blueprint.applied", types)
        # a retry with the same key replays the recorded outcome; it does not run the steps a second time
        replay = self.adapter.call("apply", bpl027.ctx(), inp)
        self.assertEqual(replay["result"]["status"], "recovery_required", replay)
        self.assertEqual(replay["result"]["operationId"], out["operationId"])
        self.assertEqual(len(self.journal()), 2)

    def test_a_working_state_write_still_ends_applied(self) -> None:
        persisted: list[str] = []
        real = self.backend.persist_site_state
        self.backend.persist_site_state = lambda t, snap: (persisted.append(snap["state"]), real(t, snap))[1]
        out = self.apply()
        self.assertEqual(out["status"], "applied", out)
        # the copy is first written as a pending marker (recovery_required), then marked ready after the store commit
        self.assertEqual(persisted, ["recovery_required", "ready"])
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["state"], "ready")

    def test_a_clean_refusal_with_no_executed_step_never_rewrites_the_unchanged_state_copy(self) -> None:
        """Review of PR #301, finding 2: readiness and the state copy both hit an unavailable tenant database."""
        def unavailable(*args):
            raise FrappeBackendError("engine_unavailable", stage="prepare", side_effect_free=True)

        writes: list[str] = []
        self.backend.check_ready = unavailable
        self.backend.persist_site_state = lambda t, snap: (writes.append(snap["state"]), unavailable())[1]
        out = self.apply()
        self.assertEqual(out["status"], "failed_clean", out)
        self.assertEqual(out["error"]["code"], "engine_unavailable", out)
        self.assertEqual(out["site"]["state"], "ready", out)
        self.assertEqual(self.site_state(), "ready")
        self.assertEqual(writes, [], "nothing took effect, so the tenant-state copy is not rewritten")

    def test_an_already_applied_replay_with_a_broken_state_copy_stays_already_applied(self) -> None:
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        inp = {"artifact": self.art, "planToken": plan["planToken"], "approvals": APPROVAL}
        self.assertEqual(self.adapter.call("apply", bpl027.ctx(), {**inp, "idempotencyKey": "idemp_bpl033_first"})["result"]["status"],
                         "applied")
        self.break_state_persistence()
        out = self.adapter.call("apply", bpl027.ctx(), {**inp, "idempotencyKey": "idemp_bpl033_again"})["result"]
        self.assertEqual(out["status"], "already_applied", out)
        self.assertEqual(self.site_state(), "ready")

    def test_a_run_where_a_step_took_effect_still_fails_closed_when_the_copy_cannot_be_written(self) -> None:
        self.backend.execute_step = lambda tenant_id, step: (_ for _ in ()).throw(
            FrappeBackendError("site_not_ready", stage="execute", side_effect_free=True)) if step["seq"] == 2 else None
        self.break_state_persistence()
        out = self.apply()
        self.assertEqual(out["status"], "recovery_required", out)
        self.assertEqual(self.site_state(), "recovery_required")


class _Death(BaseException):
    """A simulated process death: nothing catches it, nothing after it runs."""


class TestStateCopyAndStoreStayConsistent(Bpl033EngineBase):
    def dying_store(self) -> dict:
        """The store transaction that wrote the tenant-state copy never commits (the process dies first)."""
        armed = {"v": False}
        real_tx, real_persist = self.adapter.store.transaction, self.backend.persist_site_state
        self.backend.persist_site_state = lambda t, snap: (real_persist(t, snap), armed.update(v=True))[0]

        @contextmanager
        def dying():
            with real_tx():
                yield
                if armed["v"]:
                    raise _Death()  # leaving the real transaction on an exception rolls it back

        self.adapter.store.transaction = dying
        return armed

    def test_death_between_the_state_copy_commit_and_the_store_commit_leaves_no_ready_copy(self) -> None:
        """Review of PR #301, finding 3: the copy must not say ready while lease recovery marks the operation
        recovery_required."""
        self.dying_store()
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        with self.assertRaises(_Death):
            self.adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033_death", "artifact": self.art,
                                                      "planToken": plan["planToken"], "approvals": APPROVAL})
        self.adapter.store.transaction = type(self.adapter.store).transaction.__get__(self.adapter.store)
        self.adapter.store.clock = lambda: time.time() + 10_000_000  # the dead worker's lease ran out
        self.assertEqual(self.adapter.recover_interrupted(), 1)
        self.assertEqual(self.site_state(), "recovery_required")
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["state"], "recovery_required",
                         "the copy and the operation store must not diverge")

    def test_a_failed_mark_ready_after_the_store_commit_leaves_the_conservative_copy_and_the_stored_outcome(self) -> None:
        real = self.backend.persist_site_state

        def ready_write_fails(tenant_id, snap):
            if snap["state"] == "ready":
                raise RuntimeError("tenant database unavailable")
            return real(tenant_id, snap)

        self.backend.persist_site_state = ready_write_fails
        out = self.apply()
        self.assertEqual(out["status"], "applied", out)  # the outcome is committed and true
        self.assertEqual(self.site_state(), "ready")
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["state"], "recovery_required", "fail closed")


class TestStateCopyMirrorsTheStore(Bpl033EngineBase):
    """Re-review of PR #301 at cb5a8ce. The operation store is the source of truth; the tenant-database copy is a mirror.
    Writes made while the operation still holds the site lock go in unconditionally; every write made after the lock was
    released (mark ready, repair) is a compare-and-set on the write token it saw, so a stale writer changes nothing."""

    def second_artifact(self) -> dict:
        """A second revision on top of the first, with its own warehouses, so a second operation can run after the first."""
        art = copy.deepcopy(self.art)
        old, new = art["blueprint"]["target"], {"hash": "sha256:" + "2" * 64, "revision": 2}
        steps = []
        for step in art["steps"]:
            wid = step["subject"]["id"].replace("wh_", "new_")
            step["subject"]["id"], step["pointer"], step["sourceOps"] = wid, "/locations/" + wid, ["/locations/" + wid]
            step["params"]["definition"]["id"] = wid
            steps.append(step)
        art["blueprint"].update(base=old, target=new)
        undo = [{**copy.deepcopy(s), "kind": "location.disable", "phase": 17} for s in steps]
        inverse = {**copy.deepcopy(art), "kind": "inverse", "steps": undo, "inverse": None}
        inverse["blueprint"].update(base=new, target=old)
        art["inverse"] = bpl027.seal(inverse)
        return bpl027.seal(art)

    def hydrated_state(self) -> str:
        fresh = ChangeEngineAdapter(environment="test", frappe_backend=self.backend)  # an empty store: hydrates from the copy
        return fresh.call("site_status", bpl027.ctx(), {})["result"]["state"]

    def copy_state(self) -> str:
        return self.backend.load_site_state(bpl027.TENANT)["state"]

    def test_a_stale_worker_cannot_overwrite_newer_recovery_state(self) -> None:
        """Finding 1: worker A commits, releases the lock and pauses before its final copy write; worker B runs a step and
        ends recovery_required; A resumes and used to write `ready` over it."""
        real, nested = self.backend.persist_site_state, []
        second = self.second_artifact()
        run_step = self.backend.execute_step

        def paused_stale_writer(tenant_id, snap):
            if snap["state"] == "ready" and not nested:  # A's final write; the store has committed and the lock is free
                nested.append(None)
                self.assertIsNone(self.adapter.store.get_site(tenant_id).lock)

                def committed_write_then_lost_response(tenant, step):
                    run_step(tenant, step)
                    raise RuntimeError("lost response after a committed engine write")

                self.backend.execute_step = committed_write_then_lost_response
                plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": second})
                self.assertTrue(plan["ok"], plan)
                nested[0] = self.adapter.call("apply", bpl027.ctx(), {
                    "idempotencyKey": "idemp_bpl033_second", "artifact": second,
                    "planToken": plan["result"]["planToken"], "approvals": APPROVAL})["result"]
            return real(tenant_id, snap)

        self.backend.persist_site_state = paused_stale_writer
        first = self.apply("idemp_bpl033_first")
        self.assertEqual(first["status"], "applied", first)
        self.assertEqual(nested[0]["status"], "recovery_required", nested[0])
        self.assertEqual(self.site_state(), "recovery_required")
        self.assertEqual(self.copy_state(), "recovery_required", "the stale `ready` write must be a no-op")
        self.assertEqual(self.hydrated_state(), "recovery_required")

    def test_a_stale_mark_ready_is_a_no_op_after_a_newer_clean_operation_too(self) -> None:
        """The same stale writer when the newer operation succeeded: the copy keeps the newer applied revision."""
        real, nested, second = self.backend.persist_site_state, [], self.second_artifact()

        def paused_stale_writer(tenant_id, snap):
            if snap["state"] == "ready" and not nested:
                nested.append(None)
                plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": second})
                nested[0] = self.adapter.call("apply", bpl027.ctx(), {
                    "idempotencyKey": "idemp_bpl033_second_ok", "artifact": second,
                    "planToken": plan["result"]["planToken"], "approvals": APPROVAL})["result"]
                self.backend.persist_site_state = real  # the newer operation is done; only A's write is left
            return real(tenant_id, snap)

        self.backend.persist_site_state = paused_stale_writer
        self.apply("idemp_bpl033_first")
        self.assertEqual(nested[0]["status"], "applied", nested[0])
        stored = self.adapter.store.get_site(bpl027.TENANT)
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["applied"], stored.applied)
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["applied"]["revision"]["revision"], 2)

    def crash_before_mark_ready(self, inp_key: str):
        """The store committed; the process dies (or the tenant database fails) before the copy is marked ready."""
        real = self.backend.persist_site_state

        def die_on_ready(tenant_id, snap):
            if snap["state"] == "ready":
                raise _Death()
            return real(tenant_id, snap)

        self.backend.persist_site_state = die_on_ready
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        inp = {"idempotencyKey": inp_key, "artifact": self.art, "planToken": plan["planToken"], "approvals": APPROVAL}
        with self.assertRaises(_Death):
            self.adapter.call("apply", bpl027.ctx(), inp)
        self.backend.persist_site_state = real
        self.assertEqual(self.site_state(), "ready")
        self.assertEqual(self.copy_state(), "recovery_required", "precondition: the marker is left behind")
        return inp

    def test_recover_interrupted_repairs_a_marker_left_by_a_crash_before_mark_ready(self) -> None:
        """Finding 2: the store says ready and applied, the copy still says recovery_required, and nothing repaired it."""
        self.crash_before_mark_ready("idemp_bpl033_crash")
        self.adapter.store.clock = lambda: time.time() + 10_000_000
        self.adapter.recover_interrupted()
        self.assertEqual(self.copy_state(), "ready")
        self.assertEqual(self.hydrated_state(), "ready")

    def test_a_same_key_replay_repairs_the_marker(self) -> None:
        inp = self.crash_before_mark_ready("idemp_bpl033_crash_replay")
        self.assertEqual(self.adapter.call("apply", bpl027.ctx(), inp)["result"]["status"], "applied")
        self.assertEqual(self.copy_state(), "ready")

    def test_a_new_key_already_applied_repairs_the_marker(self) -> None:
        inp = self.crash_before_mark_ready("idemp_bpl033_crash_new_key")
        out = self.adapter.call("apply", bpl027.ctx(), {**inp, "idempotencyKey": "idemp_bpl033_new_key"})["result"]
        self.assertEqual(out["status"], "already_applied", out)
        self.assertEqual(self.copy_state(), "ready")
        self.assertEqual(self.hydrated_state(), "ready")

    def test_a_failed_mark_ready_is_repaired_the_same_way(self) -> None:
        real = self.backend.persist_site_state

        def ready_write_fails(tenant_id, snap):
            if snap["state"] == "ready":
                raise OSError("transient ready-write failure")
            return real(tenant_id, snap)

        self.backend.persist_site_state = ready_write_fails
        self.assertEqual(self.apply()["status"], "applied")
        self.backend.persist_site_state = real
        self.assertEqual(self.copy_state(), "recovery_required")
        self.adapter.recover_interrupted()
        self.assertEqual(self.copy_state(), "ready")

    def test_a_worker_that_dies_during_the_steps_leaves_a_copy_the_recovery_sweep_corrects(self) -> None:
        """The window the first round left open: death before finalize leaves the copy at the old `ready`; lease recovery
        marks the store recovery_required and the sweep now carries that into the copy."""
        real = self.backend.execute_step

        def die_in_step_2(tenant_id, step):
            if step["seq"] == 2:
                raise _Death()
            return real(tenant_id, step)

        self.backend.execute_step = die_in_step_2
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": self.art})["result"]
        with self.assertRaises(_Death):
            self.adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033_die_in_steps", "artifact": self.art,
                                                      "planToken": plan["planToken"], "approvals": APPROVAL})
        self.backend.execute_step = real
        self.assertEqual(self.copy_state(), "ready", "precondition: nothing wrote the copy yet")
        self.adapter.store.clock = lambda: time.time() + 10_000_000
        self.assertEqual(self.adapter.recover_interrupted(), 1)
        self.assertEqual(self.site_state(), "recovery_required")
        self.assertEqual(self.copy_state(), "recovery_required")
        self.assertEqual(self.hydrated_state(), "recovery_required")

    def test_repair_never_runs_over_a_running_operation_and_never_unblocks_a_blocked_site(self) -> None:
        """A site the store holds as recovery_required stays blocked in the copy; a locked site is left to its operation."""
        self.backend.execute_step = lambda tenant_id, step: (_ for _ in ()).throw(RuntimeError("engine down")) if step["seq"] == 2 else None
        self.assertEqual(self.apply()["status"], "recovery_required")
        self.assertEqual(self.copy_state(), "recovery_required")
        self.adapter.recover_interrupted()
        self.assertEqual(self.copy_state(), "recovery_required")
        self.assertEqual(self.hydrated_state(), "recovery_required")

    def test_a_write_that_expects_another_token_changes_nothing(self) -> None:
        """The compare-and-set itself, on the backend: the copy is replaced only while it still carries the expected token."""
        site = self.adapter.store.get_site(bpl027.TENANT)
        first = {**ChangeEngineAdapter._site_snapshot(site), "write_token": "tok_1"}
        self.backend.persist_site_state(bpl027.TENANT, first)
        stale = {**first, "state": "ready", "history": [{"stale": True}], "write_token": "tok_stale", "expect_token": "tok_0"}
        self.backend.persist_site_state(bpl027.TENANT, stale)
        loaded = self.backend.load_site_state(bpl027.TENANT)
        self.assertEqual(loaded["history"], [], "a writer that expected tok_0 must not replace tok_1")
        self.assertEqual(loaded["write_token"], "tok_1")
        self.backend.persist_site_state(bpl027.TENANT, {**stale, "expect_token": "tok_1", "write_token": "tok_2"})
        loaded = self.backend.load_site_state(bpl027.TENANT)
        self.assertEqual((loaded["history"], loaded["write_token"]), ([{"stale": True}], "tok_2"))

    def test_a_schema_valid_zero_step_apply_updates_the_copy_with_the_store(self) -> None:
        """Finding 3: a zero-step artifact is applied, the store's applied revision and history advance, the copy stayed null."""
        art = copy.deepcopy(self.art)
        art["steps"] = []
        art["risk"]["counts"]["config"], art["risk"]["total"], art["risk"]["maxImpact"] = 0, 0, "cosmetic"
        art = bpl027.seal(art)
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": art})
        self.assertTrue(plan["ok"], plan)
        out = self.adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033_zero", "artifact": art,
                                                 "planToken": plan["result"]["planToken"], "approvals": APPROVAL})["result"]
        self.assertEqual(out["status"], "applied", out)
        stored = self.adapter.store.get_site(bpl027.TENANT)
        self.assertIsNotNone(stored.applied)
        loaded = self.backend.load_site_state(bpl027.TENANT)
        self.assertEqual(loaded["applied"], stored.applied)
        self.assertEqual(loaded["history"], stored.history)
        self.assertEqual(loaded["state"], "ready")


class TestRecoveryRotatesTheCopyToken(Bpl033EngineBase):
    """Re-review 2 at aa8849d: a recovery that left a matching copy untouched kept an older writer's token valid, so a
    paused mark-ready or repair could promote the copy to ready after the store was blocked. Recovery now rewrites the
    copy of every site it closed with a fresh token."""

    second_artifact = TestStateCopyMirrorsTheStore.second_artifact
    crash_before_mark_ready = TestStateCopyMirrorsTheStore.crash_before_mark_ready
    copy_state = TestStateCopyMirrorsTheStore.copy_state
    hydrated_state = TestStateCopyMirrorsTheStore.hydrated_state

    def _second_worker_dies_and_is_recovered(self) -> None:
        art = self.second_artifact()
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": art})
        self.assertTrue(plan["ok"], plan)
        real_step = self.backend.execute_step

        def die_after_step(tenant, step):
            real_step(tenant, step)
            raise _Death()

        with mock.patch.object(self.backend, "execute_step", side_effect=die_after_step):
            with self.assertRaises(_Death):
                self.adapter.call("apply", bpl027.ctx(), {"artifact": art, "planToken": plan["result"]["planToken"],
                                                          "idempotencyKey": "idemp_bpl033_rotate_second",
                                                          "approvals": APPROVAL})
        self.adapter.store.clock = lambda: time.time() + 10_000_000
        self.assertEqual(self.adapter.recover_interrupted(), 1)
        self.assertEqual(self.site_state(), "recovery_required")

    def _pause_first_ready_write(self):
        real = self.backend.persist_site_state
        entered = []

        def pause(tenant, snap):
            if snap["state"] == "ready" and not entered:
                entered.append(True)
                self._second_worker_dies_and_is_recovered()
            return real(tenant, snap)

        return mock.patch.object(self.backend, "persist_site_state", side_effect=pause)

    def _assert_blocked_everywhere(self) -> None:
        self.assertEqual(self.site_state(), "recovery_required")
        self.assertEqual(self.backend.load_site_state(bpl027.TENANT)["state"], "recovery_required")
        fresh = ChangeEngineAdapter(environment="test", frappe_backend=self.backend)
        self.assertEqual(fresh.call("site_status", bpl027.ctx(), {})["result"]["state"], "recovery_required")

    def test_a_paused_mark_ready_cannot_promote_the_copy_after_a_later_recovery(self) -> None:
        with self._pause_first_ready_write():
            self.assertEqual(self.apply("idemp_bpl033_rotate_first")["status"], "applied")
        self._assert_blocked_everywhere()

    def test_a_paused_repair_cannot_promote_the_copy_after_a_later_recovery(self) -> None:
        self.crash_before_mark_ready("idemp_bpl033_rotate_crash")
        with self._pause_first_ready_write():
            self.adapter._repair_state_copy(bpl027.TENANT)
        self._assert_blocked_everywhere()


class TestReadinessBeforeExecute(Bpl033EngineBase):
    def test_a_site_that_is_not_ready_fails_clean_before_any_step_runs(self) -> None:
        ran: list[int] = []
        self.backend.execute_step = lambda tenant_id, step: ran.append(step["seq"])

        def not_ready(tenant_id, steps):
            raise FrappeBackendError("site_not_ready", stage="prepare", side_effect_free=True)

        self.backend.check_ready = not_ready
        out = self.apply()
        self.assertEqual(ran, [], "no step may run on a site that is not ready")
        self.assertEqual(out["status"], "failed_clean", out)
        self.assertEqual(out["error"]["code"], "site_not_ready", out)
        self.assertEqual(self.journal(), [])
        self.assertEqual(self.site_state(), "ready")
        self.assertEqual([s["status"] for s in out["steps"]], ["not_run", "not_run"])

    def test_the_real_check_runs_with_the_steps_of_the_artifact(self) -> None:
        seen: list[list[int]] = []
        real = self.backend.check_ready
        self.backend.check_ready = lambda tenant_id, steps: (seen.append([s["seq"] for s in steps]), real(tenant_id, steps))[1]
        self.assertEqual(self.apply()["status"], "applied")
        self.assertEqual(seen, [[1, 2]])


class TestDisableNeedsAKindEndToEnd(Bpl033EngineBase):
    def test_a_schema_valid_disable_without_a_kind_fails_clean_and_leaves_the_warehouse_alone(self) -> None:
        """Review of PR #301, finding 1: the plan accepts it, so the refusal must come from the adapter, before any write."""
        base_target = self.art["blueprint"]["target"]
        self.assertEqual(self.apply()["status"], "applied")  # wh_a exists, as the first revision
        ran: list[str] = []
        real = self.backend.execute_step
        self.backend.execute_step = lambda tenant_id, step: (ran.append(step["kind"]), real(tenant_id, step))[1]
        disable = {"seq": 1, "phase": 17, "kind": "location.disable", "subject": {"kind": "location", "id": "wh_a", "parents": []},
                   "pointer": "/locations/wh_a", "impact": "config", "ddlImpact": "none", "reversible": True,
                   "params": {"definition": {"id": "wh_a", "labels": {"en": "wh_a", "ar": "wh_a"}}}, "sourceOps": ["/locations/wh_a"]}
        target_2 = {"hash": "sha256:" + "2" * 64, "revision": 2}
        undo = {**self.art["steps"][0], "seq": 1, "phase": 3}  # the inverse of a disable re-creates the warehouse
        inverse = bpl027.seal({**self.art, "kind": "inverse", "steps": [undo], "inverse": None,
                               "blueprint": {**self.art["blueprint"], "base": target_2, "target": base_target}})
        art = bpl027.seal({**self.art, "steps": [disable], "inverse": inverse,
                           "blueprint": {**self.art["blueprint"], "base": base_target, "target": target_2}})
        plan = self.adapter.call("plan", bpl027.ctx(), {"artifact": art})
        self.assertTrue(plan["ok"], plan)
        out = self.adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033_disable", "artifact": art,
                                                 "planToken": plan["result"]["planToken"], "approvals": APPROVAL})["result"]
        self.assertEqual(out["status"], "failed_clean", out)
        self.assertEqual(out["error"]["code"], "invalid_request", out)
        self.assertEqual(ran, [], "no step of the refused artifact ran")
        self.assertEqual(self.journal(), [(1, "execute"), (2, "execute")], "only the first apply is journaled")


if __name__ == "__main__":
    unittest.main()
