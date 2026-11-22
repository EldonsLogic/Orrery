"""Tests for the real KSA and UAE country packs (CMP-029).

The packs live in the real packs root, `components/compliance/country_pack/packs/`.
They hold declarative metadata only. Each version folder also has an `evidence.json`
with a source, access date and evidence label for every statutory fact, because
`pack.schema.json` has no per-fact evidence field and `notes` is capped at 500 characters.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from components.compliance.country_pack import (
    OverrideRejectedError,
    PackNotFoundError,
    PackValidationError,
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)
from components.compliance.country_pack.tests.pack_checks import (
    PACKS_DIR,
    REPO_ROOT,
    blueprint_modes,
    read_json,
    requires_key,
)

SAMPLE_PACKS_DIR = Path(__file__).resolve().parent / "sample_packs"
KSA_DATA_DIR = "apps/engine/compliance/ksa/"

PACKS = {"SA": "0.1.0", "AE": "0.1.0"}
# Locked areas a company override must never reach (paths relative to localeDefaults).
LOCKED_OVERRIDES = [
    {"tax": {"vatSupported": False}},
    {"tax": {"roundingRule": "half_even"}},
    {"eInvoicing": {"required": False}},
    {"coaTemplate": {"artifactRef": "other_chart"}},
    {"formats": {"currencyDecimals": 3}},
    {"payrollHooks": {"wpsEnabled": True}},
    {"printFormats": {"legalLayoutPrecedence": False}},
    {"currency": "USD"},
    {"holidays": {"calendarRef": {"id": "qa.holidays", "version": "0.1.0"}}},
    {"countryCode": "QA"},
]


def _version_dir(code: str) -> Path:
    return PACKS_DIR / code.lower() / PACKS[code]


class TestRealPacksLoad(unittest.TestCase):
    def test_both_packs_load_from_real_root(self) -> None:
        for code, version in PACKS.items():
            with self.subTest(code=code):
                pinned = load_country_pack(code, PACKS_DIR, version=version, environment="test")
                latest = load_country_pack(code, PACKS_DIR, environment="test")
                self.assertEqual(pinned, latest)
                self.assertEqual(validate_pack(pinned), [])
                self.assertEqual(pinned["countryCode"], code)
                self.assertEqual(pinned["componentId"], f"country.{code.lower()}")

    def test_real_packs_are_refused_in_production(self) -> None:
        # CMP-034 go-live gate: `tested` packs with `unverified` evidence never load in production (default environment).
        for code, version in PACKS.items():
            with self.subTest(code=code):
                with self.assertRaises(PackValidationError) as ctx:
                    load_country_pack(code, PACKS_DIR, version=version)
                self.assertIn("cannot be used in production", str(ctx.exception))
                with self.assertRaises(PackValidationError):
                    resolve_country_pack(code, PACKS_DIR, version=version)
                with self.assertRaises(PackValidationError):
                    load_country_pack(code, PACKS_DIR, version=version, environment="production")

    def test_currency_and_zone_per_country(self) -> None:
        expected = {"SA": ("SAR", "Asia/Riyadh"), "AE": ("AED", "Asia/Dubai")}
        for code, (currency, zone) in expected.items():
            with self.subTest(code=code):
                resolved = resolve_country_pack(code, PACKS_DIR, version=PACKS[code], environment="test")
                self.assertEqual(resolved["locale"]["currency"], currency)
                self.assertEqual(resolved["locked"]["formats"]["currency"], currency)
                self.assertEqual(resolved["locale"]["timezone"], zone)
                self.assertEqual(resolved["appliedOverrides"], [])


class TestTestOnlyStillRefused(unittest.TestCase):
    def test_sample_pack_refused_without_flag(self) -> None:
        with self.assertRaises(PackValidationError):
            load_country_pack("SA", SAMPLE_PACKS_DIR, version="0.1.0", environment="test")

    def test_real_pack_marked_test_only_is_refused(self) -> None:
        pack = read_json(_version_dir("SA") / "pack.json")
        pack["testOnly"] = True
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sa" / "0.1.0"
            target.mkdir(parents=True)
            (target / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaises(PackValidationError):
                load_country_pack("SA", Path(tmp), version="0.1.0", environment="test")
            with self.assertRaises(PackNotFoundError):
                load_country_pack("SA", Path(tmp), environment="test")


class TestOverrides(unittest.TestCase):
    def test_locked_areas_reject_overrides(self) -> None:
        for code in PACKS:
            for override in LOCKED_OVERRIDES:
                with self.subTest(code=code, override=override):
                    with self.assertRaises(OverrideRejectedError):
                        resolve_country_pack(
                            code, PACKS_DIR, version=PACKS[code], company_overrides=override, environment="test"
                        )

    def test_unknown_path_rejected(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                with self.assertRaises(OverrideRejectedError):
                    resolve_country_pack(
                        code, PACKS_DIR, version=PACKS[code], company_overrides={"vatRate": 0}, environment="test"
                    )

    def test_ksa_company_overrides_validate(self) -> None:
        pack = load_country_pack("SA", PACKS_DIR, environment="test")
        override = {
            "week": {"startDay": "mon", "weekendDays": ["sat", "sun"]},
            "workingTime": {"workDays": ["mon", "tue", "wed", "thu", "fri"], "hours": {"from": "09:00", "to": "18:00"}},
            "fiscalYear": {"type": "hijri", "startMonth": 1, "startDay": 1},
            "calendar": {"primary": "hijri_umm_al_qura"},
        }
        resolved = resolve_country_pack(
            "SA", PACKS_DIR, version=PACKS["SA"], company_overrides=override, environment="test"
        )
        self.assertEqual(resolved["locale"]["week"]["weekendDays"], ["sat", "sun"])
        self.assertEqual(resolved["locale"]["fiscalYear"]["type"], "hijri")
        self.assertEqual(resolved["locale"]["calendar"]["secondaryDisplay"], "hijri_umm_al_qura")
        self.assertEqual(resolved["locale"]["currency"], "SAR")
        self.assertEqual(resolved["locked"]["tax"], pack["tax"])
        self.assertEqual(resolved["locked"]["coaTemplate"], pack["coaTemplate"])

    def test_uae_company_overrides_validate(self) -> None:
        pack = load_country_pack("AE", PACKS_DIR, environment="test")
        override = {
            "week": {"startDay": "sun", "weekendDays": ["fri", "sat"]},
            "workingTime": {"workDays": ["sun", "mon", "tue", "wed", "thu"]},
            "fiscalYear": {"type": "gregorian", "startMonth": 4, "startDay": 1},
            "holidays": {"overrides": [{"action": "move", "date": "2027-03-20", "movedTo": "2027-03-21"}]},
        }
        resolved = resolve_country_pack(
            "AE", PACKS_DIR, version=PACKS["AE"], company_overrides=override, environment="test"
        )
        self.assertEqual(resolved["locale"]["fiscalYear"]["startMonth"], 4)
        self.assertEqual(resolved["locked"]["eInvoicing"], pack["eInvoicing"])

    def test_overrides_breaking_invariants_rejected(self) -> None:
        with self.assertRaises(OverrideRejectedError):  # workDays overlap the new weekend
            resolve_country_pack(
                "SA", PACKS_DIR, version=PACKS["SA"], company_overrides={"week": {"weekendDays": ["sun"]}},
                environment="test",
            )
        with self.assertRaises(OverrideRejectedError):  # Hijri fiscal year is not allowed in the UAE pack
            resolve_country_pack(
                "AE", PACKS_DIR, version=PACKS["AE"],
                company_overrides={"fiscalYear": {"type": "hijri", "startMonth": 1, "startDay": 1}},
                environment="test",
            )


class TestDeclarativeOnly(unittest.TestCase):
    def test_einvoicing_mode_is_a_blueprint_value(self) -> None:
        modes = blueprint_modes()
        expected = {"SA": "zatca_phase1", "AE": "uae_e_invoicing"}
        for code, mode in expected.items():
            with self.subTest(code=code):
                pack = load_country_pack(code, PACKS_DIR, environment="test")
                self.assertEqual(pack["eInvoicing"]["mode"], mode)
                self.assertIn(mode, modes)

    def test_print_languages_are_the_sourced_minimum(self) -> None:
        for code in PACKS:
            vdir = _version_dir(code)
            pack, evidence = read_json(vdir / "pack.json"), read_json(vdir / "evidence.json")
            facts = [f for f in evidence["facts"] if "printFormats.mandatoryLanguages" in f["paths"]]
            with self.subTest(code=code):
                self.assertEqual(pack["printFormats"]["mandatoryLanguages"], ["ar"])
                self.assertEqual(len(facts), 1)
                if code == "AE":  # no source says any language is mandatory (matrix U7)
                    self.assertEqual(facts[0]["status"], "UNVERIFIED")
                    self.assertIn("U7", facts[0]["ref"])

    def test_payroll_disabled_for_v1(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                hooks = load_country_pack(code, PACKS_DIR, environment="test")["payrollHooks"]
                self.assertEqual(
                    hooks, {"wpsEnabled": False, "wpsFormatRef": None, "socialInsuranceRef": None, "eosbRuleRef": None}
                )

    def test_ksa_references_cmp006_without_copying(self) -> None:
        pack = load_country_pack("SA", PACKS_DIR, environment="test")
        refs = {"coaTemplate.artifactRef": pack["coaTemplate"]["artifactRef"], "tax.taxCodesRef": pack["tax"]["taxCodesRef"]}
        for label, ref in refs.items():
            with self.subTest(ref=label):
                self.assertTrue(ref.startswith(KSA_DATA_DIR), ref)
                target = read_json(REPO_ROOT / ref)
                self.assertEqual(target["version"], "0.1.0")
                self.assertEqual(target["status"], "draft")
        self.assertEqual(pack["coaTemplate"]["versionRange"], ">=0.1.0 <0.2.0")
        text = (_version_dir("SA") / "pack.json").read_text(encoding="utf-8")
        for copied in ("VATEX", "account_number", "root_type", "posting_accounts", "1110"):
            self.assertNotIn(copied, text)

    def test_ksa_print_templates_exist(self) -> None:
        evidence = read_json(_version_dir("SA") / "evidence.json")
        pending = {(p["path"], p["value"]) for p in evidence["pendingRefs"]}
        for idx, tpl in enumerate(load_country_pack("SA", PACKS_DIR, environment="test")["printFormats"]["templates"]):
            with self.subTest(kind=tpl["kind"]):
                path, _, layout = tpl["templateRef"].partition("#")
                self.assertIn(layout, (REPO_ROOT / path).read_text(encoding="utf-8"))
                # compliance.zatca_sa provides no print formats; the layout owner is a pending placeholder
                self.assertNotEqual(tpl["componentId"], "compliance.zatca_sa")
                self.assertIn((f"printFormats.templates[{idx}].componentId", tpl["componentId"]), pending)


class TestManifests(unittest.TestCase):
    def test_requires_core_entries(self) -> None:
        expected = {
            "SA": {
                ("component", "finance.coa_sa_trading"),
                ("component", "finance.vat_sa_treatments"),
                ("component", "compliance.zatca_sa"),
                ("capability", "compliance.zatca_sa.phase2_clearance_reporting"),
            },
            "AE": {
                ("component", "finance.coa_ae_trading"),
                ("component", "finance.vat_ae_treatments"),
                ("component", "compliance.pint_ae"),
            },
        }
        for code, keys in expected.items():
            manifest = read_json(_version_dir(code) / "manifest.json")
            with self.subTest(code=code):
                self.assertLessEqual(keys, {requires_key(r) for r in manifest["requires"]})
        sa = {r.get("component"): r["versionRange"] for r in read_json(_version_dir("SA") / "manifest.json")["requires"]}
        self.assertEqual(sa["compliance.zatca_sa"], ">=0.1.0 <0.2.0")


class TestEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {}
        for code in PACKS:
            vdir = _version_dir(code)
            self.data[code] = (
                read_json(vdir / "pack.json"), read_json(vdir / "manifest.json"), read_json(vdir / "evidence.json")
            )

    def _facts_for(self, code: str, path: str) -> list[dict]:
        return [f for f in self.data[code][2]["facts"] if path in f["paths"]]

    def test_ksa_phase2_and_ledger_blockers(self) -> None:
        blockers = {b["id"]: b for b in self.data["SA"][2]["goLiveBlockers"]}
        phase2 = blockers["zatca_phase2"]
        self.assertEqual(phase2["requires"]["capability"], "compliance.zatca_sa.phase2_clearance_reporting")
        for ref in ("Q-559", "ADR-0042", "K3"):
            self.assertTrue(any(ref in r for r in phase2["refs"]), ref)
        self.assertIn("Q-23", blockers["immutable_ledger"]["refs"])
        self.assertIn("Q-267", blockers["vat_treatments_component"]["refs"])
        self.assertTrue(any("Q-267" in f["claim"] for f in self._facts_for("SA", "tax.taxCodesRef")))

    def test_ksa_component_choice_is_not_labelled_official(self) -> None:
        for path in ("eInvoicing.componentId", "eInvoicing.mode"):
            facts = self._facts_for("SA", path)
            with self.subTest(path=path):
                self.assertEqual(len(facts), 1)
                self.assertEqual(facts[0]["status"], "PLATFORM-DEFAULT")
                self.assertEqual(facts[0]["paths"], [path])

    def test_uae_einvoicing_blocker(self) -> None:
        blockers = {b["id"]: b for b in self.data["AE"][2]["goLiveBlockers"]}
        einv = blockers["uae_e_invoicing"]
        self.assertEqual(einv["requires"], {"component": "compliance.pint_ae", "versionRange": ">=0.1.0 <1.0.0"})
        self.assertEqual(einv["status"], "VERIFIED-OFFICIAL")
        for ref in ("Q-210", "Q-211"):
            self.assertIn(ref, einv["refs"])
        self.assertIn("vat_ae_treatments", json.dumps(blockers["vat_treatments_component"]))

    def test_uae_labels(self) -> None:
        authority = self._facts_for("AE", "eInvoicing.authority")
        self.assertEqual(len(authority), 1)
        self.assertNotEqual(authority[0]["status"], "VERIFIED-OFFICIAL")
        retention = self._facts_for("AE", "eInvoicing.archiveRetentionYears")
        self.assertEqual(retention[0]["status"], "UNVERIFIED")
        self.assertIn("Q-213", retention[0]["claim"])
        language = self._facts_for("AE", "eInvoicing.mandatoryDocumentLanguages")
        self.assertIn("U7", language[0]["ref"])
        self.assertNotIn("U6", language[0]["ref"])
        for code in PACKS:
            with self.subTest(code=code):
                facts = self._facts_for(code, "eInvoicing.archiveRetentionYears")
                self.assertEqual(facts[0]["status"], "UNVERIFIED")

    def test_uae_trade_licence_pattern_is_unsourced(self) -> None:
        _, _, evidence = self.data["AE"]
        facts = [f for f in evidence["facts"] if "tax.crNumberPattern" in f["paths"]]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["status"], "UNVERIFIED")
        self.assertNotIn("ref", facts[0])
        self.assertNotIn("sources", facts[0])

    def test_uae_einvoicing_refs_cite_the_right_items(self) -> None:
        # Review of #257 (Low 3): provider-selection items 1 (DCTCE, MoF page) and 9 (PINT AE) back the mode;
        # items 1 and 3 (FTA as Corner 5, an inference) back the authority.
        mode = self._facts_for("AE", "eInvoicing.mode")
        authority = self._facts_for("AE", "eInvoicing.authority")
        self.assertEqual((len(mode), len(authority)), (1, 1))
        self.assertIn("uae-einvoicing-provider-selection.md section 1, items 1 and 9", mode[0]["ref"])
        self.assertIn("uae-einvoicing-provider-selection.md section 1, items 1 and 3", authority[0]["ref"])
        # Review of #267 (Low): the PINT AE page is item 9 and backs neither item 1 nor item 3.
        urls = [s["url"] for s in authority[0]["sources"]]
        self.assertEqual(urls, ["https://mof.gov.ae/en/about-us/initiatives/einvoicing/"])
        self.assertIn("PINT AE", authority[0]["sourceNote"])


if __name__ == "__main__":
    unittest.main()
