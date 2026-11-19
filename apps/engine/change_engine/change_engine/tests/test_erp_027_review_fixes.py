"""ERP-027 review fixes (Tier 3 DDL gate): explicit offline simulator flag, revision-hash rejection in the
Property Setter engine, and a pinned statement-verb allowlist for ``requires_ddl_check``."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.adapter import (  # noqa: E402
    FrappeBackendError,
    FrappeRuntimeBackend,
    SimulatedFrappeRuntime,
    make_frappe_adapter,
)
from change_engine.adapter.frappe_backend import ENGINE_ENV_VAR  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter, RevisionHashError  # noqa: E402
from change_engine.guarded_apply.ddl_plan_gate import requires_ddl_check  # noqa: E402
from change_engine.guarded_apply.property_setter_engine import execute_property_setter_deployment  # noqa: E402


def _env(value):
    """Patch CHANGE_ENGINE_ENV; ``None`` removes it (unset, which counts as production)."""
    env = {k: v for k, v in os.environ.items() if k != ENGINE_ENV_VAR}
    if value is not None:
        env[ENGINE_ENV_VAR] = value
    return mock.patch.dict(os.environ, env, clear=True)


class TestOfflineSimulatorIsExplicit(unittest.TestCase):
    def test_a_factory_alone_never_enables_the_simulator(self):
        sim = SimulatedFrappeRuntime()
        with _env(None):  # no env needed: nothing offline is requested
            backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
            self.assertIs(backend._deployment_adapter(sim).offline_ddl_simulator, False)
        with _env("test"):
            backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, auto_create_sites=True)
            self.assertIs(backend._deployment_adapter(sim).offline_ddl_simulator, False)

    def test_explicit_flag_is_allowed_only_in_dev_or_test(self):
        sim = SimulatedFrappeRuntime()
        for value in ("dev", "test", " TEST "):
            with self.subTest(env=value), _env(value):
                backend = FrappeRuntimeBackend(frappe_factory=lambda: sim, offline_ddl_simulator=True)
                self.assertIs(backend._deployment_adapter(sim).offline_ddl_simulator, True)

    def test_production_and_unset_env_refuse_the_simulator(self):
        for value in (None, "", "production", "prod", "staging", "testing", "dev,prod"):
            with self.subTest(env=value), _env(value):
                with self.assertRaises(FrappeBackendError) as ctx:
                    FrappeRuntimeBackend(frappe_factory=lambda: SimulatedFrappeRuntime(), offline_ddl_simulator=True)
                self.assertEqual(ctx.exception.code, "offline_ddl_simulator_forbidden")

    def test_harness_opts_in_for_simulated_only(self):
        with _env("test"):
            self.assertTrue(make_frappe_adapter(simulated=True).frappe_backend._offline_ddl_simulator)
            sim = SimulatedFrappeRuntime()
            adapter = make_frappe_adapter(frappe_factory=lambda: sim, auto_create_sites=True)
            self.assertIs(adapter.frappe_backend._offline_ddl_simulator, False)
        with _env(None), self.assertRaises(FrappeBackendError):
            make_frappe_adapter(simulated=True)


class _StubAdapter(FrappeDeploymentAdapter):
    """In-memory adapter whose revision hash read is controlled by the test."""

    def get_doctype_revision_hash(self, doctype):
        raise RevisionHashError("information_schema unreadable")


class _NoHashAdapter:
    """Delegates to an in-memory adapter but cannot report a revision hash, and says it is not offline."""

    def __init__(self, in_memory: bool):
        self._inner = FrappeDeploymentAdapter()
        self.in_memory = in_memory
        self.offline_ddl_simulator = False

    def __getattr__(self, name):
        if name == "get_doctype_revision_hash":
            raise AttributeError(name)
        return getattr(self._inner, name)


class TestPropertySetterRevisionHash(unittest.TestCase):
    def setUp(self):
        FrappeDeploymentAdapter.reset_in_memory_state()
        self.addCleanup(FrappeDeploymentAdapter.reset_in_memory_state)

    def _apply(self, db, dep):
        return execute_property_setter_deployment(
            db=db, deployment_id=dep, site_id="site1.local", doctype="Sales Order", fieldname="po_no",
            property_name="label", value="Customer PO", property_type="Data", user_roles=["System Manager"])

    def test_unreadable_revision_hash_is_a_rejection_not_an_exception(self):
        out = self._apply(_StubAdapter(), "dep_rev_raise")
        self.assertEqual((out["status"], out["success"], out["disposition"]), ("REJECTED", False, "REVISION_HASH_UNAVAILABLE"))
        self.assertEqual(out["stage"], "INSPECT")

    def test_live_adapter_without_a_revision_hash_method_is_rejected(self):
        out = self._apply(_NoHashAdapter(in_memory=False), "dep_rev_missing")
        self.assertEqual((out["status"], out["disposition"]), ("REJECTED", "REVISION_HASH_UNAVAILABLE"))

    def test_explicit_offline_adapter_keeps_the_stand_in_hash(self):
        out = self._apply(_NoHashAdapter(in_memory=True), "dep_rev_offline")
        self.assertTrue(out["success"], out)


class TestRequiresDdlCheckVerbAllowlist(unittest.TestCase):
    """Pins the exact verbs ``requires_ddl_check`` lets through unchecked: the set the ``real-bench-tests`` job
    (live Frappe on MariaDB 11.4, ``Custom Field.insert`` and apply) passes with. A Frappe upgrade that starts
    issuing another verb gets it rejected as DDL in the bench job and this test fails with the verb named, so
    widening the list is a reviewed change here, never a surprise in a customer apply."""

    BENIGN = ("SELECT 1", "select * from tabDocType", "SHOW COLUMNS FROM `tabItem`", "DESCRIBE `tabItem`",
              "INSERT INTO `tabX` (a) VALUES (1)", "UPDATE `tabX` SET a = 1", "DELETE FROM `tabX`", "COMMIT",
              "ROLLBACK", "SAVEPOINT s1", "RELEASE SAVEPOINT s1", "START TRANSACTION", "  start   transaction")
    CHECKED = ("SET autocommit=0", "WITH t AS (SELECT 1) SELECT * FROM t", "REPLACE INTO `tabX` VALUES (1)",
               "LOCK TABLES `tabX` WRITE", "UNLOCK TABLES", "(SELECT 1)", "BEGIN", "ALTER TABLE `tabX` ADD COLUMN a int",
               "CREATE TABLE t (a int)", "DROP TABLE t", "TRUNCATE TABLE t", "RENAME TABLE a TO b", "CALL p()",
               "/* c */ SELECT 1", "-- c\nSELECT 1", "# c\nSELECT 1", "SELECTX 1", "SELECT 1; DROP TABLE t")

    def test_benign_verbs_pass_unchecked(self):
        for q in self.BENIGN:
            with self.subTest(q=q):
                self.assertFalse(requires_ddl_check(q), f"verb newly treated as DDL: {q!r}")

    def test_every_other_verb_is_checked_as_ddl(self):
        for q in self.CHECKED:
            with self.subTest(q=q):
                self.assertTrue(requires_ddl_check(q), f"verb newly admitted without a DDL check: {q!r}")


if __name__ == "__main__":
    unittest.main()
