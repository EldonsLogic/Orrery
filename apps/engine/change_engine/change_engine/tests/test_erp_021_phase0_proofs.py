"""Unit and contract tests for the ERP-021 Phase 0 Engine Proof Suite."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[5]
CHANGE_ENGINE_ROOT = REPO_ROOT / "apps" / "engine" / "change_engine"
DOCKER_DIR = REPO_ROOT / "infra" / "dev" / "docker"

for p in (str(REPO_ROOT), str(CHANGE_ENGINE_ROOT), str(DOCKER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from change_engine.adapter import ChangeEngineAdapter  # noqa: E402
from change_engine.proofs.phase0_bench_proof import (  # noqa: E402
    _ctx,
    _seal_artifact,
    verify_mapping_against_meta,
    verify_trial_balance_reconciliation,
)
from components.compliance.zatca_sa.phase1 import generate_phase1_invoice  # noqa: E402
import run_phase0_proofs  # noqa: E402


def _load_json(rel_path: str) -> dict:
    return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))


class TestErp021MappingVerification(unittest.TestCase):
    def test_verify_mapping_against_golden_path_fixture_detects_type_mismatch(self) -> None:
        mapping = _load_json("contracts/examples/engine-mapping-golden-path.json")
        # Construct realistic Frappe v15 meta where additional_discount_percentage is Float
        meta_by_doctype = {}
        for entity in mapping["entities"]:
            dt = entity["engineDocType"]
            fields = meta_by_doctype.setdefault(
                dt, {"submittable": bool(entity.get("submittable")), "fields": {}}
            )["fields"]
            for fld in entity["fields"]:
                via = fld.get("via")
                if via:
                    v_dt = via["engineDocType"]
                    v_fields = meta_by_doctype.setdefault(
                        v_dt, {"submittable": False, "fields": {}}
                    )["fields"]
                    v_fields[via["engineField"]] = fld["engineType"]
                elif fld.get("engineField"):
                    ef = fld["engineField"]
                    ft = fld["engineType"]
                    if ef == "additional_discount_percentage":
                        ft = "Float"
                    fields[ef] = ft

        report = verify_mapping_against_meta(mapping, meta_by_doctype)
        self.assertEqual(report["missing_doctypes"], [])
        self.assertEqual(report["missing_fields"], [])
        self.assertEqual(len(report["type_mismatches"]), 2)
        self.assertEqual(
            {(m["doctype"], m["field"], m["mapping"], m["engine"]) for m in report["type_mismatches"]},
            {
                ("Sales Order", "additional_discount_percentage", "Percent", "Float"),
                ("Sales Invoice", "additional_discount_percentage", "Percent", "Float"),
            },
        )
        self.assertFalse(report["exact_match"])

    def test_verify_mapping_reports_missing_doctype_and_field(self) -> None:
        mapping = {
            "entities": [
                {
                    "engineDocType": "Missing Doc",
                    "submittable": False,
                    "fields": [{"engineField": "x", "engineType": "Data"}],
                },
                {
                    "engineDocType": "Customer",
                    "submittable": False,
                    "fields": [{"engineField": "missing_col", "engineType": "Data"}],
                },
            ]
        }
        report = verify_mapping_against_meta(
            mapping, {"Customer": {"submittable": False, "fields": {}}}
        )
        self.assertEqual(report["missing_doctypes"], ["Missing Doc"])
        self.assertEqual(
            report["missing_fields"], [{"doctype": "Customer", "field": "missing_col"}]
        )
        self.assertFalse(report["exact_match"])


class TestErp021TrialBalanceReconciliation(unittest.TestCase):
    def test_reconciliation_passes_for_golden_path_figures(self) -> None:
        gl_rows = [
            # Material receipt: 100 pcs @ 10 = 1000
            {"account": "Stock In Hand - GTC", "debit": 1000.0, "credit": 0.0, "is_cancelled": 0},
            {"account": "Temporary Opening - GTC", "debit": 0.0, "credit": 1000.0, "is_cancelled": 0},
            # Delivery Note: 10 pcs @ 10 = 100
            {"account": "Cost of Goods Sold - GTC", "debit": 100.0, "credit": 0.0, "is_cancelled": 0},
            {"account": "Stock In Hand - GTC", "debit": 0.0, "credit": 100.0, "is_cancelled": 0},
            # Sales Invoice: 10 pcs @ 15 = 150
            {"account": "Debtors - GTC", "debit": 150.0, "credit": 0.0, "is_cancelled": 0},
            {"account": "Sales - GTC", "debit": 0.0, "credit": 150.0, "is_cancelled": 0},
            # Cancelled entry must be ignored
            {"account": "Debtors - GTC", "debit": 999.0, "credit": 0.0, "is_cancelled": 1},
        ]
        res = verify_trial_balance_reconciliation(
            gl_rows=gl_rows,
            expected_stock_value=900.0,
            actual_stock_value=900.0,
            expected_ar=150.0,
            actual_ar=150.0,
            inventory_account="Stock In Hand - GTC",
            ar_account="Debtors - GTC",
        )
        self.assertTrue(res["reconciled"])
        self.assertEqual(res["inventory_gl_balance"], 900.0)
        self.assertEqual(res["ar_gl_balance"], 150.0)
        self.assertEqual(res["total_debit"], 1250.0)
        self.assertEqual(res["total_credit"], 1250.0)
        self.assertEqual(res["net_trial_balance_debit"], 1150.0)
        self.assertEqual(res["net_trial_balance_credit"], 1150.0)

    def test_reconciliation_fails_on_stock_or_ar_drift(self) -> None:
        gl_rows = [
            {"account": "Stock In Hand - GTC", "debit": 900.0, "credit": 0.0, "is_cancelled": 0},
            {"account": "Debtors - GTC", "debit": 150.0, "credit": 0.0, "is_cancelled": 0},
            {"account": "Sales - GTC", "debit": 0.0, "credit": 1050.0, "is_cancelled": 0},
        ]
        res = verify_trial_balance_reconciliation(
            gl_rows=gl_rows,
            expected_stock_value=900.0,
            actual_stock_value=890.0,
            expected_ar=150.0,
            actual_ar=150.0,
            inventory_account="Stock In Hand - GTC",
            ar_account="Debtors - GTC",
        )
        self.assertFalse(res["inventory_tie_out"])
        self.assertFalse(res["reconciled"])


class TestErp021OfflineAdapterAndComponentContracts(unittest.TestCase):
    def test_adapter_isolation_authz_fault_and_quarantine_contracts(self) -> None:
        ce = ChangeEngineAdapter(test_hooks=True)
        prov = ce.call(
            "provision_site",
            _ctx("t_alpha", "u_prov"),
            {
                "idempotencyKey": "u_prov_000000001",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "countryPack": "sa",
                "siteClass": "sandbox",
                "blueprintId": "example-trading-001",
            },
        )
        self.assertTrue(prov["ok"])

        unknown = ce.call(
            "site_status",
            _ctx("t_unknown", "u_unknown"),
            {},
        )
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["error"]["code"], "tenant_not_found")

        svc_denied = ce.call(
            "apply",
            _ctx("t_alpha", "u_svc", service="observability"),
            {"idempotencyKey": "u_svc_0000000001"},
        )
        self.assertFalse(svc_denied["ok"])
        self.assertEqual(svc_denied["error"]["code"], "permission_denied")

        # Seal minimal artifact and verify fault injection preserves zero dropped data
        art = _seal_artifact(
            {
                "artifactSchema": "0.1.0",
                "kind": "forward",
                "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
                "blueprint": {
                    "id": "example-trading-001",
                    "base": None,
                    "target": {"hash": "sha256:" + "0" * 64, "revision": 1},
                    "diffHash": None,
                },
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "components": [],
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
                        "params": {
                            "definition": {
                                "id": "customer",
                                "kind": "master",
                                "labels": {"en": "Customer", "ar": "عميل"},
                                "fields": [{"id": "customer_name", "type": "string", "labels": {"en": "Name", "ar": "الاسم"}}],
                            }
                        },
                        "sourceOps": ["/entities/customer"],
                    }
                ],
                "skippedOps": [],
                "postConditions": [{"id": "pc_001", "check": "exists", "pointer": "/entities/customer"}],
                "risk": {
                    "counts": {"cosmetic": 0, "config": 0, "data_shape": 1, "destructive": 0, "compliance": 0, "access": 0, "branding": 0},
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
        plan = ce.call("plan", _ctx("t_alpha", "u_plan"), {"artifact": art})
        self.assertTrue(plan["ok"])
        ce.fault("execute", step_seq=1)
        faulted = ce.call(
            "apply",
            _ctx("t_alpha", "u_fault"),
            {
                "idempotencyKey": "u_fault_00000001",
                "artifact": art,
                "planToken": plan["result"]["planToken"],
                "approvals": {
                    "changeApproved": "01J00000000000000000000099",
                    "gateApproved": "01J00000000000000000000098",
                },
            },
        )
        self.assertTrue(faulted["ok"])
        self.assertEqual(faulted["result"]["status"], "compensated")
        self.assertEqual(ce.dropped_data(), [])

    def test_bundle_loads_and_zatca_generates_qr(self) -> None:
        bundle = run_phase0_proofs.build_artifacts_bundle()
        self.assertEqual(bundle["zatca_manifest"]["id"], "compliance.zatca_sa")
        inv = generate_phase1_invoice(
            {
                "invoice_id": "GTC-SI-0001",
                "issue_date": "2026-01-12",
                "issue_time": "11:00:00",
                "timezone": "Asia/Riyadh",
                "currency": "SAR",
                "invoice_type": "simplified",
                "transaction_type": "simplified_tax_invoice",
                "seller": {
                    "name": "Golden Trading Co",
                    "name_ar": "شركة المثال للتجارة",
                    "vat_number": "300000000000003",
                    "address": {
                        "street": "King Fahd Rd",
                        "building_no": "100",
                        "postal_code": "11564",
                        "city": "Riyadh",
                        "district": "Al-Olaya",
                        "country_code": "SA",
                    },
                },
                "lines": [
                    {
                        "item_code": "ITEM-001",
                        "description": "Golden Trading Widget",
                        "quantity": "10",
                        "unit_price": "15.00",
                        "vat_rate": "0.00",
                        "vat_category": "Z",
                        "exemption_reason_code": "VATEX-SA-34",
                        "exemption_reason": "Zero-rated golden path fixture",
                    }
                ],
                "totals": {
                    "total_taxable_amount": "150.00",
                    "total_vat_amount": "0.00",
                    "grand_total": "150.00",
                },
            }
        )
        self.assertTrue(inv.qr_code_tlv)

    def test_runner_cli_rejects_unsafe_project_or_missing_sites(self) -> None:
        with self.assertRaises(ValueError):
            run_phase0_proofs.run_live_suite(project="bad;project")
        rc = run_phase0_proofs.main(["--compose-project", "demo", "--skip-provision"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
