"""Unit tests for the Egypt country pack (`country.eg` 0.1.0, CMP-028)."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from components.compliance.country_pack import (
    OverrideRejectedError,
    apply_company_overrides,
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)

COUNTRY_PACK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COUNTRY_PACK_DIR.parents[2]
PACKS_DIR = COUNTRY_PACK_DIR / "packs"
EG_PACK_DIR = PACKS_DIR / "eg" / "0.1.0"
MANIFEST_SCHEMA_PATH = REPO_ROOT / "contracts" / "component.manifest.schema.json"


class TestEgyptCountryPack(unittest.TestCase):
    """Validates Egypt country pack loading, schema conformance, locked paths, overrides, and ADR-0031/0033 rules."""

    def setUp(self) -> None:
        self.pack = load_country_pack("EG", PACKS_DIR, version="0.1.0")
        self.manifest = json.loads((EG_PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.strings = json.loads((EG_PACK_DIR / "strings.json").read_text(encoding="utf-8"))

    def test_loads_from_packs_root_without_test_only(self) -> None:
        latest = load_country_pack("eg", PACKS_DIR)
        self.assertEqual(latest["version"], "0.1.0")
        self.assertEqual(self.pack["packId"], "eg")
        self.assertEqual(self.pack["componentId"], "country.eg")
        self.assertEqual(self.pack["countryCode"], "EG")
        self.assertEqual(self.pack["status"], "draft")
        self.assertEqual(self.pack["evidenceStatus"], "unverified")
        self.assertFalse(self.pack["testOnly"])
        self.assertEqual(validate_pack(self.pack), [])

    def test_manifest_validates_against_component_contract(self) -> None:
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.manifest)

        self.assertEqual(self.manifest["id"], self.pack["componentId"])
        self.assertEqual(self.manifest["version"], self.pack["version"])
        self.assertEqual(self.manifest["kind"], "rigid")
        self.assertEqual(self.manifest["parameters"], [])
        self.assertEqual(self.manifest["owner"]["github"], "sayegh9")
        self.assertEqual(self.manifest["certification"]["level"], "tested")
        self.assertTrue(self.manifest["certification"]["touchesLedgerOrTax"])
        self.assertEqual(self.manifest["certification"]["reviewedBy"], [])
        self.assertEqual(self.manifest["i18n"]["locales"], ["ar", "en"])
        self.assertFalse(self.manifest["i18n"]["rtlVerified"])
        self.assertTrue((REPO_ROOT / self.manifest["tests"][0]["path"]).is_file())

    def test_arabic_labels_marked_unreviewed_and_out_of_scope_payroll_disabled(self) -> None:
        self.assertEqual(self.strings["reviewStatus"], "proposed_for_native_speaker_review")
        self.assertEqual(self.strings["labels"]["country.eg.name"]["ar"], self.pack["name"]["ar"])
        self.assertEqual(self.strings["labels"]["country.eg.name"]["ar"], self.manifest["name"]["ar"])
        for entry in self.strings["labels"].values():
            self.assertEqual(entry["reviewStatus"], "unreviewed")

        payroll = self.pack["payrollHooks"]
        self.assertFalse(payroll["wpsEnabled"])
        self.assertIsNone(payroll["wpsFormatRef"])
        self.assertIsNone(payroll["socialInsuranceRef"])
        self.assertIsNone(payroll["eosbRuleRef"])

    def test_egypt_metadata_no_inline_maths_and_dst_zone(self) -> None:
        tax = self.pack["tax"]
        self.assertTrue(tax["vatSupported"])
        self.assertEqual(tax["filingPeriods"], ["monthly"])
        self.assertEqual(tax["roundingRule"], "half_away_from_zero")
        self.assertNotIn("rate", tax)
        self.assertNotIn("rates", tax)

        einv = self.pack["eInvoicing"]
        self.assertTrue(einv["required"])
        self.assertEqual(einv["mode"], "eg_e_invoice")
        self.assertEqual(einv["authority"], "Egyptian Tax Authority (ETA)")
        self.assertEqual(einv["archiveRetentionYears"], 5)

        loc = self.pack["localeDefaults"]
        self.assertEqual(loc["timezone"], "Africa/Cairo")
        self.assertEqual(loc["currency"], "EGP")
        self.assertEqual(self.pack["formats"]["currency"], "EGP")
        self.assertEqual(self.pack["formats"]["currencyDecimals"], 2)
        self.assertEqual(loc["calendar"], {"primary": "gregorian", "secondaryDisplay": "none"})
        self.assertEqual(loc["week"], {"startDay": "sun", "weekendDays": ["fri", "sat"]})
        self.assertEqual(loc["numberSystem"], "western")

        # Egypt DST is handled via IANA tzdata (Africa/Cairo), never a fixed offset.
        cairo = ZoneInfo(loc["timezone"])
        winter_offset = datetime(2026, 1, 15, 12, 0, tzinfo=cairo).utcoffset()
        summer_offset = datetime(2026, 7, 15, 12, 0, tzinfo=cairo).utcoffset()
        self.assertIsNotNone(winter_offset)
        self.assertIsNotNone(summer_offset)
        self.assertNotEqual(winter_offset, summer_offset)

    def test_locked_areas_reject_overrides(self) -> None:
        locked_attempts = [
            {"countryCode": "SA"},
            {"packId": "sa"},
            {"componentId": "country.sa"},
            {"version": "0.2.0"},
            {"coaTemplate": {"artifactRef": "custom"}},
            {"tax": {"vatSupported": False}},
            {"tax": {"filingPeriods": ["quarterly"]}},
            {"eInvoicing": {"required": False}},
            {"eInvoicing": {"mode": "none"}},
            {"formats": {"currencyDecimals": 3}},
            {"payrollHooks": {"wpsEnabled": True}},
            {"payrollHooks": {"socialInsuranceRef": "eg.social_insurance"}},
            {"printFormats": {"mandatoryLanguages": ["en"]}},
            {"holidays": {"calendarRef": {"id": "sa.holidays", "version": "0.1.0"}}},
            {"currency": "USD"},
            {"unknownSetting": "disallowed"},
        ]
        for attempt in locked_attempts:
            with self.subTest(attempt=attempt):
                with self.assertRaises(OverrideRejectedError):
                    resolve_country_pack("EG", PACKS_DIR, company_overrides=attempt, version="0.1.0")

        # Constraint & post-merge invariant checks fail closed.
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.pack, {"fiscalYear": {"type": "hijri"}})
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.pack, {"workingTime": {"workDays": ["sun", "fri"]}})
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.pack, {"timezone": "Invalid/Zone"})

    def test_allowed_company_overrides_validate_and_resolve(self) -> None:
        overrides = {
            "numberSystem": "eastern_arabic",
            "calendar": {"secondaryDisplay": "hijri_umm_al_qura"},
            "week": {"startDay": "mon", "weekendDays": ["sat", "sun"]},
            "workingTime": {
                "workDays": ["mon", "tue", "wed", "thu", "fri"],
                "hours": {"from": "09:30", "to": "17:30"},
                "reducedPeriods": [
                    {
                        "id": "ramadan_hours",
                        "labels": {"ar": "ساعات رمضان", "en": "Ramadan Hours"},
                        "rule": "ramadan",
                        "hours": {"from": "09:30", "to": "15:00"},
                    }
                ],
            },
            "fiscalYear": {"startMonth": 7, "startDay": 1},
            "holidays": {
                "overrides": [
                    {
                        "action": "add",
                        "date": "2026-07-23",
                        "labels": {"ar": "عيد الثورة", "en": "Revolution Day"},
                        "reason": "Egypt national holiday",
                    }
                ]
            },
        }
        resolved = resolve_country_pack("EG", PACKS_DIR, company_overrides=overrides, version="0.1.0")
        self.assertEqual(resolved["status"], "draft")
        self.assertEqual(resolved["evidenceStatus"], "unverified")
        self.assertEqual(resolved["locale"]["numberSystem"], "eastern_arabic")
        self.assertEqual(resolved["locale"]["calendar"]["secondaryDisplay"], "hijri_umm_al_qura")
        self.assertEqual(resolved["locale"]["week"], {"startDay": "mon", "weekendDays": ["sat", "sun"]})
        self.assertEqual(resolved["locale"]["fiscalYear"], {"type": "gregorian", "startMonth": 7, "startDay": 1})
        self.assertEqual(resolved["locale"]["currency"], "EGP")
        self.assertEqual(resolved["locale"]["holidays"]["calendarRef"]["id"], "eg.holidays")
        self.assertEqual(len(resolved["locale"]["holidays"]["overrides"]), 1)
        self.assertEqual(resolved["locked"]["tax"], self.pack["tax"])
        self.assertEqual(resolved["locked"]["eInvoicing"], self.pack["eInvoicing"])
        self.assertEqual(resolved["locked"]["payrollHooks"], self.pack["payrollHooks"])
        self.assertIn("numberSystem", resolved["appliedOverrides"])


if __name__ == "__main__":
    unittest.main()
