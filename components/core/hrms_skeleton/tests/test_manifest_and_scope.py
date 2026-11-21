"""Manifest contract and the twelve-doctype scope guard (ERP-010)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from components.core.hrms_skeleton import (
    ALLOWED_DOCTYPES,
    KNOWN_OUT_OF_SCOPE_DOCTYPES,
    HrmsError,
    assert_allowed_doctype,
    is_allowed_doctype,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_DIR.parents[2]
SPEC_DOCTYPES = {
    "Employee", "Department", "Designation", "Branch",
    "Leave Type", "Leave Period", "Leave Policy", "Leave Allocation", "Leave Application",
    "Salary Component", "Salary Structure", "Salary Structure Assignment",
}


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_validates_against_contract_schema(self):
        from jsonschema import Draft202012Validator  # CI installs it; a missing validator must fail

        schema = json.loads((REPO_ROOT / "contracts" / "component.manifest.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(self.manifest)

    def test_tier3_certification_awaits_human_review(self):
        cert = self.manifest["certification"]
        self.assertEqual(cert["level"], "tested")
        self.assertEqual(cert["reviewedBy"], [])
        self.assertTrue(cert["touchesLedgerOrTax"])
        self.assertNotIn("certifiedAt", cert)

    def test_identity_owner_and_locales(self):
        self.assertEqual(self.manifest["id"], "core.hrms_skeleton")
        self.assertEqual(self.manifest["owner"]["github"], "sayegh9")
        self.assertEqual(self.manifest["kind"], "rigid")
        self.assertEqual(self.manifest["parameters"], [])
        self.assertEqual(self.manifest["i18n"]["locales"], ["ar", "en"])
        self.assertEqual(self.manifest["i18n"]["stringsFile"], "strings.json")

    def test_entities_are_exactly_the_twelve_and_payroll_is_not_plain(self):
        entities = {
            a["ref"]: a.get("riskClass")
            for p in self.manifest["provides"] for a in p["artifacts"] if a["type"] == "entity"
        }
        self.assertEqual(set(entities), SPEC_DOCTYPES)
        for name in ("Salary Component", "Salary Structure", "Salary Structure Assignment"):
            self.assertEqual(entities[name], "ledger")

    def test_every_referenced_function_and_test_file_exists(self):
        import importlib

        for p in self.manifest["provides"]:
            for a in p["artifacts"]:
                if a["type"] != "function":
                    continue
                parts = a["ref"].split(".")
                for cut in range(len(parts) - 1, 0, -1):
                    try:
                        obj = importlib.import_module(".".join(parts[:cut]))
                    except ImportError:
                        continue
                    for attr in parts[cut:]:
                        obj = getattr(obj, attr)
                    break
                else:
                    self.fail(f"cannot resolve {a['ref']}")
        for t in self.manifest["tests"]:
            self.assertTrue((PACKAGE_DIR / t["path"]).is_file(), t["path"])


class ScopeGuardTests(unittest.TestCase):
    def test_allow_list_is_exactly_the_twelve_doctypes(self):
        self.assertEqual(set(ALLOWED_DOCTYPES), SPEC_DOCTYPES)
        self.assertEqual(len(ALLOWED_DOCTYPES), 12)
        for name in SPEC_DOCTYPES:
            self.assertTrue(is_allowed_doctype(name))
            self.assertEqual(assert_allowed_doctype(name), name)

    def test_named_out_of_scope_doctypes_are_blocked(self):
        for name in ("Salary Slip", "Payroll Entry", "Attendance", "Expense Claim", "Job Opening",
                     "Employee Onboarding", "Appraisal", "Training Event", "Employee Checkin",
                     "Shift Type", "Vehicle Log", "Additional Salary", "Gratuity", "End of Service"):
            self.assertIn(name, KNOWN_OUT_OF_SCOPE_DOCTYPES)
        for name in KNOWN_OUT_OF_SCOPE_DOCTYPES:
            self.assertFalse(is_allowed_doctype(name), name)
            with self.assertRaises(HrmsError) as ctx:
                assert_allowed_doctype(name)
            self.assertEqual(ctx.exception.code, "doctype_not_allowed")

    def test_blocked_list_never_overlaps_the_allow_list(self):
        self.assertFalse(KNOWN_OUT_OF_SCOPE_DOCTYPES & ALLOWED_DOCTYPES)

    def test_unknown_and_malformed_names_fail_closed(self):
        for bad in ("", " ", "Unknown DocType", "employee", "EMPLOYEE", "Employee ", " Employee",
                    "Employee\n", "Employee\x00", "Leave  Type", "Salary Detail", "Leave Policy Detail",
                    "Holiday List", "User", "Company", None, 0, [], ("Employee",), b"Employee",
                    {"Employee"}, "Employеe"):  # last one uses a Cyrillic letter
            self.assertFalse(is_allowed_doctype(bad), repr(bad))
            with self.assertRaises(HrmsError):
                assert_allowed_doctype(bad)


if __name__ == "__main__":
    unittest.main()
