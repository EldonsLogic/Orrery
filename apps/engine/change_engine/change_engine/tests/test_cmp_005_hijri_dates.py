"""CMP-005: strict entry, computed display, companion sync and print regressions."""

from datetime import date, datetime, timedelta
from decimal import Decimal
import importlib
import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from change_engine import calendar_dates
from change_engine.i18n import hijri
from change_engine.i18n import hijri_fields
from change_engine.i18n.hijri_fields import companion_fields, derive_companions, sync_companions
from change_engine.print_formats.bilingual_tax_invoice import (
    render_frappe_sales_invoice_html, render_tax_invoice_html, render_tax_invoice_pdf,
    sales_invoice_to_zatca_dict,
)
from change_engine.tests.test_erp_007_bilingual_tax_invoice import (
    TestFrappeSalesInvoiceIntegration, _sample_zatca_standard,
)


def invoice():
    """Synthetic neutral invoice: no accounting computation performed by these tests."""
    return {"invoice_id": "SYNTH-005", "issue_date": "2024-09-18", "currency": "QAR",
            "seller": {"name": "Synthetic Trading"},
            "lines": [{"description": "Synthetic item", "quantity": "1", "unit_price": "10"}],
            "totals": {"total_taxable_amount": "10.00", "total_vat_amount": "0.00",
                       "grand_total": "10.00"}}


class HijriDatesTest(unittest.TestCase):
    def test_literal_pairs_and_round_trips_through_full_table(self):
        for gregorian, expected in (("1924-08-01", "1343-01-01"),
                                    ("2024-09-18", "1446-03-15"),
                                    ("2077-11-16", "1500-12-30")):
            self.assertEqual(hijri.to_hijri(gregorian), expected)
            self.assertEqual(hijri.normalise_date(expected, calendar="hijri_umm_al_qura"), gregorian)
        current, end = date(1924, 8, 1), date(2077, 11, 16)
        while current <= end:
            canonical = current.isoformat()
            self.assertEqual(hijri.normalise_date(hijri.to_hijri(canonical),
                             calendar="hijri_umm_al_qura"), canonical)
            current += timedelta(days=1)

    def test_digit_entry_requires_explicit_calendar(self):
        for value in ("١٤٤٦-٠٣-١٥", "۱۴۴۶-۰۳-۱۵", "1446-03-15"):
            self.assertEqual(hijri.normalise_date(value, calendar="hijri_umm_al_qura"), "2024-09-18")
        self.assertEqual(hijri.normalise_date("٢٠٢٤-٠٩-١٨", calendar="gregorian"), "2024-09-18")
        with self.assertRaises(TypeError):
            hijri.normalise_date("1446-03-15")

    def test_invalid_ambiguous_and_out_of_range_inputs_fail_closed(self):
        for value in ("01/02/1446", "1446-3-15", "1446-13-01", "1446-02-31",
                      "1342-12-30", "1501-01-01", " 1446-03-15", "1446-03-15\n",
                      "\u20671446-03-15\u2069", "１４４６-０３-１５", None, 14460315):
            with self.subTest(value=value), self.assertRaises(hijri.HijriDateError):
                hijri.normalise_date(value, calendar="hijri_umm_al_qura")
        for value in ("1924-07-31", "2077-11-17", "2024-02-30", "٢٠٢٤-٠٩-١٨",
                      datetime(2024, 9, 18), "2024-09-18T12:00:00"):
            with self.subTest(value=value), self.assertRaises(hijri.HijriDateError):
                hijri.to_hijri(value)
        with self.assertRaises(hijri.HijriDateError):
            hijri.normalise_date("1446-03-15", calendar="hijri")

    def test_missing_library_is_a_safe_localised_error_not_an_approximation(self):
        with patch.dict("sys.modules", {"hijridate": None}):
            for convert in (lambda: hijri.to_hijri("2024-09-18"),
                            lambda: hijri.normalise_date("1446-03-15", calendar="hijri_umm_al_qura")):
                with self.assertRaises(hijri.HijriDateError) as raised:
                    convert()
                self.assertEqual(raised.exception.code, "calendar_unavailable")
                self.assertTrue(raised.exception.message("ar"))
                self.assertNotRegex(str(raised.exception).lower(), "frappe|erpnext|hijridate")

    def test_existing_numeric_interface_rejects_coercion(self):
        for parts in ((True, 3, 15), (1446.0, 3, 15), (1446, "3", 15)):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                calendar_dates.hijri_to_gregorian(*parts)

    def test_month_names_digits_bidi_and_review_status(self):
        en = hijri.format_hijri("2024-09-18", language="en", number_system="western")
        ar = hijri.format_hijri("2024-09-18", language="ar", number_system="eastern_arabic")
        self.assertEqual(en.text, "\u206615 Rabi' al-Awwal 1446\u2069")
        self.assertEqual(ar.text, "\u2067١٥ ربيع الأول ١٤٤٦\u2069")
        self.assertEqual(ar.review_status, "unreviewed")
        self.assertEqual(ar.source, "computed")
        self.assertEqual(hijri.format_hijri("2024-09-18", language="ar",
                         number_system="western").text, "\u206715 ربيع الأول 1446\u2069")
        for kwargs in ({"language": "fr"}, {"number_system": "arbitrary"}):
            with self.assertRaises(hijri.HijriDateError):
                hijri.format_hijri("2024-09-18", **kwargs)


class HijriCompanionsTest(unittest.TestCase):
    def setUp(self):
        # Other suites may leave a mock frappe module in sys.modules; pin "no engine" here.
        patcher = patch.object(hijri_fields, "frappe", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_lifecycle_hooks_keep_policy_checks_before_sync(self):
        from change_engine import hooks

        for event in ("validate", "before_submit", "before_update_after_submit"):
            handlers = hooks.doc_events["*"][event]
            self.assertEqual(handlers[0], "change_engine.api.endpoints.enforce_runtime_policies_on_" +
                             {"validate": "validate", "before_submit": "submit",
                              "before_update_after_submit": "update_after_submit"}[event])
            module, name = handlers[1].rsplit(".", 1)
            doc = SimpleNamespace(doctype="Sales Invoice", posting_date="2024-09-18",
                                  meta=SimpleNamespace(has_field=lambda field: field == "custom_posting_date_hijri"))
            getattr(importlib.import_module(module), name)(doc, event)
            self.assertEqual(doc.custom_posting_date_hijri, "1446-03-15")

    def test_definitions_and_derivation_keep_gregorian_authoritative(self):
        fields = companion_fields("Sales Invoice", language="ar")
        self.assertEqual({f["insert_after"] for f in fields}, {"posting_date", "due_date"})
        for field in fields:
            self.assertEqual((field["fieldtype"], field["read_only"], field["no_copy"]), ("Data", 1, 1))
        doc = {"doctype": "Sales Invoice", "posting_date": "2024-09-18", "due_date": None,
               "custom_posting_date_hijri": "spoofed"}
        self.assertEqual(derive_companions(doc), {"custom_posting_date_hijri": "1446-03-15",
                                                "custom_due_date_hijri": ""})
        self.assertEqual(doc["custom_posting_date_hijri"], "spoofed")
        for doctype in ("Purchase Invoice", "Sales Order", "Purchase Order", "Quotation",
                        "Delivery Note", "Purchase Receipt", "Payment Entry", "Stock Entry"):
            self.assertTrue(companion_fields(doctype))

    def test_validate_hook_recomputes_installed_fields_and_clears_empty_sources(self):
        doc = SimpleNamespace(doctype="Sales Invoice", posting_date=date(2024, 9, 18), due_date=None,
                              custom_posting_date_hijri="spoofed", custom_due_date_hijri="stale",
                              meta=SimpleNamespace(has_field=lambda field: True))
        sync_companions(doc)
        self.assertEqual(doc.custom_posting_date_hijri, "1446-03-15")
        self.assertEqual(doc.custom_due_date_hijri, "")
        doc.posting_date = "2024-09-19"
        sync_companions(doc)
        self.assertEqual(doc.custom_posting_date_hijri, "1446-03-16")
        # Malformed text is still rejected atomically: no field is changed on failure.
        doc.due_date = "not-a-date"
        doc.custom_posting_date_hijri = "unchanged on failure"
        with self.assertRaises(hijri.HijriDateError):
            sync_companions(doc)
        self.assertEqual(doc.custom_posting_date_hijri, "unchanged on failure")

    def test_out_of_range_sentinel_dates_do_not_block_document_saves(self):
        for doctype, source in (("Quotation", "valid_till"), ("Purchase Order", "schedule_date"),
                                ("Sales Invoice", "due_date")):
            for sentinel in ("2099-12-31", date(9999, 12, 31), "1900-01-01", "1800-01-01"):
                doc = SimpleNamespace(doctype=doctype, transaction_date="2024-09-18", posting_date="2024-09-18",
                                      meta=SimpleNamespace(has_field=lambda field: True),
                                      **{source: sentinel, f"custom_{source}_hijri": "stale"})
                with self.subTest(doctype=doctype, sentinel=sentinel), \
                        self.assertLogs(hijri_fields.__name__, "WARNING") as logged:
                    sync_companions(doc, "validate")
                self.assertEqual(getattr(doc, f"custom_{source}_hijri"), "")
                self.assertEqual(getattr(doc, source), sentinel)  # Gregorian source untouched
                self.assertNotIn(str(sentinel), " ".join(logged.output))  # no values in logs
                self.assertEqual(derive_companions(doc)[f"custom_{source}_hijri"], "")
        # The in-range companions of the same document are still derived.
        doc = SimpleNamespace(doctype="Quotation", transaction_date="2024-09-18", valid_till="2099-12-31",
                              meta=SimpleNamespace(has_field=lambda field: True))
        with self.assertLogs(hijri_fields.__name__, "WARNING"):
            sync_companions(doc)
        self.assertEqual((doc.custom_transaction_date_hijri, doc.custom_valid_till_hijri), ("1446-03-15", ""))

    def test_hook_failures_become_frappe_validation_errors_when_running_in_the_engine(self):
        class ValidationError(Exception):
            pass

        def throw(message):
            raise ValidationError(message)

        fake = SimpleNamespace(throw=throw, local=SimpleNamespace(lang="ar"))
        doc = SimpleNamespace(doctype="Quotation", transaction_date="2024-09-18", valid_till="31/12/2099",
                              meta=SimpleNamespace(has_field=lambda field: True))
        with patch.object(hijri_fields, "frappe", fake), self.assertRaises(ValidationError) as raised:
            sync_companions(doc)
        self.assertEqual(str(raised.exception), hijri.MESSAGES["invalid_date"]["ar"])
        self.assertFalse(hasattr(doc, "custom_transaction_date_hijri"))
        # Without the engine the stable localisable error remains, never a bare ValueError.
        with self.assertRaises(hijri.HijriDateError):
            sync_companions(doc)

    def test_missing_converter_blocks_installed_companion_sync_with_a_safe_error(self):
        doc = SimpleNamespace(doctype="Sales Invoice", posting_date="2024-09-18",
                              meta=SimpleNamespace(has_field=lambda field: True))
        with patch.dict("sys.modules", {"hijridate": None}), self.assertRaises(hijri.HijriDateError) as raised:
            sync_companions(doc)
        self.assertEqual(raised.exception.code, "calendar_unavailable")

    def test_unconfigured_and_unrelated_documents_are_untouched(self):
        for doc in (SimpleNamespace(doctype="Sales Invoice", posting_date="1800-01-01",
                                    meta=SimpleNamespace(has_field=lambda field: False)),
                    SimpleNamespace(doctype="User")):
            before = vars(doc).copy()
            sync_companions(doc)
            self.assertEqual(vars(doc), before)

    def test_non_trading_doctypes_and_documents_without_companions_are_untouched(self):
        # Even an unconvertible date on an unrelated DocType or without installed fields is ignored.
        for doctype in ("User", "ToDo", "Item", "Journal Entry", "Employee"):
            self.assertNotIn(doctype, hijri_fields.TRADING_DATES)
            doc = SimpleNamespace(doctype=doctype, posting_date="not-a-date", due_date="2099-12-31",
                                  meta=SimpleNamespace(has_field=lambda field: True))
            before = vars(doc).copy()
            sync_companions(doc, "validate")
            self.assertEqual(vars(doc), before)
            self.assertEqual(derive_companions(doc), {})
        doc = {"doctype": "Sales Invoice", "posting_date": "not-a-date"}  # no meta: nothing installed
        sync_companions(doc)
        self.assertEqual(doc, {"doctype": "Sales Invoice", "posting_date": "not-a-date"})
        partial = SimpleNamespace(doctype="Sales Invoice", posting_date="2024-09-18", due_date="2024-10-18",
                                  meta=SimpleNamespace(has_field=lambda field: field == "custom_due_date_hijri"))
        sync_companions(partial)
        self.assertFalse(hasattr(partial, "custom_posting_date_hijri"))
        self.assertEqual(partial.custom_due_date_hijri, "1446-04-15")


class HijriPrintTest(unittest.TestCase):
    def test_pdf_backend_receives_configured_dual_date_html(self):
        captured = []

        # Replace only the external PDF backend; exercise the real HTML renderer.
        def pdf_backend(*, string):
            captured.append(string)
            return SimpleNamespace(write_pdf=lambda: b"%PDF-synthetic")

        with patch.dict("sys.modules", {"weasyprint": SimpleNamespace(HTML=pdf_backend)}):
            render_tax_invoice_pdf(invoice(), mode="neutral", backend="weasyprint",
                compliance_profile={"hijriDisplay": {"enabled": True}})
        self.assertEqual(len(captured), 1)
        self.assertIn("15 Rabi&#x27; al-Awwal 1446", captured[0])
        self.assertIn("2024-09-18", captured[0])

    def test_dual_date_print_derives_from_issue_date_and_ignores_cached_hijri(self):
        data = invoice()
        data["hijri_date"] = "<script>spoofed</script>"
        rendered = render_tax_invoice_html(data, mode="neutral",
            locale={"calendar": {"secondaryDisplay": "hijri_umm_al_qura"},
                    "numberSystem": "eastern_arabic"})
        # The legal Gregorian issue date keeps Western digits; only the Hijri line is localised.
        self.assertIn("2024-09-18", rendered)
        self.assertNotIn("٢٠٢٤-٠٩-١٨", rendered)
        self.assertIn("١٤٤٦-٠٣-١٥", rendered)
        self.assertIn("١٥ ربيع الأول ١٤٤٦", rendered)
        self.assertIn("١٥ Rabi&#x27; al-Awwal ١٤٤٦", rendered)
        self.assertIn('data-review-status="unreviewed"', rendered)
        self.assertNotIn("spoofed", rendered)
        self.assertNotRegex(rendered.lower(), "frappe|erpnext")
        # The mandatory Gregorian date still fails closed when malformed.
        for bad in ("2024-02-30", "2024-9-18"):
            data["issue_date"] = bad
            with self.subTest(issue_date=bad), self.assertRaises(ValueError):
                render_tax_invoice_html(data, mode="neutral", compliance_profile={"hijriDisplay": {"enabled": True}})

    def test_legal_zatca_invoice_renders_without_hijri_when_conversion_fails(self):
        def zatca(issue_date):
            data = _sample_zatca_standard()
            data["issue_date"] = issue_date
            data["hijri_date"] = "<script>spoofed</script>"
            return data

        baseline = render_tax_invoice_html(zatca("2026-11-17"), mode="zatca_sa")
        self.assertIn("Jumada", baseline)  # Saudi mode shows Hijri by default
        qr = lambda html: re.search(r'data-zatca-tlv="[^"]+"', html).group(0)
        cases = {
            "library missing": (zatca("2026-11-17"), {"sys.modules": {"hijridate": None}}),
            "date after table end": (zatca("2077-11-17"), {}),
            "date before table start": (zatca("1924-07-31"), {}),
        }
        for name, (data, patches) in cases.items():
            with self.subTest(name), patch.dict("sys.modules", patches.get("sys.modules", {})), \
                    self.assertLogs("change_engine.print_formats.bilingual_tax_invoice", "WARNING") as logged:
                rendered = render_tax_invoice_html(data, mode="zatca_sa")
            self.assertIn(data["issue_date"], rendered)  # mandatory Gregorian date
            self.assertIn("data-zatca-tlv=", rendered)  # QR
            self.assertNotIn("Jumada", rendered)
            self.assertNotIn("جمادى", rendered)
            self.assertNotIn("data-calendar-source", rendered)
            self.assertNotIn("spoofed", rendered)
            self.assertNotRegex(" ".join(logged.output).lower(), "frappe|erpnext|2077|1924")
        # Same totals and QR as the version with Hijri when only the Hijri row is lost.
        with patch.dict("sys.modules", {"hijridate": None}), self.assertLogs(level="WARNING"):
            degraded = render_tax_invoice_html(zatca("2026-11-17"), mode="zatca_sa")
        self.assertEqual(qr(degraded), qr(baseline))
        self.assertIn("2026-11-17", degraded)

    def test_hijri_failure_in_neutral_mode_and_pdf_keeps_rendering(self):
        profile = {"hijriDisplay": {"enabled": True}}
        with patch.dict("sys.modules", {"hijridate": None}), self.assertLogs(level="WARNING"):
            rendered = render_tax_invoice_html(invoice(), mode="neutral", compliance_profile=profile)
        self.assertIn("2024-09-18", rendered)
        self.assertNotIn("Rabi", rendered)
        data = invoice()
        data["issue_date"] = "2099-12-31"
        with self.assertLogs(level="WARNING"):
            self.assertIn("2099-12-31", render_tax_invoice_html(data, mode="neutral", compliance_profile=profile))
        with self.assertLogs(level="WARNING"), patch.dict("sys.modules", {"weasyprint": SimpleNamespace(
                HTML=lambda *, string: SimpleNamespace(write_pdf=lambda: b"%PDF-synthetic"))}):
            self.assertEqual(render_tax_invoice_pdf(data, mode="neutral", backend="weasyprint",
                             compliance_profile=profile), b"%PDF-synthetic")

    def test_display_switches_and_required_profile_precedence(self):
        data = invoice()
        self.assertNotIn("Rabi", render_tax_invoice_html(data, mode="neutral"))
        self.assertIn("Rabi", render_tax_invoice_html(data, mode="neutral",
            locale={"calendar": {"secondaryDisplay": "none"}},
            compliance_profile={"hijriDisplay": {"enabled": True}}))
        with self.assertRaises(hijri.HijriDateError):
            render_tax_invoice_html(data, mode="neutral", compliance_profile={"hijriDisplay": {"enabled": "false"}})
        for locale in ([], {"calendar": None}, {"numberSystem": "unknown"},
                       {"calendar": {"secondaryDisplay": "hijri"}}):
            with self.subTest(locale=locale), self.assertRaises(hijri.HijriDateError):
                render_tax_invoice_html(data, mode="neutral", locale=locale)

    def test_explicit_profile_disable_overrides_locale_and_country_default(self):
        data = invoice()
        for locale in ({"calendar": {"secondaryDisplay": "hijri_umm_al_qura"}},
                       {"calendar": {"primary": "hijri_umm_al_qura"}}):
            with self.subTest(locale=locale):
                self.assertTrue(hijri.display_enabled(locale, {}, country_default=False))
                self.assertFalse(hijri.display_enabled(locale, {"hijriDisplay": {"enabled": False}},
                                                       country_default=True))
                self.assertTrue(hijri.display_enabled(locale, {"hijriDisplay": {"enabled": True}},
                                                      country_default=False))
                rendered = render_tax_invoice_html(data, mode="neutral", locale=locale,
                                                   compliance_profile={"hijriDisplay": {"enabled": False}})
                self.assertNotIn("Rabi", rendered)
                self.assertIn("2024-09-18", rendered)
        saudi = render_tax_invoice_html(_sample_zatca_standard(), mode="zatca_sa",
                                        compliance_profile={"hijriDisplay": {"enabled": False}})
        self.assertNotIn("Jumada", saudi)
        self.assertIn("Jumada", render_tax_invoice_html(_sample_zatca_standard(), mode="zatca_sa"))

    def test_explicit_settings_errors_still_fail_closed_with_a_missing_library(self):
        with patch.dict("sys.modules", {"hijridate": None}):
            for kwargs in ({"locale": {"numberSystem": "unknown"}},
                           {"locale": {"calendar": {"secondaryDisplay": "hijri"}}},
                           {"compliance_profile": {"hijriDisplay": {"enabled": "yes"}}}):
                with self.subTest(kwargs=kwargs), self.assertRaises(hijri.HijriDateError) as raised:
                    render_tax_invoice_html(invoice(), mode="neutral", **kwargs)
                self.assertEqual(raised.exception.code, "invalid_locale")

    def test_engine_entrypoint_uses_canonical_posting_date_on_every_render(self):
        doc = SimpleNamespace(name="SYNTH-005", posting_date=date(2024, 9, 18), currency="QAR",
            company="Synthetic Trading", net_total="10.00", total_taxes_and_charges="0.00",
            grand_total="10.00", items=[SimpleNamespace(item_code="SYNTH", qty=1, rate="10.00")],
            custom_hijri_date="untrusted", custom_posting_date_hijri="stale")
        kwargs = {"mode": "neutral", "compliance_profile": {"hijriDisplay": {"enabled": True}}}
        self.assertIn("15 Rabi&#x27; al-Awwal 1446", render_frappe_sales_invoice_html(doc, **kwargs))
        doc.posting_date = "2024-09-19"
        self.assertIn("16 Rabi&#x27; al-Awwal 1446", render_frappe_sales_invoice_html(doc, **kwargs))
        # Frappe Date fields load as date and REST payloads as ISO strings; both are accepted.
        # A timestamp is rejected on purpose: truncating it can move the legal day across time zones.
        for timestamp in (datetime(2024, 9, 18, 23, 30), "2024-09-18T23:30:00", "2024-09-18 23:30:00"):
            doc.posting_date = timestamp
            with self.subTest(posting_date=timestamp):
                with self.assertRaises(hijri.HijriDateError):
                    sales_invoice_to_zatca_dict(doc, mode="neutral")
                with self.assertRaises(hijri.HijriDateError):
                    render_frappe_sales_invoice_html(doc, **kwargs)

    def test_saudi_sales_invoice_posting_date_forms_through_frappe_entrypoint(self):
        fm, _ = TestFrappeSalesInvoiceIntegration()._mock_ksa_frappe_env()

        def sales_invoice(posting_date):
            return SimpleNamespace(
                name="ACC-SINV-2026-0001", company="Al-Noor Trading Est", company_address="ADDR-COMP-1",
                customer="CUST-GULF", customer_name="Gulf Enterprises LLC", customer_address="ADDR-CUST-1",
                posting_date=posting_date, posting_time=timedelta(hours=14, minutes=30), currency="SAR",
                is_pos=0, is_return=0, is_debit_note=0, net_total=Decimal("200.00"),
                total_taxes_and_charges=Decimal("30.00"), grand_total=Decimal("230.00"),
                taxes=[SimpleNamespace(rate=15.0)],
                items=[SimpleNamespace(item_code="ITEM-001", item_name="Office Desk Chair", qty=2,
                                       rate=Decimal("100.00"), discount_amount=Decimal("0.00"),
                                       net_amount=Decimal("200.00"),
                                       item_tax_rate=json.dumps({"VAT 15%": 15.0}))])

        for posting_date in (date(2026, 11, 17), "2026-11-17"):
            with self.subTest(posting_date=posting_date):
                invoice_dict, _ = sales_invoice_to_zatca_dict(sales_invoice(posting_date), frappe_module=fm)
                self.assertEqual(invoice_dict["issue_date"], "2026-11-17")
                rendered = render_frappe_sales_invoice_html(sales_invoice(posting_date), frappe_module=fm)
                self.assertIn("2026-11-17", rendered)
                self.assertIn("data-zatca-tlv=", rendered)
                self.assertIn("Jumada", rendered)
        # Timestamps never reach the legal invoice: the whole render fails closed.
        for timestamp in (datetime(2026, 11, 17, 23, 30), "2026-11-17T23:30:00"):
            with self.subTest(posting_date=timestamp), self.assertRaises(hijri.HijriDateError):
                render_frappe_sales_invoice_html(sales_invoice(timestamp), frappe_module=fm)
        # A date past the Hijri table still produces the legal invoice, without the Hijri line.
        with self.assertLogs(level="WARNING"):
            rendered = render_frappe_sales_invoice_html(sales_invoice("2080-01-01"), frappe_module=fm)
        self.assertIn("2080-01-01", rendered)
        self.assertNotIn("Jumada", rendered)


if __name__ == "__main__":
    unittest.main()
