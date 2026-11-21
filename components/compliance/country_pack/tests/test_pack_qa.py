"""Tests for the Qatar country pack 0.1.0 (CMP-031). Declarative data only: no tax maths is checked here."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from jsonschema import Draft202012Validator

from components.compliance.country_pack import (
    OverrideRejectedError,
    apply_company_overrides,
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKS_DIR = PACKAGE_DIR / "packs"
QA_DIR = PACKS_DIR / "qa" / "0.1.0"
REPO_ROOT = PACKAGE_DIR.parents[2]
ARABIC_RE = re.compile(r"[؀-ۿ]")


class TestQatarPack(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_country_pack("QA", PACKS_DIR, version="0.1.0")

    def test_loads_through_production_path_and_validates(self) -> None:
        self.assertEqual(validate_pack(self.pack), [])
        self.assertEqual(self.pack["countryCode"], "QA")
        self.assertEqual(self.pack["packId"], "qa")
        self.assertEqual(self.pack["componentId"], "country.qa")
        self.assertIs(self.pack["testOnly"], False)
        # Unpinned load picks the same pack (no test-only version beside it).
        self.assertEqual(load_country_pack("qa", PACKS_DIR)["version"], "0.1.0")

    def test_status_is_tested_and_evidence_unverified(self) -> None:
        # Tested = structure only; the facts stay UNVERIFIED and Arabic text needs sign-off (ADR-0033).
        self.assertEqual(self.pack["status"], "tested")
        self.assertEqual(self.pack["evidenceStatus"], "unverified")
        self.assertIn("UNVERIFIED", self.pack["notes"])
        self.assertLessEqual(len(self.pack["notes"]), 500)

    def test_vat_not_assumed(self) -> None:
        tax = self.pack["tax"]
        self.assertFalse(tax["vatSupported"])
        self.assertIsNone(tax["taxCodesRef"])
        self.assertEqual(tax["filingPeriods"], [])
        # The VAT number pattern accepts nothing, because no VAT number exists.
        for sample in ("", "0", "123456789012345", "QA123456789"):
            self.assertIsNone(re.match(tax["vatNumberPattern"], sample))

    def test_no_e_invoicing_mandate_asserted(self) -> None:
        einv = self.pack["eInvoicing"]
        self.assertFalse(einv["required"])
        self.assertEqual(einv["mode"], "none")
        self.assertIsNone(einv["authority"])
        self.assertIsNone(einv["componentId"])
        self.assertEqual(einv["mandatoryDocumentLanguages"], [])

    def test_payroll_and_wps_out_of_scope(self) -> None:
        hooks = self.pack["payrollHooks"]
        self.assertFalse(hooks["wpsEnabled"])
        for key in ("wpsFormatRef", "socialInsuranceRef", "eosbRuleRef"):
            self.assertIsNone(hooks[key])

    def test_locale_and_formats(self) -> None:
        loc = self.pack["localeDefaults"]
        self.assertEqual(loc["currency"], "QAR")
        self.assertEqual(self.pack["formats"]["currency"], "QAR")
        self.assertEqual(loc["timezone"], "Asia/Qatar")
        self.assertEqual(loc["calendar"]["primary"], "gregorian")
        self.assertIn("fri", loc["week"]["weekendDays"])
        self.assertFalse(set(loc["week"]["weekendDays"]) & set(loc["workingTime"]["workDays"]))
        self.assertEqual(loc["fiscalYear"], {"type": "gregorian", "startMonth": 1, "startDay": 1})
        self.assertEqual(loc["holidays"]["calendarRef"]["id"], "qa.holidays")

    def test_no_numbers_that_look_like_tax_rates_or_maths(self) -> None:
        # Principle 3: declarative metadata only. No rate, percent or formula keys anywhere.
        text = json.dumps(self.pack).lower()
        for banned in ("rate", "percent", "formula", "expression"):
            self.assertNotIn(banned, text)

    def test_arabic_labels_present_and_marked_unreviewed(self) -> None:
        labels = [self.pack["name"]["ar"]]
        for rp in self.pack["localeDefaults"]["workingTime"]["reducedPeriods"]:
            labels.append(rp["labels"]["ar"])
        for label in labels:
            self.assertRegex(label, ARABIC_RE)
        self.assertIn("ADR-0033", self.pack["notes"])
        self.assertIn("unreviewed", self.pack["notes"].lower())
        sources = (QA_DIR / "SOURCES.md").read_text(encoding="utf-8")
        self.assertIn("Arabic text needing native review", sources)

    def test_sources_file_has_urls_and_access_date(self) -> None:
        sources = (QA_DIR / "SOURCES.md").read_text(encoding="utf-8")
        self.assertIn("2026-11-18", sources)
        self.assertIn("https://www.gta.gov.qa/en", sources)
        self.assertIn("UNVERIFIED", sources)

    def test_every_locked_field_with_a_value_has_a_sources_row(self) -> None:
        """Per-field traceability: a SOURCES.md row names the field and has a URL or an explicit no-source note."""
        rows = []
        for line in (QA_DIR / "SOURCES.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("| `"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                rows.append((re.findall(r"`([^`]+)`", cells[0]), line))
        self.assertTrue(rows)

        def leaves(node: object, path: str):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield from leaves(value, f"{path}.{key}" if path else key)
            elif node not in (None, [], ""):
                yield path

        def row_matches(token: str, path: str) -> bool:
            if token.endswith(".*"):
                return path.startswith(token[:-1])
            return path == token or path.startswith(token + ".") or path.endswith("." + token)

        locked = {k: self.pack[k] for k in ("coaTemplate", "tax", "eInvoicing", "formats", "payrollHooks", "printFormats")}
        locked["localeDefaults"] = {
            "currency": self.pack["localeDefaults"]["currency"],
            "holidays": {"calendarRef": self.pack["localeDefaults"]["holidays"]["calendarRef"]},
        }
        checked = 0
        for path in leaves(locked, ""):
            matching = [line for tokens, line in rows if any(row_matches(t, path) for t in tokens)]
            with self.subTest(path=path):
                self.assertTrue(matching, f"no SOURCES.md row for {path}")
                self.assertTrue(
                    any("http" in line or "no source" in line or "Platform default" in line for line in matching),
                    f"row for {path} has neither a URL nor an explicit 'no source' note",
                )
            checked += 1
        self.assertGreater(checked, 20)

    def test_locked_areas_cover_every_non_locale_area(self) -> None:
        locked = set(self.pack["overridesPolicy"]["lockedPaths"])
        for area in ("coaTemplate", "tax", "eInvoicing", "formats", "payrollHooks", "printFormats",
                     "holidays.calendarRef", "currency", "countryCode", "packId", "componentId", "version"):
            self.assertIn(area, locked)

    def test_locked_areas_rejected_as_overrides(self) -> None:
        for override in (
            {"tax": {"vatSupported": True}},
            {"eInvoicing": {"required": True}},
            {"payrollHooks": {"wpsEnabled": True}},
            {"formats": {"currency": "SAR"}},
            {"currency": "SAR"},
            {"holidays": {"calendarRef": {"id": "sa.holidays", "version": "0.1.0"}}},
        ):
            with self.subTest(override=override), self.assertRaises(OverrideRejectedError) as ctx:
                apply_company_overrides(self.pack, override)
            self.assertIn("locked", str(ctx.exception))
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.pack, {"notAPath": 1})

    def test_valid_company_overrides_apply(self) -> None:
        resolved = resolve_country_pack(
            "QA",
            PACKS_DIR,
            company_overrides={
                "week": {"weekendDays": ["fri"]},
                "workingTime": {
                    "workDays": ["sat", "sun", "mon", "tue", "wed", "thu"],
                    "hours": {"from": "07:00", "to": "15:00"},
                },
                "calendar": {"secondaryDisplay": "hijri_umm_al_qura"},
                "fiscalYear": {"type": "gregorian", "startMonth": 7, "startDay": 1},
                "holidays": {"overrides": [
                    {"action": "add", "date": "2026-12-18", "labels": {"ar": "اليوم الوطني", "en": "National Day"}},
                ]},
                "numberSystem": "eastern_arabic",
            },
            version="0.1.0",
        )
        self.assertEqual(resolved["locale"]["week"]["weekendDays"], ["fri"])
        self.assertEqual(resolved["locale"]["fiscalYear"]["startMonth"], 7)
        self.assertEqual(resolved["locale"]["numberSystem"], "eastern_arabic")
        self.assertEqual(resolved["locked"]["tax"], self.pack["tax"])
        self.assertFalse(resolved["locked"]["eInvoicing"]["required"])
        self.assertIn("week.weekendDays", resolved["appliedOverrides"])

    def test_ramadan_reduced_period_override(self) -> None:
        resolved = resolve_country_pack(
            "QA",
            PACKS_DIR,
            company_overrides={
                "workingTime": {
                    "reducedPeriods": [{
                        "id": "ramadan",
                        "labels": {"ar": "ساعات رمضان", "en": "Ramadan hours"},
                        "rule": "ramadan",
                        "hours": {"from": "09:00", "to": "13:00"},
                    }],
                },
            },
            version="0.1.0",
        )
        period = resolved["locale"]["workingTime"]["reducedPeriods"][0]
        self.assertEqual(period["hours"], {"from": "09:00", "to": "13:00"})
        self.assertIn("workingTime.reducedPeriods", resolved["appliedOverrides"])
        # An invalid reduced period (end before start) is refused.
        with self.assertRaises(OverrideRejectedError):
            apply_company_overrides(self.pack, {"workingTime": {"reducedPeriods": [{
                "id": "ramadan",
                "labels": {"ar": "ساعات رمضان", "en": "Ramadan hours"},
                "rule": "ramadan",
                "hours": {"from": "14:00", "to": "08:00"},
            }]}})

    def test_invalid_company_overrides_rejected(self) -> None:
        for override in (
            {"timezone": "Not/AZone"},
            {"week": {"weekendDays": ["fri"]}, "workingTime": {"workDays": ["fri", "sun"]}},
            {"workingTime": {"hours": {"from": "17:00", "to": "08:00"}}},
            {"fiscalYear": {"type": "hijri", "startMonth": 1, "startDay": 1}},
            {"numberSystem": "roman"},
            {"holidays": {"overrides": [{"action": "move", "date": "2026-12-18"}]}},
        ):
            with self.subTest(override=override), self.assertRaises(OverrideRejectedError):
                apply_company_overrides(self.pack, override)

    def test_unresolved_placeholders_are_required_by_manifest(self) -> None:
        manifest = json.loads((QA_DIR / "manifest.json").read_text(encoding="utf-8"))
        required = {r.get("component") for r in manifest["requires"]}
        placeholders = {self.pack["coaTemplate"]["componentId"]} | {
            t["componentId"] for t in self.pack["printFormats"]["templates"]
        }
        self.assertEqual(placeholders, {"finance.coa_qa_unresolved", "sales.invoice_print_qa_unresolved"})
        self.assertTrue(placeholders <= required, "the compiler must refuse the pack until real components exist")

    def test_mandatory_print_languages_are_arabic_only(self) -> None:
        self.assertEqual(self.pack["printFormats"]["mandatoryLanguages"], ["ar"])

    def test_manifest_matches_pack_and_schema(self) -> None:
        manifest = json.loads((QA_DIR / "manifest.json").read_text(encoding="utf-8"))
        schema = json.loads((REPO_ROOT / "contracts" / "component.manifest.schema.json").read_text(encoding="utf-8"))
        errors = [e.message for e in Draft202012Validator(schema).iter_errors(manifest)]
        self.assertEqual(errors, [])
        self.assertEqual(manifest["id"], self.pack["componentId"])
        self.assertEqual(manifest["version"], self.pack["version"])
        self.assertEqual(manifest["certification"]["level"], self.pack["status"])
        # The pack locks tax, CoA and e-invoicing settings, so it touches ledger or tax and cannot be draft.
        self.assertIs(manifest["certification"]["touchesLedgerOrTax"], True)
        self.assertIn(manifest["certification"]["level"], ("draft", "tested"))
        self.assertNotIn(manifest["certification"]["level"], ("reviewed", "certified", "regulated"))
        self.assertEqual(self.pack["evidenceStatus"], "unverified")
        self.assertEqual(manifest["name"], self.pack["name"])
        self.assertTrue((REPO_ROOT / manifest["tests"][0]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
