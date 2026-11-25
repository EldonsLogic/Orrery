"""CE-SEC-011 slice 1 (G1, Tier 3): the property-setter, workflow and report engines, and the revert,
follow the single-field path's lock discipline.

  (a) site-scoped idempotency lock, then the target lock; a fresh read view after the locks; a lookup that
      fails blocks; the session timeout is set and read back before the intent; a release that is not verified
      discards the session;
  (b) stable reason codes and fixed text, never exception text (a marker string proves it);
  (c) the revert hold check runs under the target lock, on a fresh view, inside the rollback engine;
  (d) a custom ``site_map`` tenant's site resolves to the tenant id through the backend's resolver.

Reuses the transactional, fault-injecting database double of the CE-SEC-008 tests. Synthetic data only.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.adapter.frappe_backend import FrappeRuntimeBackend, FrappeSiteResolver  # noqa: E402
from change_engine.api import endpoints  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.schema_reconciler import (  # noqa: E402
    RevisionHashError,
    make_bounded_lock_key,
    make_idempotency_lock_key,
)
from change_engine.tests.test_ce_sec_008_deploy_path_durability import FIELD, _Bench, _DbDown  # noqa: E402
from change_engine.tests.test_ce_sec_008_review_fixes import (  # noqa: E402
    ADMIN,
    SECRET,
    TENANT,
    _entry_points,
    _frappe_stub,
)

ENGINES = ("property_setter", "workflow", "report")
TARGET = {"property_setter": "Item", "workflow": "Sales Order", "report": "Sales Order"}
DEP = {"property_setter": "dep_ps", "workflow": "dep_wf", "report": "dep_rp"}


def _spy(adapter, order, *names):
    for name in names:
        original = getattr(adapter, name)
        setattr(adapter, name, (lambda n, f: lambda *a, **k: (order.append((n, a)), f(*a, **k))[1])(name, original))


def _no_row(bench):
    """Nothing was recorded: no intent, so nothing could have been applied."""
    return not [r for r in bench.db.committed.values() if r["deployment_id"].startswith("dep_")]


def _finished_field_deployment(bench, adapter):
    """An APPLIED single-field deployment ``dep_1`` on Item: what a revert quarantines."""
    bench.module.make_property_setter = lambda *a, **k: None
    out = bench.deploy(adapter)
    assert out["status"] == "APPLIED", out
    return out


# ===========================================================================================
class TestA1LockOrderAndFreshView(unittest.TestCase):
    def test_idempotency_lock_then_target_lock_then_fresh_view_then_lookups_then_timeout_then_intent(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                order = []
                _spy(adapter, order, "acquire_advisory_lock", "begin_fresh_read_view",
                     "get_existing_deployment_by_idempotency", "is_target_in_recovery_required",
                     "set_lock_wait_timeout", "persist_prepare_and_audit_intent", "release_advisory_lock")
                out = calls[name](dep=DEP[name])
                self.assertNotEqual(out.get("stage"), "ACQUIRE", out)
                names = [n for n, _ in order]
                first = {n: names.index(n) for n in set(names)}
                site = bench.db.row(DEP[name])["site_id"]
                idem = make_idempotency_lock_key(site, f"idemp-{DEP[name]}")
                target = make_bounded_lock_key(site, TARGET[name])
                acquired = [a[0] for n, a in order if n == "acquire_advisory_lock"]
                self.assertEqual(acquired, [idem, target], "the site-scoped idempotency lock first, then the target")
                released = [a[0] for n, a in order if n == "release_advisory_lock"]
                self.assertEqual(released, [target, idem], "released in reverse")
                self.assertEqual(bench.db.locks, set())
                self.assertLess(first["acquire_advisory_lock"], first["begin_fresh_read_view"])
                self.assertLess(first["begin_fresh_read_view"], first["get_existing_deployment_by_idempotency"])
                self.assertLess(first["begin_fresh_read_view"], first["is_target_in_recovery_required"])
                self.assertLess(first["is_target_in_recovery_required"], first["set_lock_wait_timeout"])
                self.assertLess(first["set_lock_wait_timeout"], first["persist_prepare_and_audit_intent"])

    def test_a_second_lock_that_cannot_be_taken_releases_the_first(self):
        for name in ENGINES:
            for fault in ("timeout", "raises"):
                with self.subTest(engine=name, fault=fault):
                    bench = _Bench()
                    calls, adapter = _entry_points(bench)
                    real = adapter.acquire_advisory_lock
                    taken = []

                    def acquire(key, wait_seconds, real=real, taken=taken, fault=fault):
                        taken.append(key)
                        if len(taken) == 2:
                            if fault == "raises":
                                raise _DbDown(SECRET)
                            return 0
                        return real(key, wait_seconds)

                    adapter.acquire_advisory_lock = acquire
                    out = calls[name](dep=DEP[name])
                    self.assertEqual((out["status"], out["stage"]), ("REJECTED", "ACQUIRE"), out)
                    self.assertNotIn("SECRET", json.dumps(out))
                    self.assertEqual(bench.db.locks, set(), "the idempotency lock is not left behind")
                    self.assertTrue(_no_row(bench))

    def test_a_fresh_view_that_cannot_be_opened_blocks_with_no_effect(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                adapter.begin_fresh_read_view = lambda: (_ for _ in ()).throw(_DbDown(SECRET))
                out = calls[name](dep=DEP[name])
                self.assertEqual(out["status"], "REJECTED")
                self.assertEqual(out["reason_code"], "engine_unavailable")
                self.assertNotIn("SECRET", json.dumps(out))
                self.assertTrue(_no_row(bench))
                self.assertEqual(bench.db.locks, set())

    def test_a_row_committed_while_waiting_for_the_locks_is_seen(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                target = TARGET[name]

                def other_session_commits(_lock, bench=bench, target=target):
                    bench.db.committed.setdefault("other", {
                        "name": "other", "deployment_id": "other", "idempotency_key": "key-other",
                        "payload_hash": "h-other", "site_id": "default", "doctype": target, "fieldname": None,
                        "base_revision_hash": "r", "ddl_plan_statements": "[]", "status": "PREPARED",
                        "outcome_json": None})

                adapter.get_doctype_revision_hash("Item")  # a read before the locks opens the read view
                bench.db.on_lock = other_session_commits
                with mock.patch.object(endpoints, "frappe", _frappe_stub("default")):
                    out = calls[name](dep=DEP[name])
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
                self.assertTrue(_no_row(bench))


class TestA2LookupFailureBlocks(unittest.TestCase):
    def test_a_failed_idempotency_or_recovery_lookup_blocks_and_is_never_read_as_nothing_found(self):
        for name in ENGINES:
            for lookup in ("get_existing_deployment_by_idempotency", "is_target_in_recovery_required"):
                with self.subTest(engine=name, lookup=lookup):
                    bench = _Bench()
                    calls, adapter = _entry_points(bench)
                    setattr(adapter, lookup, lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET)))
                    out = calls[name](dep=DEP[name])
                    self.assertEqual(out["status"], "REJECTED", out)
                    self.assertEqual(out["reason_code"], "engine_unavailable")
                    self.assertNotIn("SECRET", json.dumps(out))
                    self.assertTrue(_no_row(bench), "no intent was written")
                    self.assertEqual(bench.db.locks, set())

    def test_a_stored_outcome_that_is_not_an_object_blocks_instead_of_raising(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                adapter.get_existing_deployment_by_idempotency = lambda *a, **k: {"payload_hash": "x", "outcome": None}
                out = calls[name](dep=DEP[name])
                self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
                self.assertTrue(_no_row(bench))


class TestA3TimeoutIsEffectiveBeforeTheIntent(unittest.TestCase):
    def _assert_refused(self, bench, out):
        self.assertEqual(out["status"], "REJECTED", out)
        self.assertEqual(out["reason_code"], "lock_timeout_not_effective")
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertTrue(_no_row(bench), "nothing is written when the timeout is not effective")
        self.assertEqual(bench.db.locks, set())

    def test_a_timeout_that_does_not_take_is_refused_before_the_intent(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, _adapter = _entry_points(bench)
                bench.db.ignore_timeout_set = True  # the setting is silently ignored: the read-back differs
                self._assert_refused(bench, calls[name](dep=DEP[name]))

    def test_an_empty_read_back_or_a_failing_setter_is_refused_before_the_intent(self):
        for name in ENGINES:
            for fault in ("empty", "setter_raises"):
                with self.subTest(engine=name, fault=fault):
                    bench = _Bench()
                    calls, _adapter = _entry_points(bench)
                    if fault == "empty":
                        bench.db.readback = "empty"
                    else:
                        bench.db.fail("SET SESSION LOCK_WAIT_TIMEOUT", _DbDown(SECRET))
                    self._assert_refused(bench, calls[name](dep=DEP[name]))

    def test_the_caller_session_gets_its_own_timeout_back(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, _adapter = _entry_points(bench)
                calls[name](dep=DEP[name])
                self.assertEqual(bench.db.lock_wait_timeout, 50, "the session's previous value is restored")


class TestA4ReleaseIsVerified(unittest.TestCase):
    def test_a_release_that_fails_or_is_not_confirmed_discards_the_session(self):
        for name in ENGINES:
            for fault in ("raises", "not_held"):
                with self.subTest(engine=name, fault=fault):
                    bench = _Bench()
                    calls, _adapter = _entry_points(bench)
                    if fault == "raises":
                        bench.db.fail("SELECT RELEASE_LOCK", _DbDown(SECRET))
                    else:
                        bench.db.release_result = 0
                    out = calls[name](dep=DEP[name])
                    self.assertNotIn("SECRET", json.dumps(out))
                    self.assertTrue(bench.db.closed, "the connection that may still hold a lock is discarded")
                    again = calls[name](dep=DEP[name] + "_2")
                    self.assertEqual((again["status"], again["stage"]), ("REJECTED", "ACQUIRE"), again)

    def test_an_engine_that_raises_still_releases_both_locks(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                adapter.persist_prepare_and_audit_intent = lambda r: (_ for _ in ()).throw(KeyboardInterrupt())
                with self.assertRaises(KeyboardInterrupt):
                    calls[name](dep=DEP[name])
                self.assertEqual(bench.db.locks, set())

    def test_a_clean_run_does_not_discard_the_session(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, _adapter = _entry_points(bench)
                calls[name](dep=DEP[name])
                self.assertFalse(bench.db.closed)


# ===========================================================================================
class TestB1StableReasonCodesNoExceptionText(unittest.TestCase):
    def _out(self, name, setup):
        bench = _Bench()
        calls, adapter = _entry_points(bench)
        setup(bench, adapter)
        out = calls[name](dep=DEP[name])
        self.assertNotIn("SECRET", json.dumps(out, default=str), out)
        return out

    def test_a_failed_prepare_is_a_stable_code(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                out = self._out(name, lambda b, a: setattr(
                    a, "persist_prepare_and_audit_intent", lambda r: (_ for _ in ()).throw(_DbDown(SECRET))))
                self.assertEqual((out["status"], out["disposition"], out["reason_code"]),
                                 ("FAILED_CLEAN", "AUDIT_PREPARE_FAILED", "audit_prepare_failed"))

    def test_a_failed_apply_is_a_stable_code(self):
        def property_setter(bench, adapter):
            bench.module.make_property_setter = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))

        def workflow(bench, adapter):
            adapter.apply_workflow = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))

        def report(bench, adapter):
            adapter.apply_report = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))

        for name, setup in (("property_setter", property_setter), ("workflow", workflow), ("report", report)):
            with self.subTest(engine=name):
                out = self._out(name, setup)
                self.assertEqual((out["status"], out["stage"], out["reason_code"]),
                                 ("FAILED_CLEAN", "APPLY", "apply_failed"))

    def test_a_failed_finalization_is_a_stable_code(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                out = self._out(name, lambda b, a: setattr(
                    a, "persist_final_outcome_and_audit", lambda *x, **k: (_ for _ in ()).throw(_DbDown(SECRET))))
                self.assertEqual(out["status"], "RECOVERY_REQUIRED")
                self.assertEqual(out["finalization_error"], "finalization_failed")

    def test_an_unreadable_revision_is_a_stable_code(self):
        out = self._out("property_setter", lambda b, a: setattr(
            a, "get_doctype_revision_hash", lambda d: (_ for _ in ()).throw(RevisionHashError(SECRET))))
        self.assertEqual((out["status"], out["disposition"], out["reason_code"]),
                         ("REJECTED", "REVISION_HASH_UNAVAILABLE", "revision_unavailable"))

    def test_an_invalid_definition_does_not_echo_the_validator_text(self):
        from change_engine.guarded_apply.report_engine import execute_report_deployment
        from change_engine.guarded_apply.workflow_engine import execute_workflow_deployment

        db = FrappeDeploymentAdapter(in_memory=True, use_shared_state=False)
        wf = execute_workflow_deployment(db=db, deployment_id="dep_wf", site_id="default", doctype="Sales Order",
                                         workflow_def={"workflow_name": "W", "states": "SECRET-states"},
                                         user_roles=ADMIN)
        rp = execute_report_deployment(db=db, deployment_id="dep_rp", site_id="default", doctype="Sales Order",
                                       report_def={"report_name": "R", "columns": "SECRET-columns"},
                                       user_roles=["Sales Manager"])
        for out, code in ((wf, "invalid_workflow_payload"), (rp, "invalid_report_payload")):
            with self.subTest(code=code):
                self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", code), out)
                self.assertNotIn("SECRET", json.dumps(out, default=str))

    def test_lock_failures_carry_a_code(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                adapter.acquire_advisory_lock = lambda *a, **k: 0
                out = calls[name](dep=DEP[name])
                self.assertEqual((out["disposition"], out["reason_code"]), ("LOCK_CONTENTION_OR_TIMEOUT", "lock_timeout"))
                adapter.acquire_advisory_lock = lambda *a, **k: (_ for _ in ()).throw(_DbDown(SECRET))
                out = calls[name](dep=DEP[name])
                self.assertEqual((out["stage"], out["reason_code"]), ("ACQUIRE", "engine_unavailable"))
                self.assertNotIn("SECRET", json.dumps(out))


# ===========================================================================================
class TestC1RevertHoldIsCheckedUnderTheTargetLock(unittest.TestCase):
    def _revert(self, adapter, roles=ADMIN):
        return endpoints.revert_configuration_change(deployment_id="dep_1", adapter=adapter, user_roles=roles)

    def test_the_hold_is_read_after_the_lock_and_a_fresh_view(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        order = []
        _spy(adapter, order, "acquire_advisory_lock", "begin_fresh_read_view", "get_deployment_record",
             "release_advisory_lock")
        out = self._revert(adapter)
        self.assertEqual(out["status"], "QUARANTINED", out)
        names = [n for n, _ in order]
        lock_at = names.index("acquire_advisory_lock")
        view_at = names.index("begin_fresh_read_view")
        reads = [i for i, n in enumerate(names) if n == "get_deployment_record"]
        self.assertLess(lock_at, view_at)
        self.assertTrue(any(i > view_at for i in reads), "the hold is read on the fresh view, under the lock")
        self.assertEqual(names.count("acquire_advisory_lock"), 1)
        self.assertEqual(names[-1], "release_advisory_lock")
        self.assertEqual(bench.db.locks, set())

    def test_a_hold_that_appears_while_waiting_for_the_lock_blocks_the_revert(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        before = len(bench.db.sql_log)

        def goes_on_hold(_lock):
            row = bench.db.committed["dep_1"]
            row["status"] = "RECOVERY_REQUIRED"
            row["outcome_json"] = None

        bench.db.on_lock = goes_on_hold
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["disposition"], out["reason_code"]),
                         ("REJECTED", "DEPLOYMENT_ON_HOLD", "recovery_hold"), out)
        self.assertEqual(bench.db.committed["dep_1"]["status"], "RECOVERY_REQUIRED", "the hold is untouched")
        writes = [q for q in bench.db.sql_log[before:] if q.strip().upper().startswith(("UPDATE", "DELETE", "INSERT"))]
        self.assertEqual(writes, [], "nothing was written")
        self.assertEqual(bench.db.locks, set())

    def test_a_hold_is_never_cleared_by_a_direct_call_to_the_engine(self):
        from change_engine.guarded_apply.rollback_engine import execute_rollback

        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        bench.db.committed["dep_1"]["status"] = "PREPARED"
        bench.db.committed["dep_1"]["outcome_json"] = None
        out = execute_rollback(deployment_id="dep_1", caller_roles=ADMIN, db=adapter)
        self.assertEqual((out["status"], out["disposition"]), ("REJECTED", "DEPLOYMENT_ON_HOLD"), out)

    def test_an_unauthorised_caller_still_learns_nothing(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        bench.db.committed["dep_1"]["status"] = "PREPARED"
        reads = []
        real = adapter.get_deployment_record
        adapter.get_deployment_record = lambda d: (reads.append(d), real(d))[1]
        out = self._revert(adapter, roles=["Guest"])
        self.assertEqual(out["disposition"], "UNAUTHORIZED_ROLE")
        self.assertEqual(reads, [])

    def test_a_fresh_view_that_cannot_be_opened_refuses_the_revert(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        adapter.begin_fresh_read_view = lambda: (_ for _ in ()).throw(_DbDown(SECRET))
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertEqual(bench.db.committed["dep_1"]["status"], "APPLIED")
        self.assertEqual(bench.db.locks, set())

    def test_a_failed_read_under_the_lock_is_unavailable_and_releases_the_lock(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        real = adapter.get_deployment_record
        calls = {"n": 0}

        def second_read_fails(dep):
            calls["n"] += 1
            if calls["n"] >= 2:  # the read under the lock
                raise endpoints.DurableEvidenceError("the deployment record could not be read")
            return real(dep)

        adapter.get_deployment_record = second_read_fails
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
        self.assertEqual(bench.db.committed["dep_1"]["status"], "APPLIED")
        self.assertEqual(bench.db.locks, set())

    def test_a_release_that_fails_discards_the_session(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        _finished_field_deployment(bench, adapter)
        bench.db.release_result = 0
        out = self._revert(adapter)
        self.assertEqual(out["status"], "QUARANTINED", "the outcome is still reported")
        self.assertTrue(bench.db.closed)


# ===========================================================================================
CUSTOM_SITE = "alpha.example.test"


class TestD1CustomSiteMapTenantResolvesToItsTenantId(unittest.TestCase):
    def test_the_resolver_maps_a_site_back_to_its_tenant(self):
        resolver = FrappeSiteResolver(site_map={"t_alpha": CUSTOM_SITE}, default_domain="localhost")
        self.assertEqual(resolver.tenant_of(CUSTOM_SITE), "t_alpha")
        self.assertEqual(resolver.tenant_of("t-beta.localhost"), "t_beta", "a default-domain tenant")
        self.assertIsNone(resolver.tenant_of("t-alpha.localhost"), "t_alpha lives on its mapped site, not here")
        self.assertIsNone(resolver.tenant_of("ALPHA.example.test"), "no other spelling of the site")
        self.assertIsNone(resolver.tenant_of("beta.example.test"))
        self.assertIsNone(resolver.tenant_of("t-beta.other.test"), "another domain is not this backend's tenant")
        self.assertIsNone(resolver.tenant_of(""))
        self.assertIsNone(resolver.tenant_of(None))

    def test_the_site_identity_of_a_custom_site_is_its_tenant_id(self):
        resolver = FrappeSiteResolver(site_map={TENANT: CUSTOM_SITE})
        self.assertEqual(endpoints._tenant_of_site(CUSTOM_SITE, resolver), TENANT)
        self.assertIsNone(endpoints._tenant_of_site(CUSTOM_SITE), "without a resolver it is not a tenant site")
        with mock.patch.object(endpoints, "frappe", _frappe_stub(CUSTOM_SITE)):
            self.assertEqual(endpoints._resolve_site_id(None, "dep_1", 0.0, site_resolver=resolver), (TENANT, None))
            self.assertEqual(endpoints._resolve_site_id(TENANT, "dep_1", 0.0, site_resolver=resolver), (TENANT, None))
            for caller in (CUSTOM_SITE, "t_beta", "T_ALPHA", "t-alpha", " t_alpha"):
                with self.subTest(caller=caller):
                    site, rejection = endpoints._resolve_site_id(caller, "dep_1", 0.0, site_resolver=resolver)
                    self.assertIsNone(site)
                    self.assertIn(rejection["reason_code"], ("site_mismatch", "invalid_site_id"))
            self.assertEqual(endpoints._resolve_site_id(None, "dep_1", 0.0)[0], CUSTOM_SITE, "unchanged without one")

    def test_the_legacy_host_alias_is_read_for_a_custom_site(self):
        resolver = FrappeSiteResolver(site_map={TENANT: CUSTOM_SITE})
        runtime = SimpleNamespace(local=SimpleNamespace(site=CUSTOM_SITE))
        self.assertEqual(endpoints._read_site_ids(TENANT, runtime, site_resolver=resolver), (TENANT, CUSTOM_SITE))
        self.assertEqual(endpoints._read_site_ids("t_beta", runtime, site_resolver=resolver), ("t_beta",))
        self.assertEqual(endpoints._read_site_ids(TENANT, runtime), (TENANT,))

    def test_the_backend_hands_its_resolver_to_the_deployment_adapter(self):
        resolver = FrappeSiteResolver(site_map={TENANT: CUSTOM_SITE})
        backend = FrappeRuntimeBackend(site_resolver=resolver, frappe_factory=lambda: SimpleNamespace())
        adapter = backend._deployment_adapter(SimpleNamespace(db=SimpleNamespace()))
        self.assertIs(adapter.site_resolver, resolver)

    def _rpc(self, bench, adapter, call, **kw):
        with mock.patch.object(endpoints, "frappe", _frappe_stub(CUSTOM_SITE)):
            return call(adapter=adapter, user_roles=ADMIN, **kw)

    def test_every_rpc_runs_a_custom_site_under_the_tenant_id(self):
        resolver = FrappeSiteResolver(site_map={TENANT: CUSTOM_SITE})
        bench = _Bench()
        bench.module.make_property_setter = lambda *a, **k: None
        adapter = FrappeDeploymentAdapter(frappe_module=bench.module, in_memory=False, use_shared_state=False,
                                          site_resolver=resolver)
        calls, _ = _entry_points(bench)  # only for the workflow and report payloads
        wf = calls["workflow"]
        del wf
        from change_engine.tests import test_phase3_workflow, test_phase4_report

        wf_def = test_phase3_workflow.TestPhase3WorkflowEngine(
            "test_11_api_endpoints_and_proposal")._build_valid_2_stage_workflow("Sales Order").model_dump()
        rp_def = test_phase4_report.TestPhase4ReportEngine(
            "test_11_end_to_end_api_calls")._build_valid_report_def("Sales Order").model_dump()
        cases = (
            ("dep_ps", endpoints.apply_property_setter_change,
             dict(doctype="Item", fieldname="note", property_name="label", value="X"), ADMIN),
            ("dep_wf", endpoints.apply_workflow_change, dict(doctype="Sales Order", workflow_def=wf_def), ADMIN),
            ("dep_rp", endpoints.apply_report_change, dict(doctype="Sales Order", report_def=rp_def),
             ["Sales Manager"]),
        )
        for dep, call, kw, roles in cases:
            with self.subTest(dep=dep):
                with mock.patch.object(endpoints, "frappe", _frappe_stub(CUSTOM_SITE)):
                    refused = call(deployment_id=dep, adapter=adapter, user_roles=roles, site_id="t_beta", **kw)
                    self.assertEqual(refused["reason_code"], "site_mismatch", refused)
                    self.assertIsNone(bench.db.row(dep))
                    out = call(deployment_id=dep, adapter=adapter, user_roles=roles, **kw)
                self.assertNotEqual(out.get("disposition"), "SITE_MISMATCH", out)
                self.assertEqual(bench.db.row(dep)["site_id"], TENANT, "the tenant id, never the host name")


if __name__ == "__main__":
    unittest.main()


class TestB2InvalidJsonHasAStableCode(unittest.TestCase):
    def test_unparseable_definitions_get_a_fixed_reason_and_code(self):
        from unittest import mock

        cases = (
            (endpoints.apply_configuration_change, dict(doctype="Item", field_def="{SECRET")),
            (endpoints.apply_workflow_change, dict(doctype="Item", workflow_def="{SECRET")),
            (endpoints.apply_report_change, dict(doctype="Item", report_def="{SECRET")),
        )
        for fn, kw in cases:
            with self.subTest(fn=fn.__name__):
                with mock.patch.object(endpoints, "frappe", None):
                    out = fn(deployment_id="dep_1", **kw)
                self.assertEqual(out.get("reason_code"), "invalid_json_payload", out)
                self.assertNotIn("SECRET", str(out))
                self.assertNotIn("Expecting", str(out))
