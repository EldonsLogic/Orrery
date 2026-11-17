"""Unit tests for ERP-006 Arabic translation audit and sync in change_engine."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.engine.change_engine.change_engine.i18n import (
    AREA_DOCTYPES,
    TRADING_IN_SCOPE_DOCTYPES,
    TRADING_IN_SCOPE_REPORTS,
    audit_trading_arabic_coverage,
    check_excluded_site_translations,
    sync_trading_arabic_translations,
)
from components.core.trading_ar.loader import load_translations


class _FakeDB:
    def __init__(self, store):
        self._store = store
        self.commits = 0

    def get_value(self, doctype, name, fields, as_dict=False):
        if doctype == "Language" and name == "ar":
            return {"language_code": "ar", "language_name": "العربية", "enabled": 1}
        return None

    def set_value(self, doctype, name, field, value):
        self._store[name][field] = value

    def commit(self):
        self.commits += 1


class _FakeDoc:
    def __init__(self, payload, store):
        self.payload = dict(payload)
        self._store = store

    def insert(self, ignore_permissions=False):
        idx = len(self._store) + 1
        row = dict(self.payload)
        row["name"] = f"TR-{idx:04d}"
        row.setdefault("context", None)
        self._store[row["name"]] = row


class _FakeTranslate:
    def __init__(self):
        self.cleared = 0

    def clear_cache(self):
        self.cleared += 1

    def get_translations_from_apps(self, lang):
        return {"Customer": "عميل"} if lang == "ar" else {}


class _FakeFrappe:
    def __init__(self, metas, po_strings=None):
        self.metas = metas
        self.store = {}
        self.db = _FakeDB(self.store)
        self.translate = _FakeTranslate()
        self.local = SimpleNamespace(lang="en")
        self.po_strings = po_strings or {}

    def get_meta(self, doctype):
        return self.metas[doctype]

    def get_all(self, doctype, filters=None, fields=None):
        assert doctype == "Translation"
        lang = (filters or {}).get("language")
        return [dict(r) for r in self.store.values() if lang is None or r.get("language") == lang]

    def get_doc(self, payload):
        return _FakeDoc(payload, self.store)


class TestErp006ArabicTranslations(unittest.TestCase):
    def _build_fixture_site(self):
        translations_107 = load_translations()
        metas = {}
        po_map = {}

        for dt in TRADING_IN_SCOPE_DOCTYPES:
            po_map[dt] = f"ترجمة {dt}"
            metas[dt] = SimpleNamespace(fields=[])

        # Plant a couple of the 107 missing strings plus excluded patterns
        metas["Customer"] = SimpleNamespace(
            fields=[
                SimpleNamespace(fieldtype="Data", label="From Opportunity", description=""),
                SimpleNamespace(fieldtype="Select", label="Naming Series", description="", options="CUST-.YYYY.-\n10"),
            ]
        )
        metas["Sales Invoice"] = SimpleNamespace(
            fields=[
                SimpleNamespace(fieldtype="Section Break", label="Changes", description="Issue a debit note with 0 qty against an existing Sales Invoice"),
                SimpleNamespace(fieldtype="Select", label="Naming Series", description="", options="ACC-SINV-.YYYY.-"),
            ]
        )
        metas["Account"] = SimpleNamespace(
            fields=[
                SimpleNamespace(fieldtype="Int", label="Lft", description=""),
                SimpleNamespace(fieldtype="Int", label="Rgt", description=""),
            ]
        )
        metas["Item"] = SimpleNamespace(
            fields=[
                SimpleNamespace(fieldtype="Select", label="Valuation Method", description="", options="FIFO\nLIFO\nMoving Average"),
            ]
        )
        po_map["Naming Series"] = "سلسلة الترقيم"
        po_map["Valuation Method"] = "طريقة التقييم"
        po_map["Moving Average"] = "المتوسط المتحرك"
        for rep in TRADING_IN_SCOPE_REPORTS:
            po_map[rep] = f"تقرير {rep}"

        return _FakeFrappe(metas, po_map), po_map, translations_107

    def test_scope_lists_match_spec_counts(self):
        self.assertEqual(len(TRADING_IN_SCOPE_DOCTYPES), 88)
        self.assertEqual(len(set(TRADING_IN_SCOPE_DOCTYPES)), 88)
        self.assertEqual(sum(len(v) for v in AREA_DOCTYPES.values()), 88)
        self.assertEqual(len(TRADING_IN_SCOPE_REPORTS), 31)

    def test_audit_before_and_after_sync_reaches_100_percent_and_keeps_excluded_out(self):
        fake, po_map, _ = self._build_fixture_site()

        before = audit_trading_arabic_coverage(
            frappe_module=fake,
            include_site_translations=True,
            po_map=po_map,
        )
        self.assertEqual(before["missing_excluded_unique"], 6)
        self.assertEqual(
            before["missing_translatable_strings"],
            [
                "Changes",
                "From Opportunity",
                "Issue a debit note with 0 qty against an existing Sales Invoice",
            ],
        )
        self.assertEqual(before["reports_missing"], [])
        self.assertEqual(before["excluded_site_translations"], [])

        sync_result = sync_trading_arabic_translations(dry_run=False, frappe_module=fake)
        self.assertEqual(sync_result["created"], 107)

        after = audit_trading_arabic_coverage(
            frappe_module=fake,
            include_site_translations=True,
            po_map=po_map,
        )
        self.assertEqual(after["missing_translatable_unique"], 0)
        self.assertEqual(after["translatable_coverage_pct"], 100.0)
        self.assertEqual(after["missing_excluded_unique"], 6)
        self.assertEqual(after["excluded_site_translations"], [])
        self.assertTrue(after["rtl_and_runtime"]["language_enabled"])

    def test_audit_flags_excluded_site_translations_if_injected(self):
        fake, po_map, _ = self._build_fixture_site()
        fake.store["TR-BAD"] = {
            "name": "TR-BAD",
            "language": "ar",
            "source_text": "FIFO",
            "translated_text": "خطأ",
            "context": None,
        }
        violations = check_excluded_site_translations(frappe_module=fake)
        self.assertEqual(violations, ["FIFO"])

        report = audit_trading_arabic_coverage(
            frappe_module=fake,
            include_site_translations=True,
            po_map=po_map,
        )
        self.assertEqual(report["excluded_site_translations"], ["FIFO"])

    def test_bench_style_env_path_resolves_trading_ar(self):
        from apps.engine.change_engine.change_engine.i18n import _ensure_components_on_path

        repo_root = Path(__file__).resolve().parents[5]
        with patch.dict(os.environ, {"PLATFORM_COMPONENTS_ROOT": str(repo_root / "components")}):
            _ensure_components_on_path()
            translations = load_translations()
            self.assertEqual(len(translations), 107)


if __name__ == "__main__":
    unittest.main()
