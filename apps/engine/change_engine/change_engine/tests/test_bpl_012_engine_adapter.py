"""BPL-012 unit tests for change_engine.adapter (SQLite durability, DDL gate, guardrails, production safety)."""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from change_engine.adapter import ChangeEngineAdapter, ChangeEngineHarness, HooksDisabled, make_harness
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import (
    bounded_site_lock_key,
    has_prohibited_expression,
    inspect_field_ddl,
    is_protected_entity,
    plan_statements_for_step,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
EXAMPLES_DIR = REPO_ROOT / "contracts" / "examples"


def _ctx(tenant: str = "t_alpha", service: str = "control_plane", who: dict | None = None) -> dict:
    return {
        "contractVersion": "0.1.2",
        "requestId": "01J00000000000000000000001",
        "correlationId": "corr_unit_01",
        "tenantId": tenant,
        "caller": {
            "service": service,
            "onBehalfOf": who if who is not None else {"kind": "user", "id": "usr_owner"},
        },
        "deadlineMs": 30000,
    }


def _seal(art: dict) -> dict:
    art = copy.deepcopy(art)
    if art.get("inverse"):
        art["inverse"] = _seal(art["inverse"])
    digest, art_id = cs.artifact_hashes(art)
    art["artifactId"] = art_id
    art["integrity"] = {"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None}
    return art


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _make_initial_build() -> dict:
    bp = _load_example("blueprint-trading-minimal.json")
    customer = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "customer"))
    add_field = _load_example("compiled-artifact-add-field.json")
    return _seal(
        {
            "artifactSchema": "0.1.0",
            "kind": "forward",
            "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
            "blueprint": {
                "id": add_field["blueprint"]["id"],
                "base": None,
                "target": copy.deepcopy(add_field["blueprint"]["base"]),
                "diffHash": None,
            },
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "components": copy.deepcopy(add_field["components"]),
            "steps": [
                {
                    "seq": 1,
                    "phase": 4,
                    "kind": "entity.add",
                    "subject": {"kind": "entity", "id": "customer", "parents": []},
                    "pointer": "/entities/customer",
                    "impact": "data_shape",
                    "ddlImpact": "additive",
                    "reversible": True,
                    "params": {"definition": customer},
                    "sourceOps": ["/entities/customer"],
                }
            ],
            "skippedOps": [],
            "postConditions": [{"id": "pc_001", "check": "exists", "pointer": "/entities/customer"}],
            "risk": {
                "counts": {
                    "cosmetic": 0,
                    "config": 0,
                    "data_shape": 1,
                    "destructive": 0,
                    "compliance": 0,
                    "access": 0,
                    "branding": 0,
                },
                "total": 1,
                "maxImpact": "data_shape",
                "needsDdlPlanGate": True,
                "touchesCompliance": False,
                "touchesAccess": False,
                "touchesLedgerOrTax": False,
                "requiresTeamReview": False,
                "irreversibleSteps": 0,
            },
            "inverse": None,
        }
    )


class TestBpl012EngineAdapter(unittest.TestCase):
    def test_make_harness_factory_returns_complete_harness(self):
        h = make_harness()
        self.assertIsInstance(h, ChangeEngineHarness)
        caps = h.call("capabilities", _ctx("platform"), {})
        self.assertTrue(caps["ok"])
        self.assertEqual(caps["result"]["adapterId"], "frappe")
        self.assertEqual(caps["result"]["versionSets"], ["set-example", "set-example-2"])
        self.assertTrue(caps["result"]["features"]["previewPredictsExport"])

    def test_ddl_plan_gate_supports_decimal_and_blocks_unique_or_index(self):
        ok_money, stmts_money, reason_money = inspect_field_ddl(
            "customer",
            {"id": "credit_buffer", "type": "money", "precision": 9},
        )
        self.assertTrue(ok_money, (stmts_money, reason_money))
        self.assertEqual(len(stmts_money), 1)
        self.assertIn("decimal(21,9)", stmts_money[0])

        ok_pct, stmts_pct, _ = inspect_field_ddl("customer", {"id": "margin_pct", "type": "percent"})
        self.assertTrue(ok_pct)
        self.assertIn("decimal(", stmts_pct[0])

        ok_unique, _, reason_unique = inspect_field_ddl("customer", {"id": "tax_ref", "type": "string", "unique": True})
        self.assertFalse(ok_unique)
        self.assertEqual(reason_unique, "unique_or_index")

        ok_idx, _, reason_idx = inspect_field_ddl("customer", {"id": "ext_ref", "type": "string", "indexed": True})
        self.assertFalse(ok_idx)
        self.assertEqual(reason_idx, "unique_or_index")

        ok_bad, _, reason_bad = inspect_field_ddl("customer", {"id": "blob_x", "type": "attachment"})
        self.assertFalse(ok_bad)
        self.assertEqual(reason_bad, "unsupported_value_type")

    def test_guardrails_block_protected_entities_and_prohibited_expressions(self):
        self.assertTrue(is_protected_entity("general_ledger"))
        self.assertTrue(is_protected_entity("audit_log"))
        self.assertTrue(is_protected_entity("tax_ledger"))
        self.assertFalse(is_protected_entity("customer"))

        self.assertTrue(has_prohibited_expression({"default": "eval:frappe.db.sql('select 1')"}))
        self.assertTrue(has_prohibited_expression({"client_script": "alert(1)"}))
        self.assertFalse(has_prohibited_expression({"definition": {"id": "note", "type": "string"}}))

        adapter = ChangeEngineAdapter(test_hooks=True)
        prov = adapter.call(
            "provision_site",
            _ctx(),
            {
                "idempotencyKey": "prov_guardrails_0001",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "sa",
                "siteClass": "production",
                "blueprintId": "example-trading-001",
            },
        )
        self.assertTrue(prov["ok"], prov)
        initial = _make_initial_build()
        plan0 = adapter.call("plan", _ctx(), {"artifact": initial})
        self.assertTrue(plan0["ok"], plan0)
        p0 = plan0["result"]
        app0 = adapter.call(
            "apply",
            _ctx(),
            {
                "idempotencyKey": "apply_init_guardrails_0001",
                "artifact": initial,
                "planToken": p0["planToken"],
                "approvals": {"changeApproved": "01J00000000000000000000002"},
            },
        )
        self.assertTrue(app0["ok"], app0)
        self.assertEqual(app0["result"]["status"], "applied")

        base_add = _load_example("compiled-artifact-add-field.json")
        bad_art = copy.deepcopy(base_add)
        bad_art["steps"][0]["params"]["definition"]["labels"] = {"en": "eval:1+1"}
        bad_art = _seal(bad_art)
        plan_resp = adapter.call("plan", _ctx(), {"artifact": bad_art})
        self.assertTrue(plan_resp["ok"])
        self.assertEqual(plan_resp["result"]["verdict"], "rejected")
        self.assertEqual(plan_resp["result"]["steps"][0]["reasonCode"], "prohibited_expression")

    def test_bounded_lock_key_respects_mariadb_limit(self):
        key = bounded_site_lock_key("t_" + "a" * 60, "blueprint_" + "b" * 80)
        self.assertLessEqual(len(key), 64)
        self.assertTrue(key.startswith("ce:v1:"))

    def test_plan_statements_emit_one_additive_or_quarantine_statement_per_step(self):
        add = _load_example("compiled-artifact-add-field.json")
        stmts = plan_statements_for_step(add["steps"][0])
        self.assertEqual(len(stmts), 1)
        self.assertIn("ADD COLUMN", stmts[0])
        rem = _load_example("compiled-artifact-remove-field.json")
        q_stmts = plan_statements_for_step(rem["steps"][0])
        self.assertEqual(len(q_stmts), 1)
        self.assertNotIn("DROP", q_stmts[0].upper())

    def test_sqlite_persistence_survives_adapter_reopen_and_quarantine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = str(Path(tmpdir) / "adapter_state.sqlite")
            a1 = ChangeEngineAdapter(test_hooks=True, db_path=db_file)
            prov = a1.call(
                "provision_site",
                _ctx(),
                {
                    "idempotencyKey": "prov_persist_0001",
                    "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                    "countryPack": "sa",
                    "siteClass": "production",
                    "blueprintId": "example-trading-001",
                },
            )
            self.assertTrue(prov["ok"], prov)
            initial = _make_initial_build()
            plan0 = a1.call("plan", _ctx(), {"artifact": initial})
            self.assertTrue(plan0["ok"], plan0)
            p0 = plan0["result"]
            app_init = a1.call(
                "apply",
                _ctx(),
                {
                    "idempotencyKey": "apply_init_persist_0001",
                    "artifact": initial,
                    "planToken": p0["planToken"],
                    "approvals": {"changeApproved": "01J00000000000000000000002"},
                },
            )
            self.assertTrue(app_init["ok"], app_init)
            add_field = _load_example("compiled-artifact-add-field.json")
            p1 = a1.call("plan", _ctx(), {"artifact": add_field})["result"]
            app_add = a1.call(
                "apply",
                _ctx(),
                {
                    "idempotencyKey": "apply_add_persist_0001",
                    "artifact": add_field,
                    "planToken": p1["planToken"],
                    "approvals": {"changeApproved": "01J00000000000000000000004"},
                },
            )
            self.assertTrue(app_add["ok"], app_add)
            pointer = "/entities/customer/fields/payment_terms_days"
            a1.data_probe("t_alpha", pointer, 42)
            a1.store.conn.close()

            # Reopen fresh adapter instance against the same SQLite database
            a2 = ChangeEngineAdapter(test_hooks=True, db_path=db_file)
            status = a2.call("site_status", _ctx(), {})
            self.assertTrue(status["ok"])
            self.assertEqual(status["result"]["applied"]["artifactId"], add_field["artifactId"])
            self.assertEqual(a2.data_probe("t_alpha", pointer), 42)

            # Quarantine field and verify stored data and SQLite table column remain intact
            rem_field = _load_example("compiled-artifact-remove-field.json")
            p2 = a2.call("plan", _ctx(), {"artifact": rem_field})["result"]
            res_rem = a2.call(
                "apply",
                _ctx(),
                {
                    "idempotencyKey": "apply_rem_persist_0001",
                    "artifact": rem_field,
                    "planToken": p2["planToken"],
                    "approvals": {"changeApproved": "01J00000000000000000000005"},
                },
            )
            self.assertTrue(res_rem["ok"])
            self.assertEqual(res_rem["result"]["status"], "applied")
            self.assertEqual(a2.data_probe("t_alpha", pointer), 42)
            self.assertEqual(a2.dropped_data(), [])

            # Check actual SQLite table count exists
            tables = [
                r[0]
                for r in a2.store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'tstore_%'"
                ).fetchall()
            ]
            self.assertGreaterEqual(len(tables), 1)
            a2.store.conn.close()

    def test_production_without_test_hooks_blocks_all_hooks(self):
        h = make_harness().without_test_hooks()
        for fn in (
            lambda: h.fault("execute", step_seq=1),
            lambda: h.on_lock_held(lambda: None),
            lambda: h.advance_time(60),
            lambda: h.set_site_state("t_alpha", "failed"),
            lambda: h.data_probe("/entities/customer/fields/x"),
            lambda: h.auth_probe("m_aaaaaaaa"),
            lambda: h.action_probe("m_aaaaaaaa"),
            lambda: h.plan_evidence("evd_123"),
            lambda: h.execution_journal(),
        ):
            with self.assertRaises(HooksDisabled):
                fn()

    def test_pure_python_context_validation_fallback(self):
        orig_validator = cs._validator_for
        try:
            cs._validator_for = lambda _ref: None  # force pure-Python path
            self.assertEqual(cs.validate_context(_ctx()), [])
            bad_ctx = _ctx()
            bad_ctx["tenantId"] = "INVALID"
            self.assertIn("/context/tenantId", cs.validate_context(bad_ctx))
        finally:
            cs._validator_for = orig_validator


if __name__ == "__main__":
    unittest.main()
