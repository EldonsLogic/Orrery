"""Unit and integration tests for ERP-007 bilingual Arabic/English tax invoice print format."""

from __future__ import annotations

import base64
from datetime import date, timedelta
from decimal import Decimal
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from change_engine.compliance import ZatcaValidationError, decode_phase1_tlv
from change_engine.print_formats import (
    DEFAULT_BRANDING_PRIMARY,
    InvoiceBranding,
    build_qr_matrix,
    contrast_ratio_on_white,
    install_bilingual_tax_invoice_print_format,
    render_frappe_sales_invoice_html,
    render_qr_svg,
    render_tax_invoice_html,
    render_tax_invoice_pdf,
    resolve_invoice_branding,
    sales_invoice_to_zatca_dict,
)

# 1x1 transparent PNG
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
TINY_PNG_URI = f"data:image/png;base64,{TINY_PNG_B64}"


def _sample_zatca_standard() -> dict:
    return {
        "invoice_id": "INV-2026-0001",
        "issue_date": "2026-11-17",
        "issue_time": "14:30:00",
        "hijri_date": "1448-06-07",
        "timezone": "Asia/Riyadh",
        "currency": "SAR",
        "invoice_type": "standard",
        "transaction_type": "tax_invoice",
        "seller": {
            "name": "Al-Noor Trading Est",
            "name_ar": "مؤسسة النور للتجارة",
            "vat_number": "300000000000003",
            "cr_number": "1010123456",
            "address": {
                "street": "King Fahd Road",
                "street_ar": "طريق الملك فهد",
                "building_no": "1234",
                "postal_code": "12345",
                "city": "Riyadh",
                "city_ar": "الرياض",
                "district": "Al-Olaya",
                "district_ar": "العليا",
                "country_code": "SA",
            },
        },
        "buyer": {
            "name": "Gulf Enterprises LLC",
            "name_ar": "شركة المشاريع الخليجية",
            "vat_number": "310122393500003",
            "address": {
                "street": "Prince Sultan Street",
                "street_ar": "شارع الأمير سلطان",
                "building_no": "5678",
                "postal_code": "23456",
                "city": "Jeddah",
                "city_ar": "جدة",
                "district": "Al-Rawdah",
                "district_ar": "الروضة",
                "country_code": "SA",
            },
        },
        "lines": [
            {
                "item_code": "ITEM-001",
                "description": "Office Desk Chair",
                "description_ar": "كرسي مكتب",
                "quantity": "2",
                "unit_price": "100.00",
                "discount": "0.00",
                "vat_rate": "0.15",
                "vat_category": "S",
            }
        ],
        "totals": {
            "total_taxable_amount": "200.00",
            "total_vat_amount": "30.00",
            "grand_total": "230.00",
        },
    }


def _sample_neutral_golden_path() -> dict:
    return {
        "invoice_id": "SINV-QA-0001",
        "issue_date": "2026-11-17",
        "currency": "QAR",
        "transaction_type": "invoice",
        "seller": {
            "name": "Golden Trading Co",
            "name_ar": "شركة التجارة الذهبية",
        },
        "buyer": {
            "name": "CUST-001",
            "name_ar": "العميل الأول",
        },
        "lines": [
            {
                "item_code": "ITEM-001",
                "description": "Trading Item (piece)",
                "description_ar": "صنف تجاري (قطعة)",
                "quantity": "10",
                "unit_price": "15.00",
                "discount": "0.00",
                "vat_rate": "0",
                "vat_category": "",
            }
        ],
        "totals": {
            "total_taxable_amount": "150.00",
            "total_vat_amount": "0.00",
            "grand_total": "150.00",
        },
    }


class TestBilingualTaxInvoiceHTML(unittest.TestCase):
    def test_standard_zatca_invoice_html_and_tlv_qr(self):
        doc_html = render_tax_invoice_html(_sample_zatca_standard(), mode="zatca_sa")

        self.assertIn('<html lang="ar" dir="rtl">', doc_html)
        self.assertIn("فاتورة ضريبية", doc_html)
        self.assertIn("Tax Invoice", doc_html)
        self.assertIn("مؤسسة النور للتجارة", doc_html)
        self.assertIn("Al-Noor Trading Est", doc_html)
        self.assertIn("شركة المشاريع الخليجية", doc_html)
        self.assertIn("Gulf Enterprises LLC", doc_html)
        self.assertIn('<bdi dir="ltr">INV-2026-0001</bdi>', doc_html)
        self.assertIn('<bdi dir="ltr">2026-11-17</bdi>', doc_html)
        self.assertIn('<bdi dir="ltr">1448-06-07</bdi>', doc_html)
        self.assertIn('<bdi dir="ltr">230.00 SAR</bdi>', doc_html)
        self.assertIn('<bdi dir="ltr">Seshna</bdi>', doc_html)
        self.assertIn('class="qr-clear-zone"', doc_html)
        self.assertIn('data-zatca-tlv="', doc_html)

        # Extract Base64 TLV from SVG attribute and verify round-trip decode
        tlv_b64 = doc_html.split('data-zatca-tlv="', 1)[1].split('"', 1)[0]
        decoded = decode_phase1_tlv(tlv_b64)
        self.assertEqual(decoded[1], "مؤسسة النور للتجارة")
        self.assertEqual(decoded[2], "300000000000003")
        self.assertEqual(decoded[3], "2026-11-17T11:30:00Z")
        self.assertEqual(decoded[4], "230.00")
        self.assertEqual(decoded[5], "30.00")

    def test_simplified_invoice_and_zero_rated_exemption_reason(self):
        data = _sample_zatca_standard()
        data["invoice_type"] = "simplified"
        data["transaction_type"] = "simplified_tax_invoice"
        data["lines"] = [
            {
                "item_code": "MED-01",
                "description": "Qualified Medicine",
                "description_ar": "دواء مؤهل",
                "quantity": "1",
                "unit_price": "100.00",
                "vat_rate": "0.00",
                "vat_category": "Z",
                "exemption_reason_code": "VATEX-SA-32",
                "exemption_reason_text": "Supply of qualifying medicines",
            }
        ]
        data["totals"] = {
            "total_taxable_amount": "100.00",
            "total_vat_amount": "0.00",
            "grand_total": "100.00",
        }
        doc_html = render_tax_invoice_html(data, mode="zatca_sa")
        self.assertIn("فاتورة ضريبية مبسطة", doc_html)
        self.assertIn("Simplified Tax Invoice", doc_html)
        self.assertIn("VATEX-SA-32", doc_html)
        self.assertIn("Supply of qualifying medicines", doc_html)

    def test_credit_and_debit_notes_render_preceding_reference(self):
        data = _sample_zatca_standard()
        data["invoice_id"] = "CN-2026-0001"
        data["transaction_type"] = "credit_note"
        data["preceding_invoice_reference"] = "INV-2026-0001"
        data["amendment_reason"] = "Damaged goods returned"
        cn_html = render_tax_invoice_html(data, mode="zatca_sa")
        self.assertIn("إشعار دائن ضريبي", cn_html)
        self.assertIn("Tax Credit Note", cn_html)
        self.assertIn('<bdi dir="ltr">INV-2026-0001</bdi>', cn_html)
        self.assertIn("Damaged goods returned", cn_html)

        data["invoice_id"] = "DN-2026-0001"
        data["transaction_type"] = "debit_note"
        dn_html = render_tax_invoice_html(data, mode="zatca_sa")
        self.assertIn("إشعار مدين ضريبي", dn_html)
        self.assertIn("Tax Debit Note", dn_html)

    def test_neutral_mode_is_independent_of_zatca_module(self):
        with patch.dict(sys.modules, {"change_engine.compliance": None}):
            doc_html = render_tax_invoice_html(_sample_neutral_golden_path(), mode="neutral")
        self.assertIn("فاتورة", doc_html)
        self.assertIn("Invoice", doc_html)
        self.assertIn('<bdi dir="ltr">150.00 QAR</bdi>', doc_html)
        self.assertNotIn("data-zatca-tlv", doc_html)

    def test_fail_closed_on_engine_total_mismatch(self):
        bad_zatca = _sample_zatca_standard()
        bad_zatca["totals"]["grand_total"] = "999.99"
        with self.assertRaises(ZatcaValidationError):
            render_tax_invoice_html(bad_zatca, mode="zatca_sa")

        bad_neutral = _sample_neutral_golden_path()
        bad_neutral["totals"]["grand_total"] = "149.99"
        with self.assertRaises(ValueError) as ctx:
            render_tax_invoice_html(bad_neutral, mode="neutral")
        self.assertIn("Engine totals disagree", str(ctx.exception))


class TestSeshnaTypographyAndName(unittest.TestCase):
    """GOV-071 (#328 review): the Seshna font stack (Readex Pro body, Cairo titles and figures, ADR-0066, BRD-011,
    WEB-028) and the product name kept in Latin letters inside the Arabic footer."""

    def setUp(self):
        self.doc_html = render_tax_invoice_html(_sample_zatca_standard(), mode="zatca_sa")

    def test_retired_brand_fonts_are_gone(self):
        for font in ("Alexandria", "Arial"):
            with self.subTest(font=font):
                self.assertNotIn(font, self.doc_html)

    def test_body_is_readex_pro_and_titles_and_figures_are_cairo(self):
        import re

        stacks = re.findall(r"font-family:\s*([^;]+);", self.doc_html)
        self.assertTrue(stacks and stacks[0].startswith("'Readex Pro'"), stacks)
        self.assertTrue(any(s.startswith("'Cairo'") for s in stacks), stacks)
        self.assertIn("tabular-nums", self.doc_html)

    def test_footer_keeps_seshna_in_a_latin_isolate(self):
        self.assertIn('مدعوم من <bdi dir="ltr">Seshna</bdi>', self.doc_html)
        self.assertNotIn("سيشنا", self.doc_html)


class TestBrandingAndSecurity(unittest.TestCase):
    def test_branding_contrast_and_logo_guardrails(self):
        self.assertGreaterEqual(contrast_ratio_on_white(DEFAULT_BRANDING_PRIMARY), 4.5)
        branding = InvoiceBranding(
            display_name={"ar": "النخلة للتجارة", "en": "Al Nakhla Trading"},
            primary_color="#0F766E",
            logo_data_uri=TINY_PNG_URI,
            remove_powered_by=True,
        )
        doc_html = render_tax_invoice_html(_sample_zatca_standard(), branding=branding)
        self.assertIn("#0F766E", doc_html)
        self.assertIn("النخلة للتجارة", doc_html)
        self.assertIn("Al Nakhla Trading", doc_html)
        self.assertIn("data:image/png;base64,", doc_html)
        self.assertNotIn("Powered by", doc_html)

    def test_low_contrast_or_invalid_color_rejected(self):
        with self.assertRaises(ValueError):
            resolve_invoice_branding({"primary_color": "#FFD400"})
        with self.assertRaises(ValueError):
            resolve_invoice_branding({"primary_color": "red"})

    def test_unsafe_logo_uris_rejected(self):
        svg_uri = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='alert(1)'/>").decode()
        for bad in (
            svg_uri,
            "https://evil.example/logo.png",
            "javascript:alert(1)",
            "data:image/png;base64,!!!not-base64!!!",
        ):
            with self.subTest(uri=bad):
                with self.assertRaises(ValueError):
                    resolve_invoice_branding({"logo_data_uri": bad})

    def test_xss_payloads_are_escaped(self):
        data = _sample_neutral_golden_path()
        data["seller"]["name"] = '<script>alert("xss")</script>'
        data["lines"][0]["description"] = '<img src=x onerror="alert(1)">'
        data["notes"] = 'Note "quoted" & <tag>'
        doc_html = render_tax_invoice_html(
            data,
            mode="neutral",
            branding={"display_name": 'Tenant <b>"X"</b>'},
        )
        self.assertNotIn("<script>", doc_html)
        self.assertNotIn("<img src=x", doc_html)
        self.assertIn("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;", doc_html)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", doc_html)
        self.assertIn("Tenant &lt;b&gt;&quot;X&quot;&lt;/b&gt;", doc_html)


class TestQrSvgGenerator(unittest.TestCase):
    def test_qr_matrix_and_svg_structure(self):
        payload = "ARVCb2JzIEJhc2VtZW50IFJlY29yZHMCDzEwMDAyNTkwNjcwMDAwMw=="
        matrix = build_qr_matrix(payload)
        self.assertGreaterEqual(len(matrix), 21)
        self.assertEqual(len(matrix), len(matrix[0]))
        svg = render_qr_svg(payload, size_mm=32.0, quiet_modules=4)
        self.assertIn("<svg ", svg)
        self.assertIn('width="32.0mm"', svg)
        self.assertIn('fill="#ffffff"', svg)
        self.assertIn('fill="#000000"', svg)
        with self.assertRaises(ValueError):
            render_qr_svg(payload, quiet_modules=2)


class TestFrappeSalesInvoiceIntegration(unittest.TestCase):
    def _mock_ksa_frappe_env(self):
        company = SimpleNamespace(
            company_name="Al-Noor Trading Est",
            custom_company_name_ar="مؤسسة النور للتجارة",
            tax_id="300000000000003",
            custom_cr_number="1010123456",
            country="Saudi Arabia",
        )
        seller_addr = SimpleNamespace(
            address_line1="King Fahd Road",
            custom_building_no="1234",
            pincode="12345",
            city="Riyadh",
            custom_district="Al-Olaya",
            country="Saudi Arabia",
        )
        customer = SimpleNamespace(
            customer_name="Gulf Enterprises LLC",
            custom_customer_name_ar="شركة المشاريع الخليجية",
            tax_id="310122393500003",
            customer_primary_address="ADDR-CUST-1",
        )
        cust_addr = SimpleNamespace(
            address_line1="Prince Sultan Street",
            custom_building_no="5678",
            pincode="23456",
            city="Jeddah",
            custom_district="Al-Rawdah",
            country="Saudi Arabia",
        )
        docs = {
            ("Company", "Al-Noor Trading Est"): company,
            ("Address", "ADDR-COMP-1"): seller_addr,
            ("Customer", "CUST-GULF"): customer,
            ("Address", "ADDR-CUST-1"): cust_addr,
        }
        stored_pfs = {}

        class _SavedDoc:
            def __init__(self, payload):
                for k, v in payload.items():
                    setattr(self, k, v)
                self.doctype = "Print Format"

            def insert(self, ignore_permissions=False):
                if self.name in stored_pfs:
                    raise RuntimeError("Duplicate Print Format")
                stored_pfs[self.name] = self

            def save(self, ignore_permissions=False):
                if self.name not in stored_pfs:
                    raise RuntimeError("Print Format does not exist")
                stored_pfs[self.name] = self

        fm = SimpleNamespace(
            db=SimpleNamespace(
                get_single_value=lambda dt, fn: "Asia/Riyadh" if dt == "System Settings" else None,
                exists=lambda dt, name: name in stored_pfs,
                commit=lambda: None,
            ),
            get_doc=lambda arg1, arg2=None: (
                docs[(arg1, arg2)]
                if arg2 is not None and (arg1, arg2) in docs
                else (stored_pfs[arg2] if arg2 is not None else _SavedDoc(arg1))
            ),
            make_property_setter=lambda cfg: None,
        )
        return fm, stored_pfs

    def test_ksa_sales_invoice_maps_and_renders_with_qr(self):
        fm, _ = self._mock_ksa_frappe_env()
        si = SimpleNamespace(
            name="ACC-SINV-2026-0001",
            company="Al-Noor Trading Est",
            company_address="ADDR-COMP-1",
            customer="CUST-GULF",
            customer_name="Gulf Enterprises LLC",
            customer_address="ADDR-CUST-1",
            posting_date=date(2026, 11, 17),
            posting_time=timedelta(hours=14, minutes=30),
            currency="SAR",
            is_pos=0,
            is_return=0,
            is_debit_note=0,
            net_total=Decimal("200.00"),
            total_taxes_and_charges=Decimal("30.00"),
            grand_total=Decimal("230.00"),
            taxes=[SimpleNamespace(rate=15.0)],
            items=[
                SimpleNamespace(
                    item_code="ITEM-001",
                    item_name="Office Desk Chair",
                    custom_item_name_ar="كرسي مكتب",
                    qty=2,
                    rate=Decimal("100.00"),
                    discount_amount=Decimal("0.00"),
                    net_amount=Decimal("200.00"),
                    item_tax_rate=json.dumps({"VAT 15%": 15.0}),
                )
            ],
        )
        inv_dict, mode = sales_invoice_to_zatca_dict(si, frappe_module=fm)
        self.assertEqual(mode, "zatca_sa")
        self.assertEqual(inv_dict["invoice_type"], "standard")
        rendered = render_frappe_sales_invoice_html(si, frappe_module=fm)
        self.assertIn("فاتورة ضريبية", rendered)
        self.assertIn("data-zatca-tlv=", rendered)

    def test_erpnext_negative_return_invoice_maps_to_zatca_credit_note(self):
        fm, _ = self._mock_ksa_frappe_env()
        si_ret = SimpleNamespace(
            name="ACC-SINV-RET-2026-0001",
            company="Al-Noor Trading Est",
            company_address="ADDR-COMP-1",
            customer="CUST-GULF",
            customer_name="Gulf Enterprises LLC",
            customer_address="ADDR-CUST-1",
            posting_date=date(2026, 11, 17),
            posting_time=timedelta(hours=15, minutes=0),
            currency="SAR",
            is_pos=0,
            is_return=1,
            return_against="ACC-SINV-2026-0001",
            custom_amendment_reason="Returned damaged unit",
            is_debit_note=0,
            net_total=Decimal("-100.00"),
            total_taxes_and_charges=Decimal("-15.00"),
            grand_total=Decimal("-115.00"),
            taxes=[SimpleNamespace(rate=15.0)],
            items=[
                SimpleNamespace(
                    item_code="ITEM-001",
                    item_name="Office Desk Chair",
                    qty=-1,
                    rate=Decimal("100.00"),
                    discount_amount=Decimal("0.00"),
                    net_amount=Decimal("-100.00"),
                )
            ],
        )
        inv_dict, mode = sales_invoice_to_zatca_dict(si_ret, frappe_module=fm)
        self.assertEqual(mode, "zatca_sa")
        self.assertEqual(inv_dict["transaction_type"], "credit_note")
        self.assertEqual(inv_dict["totals"]["grand_total"], "115.00")
        rendered = render_frappe_sales_invoice_html(si_ret, frappe_module=fm)
        self.assertIn("إشعار دائن ضريبي", rendered)
        self.assertIn("ACC-SINV-2026-0001", rendered)
        self.assertIn("Returned damaged unit", rendered)

    def test_qatar_golden_path_sales_invoice_auto_selects_neutral_mode(self):
        company_qa = SimpleNamespace(company_name="Golden Trading Co", country="Qatar")
        fm = SimpleNamespace(
            db=SimpleNamespace(get_single_value=lambda dt, fn: "Asia/Qatar"),
            get_doc=lambda dt, name: company_qa if dt == "Company" else None,
        )
        si_qa = SimpleNamespace(
            name="ACC-SINV-QA-0001",
            company="Golden Trading Co",
            customer="CUST-001",
            customer_name="CUST-001",
            posting_date="2026-11-17",
            posting_time="10:00:00",
            currency="QAR",
            is_return=0,
            is_debit_note=0,
            net_total=Decimal("150.00"),
            total_taxes_and_charges=Decimal("0.00"),
            grand_total=Decimal("150.00"),
            taxes=[],
            items=[
                SimpleNamespace(
                    item_code="ITEM-001",
                    item_name="Trading Item",
                    qty=10,
                    rate=Decimal("15.00"),
                    net_amount=Decimal("150.00"),
                )
            ],
        )
        rendered = render_frappe_sales_invoice_html(si_qa, frappe_module=fm)
        self.assertIn('data-print-mode="neutral"', rendered)
        self.assertIn("150.00 QAR", rendered)

    def test_install_print_format_is_idempotent_and_hooks_registered(self):
        from change_engine import hooks

        self.assertIn(
            "change_engine.print_formats.bilingual_tax_invoice.render_frappe_sales_invoice_html",
            hooks.jinja["methods"],
        )
        fm, stored_pfs = self._mock_ksa_frappe_env()
        res1 = install_bilingual_tax_invoice_print_format(frappe_module=fm)
        self.assertEqual(res1["action"], "created")
        self.assertIn("Bilingual Tax Invoice", stored_pfs)
        res2 = install_bilingual_tax_invoice_print_format(frappe_module=fm)
        self.assertEqual(res2["action"], "updated")
        self.assertEqual(
            stored_pfs["Bilingual Tax Invoice"].html,
            "{{ render_frappe_sales_invoice_html(doc) }}",
        )

    def test_real_pdf_generation_when_backend_present(self):
        try:
            pdf_bytes = render_tax_invoice_pdf(_sample_zatca_standard(), mode="zatca_sa")
        except RuntimeError as exc:
            self.skipTest(f"No PDF backend installed in unit test environment: {exc}")
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 5000)


if __name__ == "__main__":
    unittest.main()
