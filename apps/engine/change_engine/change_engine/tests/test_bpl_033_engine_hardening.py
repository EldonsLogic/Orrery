"""BPL-033 (PR #150 follow-ups), engine side: state-persistence errors fail closed and the journal follows the effect.

Offline only (the simulated engine runtime). Findings: Gemini review of PR #150, items 2 and 10, and the Codex
review's open item `adapter/engine.py:1117,1248`. Synthetic data only.
"""
from __future__ import annotations

import os
import time
import unittest
from contextlib import contextmanager
from unittest import mock

from change_engine.adapter import ADAPTER_ID, FrappeBackendError, make_frappe_adapter
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
