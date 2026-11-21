"""Tests for the real KSA and UAE country packs (CMP-029).

The packs live in the real packs root, `components/compliance/country_pack/packs/`.
They hold declarative metadata only. Each version folder also has an `evidence.json`
with a source, access date and evidence label for every statutory fact, because
`pack.schema.json` has no per-fact evidence field and `notes` is capped at 500 characters.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from components.compliance.country_pack import (
    OverrideRejectedError,
    PackNotFoundError,
    PackValidationError,
    apply_company_overrides,
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKS_DIR = PACKAGE_DIR / "packs"
SAMPLE_PACKS_DIR = Path(__file__).resolve().parent / "sample_packs"
REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_SCHEMA = REPO_ROOT / "contracts" / "component.manifest.schema.json"
KSA_DATA_DIR = "apps/engine/compliance/ksa/"

PACKS = {"SA": "0.1.0", "AE": "0.1.0"}
EVIDENCE_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY", "UNVERIFIED", "PLATFORM-DEFAULT"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Areas whose every leaf must be backed by an evidence entry.
EVIDENCED_AREAS = ("coaTemplate", "tax", "eInvoicing", "localeDefaults", "formats", "payrollHooks", "printFormats")
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
# Keys that would mean a pack carries tax, ledger or invoice maths (principle 3, ADR-0031).
MATHS_KEY = re.compile(r"rate|percent|amount|formula|expression|calc|threshold|account_number|(?<![a-z])ratio", re.I)
# The only numeric leaves a pack may hold: counts and calendar positions, never money or rates.
NUMERIC_LEAVES = {
    "formats.currencyDecimals",
    "eInvoicing.archiveRetentionYears",
    "localeDefaults.fiscalYear.startMonth",
    "localeDefaults.fiscalYear.startDay",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _version_dir(code: str) -> Path:
    return PACKS_DIR / code.lower() / PACKS[code]


def _leaves(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _leaves(val, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, obj


def _keys(obj):
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield key
            yield from _keys(val)
    elif isinstance(obj, list):
        for item in obj:
            yield from _keys(item)


def _covered(leaf: str, paths: list[str]) -> bool:
    return any(leaf == p or leaf.startswith(f"{p}.") for p in paths)


def _get(obj: dict, dotted: str):
    """Resolve a dotted path; `name[0]` indexes a list."""
    for part in dotted.split("."):
        key, _, idx = part.partition("[")
        obj = obj[key]
        if idx:
            obj = obj[int(idx.rstrip("]"))]
    return obj


def _arabic_strings(obj, prefix: str = ""):
    """Yield (path, text) for every `ar` label, including those inside lists."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key == "ar" and isinstance(val, str):
                yield path, val
            else:
                yield from _arabic_strings(val, path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from _arabic_strings(item, f"{prefix}[{idx}]")


class TestRealPacksLoad(unittest.TestCase):
    def test_both_packs_load_from_real_root(self) -> None:
        for code, version in PACKS.items():
            with self.subTest(code=code):
                pinned = load_country_pack(code, PACKS_DIR, version=version)
                latest = load_country_pack(code, PACKS_DIR)
                self.assertEqual(pinned, latest)
                self.assertEqual(validate_pack(pinned), [])
                self.assertEqual(pinned["countryCode"], code)
                self.assertEqual(pinned["componentId"], f"country.{code.lower()}")

    def test_status_is_draft_and_unverified_and_not_test_only(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                pack = load_country_pack(code, PACKS_DIR)
                self.assertEqual(pack["status"], "draft")
                self.assertEqual(pack["evidenceStatus"], "unverified")
                self.assertIs(pack["testOnly"], False)
                self.assertIn("evidence.json", pack["notes"])

    def test_real_root_holds_no_test_only_pack(self) -> None:
        for pack_file in PACKS_DIR.glob("*/*/pack.json"):
            with self.subTest(pack=str(pack_file.relative_to(PACKS_DIR))):
                self.assertIs(_read_json(pack_file).get("testOnly"), False)

    def test_currency_and_zone_per_country(self) -> None:
        expected = {"SA": ("SAR", "Asia/Riyadh"), "AE": ("AED", "Asia/Dubai")}
        for code, (currency, zone) in expected.items():
            with self.subTest(code=code):
                resolved = resolve_country_pack(code, PACKS_DIR, version=PACKS[code])
                self.assertEqual(resolved["locale"]["currency"], currency)
                self.assertEqual(resolved["locked"]["formats"]["currency"], currency)
                self.assertEqual(resolved["locale"]["timezone"], zone)
                self.assertEqual(resolved["appliedOverrides"], [])


class TestTestOnlyStillRefused(unittest.TestCase):
    def test_sample_pack_refused_without_flag(self) -> None:
        with self.assertRaises(PackValidationError):
            load_country_pack("SA", SAMPLE_PACKS_DIR, version="0.1.0")

    def test_real_pack_marked_test_only_is_refused(self) -> None:
        pack = _read_json(_version_dir("SA") / "pack.json")
        pack["testOnly"] = True
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sa" / "0.1.0"
            target.mkdir(parents=True)
            (target / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaises(PackValidationError):
                load_country_pack("SA", Path(tmp), version="0.1.0")
            with self.assertRaises(PackNotFoundError):
                load_country_pack("SA", Path(tmp))


class TestOverrides(unittest.TestCase):
    def test_locked_areas_reject_overrides(self) -> None:
        for code in PACKS:
            pack = load_country_pack(code, PACKS_DIR)
            for override in LOCKED_OVERRIDES:
                with self.subTest(code=code, override=override):
                    with self.assertRaises(OverrideRejectedError):
                        apply_company_overrides(pack, override)

    def test_unknown_path_rejected(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                with self.assertRaises(OverrideRejectedError):
                    apply_company_overrides(load_country_pack(code, PACKS_DIR), {"vatRate": 0})

    def test_ksa_company_overrides_validate(self) -> None:
        pack = load_country_pack("SA", PACKS_DIR)
        override = {
            "week": {"startDay": "mon", "weekendDays": ["sat", "sun"]},
            "workingTime": {"workDays": ["mon", "tue", "wed", "thu", "fri"], "hours": {"from": "09:00", "to": "18:00"}},
            "fiscalYear": {"type": "hijri", "startMonth": 1, "startDay": 1},
            "calendar": {"primary": "hijri_umm_al_qura"},
        }
        resolved = apply_company_overrides(pack, override)
        self.assertEqual(resolved["locale"]["week"]["weekendDays"], ["sat", "sun"])
        self.assertEqual(resolved["locale"]["fiscalYear"]["type"], "hijri")
        self.assertEqual(resolved["locale"]["calendar"]["secondaryDisplay"], "hijri_umm_al_qura")
        self.assertEqual(resolved["locale"]["currency"], "SAR")
        self.assertEqual(resolved["locked"]["tax"], pack["tax"])
        self.assertEqual(resolved["locked"]["coaTemplate"], pack["coaTemplate"])

    def test_uae_company_overrides_validate(self) -> None:
        pack = load_country_pack("AE", PACKS_DIR)
        override = {
            "week": {"startDay": "sun", "weekendDays": ["fri", "sat"]},
            "workingTime": {"workDays": ["sun", "mon", "tue", "wed", "thu"]},
            "fiscalYear": {"type": "gregorian", "startMonth": 4, "startDay": 1},
            "holidays": {"overrides": [{"action": "move", "date": "2027-03-20", "movedTo": "2027-03-21"}]},
        }
        resolved = apply_company_overrides(pack, override)
        self.assertEqual(resolved["locale"]["fiscalYear"]["startMonth"], 4)
        self.assertEqual(resolved["locked"]["eInvoicing"], pack["eInvoicing"])

    def test_overrides_breaking_invariants_rejected(self) -> None:
        sa = load_country_pack("SA", PACKS_DIR)
        with self.assertRaises(OverrideRejectedError):  # workDays overlap the new weekend
            apply_company_overrides(sa, {"week": {"weekendDays": ["sun"]}})
        ae = load_country_pack("AE", PACKS_DIR)
        with self.assertRaises(OverrideRejectedError):  # Hijri fiscal year is not allowed in the UAE pack
            apply_company_overrides(ae, {"fiscalYear": {"type": "hijri", "startMonth": 1, "startDay": 1}})


class TestDeclarativeOnly(unittest.TestCase):
    def test_no_maths_or_rates_in_packs(self) -> None:
        for code in PACKS:
            pack = _read_json(_version_dir(code) / "pack.json")
            with self.subTest(code=code):
                self.assertEqual([k for k in _keys(pack) if MATHS_KEY.search(k)], [])
                for path, val in _leaves(pack):
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        self.assertIn(path, NUMERIC_LEAVES)

    def test_payroll_disabled_for_v1(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                hooks = load_country_pack(code, PACKS_DIR)["payrollHooks"]
                self.assertEqual(
                    hooks, {"wpsEnabled": False, "wpsFormatRef": None, "socialInsuranceRef": None, "eosbRuleRef": None}
                )

    def test_ksa_references_cmp006_without_copying(self) -> None:
        pack = load_country_pack("SA", PACKS_DIR)
        refs = {"coaTemplate.artifactRef": pack["coaTemplate"]["artifactRef"], "tax.taxCodesRef": pack["tax"]["taxCodesRef"]}
        for label, ref in refs.items():
            with self.subTest(ref=label):
                self.assertTrue(ref.startswith(KSA_DATA_DIR), ref)
                target = _read_json(REPO_ROOT / ref)
                self.assertEqual(target["version"], "0.1.0")
                self.assertEqual(target["status"], "draft")
        self.assertEqual(pack["coaTemplate"]["versionRange"], ">=0.1.0 <0.2.0")
        text = (_version_dir("SA") / "pack.json").read_text(encoding="utf-8")
        for copied in ("VATEX", "account_number", "root_type", "posting_accounts", "1110"):
            self.assertNotIn(copied, text)

    def test_ksa_print_templates_exist(self) -> None:
        for tpl in load_country_pack("SA", PACKS_DIR)["printFormats"]["templates"]:
            with self.subTest(kind=tpl["kind"]):
                path, _, layout = tpl["templateRef"].partition("#")
                self.assertIn(layout, (REPO_ROOT / path).read_text(encoding="utf-8"))


class TestManifests(unittest.TestCase):
    def test_manifest_valid_and_matches_pack(self) -> None:
        validator = Draft202012Validator(_read_json(MANIFEST_SCHEMA), format_checker=FormatChecker())
        for code in PACKS:
            vdir = _version_dir(code)
            manifest, pack = _read_json(vdir / "manifest.json"), _read_json(vdir / "pack.json")
            with self.subTest(code=code):
                self.assertEqual([e.message for e in validator.iter_errors(manifest)], [])
                self.assertEqual(manifest["id"], pack["componentId"])
                self.assertEqual(manifest["version"], pack["version"])
                self.assertEqual(manifest["kind"], "rigid")
                self.assertEqual(manifest["parameters"], [])
                self.assertEqual(manifest["certification"]["reviewedBy"], [])
                for test in manifest["tests"]:
                    self.assertTrue((vdir / test["path"]).resolve().is_file(), test["path"])


class TestEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {}
        for code in PACKS:
            vdir = _version_dir(code)
            self.data[code] = (
                _read_json(vdir / "pack.json"), _read_json(vdir / "manifest.json"), _read_json(vdir / "evidence.json")
            )

    def test_every_fact_has_a_label_and_sources(self) -> None:
        today = date.today().isoformat()
        for code, (pack, _, evidence) in self.data.items():
            self.assertEqual((evidence["packId"], evidence["version"]), (pack["packId"], pack["version"]))
            for idx, fact in enumerate(evidence["facts"]):
                with self.subTest(code=code, fact=idx):
                    self.assertIn(fact["status"], EVIDENCE_LABELS)
                    self.assertTrue(fact["claim"])
                    for path in fact["paths"]:
                        _get(pack, path)  # every cited path exists in the pack
                    for src in fact.get("sources", []):
                        self.assertTrue(src["url"].startswith("https://"), src["url"])
                        self.assertRegex(src["accessed"], ISO_DATE)
                        self.assertLessEqual(src["accessed"], today)
                    if fact["status"] in {"VERIFIED-OFFICIAL", "SECONDARY"}:
                        self.assertTrue(fact.get("sources"), "a sourced label needs a URL and access date")
                    if fact["status"] == "PLATFORM-DEFAULT":
                        self.assertTrue(fact.get("ref"), "a platform default names the decision or doc")

    def test_every_leaf_is_evidenced(self) -> None:
        for code, (pack, _, evidence) in self.data.items():
            paths = [p for fact in evidence["facts"] for p in fact["paths"]]
            for area in EVIDENCED_AREAS:
                for leaf, _ in _leaves(pack[area], area):
                    with self.subTest(code=code, leaf=leaf):
                        self.assertTrue(_covered(leaf, paths), f"{leaf} has no evidence entry")

    def test_pending_refs_are_declared(self) -> None:
        for code, (pack, _, evidence) in self.data.items():
            declared = {(p["path"], p["value"]) for p in evidence["pendingRefs"]}
            found = set()
            for path, val in _leaves(pack):
                if isinstance(val, str) and val.startswith("pending:"):
                    found.add((path, val))
            for idx, tpl in enumerate(pack["printFormats"]["templates"]):
                if tpl["templateRef"].startswith("pending:"):
                    found.add((f"printFormats.templates[{idx}].templateRef", tpl["templateRef"]))
            with self.subTest(code=code):
                self.assertLessEqual(found, declared)  # every pending: value is declared
                for p in evidence["pendingRefs"]:  # declared refs may also name ids that do not resolve yet
                    self.assertEqual(_get(pack, p["path"]), p["value"])
                    self.assertTrue(p["blockedBy"])

    def test_arabic_labels_marked_unreviewed(self) -> None:
        for code, (pack, manifest, evidence) in self.data.items():
            listed = {(a["file"], a["path"]): a for a in evidence["arabicLabels"]}
            found = {("pack.json", p): t for p, t in _arabic_strings(pack)}
            found.update({("manifest.json", p): t for p, t in _arabic_strings(manifest)})
            with self.subTest(code=code):
                self.assertEqual(set(listed), set(found))
                for key, text in found.items():
                    self.assertEqual(listed[key]["text"], text)
                    self.assertEqual(listed[key]["review"], "unreviewed")


class TestPacksReadme(unittest.TestCase):
    def test_readme_names_the_packs_root(self) -> None:
        text = (PACKS_DIR / "README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# "))
        self.assertIn("components/compliance/country_pack/packs/", text)


if __name__ == "__main__":
    unittest.main()
