"""Unit tests for components.core.trading_ar (ERP-006)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from components.core.trading_ar.loader import (
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_TRANSLATABLE_COUNT,
    apply_trading_ar_translations,
    is_excluded_source,
    load_pack,
    load_translations,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PACKAGE_DIR / "manifest.json"
SPEC_PATH = Path(__file__).resolve().parents[4] / "docs" / "specs" / "arabic-translation-gap-trading.md"


class _FakeTranslationDoc:
    def __init__(self, payload, store):
        self._payload = dict(payload)
        self._store = store

    def insert(self, ignore_permissions=False):
        name = f"TR-{len(self._store) + 1:04d}"
        row = dict(self._payload)
        row["name"] = name
        row.setdefault("context", None)
        self._store[name] = row


class _FakeDB:
    def __init__(self, store):
        self._store = store
        self.commits = 0

    def set_value(self, doctype, name, field, value):
        assert doctype == "Translation"
        self._store[name][field] = value

    def commit(self):
        self.commits += 1


class _FakeTranslate:
    def __init__(self):
        self.cleared = 0

    def clear_cache(self):
        self.cleared += 1


class _FakeFrappe:
    def __init__(self):
        self.store = {}
        self.db = _FakeDB(self.store)
        self.translate = _FakeTranslate()

    def get_all(self, doctype, filters=None, fields=None):
        assert doctype == "Translation"
        lang = (filters or {}).get("language")
        return [dict(r) for r in self.store.values() if lang is None or r.get("language") == lang]

    def get_doc(self, payload):
        return _FakeTranslationDoc(payload, self.store)


class TestTradingArabicComponent(unittest.TestCase):
    def test_pack_contains_exact_107_translatable_and_45_excluded(self):
        pack = load_pack()
        self.assertEqual(pack["language"], "ar")
        self.assertEqual(len(pack["entries"]), EXPECTED_TRANSLATABLE_COUNT)
        translations = load_translations()
        self.assertEqual(len(translations), EXPECTED_TRANSLATABLE_COUNT)

        excluded_flat = [
            item
            for vals in pack["excluded"].values()
            if isinstance(vals, list)
            for item in vals
        ]
        self.assertEqual(len(excluded_flat), EXPECTED_EXCLUDED_COUNT)
        for item in excluded_flat:
            self.assertTrue(is_excluded_source(item), f"Expected {item!r} to be excluded")
            self.assertNotIn(item, translations)

    def test_manifest_fields_and_optional_schema_check(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "core.trading_ar")
        self.assertEqual(manifest["kind"], "configurable")
        self.assertEqual(manifest["parameters"], [])
        self.assertEqual(manifest["certification"]["level"], "tested")
        self.assertFalse(manifest["certification"]["touchesLedgerOrTax"])
        self.assertTrue(manifest["i18n"]["rtlVerified"])
        self.assertEqual(manifest["i18n"]["locales"], ["ar", "en"])
        self.assertEqual(manifest["owner"]["github"], "sayegh9")

        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema_path = Path(__file__).resolve().parents[4] / "contracts" / "component.manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(manifest)

    def test_html_links_and_tags_are_preserved_in_translations(self):
        translations = load_translations()
        common_party_src = (
            'Learn about <a href="https://docs.erpnext.com/docs/v13/user/manual/en/accounts/articles/'
            'common_party_accounting#:~:text=Common%20Party%20Accounting%20in%20ERPNext,Invoice%20against%20a%20primary%20Supplier.">Common Party</a>'
        )
        self.assertIn(common_party_src, translations)
        self.assertIn("https://docs.erpnext.com/docs/v13/user/manual/en/accounts/articles/common_party_accounting", translations[common_party_src])
        self.assertIn("<a href=", translations[common_party_src])
        self.assertIn("</a>", translations[common_party_src])

        company_desc = (
            "If <b>Enabled</b> - Reconciliation happens on the <b>Advance Payment posting date</b><br>\n"
            "If <b>Disabled</b> - Reconciliation happens on oldest of 2 Dates: <b>Invoice Date</b> or the <b>Advance Payment posting date</b><br>"
        )
        self.assertIn(company_desc, translations)
        self.assertEqual(translations[company_desc].count("<b>"), company_desc.count("<b>"))
        self.assertEqual(translations[company_desc].count("</b>"), company_desc.count("</b>"))
        self.assertEqual(translations[company_desc].count("<br>"), company_desc.count("<br>"))

    def test_excluded_patterns_detector(self):
        for code in (
            "CUST-.YYYY.-",
            "ACC-SINV-RET-.YYYY.-",
            "PRLE-.####",
            "#,###.##",
            "#.###,##",
            "#'###.##",
            "EAN-8",
            "EAN-12",
            "ISBN-13",
            "UPC-A",
            "FIFO",
            "LIFO",
            "Lft",
            "Rgt",
        ):
            self.assertTrue(is_excluded_source(code), code)
        for text in ("From Opportunity", "Finished Good Quantity", "Changes"):
            self.assertFalse(is_excluded_source(text), text)

    def test_apply_is_idempotent_and_updates_changed_entries(self):
        fake = _FakeFrappe()
        dry = apply_trading_ar_translations(dry_run=True, frappe_module=fake)
        self.assertEqual(dry["created"], EXPECTED_TRANSLATABLE_COUNT)
        self.assertEqual(len(fake.store), 0)

        first = apply_trading_ar_translations(dry_run=False, frappe_module=fake)
        self.assertEqual(first["created"], EXPECTED_TRANSLATABLE_COUNT)
        self.assertEqual(first["updated"], 0)
        self.assertEqual(first["unchanged"], 0)
        self.assertEqual(len(fake.store), EXPECTED_TRANSLATABLE_COUNT)
        self.assertEqual(fake.db.commits, 1)
        self.assertEqual(fake.translate.cleared, 1)

        second = apply_trading_ar_translations(dry_run=False, frappe_module=fake)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(second["unchanged"], EXPECTED_TRANSLATABLE_COUNT)
        self.assertEqual(fake.db.commits, 1)

        # Simulate stale translation edit on one row and confirm update
        any_key = next(iter(fake.store))
        fake.store[any_key]["translated_text"] = "ترجمة قديمة"
        third = apply_trading_ar_translations(dry_run=False, frappe_module=fake)
        self.assertEqual(third["created"], 0)
        self.assertEqual(third["updated"], 1)
        self.assertEqual(third["unchanged"], EXPECTED_TRANSLATABLE_COUNT - 1)
        self.assertEqual(fake.db.commits, 2)
        self.assertEqual(fake.translate.cleared, 2)

    def test_no_arabic_string_contains_forbidden_whitespace_issues(self):
        translations = load_translations()
        for src, tr in translations.items():
            self.assertEqual(src, src.strip())
            self.assertTrue(re.search(r"[\u0600-\u06FF]", tr), f"No Arabic chars in {tr!r}")
            self.assertNotEqual(src, tr)


if __name__ == "__main__":
    unittest.main()
