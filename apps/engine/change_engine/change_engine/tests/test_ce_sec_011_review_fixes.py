"""CE-SEC-011 slice 1, security review fixes (Tier 3).

  (E) the six non-DDL adapter writes verify the advisory locks before they write and before they commit; a write
      after the locks are lost is refused and the deployment is never reported APPLIED;
  (F) an RPC call that builds its own adapter (no backend resolver) on a site the database shows to be a tenant
      site is refused with ``site_unresolvable``, never run under the host name beside a hold under the tenant id;
  (G) a failed apply is reported FAILED_CLEAN only when a read-back shows the target unchanged;
  (H) the revert opens a fresh view before its first read, refuses a record whose site changed while it waited,
      and replays a revert that finished while it waited.

Reuses the CE-SEC-008 transactional database double. Synthetic data only.
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

from change_engine.adapter.frappe_backend import FrappeSiteResolver  # noqa: E402
from change_engine.api import endpoints  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.schema_reconciler import SessionDiscardedError  # noqa: E402
from change_engine.tests.test_ce_sec_008_deploy_path_durability import _Bench, _DbDown, _DurableDb  # noqa: E402
from change_engine.tests.test_ce_sec_008_review_fixes import (  # noqa: E402
    ADMIN,
    SECRET,
    TENANT,
    _entry_points,
    _frappe_stub,
)

ENGINES = ("property_setter", "workflow", "report")
DEP = {"property_setter": "dep_ps", "workflow": "dep_wf", "report": "dep_rp"}
CUSTOM_SITE = "alpha.example.test"


def _record_writes(bench):
    """Every document write and property setter the adapter sends to Frappe, in order."""
    writes = []
    real_get_doc = bench.module.get_doc

    def get_doc(args, *rest):
        doc = real_get_doc(args) if isinstance(args, dict) else SimpleNamespace()
        label = args.get("doctype") if isinstance(args, dict) else args
        return SimpleNamespace(insert=lambda **kw: writes.append(("insert", label)),
                               save=lambda **kw: writes.append(("save", label)),
                               update=lambda *a, **k: None, name=getattr(doc, "name", None))

    bench.module.get_doc = get_doc
    bench.module.make_property_setter = lambda *a, **k: writes.append(("property_setter", a or k))
    bench.db.set_value = lambda *a, **k: writes.append(("set_value", a))
    return writes


# ===========================================================================================
class TestE1EveryNonDdlWriteNeedsTheLocks(unittest.TestCase):
    CALLS = {
        "apply_property_setter": lambda a: a.apply_property_setter("Item", "note", "label", "X"),
        "ensure_workflow_state": lambda a: a.ensure_workflow_state("Draft"),
        "ensure_workflow_action": lambda a: a.ensure_workflow_action("Approve"),
        "apply_workflow": lambda a: a.apply_workflow("Sales Order", {"doctype": "Workflow", "workflow_name": "wf"}),
        "set_workflow_active": lambda a: a.set_workflow_active("wf", 0),
        "apply_report": lambda a: a.apply_report("rp", {"doctype": "Report", "report_name": "rp"}),
    }

    def test_a_write_after_the_lock_is_gone_is_refused_before_it_is_sent(self):
        for name, call in self.CALLS.items():
            with self.subTest(method=name):
                bench = _Bench()
                writes = _record_writes(bench)
                adapter = bench.new_adapter()
                adapter._held_locks.add("ce:lost")  # taken once; the server no longer has it for this session
                commits = bench.db.commits
                with self.assertRaises(SessionDiscardedError):
                    call(adapter)
                self.assertEqual(writes, [], "nothing reached Frappe")
                self.assertEqual(bench.db.commits, commits)

    def test_a_lock_lost_during_the_write_is_never_committed(self):
        for name, call in self.CALLS.items():
            with self.subTest(method=name):
                bench = _Bench()
                adapter = bench.new_adapter()
                bench.db.locks.add("ce:held")
                adapter._held_locks.add("ce:held")
                # the connection is replaced while the write runs: the lock is gone by the time it would commit
                writes = _LossyList(lambda _item, bench=bench: bench.db.locks.clear())
                _rewire(bench, writes)
                commits = bench.db.commits
                with self.assertRaises(SessionDiscardedError):
                    call(adapter)
                self.assertTrue(writes.items, "the write was sent")
                self.assertEqual(bench.db.commits, commits, "but never committed")
                self.assertTrue(bench.db.closed, "and the session was discarded")

    def test_a_write_while_the_locks_are_held_goes_through(self):
        for name, call in self.CALLS.items():
            with self.subTest(method=name):
                bench = _Bench()
                writes = _record_writes(bench)
                adapter = bench.new_adapter()
                bench.db.locks.add("ce:held")
                adapter._held_locks.add("ce:held")
                commits = bench.db.commits
                call(adapter)
                self.assertTrue(writes)
                self.assertEqual(bench.db.commits, commits + 1)
                self.assertFalse(bench.db.closed)


class _LossyList:
    def __init__(self, on_append):
        self.items = []
        self._on_append = on_append

    def append(self, item):
        self.items.append(item)
        self._on_append(item)


def _rewire(bench, sink):
    def get_doc(args, *rest):
        label = args.get("doctype") if isinstance(args, dict) else args
        return SimpleNamespace(insert=lambda **kw: sink.append(("insert", label)),
                               save=lambda **kw: sink.append(("save", label)),
                               update=lambda *a, **k: None, name=None)

    bench.module.get_doc = get_doc
    bench.module.make_property_setter = lambda *a, **k: sink.append(("property_setter", a or k))
    bench.db.set_value = lambda *a, **k: sink.append(("set_value", a))


class TestE2EnginesNeverReportAppliedAfterTheLocksAreDropped(unittest.TestCase):
    """The reviewer's probe: the locks are dropped right after the intent. The engine's write is refused, the
    deployment is held (never APPLIED, never FAILED_CLEAN), and the session is discarded."""

    def test_each_engine_holds_when_the_locks_are_lost_after_the_intent(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench()
                calls, adapter = _entry_points(bench)
                writes = _record_writes(bench)
                real = adapter.persist_prepare_and_audit_intent

                def intent_then_lose_locks(record, real=real, bench=bench):
                    real(record)
                    bench.db.locks.clear()  # e.g. the connection was dropped and silently reconnected

                adapter.persist_prepare_and_audit_intent = intent_then_lose_locks
                out = calls[name](dep=DEP[name])
                self.assertNotEqual(out["status"], "APPLIED", out)
                self.assertNotEqual(out["status"], "FAILED_CLEAN", out)
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
                self.assertEqual(out.get("reason_code"), "session_discarded", out)
                self.assertEqual(writes, [], "no write reached Frappe")
                self.assertEqual(bench.db.committed[DEP[name]]["status"], "PREPARED", "the intent stays as the hold")
                self.assertTrue(bench.db.closed, "the session was discarded")
                self.assertNotIn("SECRET", json.dumps(out))



# ===========================================================================================
STATE = "tabChange Engine Blueprint State"


class _SiteDb(_DurableDb):
    """The CE-SEC-008 double plus what the unmapped-site check reads: which tables exist, the site-state copy
    and the distinct audit site ids."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tables = {"tabChange Engine Audit"}
        self.state_rows: list[str] = []
        self.property_setters: dict[str, object] = {}  # property -> value, written by ``make_property_setter``

    def make_property_setter(self, args=None, **kw):
        args = args or kw
        self.property_setters[args["property"]] = args["value"]

    def sql(self, query, values=None, as_dict=False):
        q = " ".join(query.upper().split())
        if "INFORMATION_SCHEMA.TABLES" in q and "TABLE_NAME IN" in q:
            self._maybe_fail(q)
            self.sql_log.append(query)
            return tuple((t,) for t in values if t in self.tables)
        if f"FROM `{STATE.upper()}`" in q:
            self._maybe_fail(q)
            self.sql_log.append(query)
            other = [t for t in self.state_rows if not values or t != values[0]]
            return tuple((t,) for t in other[:1])
        if q.startswith("SELECT NAME, VALUE, PROPERTY_TYPE FROM `TABPROPERTY SETTER`"):
            prop = values[-1]
            return (("ps-" + prop, self.property_setters[prop], "Data"),) if prop in self.property_setters else ()
        if q.startswith("SELECT DISTINCT SITE_ID"):
            self._maybe_fail(q)
            self.sql_log.append(query)
            return tuple(sorted({(r["site_id"],) for r in self._visible().values() if r["site_id"] != values[0]}))
        return super().sql(query, values, as_dict)


def _rpc_runtime(bench, site):
    """The global Frappe an RPC call sees: this site, an administrator, and the bench's database."""
    m = bench.module
    return SimpleNamespace(db=m.db, get_doc=m.get_doc, clear_cache=lambda **kw: None,
                           make_property_setter=m.db.make_property_setter, local=SimpleNamespace(site=site),
                           session=SimpleNamespace(user="admin@example.test"),
                           get_roles=lambda user: ["System Manager", "Sales Manager"])


def _hold(bench, site_id, doctype, dep="dep_hold"):
    bench.db.committed[dep] = {
        "name": dep, "deployment_id": dep, "idempotency_key": f"idemp-{dep}", "payload_hash": "h", "site_id": site_id,
        "doctype": doctype, "fieldname": None, "base_revision_hash": "r", "ddl_plan_statements": None,
        "status": "RECOVERY_REQUIRED", "outcome_json": None}


def _rpc_calls():
    from change_engine.tests import test_phase3_workflow, test_phase4_report
    from change_engine.tests.test_ce_sec_008_deploy_path_durability import FIELD

    wf = test_phase3_workflow.TestPhase3WorkflowEngine(
        "test_11_api_endpoints_and_proposal")._build_valid_2_stage_workflow("Sales Order").model_dump()
    rp = test_phase4_report.TestPhase4ReportEngine(
        "test_11_end_to_end_api_calls")._build_valid_report_def("Sales Order").model_dump()
    # no ``adapter``: each call builds its own, exactly as a call over HTTP does
    return {
        "property_setter": ("Item", lambda dep: endpoints.apply_property_setter_change(
            doctype="Item", deployment_id=dep, fieldname="note", property_name="label", value="X", user_roles=ADMIN)),
        "workflow": ("Sales Order", lambda dep: endpoints.apply_workflow_change(
            doctype="Sales Order", deployment_id=dep, workflow_def=wf, user_roles=ADMIN)),
        "report": ("Sales Order", lambda dep: endpoints.apply_report_change(
            doctype="Sales Order", deployment_id=dep, report_def=rp, user_roles=["Sales Manager"])),
        "field": ("Item", lambda dep: endpoints.apply_configuration_change(
            doctype="Item", deployment_id=dep, field_def={**FIELD, "fieldname": "custom_xyz"}, user_roles=ADMIN)),
    }


class TestF1RpcOnAMappedSiteIsRefused(unittest.TestCase):
    def _run(self, bench, site, name, dep="dep_rpc"):
        doctype, call = _rpc_calls()[name]
        with mock.patch.object(endpoints, "frappe", _rpc_runtime(bench, site)):
            return doctype, call(dep)

    def test_a_hold_under_the_tenant_id_is_not_stepped_around_through_the_rpc(self):
        for name in ("property_setter", "workflow", "report", "field"):
            with self.subTest(rpc=name):
                bench = _Bench(db=_SiteDb())
                doctype = _rpc_calls()[name][0]
                _hold(bench, TENANT, doctype)  # written by the backend, under the tenant id
                _, out = self._run(bench, CUSTOM_SITE, name)
                self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "site_unresolvable"), out)
                self.assertIsNone(bench.db.row("dep_rpc"), "nothing was recorded under the host name")
                self.assertEqual(bench.db.committed["dep_hold"]["status"], "RECOVERY_REQUIRED")
                self.assertEqual(bench.db.locks, set())

    def test_a_mapped_host_shaped_like_another_tenants_default_site_is_refused(self):
        """``{"t_alpha": "t-beta.other.test"}`` is a valid map: without the resolver the host reads as ``t_beta``."""
        for name in ("property_setter", "workflow", "report", "field"):
            for evidence in ("audit", "state"):
                with self.subTest(rpc=name, evidence=evidence):
                    bench = _Bench(db=_SiteDb())
                    if evidence == "audit":
                        _hold(bench, TENANT, _rpc_calls()[name][0])
                    else:
                        bench.db.tables.add(STATE)
                        bench.db.state_rows = [TENANT]
                    _, out = self._run(bench, "t-beta.other.test", name)
                    self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "site_unresolvable"), out)
                    self.assertIsNone(bench.db.row("dep_rpc"))

    def test_the_check_reads_the_table_the_backend_provisions(self):
        from change_engine.adapter import frappe_backend

        self.assertEqual(endpoints._SITE_STATE_TABLE, frappe_backend._STATE_TABLE)

    def test_a_provisioned_site_with_no_deployment_yet_is_refused(self):
        for name in ("property_setter", "workflow", "report", "field"):
            with self.subTest(rpc=name):
                bench = _Bench(db=_SiteDb())
                bench.db.tables.add(STATE)
                bench.db.state_rows = [TENANT]
                _, out = self._run(bench, CUSTOM_SITE, name)
                self.assertEqual(out["reason_code"], "site_unresolvable", out)
                self.assertIsNone(bench.db.row("dep_rpc"))

    def test_a_failed_identity_read_refuses_without_echoing_the_error(self):
        for fragment in ("INFORMATION_SCHEMA.TABLES", "SELECT DISTINCT SITE_ID"):
            for name in ("property_setter", "workflow", "report"):
                with self.subTest(fault=fragment, rpc=name):
                    bench = _Bench(db=_SiteDb())
                    bench.db.fail(fragment, _DbDown(SECRET))
                    _, out = self._run(bench, CUSTOM_SITE, name)
                    self.assertEqual(out["reason_code"], "site_unresolvable", out)
                    self.assertNotIn("SECRET", json.dumps(out))
                    self.assertIsNone(bench.db.row("dep_rpc"))

    def test_a_plain_bench_site_still_runs_under_its_own_name(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(rpc=name):
                bench = _Bench(db=_SiteDb())
                _hold(bench, "site1.localhost", "Customer", dep="dep_other")  # its own rows, another target
                _, out = self._run(bench, "site1.localhost", name)
                self.assertEqual(out["status"], "APPLIED", out)
                self.assertEqual(bench.db.row("dep_rpc")["site_id"], "site1.localhost")

    def test_a_default_domain_tenant_site_sees_the_hold_under_its_tenant_id(self):
        for name in ("property_setter", "workflow", "report"):
            with self.subTest(rpc=name):
                bench = _Bench(db=_SiteDb())
                bench.db.tables.add(STATE)
                bench.db.state_rows = ["t_beta"]  # its own provisioned state: not another tenant's identity
                doctype = _rpc_calls()[name][0]
                _hold(bench, "t_beta", doctype)
                _, out = self._run(bench, "t-beta.localhost", name)
                self.assertNotEqual(out.get("reason_code"), "site_unresolvable", out)
                self.assertNotEqual(out["status"], "APPLIED", out)
                self.assertIn(out["status"], ("REJECTED", "RECOVERY_REQUIRED"), out)
                self.assertIsNone(bench.db.row("dep_rpc"))

    def test_an_injected_adapter_with_the_backend_resolver_is_not_affected(self):
        bench = _Bench(db=_SiteDb())
        bench.db.tables.add(STATE)
        bench.db.state_rows = [TENANT]
        bench.module.make_property_setter = bench.db.make_property_setter
        adapter = FrappeDeploymentAdapter(frappe_module=bench.module, in_memory=False, use_shared_state=False,
                                          site_resolver=FrappeSiteResolver(site_map={TENANT: CUSTOM_SITE}))
        with mock.patch.object(endpoints, "frappe", _frappe_stub(CUSTOM_SITE)):
            out = endpoints.apply_property_setter_change(doctype="Item", deployment_id="dep_rpc", fieldname="note",
                                                         property_name="label", value="X", adapter=adapter,
                                                         user_roles=ADMIN)
        self.assertEqual(out["status"], "APPLIED", out)
        self.assertEqual(bench.db.row("dep_rpc")["site_id"], TENANT)
        self.assertFalse([q for q in bench.db.sql_log if "information_schema.TABLES" in q], "no identity probe")

    def test_the_revert_through_the_rpc_keys_on_the_record_and_sees_the_tenant_hold(self):
        """The revert takes its site from the record, not from the host, so the RPC needs no resolver for it."""
        bench = _Bench(db=_SiteDb())
        _hold(bench, TENANT, "Item", dep="dep_1")
        with mock.patch.object(endpoints, "frappe", _rpc_runtime(bench, CUSTOM_SITE)):
            out = endpoints.revert_configuration_change(deployment_id="dep_1", user_roles=ADMIN)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "recovery_hold"), out)
        self.assertEqual(bench.db.committed["dep_1"]["status"], "RECOVERY_REQUIRED")



# ===========================================================================================
_TARGET_QUERY = {"property_setter": "SELECT NAME, VALUE, MODIFIED FROM `TABPROPERTY SETTER`",
                 "workflow": "SELECT NAME, IS_ACTIVE, MODIFIED FROM `TABWORKFLOW`",
                 "report": "SELECT NAME, DISABLED, MODIFIED FROM `TABREPORT`"}
_WRITE = {"property_setter": "apply_property_setter", "workflow": "apply_workflow", "report": "apply_report"}


class _TargetDb(_DurableDb):
    """The CE-SEC-008 double plus the committed target rows an apply's read-back sees."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.targets = {kind: () for kind in _TARGET_QUERY}

    def sql(self, query, values=None, as_dict=False):
        q = " ".join(query.upper().split())
        for kind, prefix in _TARGET_QUERY.items():
            if q.startswith(prefix):
                self._maybe_fail(q)
                self.sql_log.append(query)
                return self.targets[kind]
        return super().sql(query, values, as_dict)


class TestG1FailedCleanOnlyWhenTheTargetReadsBackUnchanged(unittest.TestCase):
    def _arm(self, bench, adapter, name, *, lands):
        real = getattr(adapter, _WRITE[name])

        def write_then_raise(*a, **k):
            real(*a, **k)
            if lands:  # the commit went through, and then the call failed (an ambiguous commit failure)
                bench.db.targets[name] = (("target", "1", "2026-11-26 10:00:00"),)
            raise _DbDown(SECRET)

        setattr(adapter, _WRITE[name], write_then_raise)

    def test_a_failed_apply_whose_write_landed_is_held_not_clean(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench(db=_TargetDb())
                calls, adapter = _entry_points(bench)
                self._arm(bench, adapter, name, lands=True)
                out = calls[name](dep=DEP[name])
                self.assertEqual((out["status"], out["reason_code"]), ("RECOVERY_REQUIRED", "apply_failed"), out)
                self.assertEqual(bench.db.committed[DEP[name]]["status"], "RECOVERY_REQUIRED", "the target is held")
                self.assertNotIn("SECRET", json.dumps(out))

    def test_a_failed_apply_that_left_the_target_as_it_was_is_still_clean(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench(db=_TargetDb())
                calls, adapter = _entry_points(bench)
                self._arm(bench, adapter, name, lands=False)
                out = calls[name](dep=DEP[name])
                self.assertEqual((out["status"], out["reason_code"]), ("FAILED_CLEAN", "apply_failed"), out)
                self.assertEqual(bench.db.committed[DEP[name]]["status"], "FAILED_CLEAN")

    def test_a_read_back_that_fails_is_never_clean(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench(db=_TargetDb())
                calls, adapter = _entry_points(bench)
                self._arm(bench, adapter, name, lands=False)
                real_settle = adapter._rollback_durable

                def rollback_then_break_reads(real=real_settle, bench=bench, name=name):
                    result = real()
                    bench.db.fail(_TARGET_QUERY[name], _DbDown(SECRET))  # only the read after the failure
                    return result

                adapter._rollback_durable = rollback_then_break_reads
                out = calls[name](dep=DEP[name])
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
                self.assertNotIn("SECRET", json.dumps(out))

    def test_two_unreadable_reads_are_not_the_same_state(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                bench = _Bench(db=_TargetDb())
                calls, adapter = _entry_points(bench)
                self._arm(bench, adapter, name, lands=False)
                bench.db.fail(_TARGET_QUERY[name], _DbDown(SECRET))  # before the intent and after the failure
                out = calls[name](dep=DEP[name])
                self.assertEqual(out["status"], "RECOVERY_REQUIRED", out)
                self.assertNotIn("SECRET", json.dumps(out))



# ===========================================================================================
class TestH1RevertReadsAndReplaysUnderTheLock(unittest.TestCase):
    def _finished(self):
        bench = _Bench()
        adapter = bench.new_adapter()
        bench.module.make_property_setter = lambda *a, **k: None
        out = bench.deploy(adapter)
        self.assertEqual(out["status"], "APPLIED", out)
        return bench, adapter

    def _revert(self, adapter):
        return endpoints.revert_configuration_change(deployment_id="dep_1", adapter=adapter, user_roles=ADMIN)

    def _writes(self, bench, since):
        return [q for q in bench.db.sql_log[since:] if q.strip().upper().startswith(("UPDATE", "DELETE", "INSERT"))]

    def test_a_fresh_view_opens_before_the_first_read(self):
        bench, adapter = self._finished()
        order = []
        for name in ("begin_fresh_read_view", "get_deployment_record", "acquire_advisory_lock"):
            real = getattr(adapter, name)
            setattr(adapter, name, (lambda n, f: lambda *a, **k: (order.append(n), f(*a, **k))[1])(name, real))
        out = self._revert(adapter)
        self.assertEqual(out["status"], "QUARANTINED", out)
        self.assertEqual(order[0], "begin_fresh_read_view", order)

    def test_pending_caller_writes_refuse_the_revert_and_are_never_committed(self):
        bench, adapter = self._finished()
        bench.db.pending.append(("update", "dep_1", {"fieldname": "caller_work"}))  # a caller's uncommitted write
        commits, before = bench.db.commits, len(bench.db.sql_log)
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
        self.assertEqual(bench.db.commits, commits, "nothing committed the caller's work")
        self.assertFalse([q for q in bench.db.sql_log[before:] if "CREATE TABLE" in q.upper()], "no implicit commit")
        self.assertEqual(len(bench.db.pending), 1, "the caller's work is left as it is")
        self.assertEqual(bench.db.committed["dep_1"]["status"], "APPLIED")

    def test_a_record_whose_site_changed_while_waiting_is_refused(self):
        bench, adapter = self._finished()

        def moved(_lock, bench=bench):
            bench.db.committed["dep_1"]["site_id"] = "site-b"

        bench.db.on_lock = moved
        before = len(bench.db.sql_log)
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
        self.assertEqual(self._writes(bench, before), [], "nothing was written")
        self.assertEqual(bench.db.committed["dep_1"]["status"], "APPLIED")
        self.assertEqual(bench.db.locks, set())

    def test_a_record_whose_target_changed_while_waiting_is_refused(self):
        bench, adapter = self._finished()

        def moved(_lock, bench=bench):
            bench.db.committed["dep_1"]["doctype"] = "Customer"

        bench.db.on_lock = moved
        before = len(bench.db.sql_log)
        out = self._revert(adapter)
        self.assertEqual((out["status"], out["reason_code"]), ("REJECTED", "engine_unavailable"), out)
        self.assertEqual(self._writes(bench, before), [])

    def test_a_revert_that_finished_while_waiting_is_replayed_not_repeated(self):
        for done in ("QUARANTINED", "ROLLED_BACK"):
            with self.subTest(finished=done):
                bench, adapter = self._finished()

                def finished(_lock, bench=bench, done=done):
                    bench.db.committed["dep_1"]["status"] = done  # another session's revert committed first

                bench.db.on_lock = finished
                before = len(bench.db.sql_log)
                out = self._revert(adapter)
                self.assertEqual((out["status"], out["disposition"]), (done, f"ALREADY_{done}"), out)
                self.assertTrue(out["success"])
                self.assertEqual(self._writes(bench, before), [], "the revert is not run a second time")
                self.assertEqual(bench.db.locks, set())


if __name__ == "__main__":
    unittest.main()
