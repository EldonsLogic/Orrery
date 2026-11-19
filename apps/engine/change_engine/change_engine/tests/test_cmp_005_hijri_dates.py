"""CMP-005: strict entry, computed display, companion sync and print regressions."""

from datetime import date, datetime, timedelta
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from change_engine import calendar_dates
from change_engine.i18n import hijri
from change_engine.i18n.hijri_fields import companion_fields, derive_companions, sync_companions
from change_engine.print_formats.bilingual_tax_invoice import (
    render_frappe_sales_invoice_html, render_tax_invoice_html, render_tax_invoice_pdf,
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
        doc.due_date = "1800-01-01"
        doc.custom_posting_date_hijri = "unchanged on failure"
        with self.assertRaises(hijri.HijriDateError):
            sync_companions(doc)
        self.assertEqual(doc.custom_posting_date_hijri, "unchanged on failure")

    def test_unconfigured_and_unrelated_documents_are_untouched(self):
        for doc in (SimpleNamespace(doctype="Sales Invoice", posting_date="1800-01-01",
                                    meta=SimpleNamespace(has_field=lambda field: False)),
                    SimpleNamespace(doctype="User")):
            before = vars(doc).copy()
            sync_companions(doc)
            self.assertEqual(vars(doc), before)


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
        self.assertIn("٢٠٢٤-٠٩-١٨", rendered)
        self.assertIn("١٥ ربيع الأول ١٤٤٦", rendered)
        self.assertIn("١٥ Rabi&#x27; al-Awwal ١٤٤٦", rendered)
        self.assertIn('data-review-status="unreviewed"', rendered)
        self.assertNotIn("spoofed", rendered)
        self.assertNotRegex(rendered.lower(), "frappe|erpnext")
        data["issue_date"] = "1800-01-01"
        with self.assertRaises(hijri.HijriDateError):
            render_tax_invoice_html(data, mode="neutral", compliance_profile={"hijriDisplay": {"enabled": True}})

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
        with patch.dict("sys.modules", {"hijridate": None}), self.assertRaises(hijri.HijriDateError):
            render_tax_invoice_html(data, mode="neutral", compliance_profile={"hijriDisplay": {"enabled": True}})

    def test_engine_entrypoint_uses_canonical_posting_date_on_every_render(self):
        doc = SimpleNamespace(name="SYNTH-005", posting_date=date(2024, 9, 18), currency="QAR",
            company="Synthetic Trading", net_total="10.00", total_taxes_and_charges="0.00",
            grand_total="10.00", items=[SimpleNamespace(item_code="SYNTH", qty=1, rate="10.00")],
            custom_hijri_date="untrusted", custom_posting_date_hijri="stale")
        kwargs = {"mode": "neutral", "compliance_profile": {"hijriDisplay": {"enabled": True}}}
        self.assertIn("15 Rabi&#x27; al-Awwal 1446", render_frappe_sales_invoice_html(doc, **kwargs))
        doc.posting_date = "2024-09-19"
        self.assertIn("16 Rabi&#x27; al-Awwal 1446", render_frappe_sales_invoice_html(doc, **kwargs))
        doc.posting_date = datetime(2024, 9, 18, 23, 30)
        with self.assertRaises(hijri.HijriDateError):
            render_frappe_sales_invoice_html(doc, **kwargs)


if __name__ == "__main__":
    unittest.main()
