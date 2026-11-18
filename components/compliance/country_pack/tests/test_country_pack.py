"""Unit tests for the Country Pack framework (CMP-021)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from components.compliance.country_pack import (
    OverrideRejectedError,
    PackNotFoundError,
    PackValidationError,
    UnknownCountryError,
    apply_company_overrides,
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PACKAGE_DIR / "pack.schema.json"
SAMPLE_PACKS_DIR = Path(__file__).resolve().parent / "sample_packs"


class TestCountryPackFramework(unittest.TestCase):
    """Covers valid load, invalid pack rejection, locked overrides, allowed overrides, and unknown country."""

    def setUp(self) -> None:
        self.sample_pack = load_country_pack("SA", SAMPLE_PACKS_DIR, version="0.1.0")

    def test_valid_pack_loads(self) -> None:
        pack = load_country_pack("SA", SAMPLE_PACKS_DIR)
        self.assertTrue(pack["testOnly"])
        self.assertEqual(pack["countryCode"], "SA")
        self.assertEqual(pack["packId"], "sa")
        self.assertEqual(pack["componentId"], "country.sa")
        self.assertEqual(pack["version"], "0.1.0")
        self.assertEqual(validate_pack(pack), [])

        resolved = resolve_country_pack("sa", SAMPLE_PACKS_DIR)
        self.assertEqual(resolved["locale"]["currency"], "SAR")
        self.assertEqual(resolved["locale"]["timezone"], "Asia/Riyadh")
        self.assertEqual(resolved["appliedOverrides"], [])
        self.assertIn("tax", resolved["locked"])
        self.assertIn("coaTemplate", resolved["locked"])

    def test_schema_is_valid_draft_2020_12_if_jsonschema_installed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        Draft202012Validator.check_schema(schema)

    def test_invalid_pack_rejected(self) -> None:
        bad_missing = copy.deepcopy(self.sample_pack)
        del bad_missing["eInvoicing"]
        self.assertTrue(validate_pack(bad_missing))

        bad_extra = copy.deepcopy(self.sample_pack)
        bad_extra["unexpectedTopLevelKey"] = True
        self.assertTrue(validate_pack(bad_extra))

        bad_overlap_policy = copy.deepcopy(self.sample_pack)
        bad_overlap_policy["overridesPolicy"]["overridablePaths"].append("tax.vatSupported")
        errs = validate_pack(bad_overlap_policy)
        self.assertTrue(any("overlaps locked path" in e for e in errs))

        bad_currency = copy.deepcopy(self.sample_pack)
        bad_currency["localeDefaults"]["currency"] = "AED"
        self.assertTrue(validate_pack(bad_currency))

        bad_days = copy.deepcopy(self.sample_pack)
        bad_days["localeDefaults"]["workingTime"]["workDays"].append("fri")
        self.assertTrue(validate_pack(bad_days))

        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "sa" / "0.1.0"
            pdir.mkdir(parents=True)
            (pdir / "pack.json").write_text(json.dumps(bad_missing), encoding="utf-8")
            with self.assertRaises(PackValidationError):
                load_country_pack("SA", Path(tmp), version="0.1.0")

    def test_locked_setting_override_rejected(self) -> None:
        locked_attempts = [
            {"tax": {"vatSupported": False}},
            {"eInvoicing": {"required": False}},
            {"coaTemplate": {"artifactRef": "other"}},
            {"payrollHooks": {"wpsEnabled": True}},
            {"printFormats": {"mandatoryLanguages": ["en"]}},
            {"formats": {"currencyDecimals": 3}},
            {"currency": "USD"},
            {"holidays": {"calendarRef": {"id": "ae.holidays", "version": "0.1.0"}}},
            {"countryCode": "AE"},
        ]
        for attempt in locked_attempts:
            with self.subTest(attempt=attempt):
                with self.assertRaises(OverrideRejectedError):
                    apply_company_overrides(self.sample_pack, attempt)

        # Unknown override path fails closed as well
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.sample_pack, {"unknownSetting": "x"})

        # Locked fiscal year constraint fails closed
        fy_locked_pack = copy.deepcopy(self.sample_pack)
        fy_locked_pack["overridesPolicy"]["constraints"]["fiscalYearLocked"] = True
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(fy_locked_pack, {"fiscalYear": {"startMonth": 4}})

    def test_allowed_override_applied(self) -> None:
        overrides = {
            "timezone": "Asia/Dubai",
            "numberSystem": "eastern_arabic",
            "week": {"startDay": "mon", "weekendDays": ["sat", "sun"]},
            "workingTime": {
                "workDays": ["mon", "tue", "wed", "thu", "fri"],
                "hours": {"from": "09:00", "to": "18:00"},
            },
            "holidays": {
                "overrides": [
                    {
                        "action": "add",
                        "date": "2026-09-23",
                        "labels": {"ar": "إجازة شركة", "en": "Company Day"},
                        "reason": "Annual company day",
                    }
                ]
            },
        }
        resolved = resolve_country_pack("SA", SAMPLE_PACKS_DIR, company_overrides=overrides)
        self.assertEqual(resolved["locale"]["timezone"], "Asia/Dubai")
        self.assertEqual(resolved["locale"]["numberSystem"], "eastern_arabic")
        self.assertEqual(resolved["locale"]["week"]["weekendDays"], ["sat", "sun"])
        self.assertEqual(resolved["locale"]["workingTime"]["hours"], {"from": "09:00", "to": "18:00"})
        self.assertEqual(resolved["locale"]["holidays"]["calendarRef"]["id"], "sa.holidays")
        self.assertEqual(len(resolved["locale"]["holidays"]["overrides"]), 1)
        self.assertIn("numberSystem", resolved["appliedOverrides"])

    def test_invalid_post_merge_override_rejected(self) -> None:
        # Allowed path, but workDays overlaps default weekendDays (fri, sat)
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.sample_pack, {"workingTime": {"workDays": ["sun", "mon", "fri"]}})

        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.sample_pack, {"workingTime": {"hours": {"from": "17:00", "to": "08:00"}}})

        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.sample_pack, {"workingTime": {"reducedPeriods": "not-a-list"}})

        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.sample_pack, {"timezone": "Mars/Olympus"})

        constrained = copy.deepcopy(self.sample_pack)
        constrained["overridesPolicy"]["constraints"]["allowedTimezones"] = ["Asia/Riyadh"]
        constrained["overridesPolicy"]["constraints"]["allowedFiscalYearTypes"] = ["gregorian"]
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(constrained, {"timezone": "Asia/Dubai"})
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(constrained, {"fiscalYear": {"type": "hijri"}})

    def test_highest_semver_selected_when_version_omitted(self) -> None:
        v2 = copy.deepcopy(self.sample_pack)
        v2["version"] = "0.2.0"
        with tempfile.TemporaryDirectory() as tmp:
            for ver, data in (("0.1.0", self.sample_pack), ("0.2.0", v2)):
                d = Path(tmp) / "sa" / ver
                d.mkdir(parents=True)
                (d / "pack.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = load_country_pack("SA", Path(tmp))
            self.assertEqual(loaded["version"], "0.2.0")

    def test_unknown_country_fails_closed(self) -> None:
        for bad_country in ("ZZ", "FR", "AE", "", "SAUDI", "12"):
            with self.subTest(bad_country=bad_country):
                with self.assertRaises(UnknownCountryError):
                    load_country_pack(bad_country, SAMPLE_PACKS_DIR)

        with self.assertRaises(PackNotFoundError):
            load_country_pack("SA", SAMPLE_PACKS_DIR, version="9.9.9")

        with self.assertRaises(PackValidationError):
            resolve_country_pack("SA", SAMPLE_PACKS_DIR, pack_id="ae")


if __name__ == "__main__":
    unittest.main()
