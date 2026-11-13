"""
Unit test suite for ZATCA Phase 1 E-Invoicing Component (CMP-003).
Covers TLV encoding/decoding, mandatory field validation, checks on engine-supplied totals,
credit/debit notes, and error handling.
"""

from decimal import Decimal
import unittest

from components.compliance.zatca_sa.phase1 import (
    ZatcaAddress,
    ZatcaInvoice,
    ZatcaLineItem,
    ZatcaParty,
    ZatcaValidationError,
    decode_phase1_tlv,
    encode_phase1_tlv,
    generate_phase1_invoice,
    generate_phase1_qr,
)


class TestZatcaPhase1TLV(unittest.TestCase):
    """Tests for ZATCA Phase 1 5-tag TLV encoding and decoding."""

    def test_official_sample_test_vector(self):
        """Bit-for-bit match with the worked example published by ZATCA.

        Source: ZATCA, E-invoicing Detailed Technical Guideline, section 6.4 "Manual decoding a TLV
        QR Code", https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing-Detailed-Technical-Guideline.pdf
        (accessed 2026-11-13). Values and the Base64 string are copied from that document.
        """
        seller_name = "Bobs Basement Records"
        vat_number = "100025906700003"
        timestamp = "2022-04-25T15:30:00Z"
        invoice_total = "2100100.99"
        vat_total = "315015.15"

        expected_b64 = (
            "ARVCb2JzIEJhc2VtZW50IFJlY29yZHMCDzEwMDAyNTkwNjcwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoE"
            "CjIxMDAxMDAuOTkFCTMxNTAxNS4xNQ=="
        )

        actual_b64 = encode_phase1_tlv(
            seller_name=seller_name,
            vat_number=vat_number,
            timestamp_iso=timestamp,
            invoice_total_str=invoice_total,
            vat_total_str=vat_total,
        )

        self.assertEqual(actual_b64, expected_b64)

        # Verify round-trip decode
        decoded = decode_phase1_tlv(actual_b64)
        self.assertEqual(decoded[1], seller_name)
        self.assertEqual(decoded[2], vat_number)
        self.assertEqual(decoded[3], timestamp)
        self.assertEqual(decoded[4], invoice_total)
        self.assertEqual(decoded[5], vat_total)

    def test_arabic_seller_name_roundtrip(self):
        """Verify UTF-8 multi-byte encoding for Arabic business names."""
        seller_name = "شركة الأفق للتجارة والتوزيع المحدودة"
        vat_number = "300000000000003"
        timestamp = "2026-11-07T12:00:00Z"
        invoice_total = "230.00"
        vat_total = "30.00"

        b64 = encode_phase1_tlv(
            seller_name=seller_name,
            vat_number=vat_number,
            timestamp_iso=timestamp,
            invoice_total_str=invoice_total,
            vat_total_str=vat_total,
        )

        decoded = decode_phase1_tlv(b64)
        self.assertEqual(decoded[1], seller_name)
        self.assertEqual(decoded[2], vat_number)
        self.assertEqual(decoded[3], timestamp)
        self.assertEqual(decoded[4], invoice_total)
        self.assertEqual(decoded[5], vat_total)

    def test_malformed_tlv_decode(self):
        """Test rejection of corrupted or truncated TLV strings."""
        with self.assertRaises(ValueError):
            decode_phase1_tlv("NotValidBase64==")

        # Truncated TLV payload (tag byte only, missing length and value)
        import base64
        short_b64 = base64.b64encode(b"\x01").decode("ascii")
        with self.assertRaises(ValueError):
            decode_phase1_tlv(short_b64)


class TestZatcaVATValidation(unittest.TestCase):
    """Tests for KSA 15-digit VAT number format rules."""

    def test_valid_vat_numbers(self):
        valid_vats = ["300000000000003", "310122393500003", "399999999999993"]
        for vat in valid_vats:
            seller = ZatcaParty(
                name="Test Co",
                vat_number=vat,
                address=ZatcaAddress("Street", "1", "12345", "Riyadh", "Olaya", "SA"),
            )
            errors = seller.validate(is_seller=True)
            self.assertEqual(errors, [])

    def test_invalid_vat_numbers(self):
        invalid_cases = [
            ("100000000000003", "does not start with 3"),
            ("300000000000001", "does not end with 3"),
            ("300000000003", "less than 15 digits"),
            ("30000000000000003", "more than 15 digits"),
            ("3000000000000A3", "contains non-numeric characters"),
            ("", "empty vat number"),
        ]
        for vat, reason in invalid_cases:
            seller = ZatcaParty(
                name="Test Co",
                vat_number=vat,
                address=ZatcaAddress("Street", "1", "12345", "Riyadh", "Olaya", "SA"),
            )
            errors = seller.validate(is_seller=True)
            self.assertTrue(len(errors) > 0, f"Expected validation failure for {vat} ({reason})")


class TestZatcaInvoiceGeneration(unittest.TestCase):
    """Tests for Standard and Simplified invoice creation and validation."""

    def setUp(self):
        self.seller_addr = ZatcaAddress(
            street="King Fahd Road",
            building_no="1234",
            postal_code="12345",
            city="Riyadh",
            district="Al-Olaya",
            country_code="SA",
        )
        self.seller = ZatcaParty(
            name="Al-Noor Trading Est",
            name_ar="مؤسسة النور للتجارة",
            vat_number="300000000000003",
            cr_number="1010123456",
            address=self.seller_addr,
        )
        self.buyer_addr = ZatcaAddress(
            street="Prince Sultan Street",
            building_no="5678",
            postal_code="23456",
            city="Jeddah",
            district="Al-Rawdah",
            country_code="SA",
        )
        self.buyer = ZatcaParty(
            name="Gulf Enterprises LLC",
            name_ar="شركة المشاريع الخليجية",
            vat_number="310122393500003",
            address=self.buyer_addr,
        )

    def test_simplified_b2c_invoice(self):
        """Simplified (B2C) invoice for retail customer with mandatory Phase 1 QR."""
        inv_data = {
            "invoice_id": "INV-2026-0001",
            "issue_date": "2026-11-07",
            "issue_time": "14:30:00",
            "invoice_type": "simplified",
            "transaction_type": "simplified_tax_invoice",
            "currency": "SAR",
            "seller": {
                "name": "Al-Noor Trading Est",
                "name_ar": "مؤسسة النور للتجارة",
                "vat_number": "300000000000003",
                "address": {
                    "street": "King Fahd Road",
                    "building_no": "1234",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Al-Olaya",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "ITEM-001",
                    "description": "Office Desk Chair",
                    "quantity": "2",
                    "unit_price": "100.00",
                    "vat_rate": "0.15",
                    "discount": "0.00",
                    "vat_category": "S",
                }
            ],
            "totals": {"total_taxable_amount": "200.00", "total_vat_amount": "30.00", "grand_total": "230.00"},
        }

        invoice = generate_phase1_invoice(inv_data)
        self.assertIsNotNone(invoice.qr_code_tlv)

        self.assertEqual(invoice.totals.grand_total, Decimal("230.00"))

        # Verify decoded QR matches invoice amounts
        decoded_qr = decode_phase1_tlv(invoice.qr_code_tlv)
        self.assertEqual(decoded_qr[1], "مؤسسة النور للتجارة")
        self.assertEqual(decoded_qr[2], "300000000000003")
        self.assertEqual(decoded_qr[4], "230.00")
        self.assertEqual(decoded_qr[5], "30.00")

    def test_standard_b2b_invoice(self):
        """Standard (B2B) invoice requires buyer details and validates domestic addresses."""
        inv_data = {
            "invoice_id": "INV-B2B-1001",
            "issue_date": "2026-11-07",
            "issue_time": "10:15:00",
            "invoice_type": "standard",
            "transaction_type": "tax_invoice",
            "currency": "SAR",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {
                    "street": "King Fahd Road",
                    "building_no": "1234",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Al-Olaya",
                    "country_code": "SA",
                },
            },
            "buyer": {
                "name": "Gulf Enterprises LLC",
                "vat_number": "310122393500003",
                "address": {
                    "street": "Prince Sultan Street",
                    "building_no": "5678",
                    "postal_code": "23456",
                    "city": "Jeddah",
                    "district": "Al-Rawdah",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "SERV-001",
                    "description": "IT Consulting Services",
                    "quantity": "10",
                    "unit_price": "500.00",
                    "vat_rate": "0.15",
                }
            ],
            "totals": {"total_taxable_amount": "5000.00", "total_vat_amount": "750.00", "grand_total": "5750.00"},
        }

        invoice = generate_phase1_invoice(inv_data)
        decoded_qr = decode_phase1_tlv(invoice.qr_code_tlv)
        self.assertEqual(decoded_qr[4], "5750.00")
        self.assertEqual(decoded_qr[5], "750.00")

    def test_standard_b2b_missing_buyer_fails(self):
        """Standard tax invoices must fail if buyer details are omitted."""
        inv_data = {
            "invoice_id": "INV-B2B-FAIL",
            "issue_date": "2026-11-07",
            "issue_time": "10:15:00",
            "invoice_type": "standard",
            "transaction_type": "tax_invoice",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {
                    "street": "King Fahd Road",
                    "building_no": "1234",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Al-Olaya",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "ITEM-1",
                    "description": "Item",
                    "quantity": "1",
                    "unit_price": "100.00",
                }
            ],
        }

        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(inv_data)
        self.assertTrue(any("Buyer information is mandatory" in err for err in ctx.exception.errors))

    def test_credit_note_preceding_reference(self):
        """Credit and Debit notes must reference preceding invoice reference and state amendment reason."""
        inv_data = {
            "invoice_id": "CN-2026-0005",
            "issue_date": "2026-11-07",
            "issue_time": "15:00:00",
            "invoice_type": "simplified",
            "transaction_type": "credit_note",
            "preceding_invoice_reference": "INV-2026-0001",
            "amendment_reason": "Customer return of damaged chair",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {
                    "street": "King Fahd Road",
                    "building_no": "1234",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Al-Olaya",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "ITEM-001",
                    "description": "Returned Chair",
                    "quantity": "1",
                    "unit_price": "100.00",
                    "vat_rate": "0.15",
                }
            ],
            "totals": {"total_taxable_amount": "100.00", "total_vat_amount": "15.00", "grand_total": "115.00"},
        }

        invoice = generate_phase1_invoice(inv_data)
        self.assertEqual(invoice.preceding_invoice_reference, "INV-2026-0001")
        self.assertEqual(invoice.amendment_reason, "Customer return of damaged chair")

    def test_credit_note_missing_preceding_reference_fails(self):
        """Credit note missing preceding reference must fail validation."""
        inv_data = {
            "invoice_id": "CN-2026-FAIL",
            "issue_date": "2026-11-07",
            "issue_time": "15:00:00",
            "invoice_type": "simplified",
            "transaction_type": "credit_note",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {
                    "street": "Street",
                    "building_no": "1",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Olaya",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "ITEM-1",
                    "description": "Item",
                    "quantity": "1",
                    "unit_price": "100.00",
                }
            ],
        }

        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(inv_data)
        self.assertTrue(
            any("Preceding invoice reference is mandatory" in err for err in ctx.exception.errors)
        )

    def test_zero_rated_line_uses_engine_totals(self):
        """Zero-rated items validate, and the QR carries the engine's totals unchanged."""
        inv_data = {
            "invoice_id": "INV-EXEMPT-01",
            "issue_date": "2026-11-07",
            "issue_time": "11:00:00",
            "invoice_type": "simplified",
            "transaction_type": "simplified_tax_invoice",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {
                    "street": "Street",
                    "building_no": "1",
                    "postal_code": "12345",
                    "city": "Riyadh",
                    "district": "Olaya",
                    "country_code": "SA",
                },
            },
            "lines": [
                {
                    "item_code": "MED-01",
                    "description": "Qualified Medicine (Zero-rated)",
                    "quantity": "1",
                    "unit_price": "87.65",
                    "vat_rate": "0.00",
                    "vat_category": "Z",
                    "exemption_reason_code": "VATEX-SA-32",
                    "exemption_reason_text": "Supply of qualifying medicines",
                },
                {
                    "item_code": "STN-02",
                    "description": "Standard Item with odd cents",
                    "quantity": "3",
                    "unit_price": "33.33",
                    "vat_rate": "0.15",
                    "vat_category": "S",
                },
            ],
            # As computed by the engine: VAT rounded once at document level (ZATCA XML implementation
            # standard, chapter 10). This module does not recompute it.
            "totals": {"total_taxable_amount": "187.64", "total_vat_amount": "15.00", "grand_total": "202.64"},
        }

        invoice = generate_phase1_invoice(inv_data)
        decoded_qr = decode_phase1_tlv(invoice.qr_code_tlv)
        self.assertEqual(decoded_qr[4], "202.64")
        self.assertEqual(decoded_qr[5], "15.00")


class TestEngineTotalsAuthority(unittest.TestCase):
    """ADR-0031: the engine computes totals; this module checks them and fails closed."""

    def base(self, totals):
        data = {
            "invoice_id": "INV-AUTH-01",
            "issue_date": "2026-11-07",
            "issue_time": "11:00:00",
            "invoice_type": "simplified",
            "transaction_type": "simplified_tax_invoice",
            "seller": {
                "name": "Al-Noor Trading Est",
                "vat_number": "300000000000003",
                "address": {"street": "Street", "building_no": "1", "postal_code": "12345",
                            "city": "Riyadh", "district": "Olaya", "country_code": "SA"},
            },
            "lines": [{"item_code": "ITEM-1", "description": "Item", "quantity": "1",
                       "unit_price": "100.00", "vat_rate": "0.15", "vat_category": "S"}],
        }
        if totals is not None:
            data["totals"] = totals
        return data

    def test_document_discount_vat_comes_from_engine(self):
        """100.00 less a 10.00 document discount: the engine's VAT (13.50) is used, not recomputed."""
        invoice = generate_phase1_invoice(self.base(
            {"total_taxable_amount": "90.00", "total_vat_amount": "13.50", "grand_total": "103.50"}))
        decoded_qr = decode_phase1_tlv(invoice.qr_code_tlv)
        self.assertEqual(decoded_qr[4], "103.50")
        self.assertEqual(decoded_qr[5], "13.50")

    def test_missing_totals_fails(self):
        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(self.base(None))
        self.assertTrue(any("totals from the engine are mandatory" in e for e in ctx.exception.errors))

    def test_inconsistent_totals_fail_closed(self):
        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(self.base(
                {"total_taxable_amount": "90.00", "total_vat_amount": "15.00", "grand_total": "103.50"}))
        self.assertTrue(any("Engine totals disagree" in e for e in ctx.exception.errors))

    def test_unrounded_totals_fail(self):
        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(self.base(
                {"total_taxable_amount": "99.99", "total_vat_amount": "14.9985", "grand_total": "114.9885"}))
        self.assertTrue(any("rounded to 2 decimals" in e for e in ctx.exception.errors))

    def test_non_finite_amount_fails(self):
        for bad in ("NaN", "Infinity", "abc"):
            with self.assertRaises(ZatcaValidationError):
                generate_phase1_invoice(self.base(
                    {"total_taxable_amount": bad, "total_vat_amount": "15.00", "grand_total": "115.00"}))

    def test_negative_quantity_fails(self):
        data = self.base({"total_taxable_amount": "100.00", "total_vat_amount": "15.00", "grand_total": "115.00"})
        data["lines"][0]["quantity"] = "-1"
        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(data)
        self.assertTrue(any("Quantity cannot be negative" in e for e in ctx.exception.errors))

    def test_missing_vat_rate_fails(self):
        data = self.base({"total_taxable_amount": "100.00", "total_vat_amount": "15.00", "grand_total": "115.00"})
        del data["lines"][0]["vat_rate"]
        with self.assertRaises(ZatcaValidationError) as ctx:
            generate_phase1_invoice(data)
        self.assertTrue(any("VAT rate is required" in e for e in ctx.exception.errors))


if __name__ == "__main__":
    unittest.main()
