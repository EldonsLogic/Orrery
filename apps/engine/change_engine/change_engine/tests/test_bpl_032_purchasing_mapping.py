"""BPL-032 follow-up to BPL-034 (ADR-0055): the adapter maps the purchasing and price-list entities.

The reviewed mapping (`ENTITY_TO_DOCTYPE`) is the role-grant allowlist (ADR-0051 item 3). Once the engine-mapping
contract 0.2.0 names these entities, role grants on them plan and apply on both adapters (in-memory and the
engine-backed one on a simulated site), while built-ins outside the mapping are still refused. Offline; synthetic
data only. Live-bench confirmation of the engine-side names is UNVERIFIED and stays in test_bpl_027.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from change_engine.adapter import FrappeRuntimeBackend, FrappeSiteResolver, make_frappe_adapter
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import (
    ENTITY_TO_DOCTYPE,
    entity_to_doctype,
    grant_plan_reason,
    is_protected_entity,
    reviewed_grant_doctype,
)
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine
from change_engine.tests.test_sec_022_bpl_032_roles import TENANT as _ROLES_TENANT, _Base, grant, role

REPO_ROOT = Path(os.environ.get("PLATFORM_REPO_ROOT") or Path(__file__).resolve().parents[5]).expanduser()
CONTRACT_MAPPING = REPO_ROOT / "contracts" / "examples" / "engine-mapping-purchasing.json"
TENANT = "t_bpl032p"
SITE = "ci.localhost"

# Written out literally, not derived from the module under test.
NEW_PAIRS = {
    "supplier": "Supplier",
    "price_list": "Price List",
    "price_list_item": "Item Price",
    "purchase_order": "Purchase Order",
    "purchase_order_line": "Purchase Order Item",
    "purchase_receipt": "Purchase Receipt",
    "purchase_receipt_line": "Purchase Receipt Item",
    "purchase_invoice": "Purchase Invoice",
    "purchase_invoice_line": "Purchase Invoice Item",
}
# Top-level documents and masters (a child table has no permission rules of its own on the engine).
GRANTABLE = ("supplier", "price_list", "price_list_item", "purchase_order", "purchase_receipt", "purchase_invoice")
SUBMITTABLE_ENTITIES = ("purchase_order", "purchase_receipt", "purchase_invoice")
STILL_UNMAPPED = ("payment_entry", "stock_entry", "journal_entry")


class TestPurchasingMapping(unittest.TestCase):
    def test_nine_pairs_are_mapped_to_the_contract_names(self) -> None:
        for entity, doctype in NEW_PAIRS.items():
            self.assertEqual(ENTITY_TO_DOCTYPE.get(entity), doctype, entity)
            self.assertEqual(entity_to_doctype(entity), doctype, entity)

    def test_names_equal_the_merged_contract_mapping(self) -> None:
        mapping = json.loads(CONTRACT_MAPPING.read_text(encoding="utf-8"))
        contract = {e["blueprintEntity"]: e["engineDocType"] for e in mapping["entities"]}
        self.assertEqual(contract, NEW_PAIRS)
        for entity, doctype in contract.items():
            self.assertEqual(ENTITY_TO_DOCTYPE.get(entity), doctype, entity)

    def test_earlier_pairs_are_unchanged_and_protected_entities_stay_protected(self) -> None:
        self.assertEqual(ENTITY_TO_DOCTYPE["sales_order_line"], "Sales Order Item")
        self.assertEqual(ENTITY_TO_DOCTYPE["delivery_note"], "Delivery Note")
        for entity in ("general_ledger", "tax_ledger", "audit_log", "user_account", "session_token"):
            self.assertTrue(is_protected_entity(entity), entity)
            self.assertIsNone(reviewed_grant_doctype(entity), entity)

    def test_mapped_entities_are_reviewed_and_not_protected(self) -> None:
        for entity, doctype in NEW_PAIRS.items():
            self.assertFalse(is_protected_entity(entity), entity)
            self.assertEqual(reviewed_grant_doctype(entity), doctype, entity)

    def test_grant_plan_reason_allows_mapped_and_refuses_unmapped_built_ins(self) -> None:
        for entity in NEW_PAIRS:
            self.assertIsNone(grant_plan_reason(role("r", [grant(entity, "read")]), set()), entity)
        for entity in STILL_UNMAPPED:
            # Not in this Blueprint, or in it but with an engine document type the adapter did not make.
            self.assertEqual(grant_plan_reason(role("r", [grant(entity, "read")]), set()), "protected_subject", entity)
            self.assertEqual(grant_plan_reason(role("r", [grant(entity, "read")]), {entity}, own_allowed=lambda e: False),
                             "protected_subject", entity)


class TestPurchasingGrantsOnEngineBackend(_Base):
    """Apply time, on the engine-backed backend over a simulated engine (the bench is not needed)."""

    def setUp(self) -> None:
        super().setUp()
        self.engine.add_doctype("Item Price", module="Stock", custom=0)  # an engine document type the fake does not seed

    def test_role_grants_on_every_mapped_top_level_entity_reach_the_engine(self) -> None:
        self.upsert(role("buyer", [grant(e, "read", "create", "update") for e in GRANTABLE]))
        for entity in GRANTABLE:
            doctype = NEW_PAIRS[entity]
            self.assertEqual(self.granted("bp-buyer", doctype), {"read", "create", "write"}, doctype)

    def test_submit_is_granted_only_on_the_submittable_documents(self) -> None:
        self.upsert(role("approver", [grant(e, "read", "update", "submit") for e in GRANTABLE]))
        for entity in GRANTABLE:
            expected = {"read", "write", "submit"} if entity in SUBMITTABLE_ENTITIES else {"read", "write"}
            self.assertEqual(self.granted("bp-approver", NEW_PAIRS[entity]), expected, entity)

    def test_a_grant_on_a_mapped_entity_whose_table_is_missing_fails_closed(self) -> None:
        engine = CaseInsensitiveEngine(SITE)
        site = engine.current_site_db()
        site.rows["tabDocType"].pop("Supplier")
        site.rows.pop("tabSupplier")
        site.table_columns.pop("tabSupplier")
        self.engine = engine
        self.backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={_ROLES_TENANT: SITE}),
                                            frappe_factory=lambda: engine, offline_ddl_simulator=True)
        self.refused(lambda: self.upsert(role("buyer", [grant("supplier", "read")])), reason="subject_missing")
        self.assertNotIn("bp-buyer", self.roles())

    def test_built_ins_outside_the_mapping_are_still_refused_before_any_write(self) -> None:
        for entity in STILL_UNMAPPED:
            before = self.engine.rows("Custom DocPerm")
            self.refused(lambda: self.upsert(role("buyer", [grant("supplier", "read"), grant(entity, "read")])))
            self.assertNotIn("bp-buyer", self.roles(), entity)
            self.assertEqual(self.engine.rows("Custom DocPerm"), before, entity)


def _ctx() -> dict:
    return {"contractVersion": "0.1.2", "requestId": "01J00000000000000000000032", "correlationId": "corr_bpl032_purch",
            "tenantId": TENANT, "caller": {"service": "control_plane", "onBehalfOf": {"kind": "user", "id": "usr_owner"}},
            "deadlineMs": 120000}


def _step(seq: int, rid: str, perms: list[dict]) -> dict:
    return {"seq": seq, "phase": 7, "kind": "role.upsert", "subject": {"kind": "role", "id": rid, "parents": []},
            "pointer": f"/roles/{rid}", "impact": "access", "ddlImpact": "none", "reversible": True,
            "params": {"definition": role(rid, perms)}, "sourceOps": [f"/roles/{rid}"]}


def _artifact(steps: list[dict]) -> dict:
    counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
    counts["access"] = len(steps)
    art = {"artifactSchema": "0.1.0", "kind": "forward", "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
           "blueprint": {"id": "bp-bpl032p", "base": None, "target": {"hash": "sha256:" + "5" * 64, "revision": 1}, "diffHash": None},
           "engineTarget": {"adapter": "frappe", "versionSet": "set-example"}, "components": [], "steps": steps,
           "skippedOps": [], "postConditions": [],
           "risk": {"counts": counts, "total": len(steps), "maxImpact": "access", "needsDdlPlanGate": False,
                    "touchesCompliance": False, "touchesAccess": True, "touchesLedgerOrTax": False,
                    "requiresTeamReview": False, "irreversibleSteps": 0},
           "inverse": None}
    digest, art_id = cs.artifact_hashes(art)
    art.update(artifactId=art_id, integrity={"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None})
    return art


class _PlanBase:
    """Both adapters must plan a purchasing grant as the sales one: role.upsert stays gated, never blocked."""

    def make_adapter(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def plan(self, steps: list[dict]) -> dict:
        adapter = self.make_adapter()
        art = _artifact(steps)
        prov = adapter.call("provision_site", _ctx(), {"idempotencyKey": f"idemp_bpl032p_{type(self).__name__}"[:60],
                                                        "engineTarget": art["engineTarget"], "blueprintId": "bp-bpl032p",
                                                        "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        res = adapter.call("plan", _ctx(), {"artifact": art})
        self.assertTrue(res["ok"], res)
        return res["result"]

    def test_mapped_purchasing_grants_plan_as_gated_not_blocked(self) -> None:
        steps = [_step(i, f"r_{e}", [grant(e, "read", "update")]) for i, e in enumerate(NEW_PAIRS, start=1)]
        out = self.plan(steps)
        got = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in out["steps"]}
        for seq, entity in enumerate(NEW_PAIRS, start=1):
            self.assertEqual(got[seq], ("gated", "protected_subject"), entity)  # the same as sales_order: role.upsert is gated
        self.assertEqual(out["verdict"], "needs_gate_approval")

    def test_a_mixed_artifact_blocks_only_the_unmapped_built_ins(self) -> None:
        steps = [_step(1, "r_buyer", [grant("supplier", "read"), grant("purchase_order", "read", "submit")]),
                 _step(2, "r_pay", [grant("payment_entry", "read")]),
                 _step(3, "r_price", [grant("price_list", "read"), grant("price_list_item", "read")])]
        out = self.plan(steps)
        got = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in out["steps"]}
        self.assertEqual(got[1], ("gated", "protected_subject"))
        self.assertEqual(got[2], ("blocked", "protected_subject"))
        self.assertEqual(got[3], ("gated", "protected_subject"))
        self.assertEqual(out["verdict"], "rejected")


class TestPurchasingPlanInMemoryAdapter(_PlanBase, unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})
        env.start()
        self.addCleanup(env.stop)

    def make_adapter(self):
        return make_frappe_adapter(simulated=True, test_hooks=False)


class TestPurchasingPlanOfflineEngineAdapter(_PlanBase, unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})
        env.start()
        self.addCleanup(env.stop)
        self.engine = CaseInsensitiveEngine(SITE)
        self.engine.add_doctype("Item Price", module="Stock", custom=0)

    def make_adapter(self):
        return make_frappe_adapter(
            site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
            frappe_factory=lambda: self.engine,
            offline_ddl_simulator=True,
            test_hooks=False,
        )

    def test_a_missing_engine_table_for_a_mapped_entity_is_not_a_plan_time_refusal(self) -> None:
        # Existence is checked when the grant is applied (subject_missing), as for the sales documents.
        site = self.engine.current_site_db()
        site.rows["tabDocType"].pop("Supplier")
        out = self.plan([_step(1, "r_sup", [grant("supplier", "read")])])
        self.assertEqual({(s["disposition"], s.get("reasonCode")) for s in out["steps"]}, {("gated", "protected_subject")})


if __name__ == "__main__":
    unittest.main()
