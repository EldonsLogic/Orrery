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
    load_country_pack,
    resolve_country_pack,
    validate_pack,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKS_DIR = PACKAGE_DIR / "packs"
SAMPLE_PACKS_DIR = Path(__file__).resolve().parent / "sample_packs"
REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_SCHEMA = REPO_ROOT / "contracts" / "component.manifest.schema.json"
BLUEPRINT_SCHEMA = REPO_ROOT / "contracts" / "blueprint.schema.json"
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
# A sane upper bound for a locked retention period, so a rate or a mistyped number stands out.
MAX_RETENTION_YEARS = 10
# Pack levels allowed while any reference is pending: nothing above `tested` (CMP-034 gates on it).
UNCERTIFIABLE_LEVELS = ("draft", "tested")
SEMVER = r"\d+\.\d+\.\d+"
# Locked string values may hold digits only in these known id formats (path pattern, value check).
DIGIT_ALLOWED = [
    (re.compile(r"(^|\.)version$"), re.compile(rf"^{SEMVER}$").fullmatch),
    (re.compile(r"(^|\.)(versionRange|compatibilityRange)$"), re.compile(rf"^>={SEMVER} <{SEMVER}$").fullmatch),
    (re.compile(r"(^|\.)hours\.(from|to)$"), re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$").fullmatch),
    (re.compile(r"^tax\.(vatNumberPattern|crNumberPattern)$"), re.compile(r"^\^[^%]*\$$").fullmatch),
    (re.compile(r"^eInvoicing\.mode$"), None),  # checked against the Blueprint enum instead
]


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


def _all_leaves(obj, prefix: str = ""):
    """Like `_leaves`, but also walks lists (`name[0]`)."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _all_leaves(val, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from _all_leaves(item, f"{prefix}[{idx}]")
    else:
        yield prefix, obj


def _blueprint_modes() -> set[str]:
    schema = _read_json(BLUEPRINT_SCHEMA)
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            einv = node.get("eInvoicing")
            if isinstance(einv, dict):
                mode = einv.get("properties", {}).get("mode", {})
                found.update(mode.get("enum", []))
            for val in node.values():
                walk(val)
        elif isinstance(node, list):
            for val in node:
                walk(val)

    walk(schema)
    return found


def _rate_like_violations(pack: dict, modes: set[str]) -> list[str]:
    """Locked values that look like a rate, an amount or an implausible period.

    Digits in a locked string are allowed only in the known id formats of DIGIT_ALLOWED.
    """
    bad = []
    for area in (*EVIDENCED_AREAS, "upgradePolicy"):
        for path, val in _all_leaves(pack[area], area):
            plain = re.sub(r"\[\d+\]", "", path)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if plain not in NUMERIC_LEAVES:
                    bad.append(f"{path}: numeric leaf {val!r}")
                elif plain == "eInvoicing.archiveRetentionYears" and not 0 < val <= MAX_RETENTION_YEARS:
                    bad.append(f"{path}: retention {val!r} outside 1..{MAX_RETENTION_YEARS}")
            if not isinstance(val, str) or not re.search(r"\d", val):
                continue
            rule = next((check for pat, check in DIGIT_ALLOWED if pat.search(plain)), False)
            if rule is False:
                bad.append(f"{path}: digits in {val!r}")
            elif rule is None and val not in modes:
                bad.append(f"{path}: {val!r} is not a Blueprint e-invoicing mode")
            elif rule is not None and not rule(val):
                bad.append(f"{path}: {val!r} is not a known id format")
    return bad


def _pending(evidence: dict) -> list:
    return [*evidence.get("pendingRefs", []), *evidence.get("goLiveBlockers", [])]


def _certifiability_violations(pack: dict, manifest: dict, evidence: dict) -> list[str]:
    """While any reference is pending, neither the pack nor the manifest may claim more than `tested`."""
    if not _pending(evidence):
        return []
    bad = []
    if pack["status"] not in UNCERTIFIABLE_LEVELS:
        bad.append(f"pack status {pack['status']} with pending references")
    if manifest["certification"]["level"] not in UNCERTIFIABLE_LEVELS:
        bad.append(f"manifest level {manifest['certification']['level']} with pending references")
    return bad


def _requires_key(entry: dict) -> tuple[str, str]:
    kind = "component" if "component" in entry else "capability"
    return kind, entry[kind]


def _repo_components() -> tuple[set[str], set[str]]:
    """Ids and capabilities of every registered component manifest outside the packs root."""
    ids, caps = set(), set()
    for path in REPO_ROOT.glob("components/**/manifest.json"):
        if PACKS_DIR in path.parents:
            continue
        manifest = _read_json(path)
        ids.add(manifest.get("id"))
        caps.update(p["capability"] for p in manifest.get("provides", []))
    return ids, caps


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
                pinned = load_country_pack(code, PACKS_DIR, version=version, environment="test")
                latest = load_country_pack(code, PACKS_DIR, environment="test")
                self.assertEqual(pinned, latest)
                self.assertEqual(validate_pack(pinned), [])
                self.assertEqual(pinned["countryCode"], code)
                self.assertEqual(pinned["componentId"], f"country.{code.lower()}")

    def test_status_matches_level_and_evidence_unverified(self) -> None:
        for code in PACKS:
            with self.subTest(code=code):
                pack = load_country_pack(code, PACKS_DIR, environment="test")
                cert = _read_json(_version_dir(code) / "manifest.json")["certification"]
                self.assertEqual(pack["status"], cert["level"])
                self.assertEqual(pack["status"], "tested")
                self.assertIs(cert["touchesLedgerOrTax"], True)
                self.assertEqual(cert["reviewedBy"], [])
                self.assertEqual(pack["evidenceStatus"], "unverified")
                self.assertIs(pack["testOnly"], False)
                self.assertIn("evidence.json", pack["notes"])

    def test_pending_references_keep_packs_uncertifiable(self) -> None:
        for code in PACKS:
            vdir = _version_dir(code)
            pack, manifest, evidence = (_read_json(vdir / n) for n in ("pack.json", "manifest.json", "evidence.json"))
            with self.subTest(code=code):
                self.assertTrue(_pending(evidence), "both packs still have pending references")
                self.assertEqual(_certifiability_violations(pack, manifest, evidence), [])
                for level in ("reviewed", "certified", "regulated"):
                    raised = dict(pack, status=level)
                    self.assertTrue(_certifiability_violations(raised, manifest, evidence), level)
                    cert = dict(manifest["certification"], level=level)
                    self.assertTrue(_certifiability_violations(pack, dict(manifest, certification=cert), evidence))

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

    def test_real_root_holds_no_test_only_pack(self) -> None:
        for pack_file in PACKS_DIR.glob("*/*/pack.json"):
            with self.subTest(pack=str(pack_file.relative_to(PACKS_DIR))):
                self.assertIs(_read_json(pack_file).get("testOnly"), False)

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
        pack = _read_json(_version_dir("SA") / "pack.json")
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
    def test_no_maths_or_rates_in_packs(self) -> None:
        for code in PACKS:
            pack = _read_json(_version_dir(code) / "pack.json")
            with self.subTest(code=code):
                self.assertEqual([k for k in _keys(pack) if MATHS_KEY.search(k)], [])
                for path, val in _leaves(pack):
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        self.assertIn(path, NUMERIC_LEAVES)

    def test_no_rate_like_strings_in_locked_values(self) -> None:
        modes = _blueprint_modes()
        self.assertIn("zatca_phase1", modes)
        for code in PACKS:
            with self.subTest(code=code):
                self.assertEqual(_rate_like_violations(_read_json(_version_dir(code) / "pack.json"), modes), [])

    def test_rate_like_mutations_are_caught(self) -> None:
        modes = _blueprint_modes()
        base = _read_json(_version_dir("SA") / "pack.json")
        mutations = {
            "taxCodesRef": ("tax", "taxCodesRef", "vat:0.15"),
            "mode": ("eInvoicing", "mode", "standard_15_pct"),
            "retention": ("eInvoicing", "archiveRetentionYears", 15),
            "retention zero": ("eInvoicing", "archiveRetentionYears", 0),
            "artifact": ("coaTemplate", "artifactRef", "chart_vat_5pct.json"),
            "range": ("coaTemplate", "versionRange", "0.15"),
            "pattern": ("tax", "vatNumberPattern", "15%"),
            "currency": ("localeDefaults", "currency", "SAR15"),
        }
        for label, (area, key, value) in mutations.items():
            with self.subTest(mutation=label):
                pack = json.loads(json.dumps(base))
                pack[area][key] = value
                self.assertTrue(_rate_like_violations(pack, modes))

    def test_einvoicing_mode_is_a_blueprint_value(self) -> None:
        modes = _blueprint_modes()
        expected = {"SA": "zatca_phase1", "AE": "uae_e_invoicing"}
        for code, mode in expected.items():
            with self.subTest(code=code):
                pack = load_country_pack(code, PACKS_DIR, environment="test")
                self.assertEqual(pack["eInvoicing"]["mode"], mode)
                self.assertIn(mode, modes)

    def test_print_languages_are_the_sourced_minimum(self) -> None:
        for code in PACKS:
            vdir = _version_dir(code)
            pack, evidence = _read_json(vdir / "pack.json"), _read_json(vdir / "evidence.json")
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
                target = _read_json(REPO_ROOT / ref)
                self.assertEqual(target["version"], "0.1.0")
                self.assertEqual(target["status"], "draft")
        self.assertEqual(pack["coaTemplate"]["versionRange"], ">=0.1.0 <0.2.0")
        text = (_version_dir("SA") / "pack.json").read_text(encoding="utf-8")
        for copied in ("VATEX", "account_number", "root_type", "posting_accounts", "1110"):
            self.assertNotIn(copied, text)

    def test_ksa_print_templates_exist(self) -> None:
        evidence = _read_json(_version_dir("SA") / "evidence.json")
        pending = {(p["path"], p["value"]) for p in evidence["pendingRefs"]}
        for idx, tpl in enumerate(load_country_pack("SA", PACKS_DIR, environment="test")["printFormats"]["templates"]):
            with self.subTest(kind=tpl["kind"]):
                path, _, layout = tpl["templateRef"].partition("#")
                self.assertIn(layout, (REPO_ROOT / path).read_text(encoding="utf-8"))
                # compliance.zatca_sa provides no print formats; the layout owner is a pending placeholder
                self.assertNotEqual(tpl["componentId"], "compliance.zatca_sa")
                self.assertIn((f"printFormats.templates[{idx}].componentId", tpl["componentId"]), pending)


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
                    self.assertFalse(test["path"].startswith(("/", ".")), "test path is repo-root relative")
                    self.assertTrue((REPO_ROOT / test["path"]).is_file(), test["path"])

    def test_requires_lists_every_referenced_component(self) -> None:
        # The compiler fails closed on unmet `requires`, so every component a pack points at,
        # including ones that do not exist yet, must be listed there.
        for code in PACKS:
            vdir = _version_dir(code)
            manifest, pack = _read_json(vdir / "manifest.json"), _read_json(vdir / "pack.json")
            referenced = {
                val for path, val in _leaves(pack)
                if isinstance(val, str) and (path.endswith(".componentId") or path.endswith("calendarRef.id"))
            }
            referenced.update(t["componentId"] for t in pack["printFormats"]["templates"] if t.get("componentId"))
            evidence = _read_json(vdir / "evidence.json")
            blocker_reqs = [b["requires"] for b in evidence["goLiveBlockers"] if "requires" in b]
            expected = {("component", c) for c in referenced} | {_requires_key(r) for r in blocker_reqs}
            required = [_requires_key(r) for r in manifest["requires"]]
            with self.subTest(code=code):
                self.assertTrue(referenced)
                self.assertNotIn(pack["componentId"], referenced)
                self.assertEqual(len(required), len(set(required)), "no duplicate requires")
                self.assertEqual(set(required), expected)
                for req in blocker_reqs:  # a blocker's entry is copied verbatim into requires
                    self.assertIn(req, manifest["requires"])

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
            manifest = _read_json(_version_dir(code) / "manifest.json")
            with self.subTest(code=code):
                self.assertLessEqual(keys, {_requires_key(r) for r in manifest["requires"]})
        sa = {r.get("component"): r["versionRange"] for r in _read_json(_version_dir("SA") / "manifest.json")["requires"]}
        self.assertEqual(sa["compliance.zatca_sa"], ">=0.1.0 <0.2.0")

    def test_manifest_provides_only_the_shared_loader(self) -> None:
        # The manifest contract needs at least one artifact and has no data or pack artifact type,
        # so the shared loader function stays listed once per manifest (finding 14 cannot be removed).
        for code in PACKS:
            manifest = _read_json(_version_dir(code) / "manifest.json")
            refs = [a["ref"] for p in manifest["provides"] for a in p["artifacts"]]
            with self.subTest(code=code):
                self.assertEqual(refs, ["components.compliance.country_pack.loader.resolve_country_pack"])


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
            for idx, fact in enumerate([*evidence["facts"], *evidence["goLiveBlockers"]]):
                with self.subTest(code=code, fact=idx):
                    self.assertIn(fact["status"], EVIDENCE_LABELS)
                    self.assertTrue(fact["claim"])
                    for path in fact.get("paths", [fact.get("backs")] if fact.get("backs") else []):
                        _get(pack, path)  # every cited path exists in the pack
                    for src in fact.get("sources", []):
                        self.assertTrue(src["url"].startswith("https://"), src["url"])
                        if re.search(r"not (fetched|read)", src.get("note", "")):
                            self.assertNotIn("accessed", src, "an unread source has no access date")
                            continue
                        self.assertRegex(src["accessed"], ISO_DATE)
                        self.assertLessEqual(src["accessed"], today)
                    if fact["status"] in {"VERIFIED-OFFICIAL", "SECONDARY"}:
                        read = [s for s in fact.get("sources", []) if "accessed" in s]
                        self.assertTrue(read, "a sourced label needs a URL and access date")
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

    def _facts_for(self, code: str, path: str) -> list[dict]:
        return [f for f in self.data[code][2]["facts"] if path in f["paths"]]

    def test_go_live_blockers_are_declared_and_unresolvable(self) -> None:
        ids, caps = _repo_components()
        for code, (_, manifest, evidence) in self.data.items():
            for blocker in evidence["goLiveBlockers"]:
                with self.subTest(code=code, blocker=blocker["id"]):
                    self.assertTrue(blocker["blockedBy"])
                    self.assertTrue(blocker["refs"])
                    if "requires" in blocker:
                        kind, name = _requires_key(blocker["requires"])
                        self.assertNotIn(name, ids if kind == "component" else caps, "placeholder must not resolve yet")

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
        self.assertIn("test_pack_<cc>.py", text)
        self.assertNotIn("test_pack_sa_ae.py", text)  # generic, so other packs' tests fit


if __name__ == "__main__":
    unittest.main()
