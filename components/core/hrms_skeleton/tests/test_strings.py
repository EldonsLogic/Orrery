"""Arabic and English coverage, the unreviewed-Arabic marker and engine invisibility (ADR-0016, ADR-0033)."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from components.core.hrms_skeleton import ALLOWED_DOCTYPES, ERROR_CODES, HrmsError
from components.core.hrms_skeleton.errors import STRINGS_PATH
from components.core.hrms_skeleton.specs import PLATFORM_CUSTOM_FIELDS

PACKAGE_DIR = Path(__file__).resolve().parents[1]
ARABIC = re.compile(r"[؀-ۿ]")
ENGINE_NAMES = re.compile(r"frappe|erpnext|hrms|ERPGulf", re.IGNORECASE)


def leaf_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from leaf_strings(value)


class StringTests(unittest.TestCase):
    def setUp(self):
        self.strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))

    def test_applicant_account_label_has_english_and_arabic(self):
        labels = self.strings.get("fieldLabels", {}).get("applicant_account", {})
        self.assertEqual(set(labels), {"ar", "en"})
        self.assertRegex(labels["ar"], ARABIC)
        (field,) = PLATFORM_CUSTOM_FIELDS["Leave Application"]
        self.assertEqual(field["label"], labels["en"])

    def test_every_error_code_has_english_and_arabic(self):
        self.assertEqual(set(self.strings["errors"]), set(ERROR_CODES))
        for code, entry in self.strings["errors"].items():
            self.assertEqual(set(entry), {"ar", "en"}, code)
            self.assertTrue(entry["en"].strip() and not ARABIC.search(entry["en"]), code)
            self.assertRegex(entry["ar"], ARABIC, code)

    def test_every_doctype_and_action_label_is_bilingual(self):
        self.assertEqual(set(self.strings["doctypeLabels"]), set(ALLOWED_DOCTYPES))
        for section in ("doctypeLabels", "actionLabels"):
            for key, entry in self.strings[section].items():
                self.assertEqual(set(entry), {"ar", "en"}, key)
                self.assertRegex(entry["ar"], ARABIC, key)
                self.assertNotRegex(entry["en"], ARABIC, key)

    def test_arabic_is_marked_unreviewed(self):
        self.assertEqual(self.strings["reviewStatus"], "proposed_for_native_speaker_review")
        self.assertIn("native speaker", self.strings["note"])

    def test_no_engine_name_in_any_customer_text_or_code(self):
        for text in leaf_strings({k: v for k, v in self.strings.items() if k != "note"}):
            self.assertNotRegex(text, ENGINE_NAMES, text)
        for code in ERROR_CODES:
            self.assertNotRegex(code, ENGINE_NAMES, code)
        manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))
        for text in manifest["name"].values():
            self.assertNotRegex(text, ENGINE_NAMES, text)

    def test_error_messages_render_in_both_languages_and_fall_back_to_english(self):
        error = HrmsError("self_approval_forbidden")
        self.assertEqual(str(error), "self_approval_forbidden")
        self.assertRegex(error.message("ar"), ARABIC)
        self.assertNotRegex(error.message("en"), ARABIC)
        self.assertEqual(error.message("fr"), error.message("en"))

    def test_unknown_error_code_cannot_be_raised(self):
        with self.assertRaises(ValueError):
            HrmsError("made_up_code")

    def test_error_codes_used_in_source_are_all_declared(self):
        used = set()
        for path in PACKAGE_DIR.glob("*.py"):
            used |= set(re.findall(r'HrmsError\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
        used.discard("made_up_code")
        self.assertTrue(used <= set(ERROR_CODES), used - set(ERROR_CODES))
        self.assertEqual(set(ERROR_CODES) - used, set(), "declared but never raised")


if __name__ == "__main__":
    unittest.main()
