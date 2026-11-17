"""
Engine-side integration tests for ZATCA Phase 1 invoicing.
"""

from decimal import Decimal
import unittest

from apps.engine.change_engine.change_engine.compliance import (
    decode_phase1_tlv,
    encode_phase1_tlv,
    generate_phase1_invoice,
)


class TestEngineZatcaPhase1(unittest.TestCase):
    """Test engine import and invocation of ZATCA Phase 1 compliance."""

    def test_engine_tlv_generation(self):
        b64 = encode_phase1_tlv(
            seller_name="شركة الرياض للتوزيع",
            vat_number="300000000000003",
            timestamp_iso="2026-11-07T12:00:00Z",
            invoice_total_str="115.00",
            vat_total_str="15.00",
        )
        decoded = decode_phase1_tlv(b64)
        self.assertEqual(decoded[1], "شركة الرياض للتوزيع")
        self.assertEqual(decoded[2], "300000000000003")
        self.assertEqual(decoded[4], "115.00")
        self.assertEqual(decoded[5], "15.00")

    def test_engine_invoice_factory(self):
        inv_data = {
            "invoice_id": "ENG-INV-001",
            "issue_date": "2026-11-07",
            "issue_time": "09:30:00",
            "timezone": "Asia/Riyadh",
            "currency": "SAR",
            "invoice_type": "simplified",
            "transaction_type": "simplified_tax_invoice",
            "seller": {
                "name": "Riyadh Logistics",
                "name_ar": "شركة الرياض اللوجستية",
                "vat_number": "300000000000003",
                "address": {
                    "street": "Al-Amir Road",
                    "building_no": "100",
                    "postal_code": "11564",
                    "city": "Riyadh",
                    "district": "Al-Malaz",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "LOG-01",
                    "description": "Courier Delivery",
                    "quantity": "5",
                    "unit_price": "20.00",
                    "vat_rate": "0.15",
                    "vat_category": "S",
                }
            ],
            "totals": {"total_taxable_amount": "100.00", "total_vat_amount": "15.00", "grand_total": "115.00"},
        }

        invoice = generate_phase1_invoice(inv_data)
        self.assertIsNotNone(invoice.qr_code_tlv)
        self.assertEqual(invoice.totals.grand_total, Decimal("115.00"))
        self.assertEqual(decode_phase1_tlv(invoice.qr_code_tlv)[4], "115.00")

    def test_bench_import_resolves_without_repo_root_on_sys_path(self):
        """Importing change_engine.compliance from a bench cwd works without repo root on PYTHONPATH."""
        from pathlib import Path
        import subprocess
        import sys

        app_root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, {str(app_root)!r}); "
                    "import change_engine.compliance as c; "
                    "assert hasattr(c, 'generate_phase1_invoice')"
                ),
            ],
            cwd="/tmp",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
