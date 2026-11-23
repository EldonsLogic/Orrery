"""CMP-036 review fixes on PR #300 (ADR-0067): scope, dependency, provisional-entry and shape regressions.

Every approval and source here is synthetic. Each test checks production refusal and, through
`_Fixture.refuse`, that sandbox and test still load the same version.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from components.compliance.country_pack import PackValidationError, load_country_pack
from components.compliance.country_pack import certification, evidence as evidence_mod
from components.compliance.country_pack.tests.test_production_rules import RESOLVED, _Fixture

REAL_ZATCA = Path(__file__).resolve().parents[3] / "compliance" / "zatca_sa"
DEFAULT_REF = "docs/decisions/ADR-0033-synthetic.md"
PROVISIONAL_RESOLUTION = {**RESOLVED, "ref": "docs/research/synthetic-accountant-answer.md"}


class TestOutsideSchemaScope(_Fixture):
    """Finding 1: an UNVERIFIED outside-schema entry must declare which pack paths it concerns."""

    def test_unscoped_unverified_entries_refuse_production(self) -> None:
        for label, entry in (
            ("paths missing", {"claim": "The VAT rate is 15%.", "status": "UNVERIFIED"}),
            ("paths empty", {"claim": "The VAT rate is 15%.", "status": "UNVERIFIED", "paths": []}),
        ):
            with self.subTest(entry=label):
                v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry]))
                self.refuse(v, r"factsOutsideSchema\[0\].*UNVERIFIED.*paths")

    def test_unverified_entry_with_an_explicit_non_locked_scope_still_loads(self) -> None:
        entry = {"claim": "synthetic", "status": "UNVERIFIED", "paths": ["localeDefaults.week.startDay"]}
        self.f._assert_loads(self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry])))

    def test_unscoped_entries_with_a_sourced_label_are_unchanged(self) -> None:
        entry = {"claim": "synthetic", "status": "SECONDARY",
                 "sources": [{"url": "https://example.org/synthetic", "accessed": "2026-01-01"}]}
        self.f._assert_loads(self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry])))


class TestRequiresResolution(_Fixture):
    """Finding 2: a requirement resolves only to a contract-valid provider whose version is in range."""

    def registry(self, *providers: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for index, manifest in enumerate(providers):
            folder = Path(tmp.name) / "area" / f"provider{index}"
            folder.mkdir(parents=True)
            (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return Path(tmp.name)

    def provider(self, version: str = "0.1.0", component: str = "finance.vat_synthetic",
                 capability: str = "finance.vat.synthetic_cap") -> dict:
        return self.valid_provider(component, version, capability)

    def requiring(self, entry: dict, root: Path, expect: bool) -> None:
        v = self.mutate("manifest.json", lambda m: m.update(requires=[entry]))
        with patch.object(certification, "COMPONENTS_ROOT", root):
            if expect:
                self.f._assert_loads(v)
            else:
                with self.assertRaisesRegex(PackValidationError, "requires"):
                    load_country_pack("SA", self.f.packs_dir, version=v)
        for environment in ("sandbox", "test"):
            self.f._assert_loads(v, environment=environment)

    def test_real_dependency_with_an_unsatisfiable_range_is_refused(self) -> None:
        manifest = json.loads((REAL_ZATCA / "manifest.json").read_text(encoding="utf-8"))
        real_root = REAL_ZATCA.parents[1]
        self.assertEqual(manifest["version"], "0.1.0")
        self.requiring({"component": "compliance.zatca_sa", "versionRange": ">=9999.0.0"}, real_root, False)
        self.requiring({"component": "compliance.zatca_sa", "versionRange": ">=0.1.0 <0.2.0"}, real_root, True)

    def test_oversized_version_numbers_refuse_cleanly(self) -> None:
        """Re-review at 2ce73b1: a 5,000-digit segment exceeded int()'s digit limit and escaped as ValueError."""
        huge = "1" + "0" * 5000
        self.assertFalse(certification.version_in_range(f">={huge}.0.0", "0.1.0"))
        self.assertFalse(certification.version_in_range(">=0.1.0", f"{huge}.0.0"))
        root = self.registry(self.provider())
        self.requiring({"component": "finance.vat_synthetic", "versionRange": f">={huge}.0.0"}, root, False)
        only_huge = self.registry(self.provider(version=f"{huge}.0.0"))
        self.requiring({"component": "finance.vat_synthetic", "versionRange": ">=0.1.0"}, only_huge, False)
        both = self.registry(self.provider(version=f"{huge}.0.0"), self.provider())
        self.requiring({"component": "finance.vat_synthetic", "versionRange": ">=0.1.0"}, both, True)

    def test_version_ranges(self) -> None:
        root = self.registry(self.provider("0.1.0"))
        for rng, ok in (
            (">=0.1.0 <0.2.0", True), ("0.1.0", True), ("=0.1.0", True), ("^0.1.0", True), ("~0.1.0", True),
            ("<=0.1.0", True), (">=0.0.1", True), ("^0.1.0 || ^2.0.0", True), ("^2.0.0 || >=0.1.0 <0.2.0", True),
            (">0.1.0", False), ("<0.1.0", False), (">=9999.0.0", False), ("^1.0.0", False), ("^0.2.0", False),
            ("~0.2.0", False), ("0.1.1", False), (">=0.1.0 <0.1.0", False), (">=0.2.0 || >=0.3.0", False),
        ):
            with self.subTest(range=rng):
                self.requiring({"component": "finance.vat_synthetic", "versionRange": rng}, root, ok)
                self.requiring({"capability": "finance.vat.synthetic_cap", "versionRange": rng}, root, ok)

    def test_caret_and_tilde_follow_the_zero_major_rules(self) -> None:
        satisfied = certification.version_in_range
        self.assertTrue(satisfied("^1.2.3", "1.9.9"))
        self.assertFalse(satisfied("^1.2.3", "2.0.0"))
        self.assertTrue(satisfied("^0.0.3", "0.0.3"))
        self.assertFalse(satisfied("^0.0.3", "0.0.4"))
        self.assertTrue(satisfied("~1.2.3", "1.2.9"))
        self.assertFalse(satisfied("~1.2.3", "1.3.0"))

    def test_ranges_the_comparator_cannot_parse_are_refused(self) -> None:
        root = self.registry(self.provider("0.1.0"))
        for rng in ("banana", "1.x", "1", "1.2", ">=0.1", "*", "x", "latest", " ", ">= 0.1.0", "0.1.0 - 0.2.0",
                    ">=0.1.0 ||", "|| >=0.1.0", ">=0.1.0 | <0.2.0", ">=0.1.0,<0.2.0", "01.0.0", ">=0.1.0-beta",
                    "^", "≥0.1.0", "٠.١.٠", ">=0.1.0\n", "v0.1.0", "0.1.0+build", "=>0.1.0", "<>0.1.0"):
            with self.subTest(range=rng):
                self.assertFalse(certification.version_in_range(rng, "0.1.0"))
                self.requiring({"component": "finance.vat_synthetic", "versionRange": rng}, root, False)

    def test_a_prerelease_provider_never_satisfies_a_range(self) -> None:
        root = self.registry(self.provider("0.1.0-beta.1"))
        for rng in (">=0.0.1", "^0.1.0-beta.1", ">=0.1.0-beta.1", "<1.0.0"):
            with self.subTest(range=rng):
                self.requiring({"component": "finance.vat_synthetic", "versionRange": rng}, root, False)

    def test_incomplete_provider_manifests_do_not_resolve(self) -> None:
        for label, manifest in (
            ("only id and provides", {"id": "finance.vat_synthetic",
                                       "provides": [{"capability": "finance.vat.synthetic_cap"}]}),
            ("only id and version", {"id": "finance.vat_synthetic", "version": "0.1.0"}),
            ("no owner", {k: v for k, v in self.provider().items() if k != "owner"}),
            ("bad version", {**self.provider(), "version": "not-a-version"}),
            ("extra key", {**self.provider(), "extra": True}),
        ):
            with self.subTest(provider=label):
                root = self.registry(manifest)
                self.requiring({"component": "finance.vat_synthetic", "versionRange": ">=0.0.1"}, root, False)
                self.requiring({"capability": "finance.vat.synthetic_cap", "versionRange": ">=0.0.1"}, root, False)

    def test_an_invalid_provider_does_not_hide_a_valid_one(self) -> None:
        root = self.registry({"id": "finance.vat_synthetic"}, self.provider("0.1.0"))
        self.requiring({"component": "finance.vat_synthetic", "versionRange": "^0.1.0"}, root, True)

    def test_capability_provided_but_out_of_range_is_refused(self) -> None:
        root = self.registry(self.provider("0.1.0"))
        self.requiring({"capability": "finance.vat.synthetic_cap", "versionRange": ">=1.0.0"}, root, False)

    def test_component_id_never_matches_a_capability_name(self) -> None:
        root = self.registry(self.provider("0.1.0"))
        self.requiring({"component": "finance.vat.synthetic_cap", "versionRange": ">=0.1.0"}, root, False)


class TestProvisionalProductChoiceEntries(_Fixture):
    """Finding 3: provisional product-choice entries authorise nothing until resolved with evidence."""

    def choice_file(self, entry: dict) -> Path:
        path = Path(self.f._tmp.name) / "choice.json"
        path.write_text(json.dumps({"markets": {"SA": [entry]}}), encoding="utf-8")
        return path

    def entry(self, **extra) -> dict:
        return {"path": "tax.roundingRule", "reason": "synthetic", "provisional": "synthetic open question", **extra}

    def test_shipped_provisional_entries_do_not_authorise_a_default_in_production(self) -> None:
        for market in ("SA", "AE", "QA"):
            with self.subTest(market=market):
                entry = next(e for e in evidence_mod.product_choice_entries()[market] if e["path"] == "tax.roundingRule")
                self.assertTrue(entry.get("provisional"))
                self.assertNotIn("resolution", entry)
                self.assertNotIn("tax.roundingRule", evidence_mod.active_product_choice_paths(market, {"eldonslogic"}))
        self.refuse(self.with_default("tax.roundingRule"), "PLATFORM-DEFAULT.*tax.roundingRule.*product-choice")

    def test_settled_entries_stay_active(self) -> None:
        for market, expected in (("SA", {"eInvoicing.componentId", "eInvoicing.mode"}), ("EG", set())):
            self.assertEqual(set(evidence_mod.active_product_choice_paths(market, {"eldonslogic"})), expected)
        self.f._assert_loads(self.with_default("eInvoicing.mode"))

    def test_a_provisional_entry_without_a_resolution_is_inactive(self) -> None:
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self.choice_file(self.entry())):
            self.refuse(self.with_default("tax.roundingRule"), "product-choice")

    def test_a_resolved_provisional_entry_becomes_active(self) -> None:
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE",
                          self.choice_file(self.entry(resolution=dict(PROVISIONAL_RESOLUTION)))):
            self.f._assert_loads(self.with_default("tax.roundingRule"))
            self.f._assert_loads(self.with_default("tax.roundingRule"), environment="production")

    def test_resolution_record_needs_status_who_when_and_a_source_ref(self) -> None:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        good = PROVISIONAL_RESOLUTION
        cases = {
            "status open": dict(good, status="open"),
            "who unknown": dict(good, by="synthetic-nobody"),
            "who not text": dict(good, by=["EldonsLogic"]),
            "when future": dict(good, at=tomorrow),
            "when impossible": dict(good, at="2026-02-30"),
            "when too old": dict(good, at="1999-01-01"),
            "ref missing": {k: v for k, v in good.items() if k != "ref"},
            "ref blank": dict(good, ref=" "),
            "ref not text": dict(good, ref=["x"]),
            "who missing": {k: v for k, v in good.items() if k != "by"},
            "unknown key": dict(good, revoked=True),
            "not an object": "resolved",
        }
        for label, resolution in cases.items():
            with self.subTest(resolution=label):
                with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self.choice_file(self.entry(resolution=resolution))):
                    self.refuse(self.with_default("tax.roundingRule"), "product-choice")

    def test_a_resolution_on_a_settled_entry_makes_the_list_unusable(self) -> None:
        settled = {"path": "tax.roundingRule", "reason": "synthetic", "resolution": dict(PROVISIONAL_RESOLUTION)}
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self.choice_file(settled)):
            with self.assertRaisesRegex(PackValidationError, "product-choice list"):
                load_country_pack("SA", self.f.packs_dir, version=self.f._write("certified", "verified_official"))

    def test_unknown_founders_activate_no_provisional_entry(self) -> None:
        self.assertEqual(evidence_mod.active_product_choice_paths("SA", None), ["eInvoicing.componentId", "eInvoicing.mode"])
        resolved = self.choice_file(self.entry(resolution=dict(PROVISIONAL_RESOLUTION)))
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", resolved):
            self.assertEqual(evidence_mod.active_product_choice_paths("SA", {"eldonslogic"}), ["tax.roundingRule"])
            self.assertEqual(evidence_mod.active_product_choice_paths("SA", None), [])


class TestNoExceptionEscapesTheLoader(_Fixture):
    """Finding 4: malformed JSON shapes refuse; they never raise TypeError or any non-validation error."""

    BAD_VALUES = ([], {}, 0, None, "", "x", True, [[]], [{}], [None], [0])

    def production(self, version: str) -> None:
        try:
            load_country_pack("SA", self.f.packs_dir, version=version)
        except PackValidationError:
            return  # a clean refusal
        # anything else (TypeError, AttributeError, KeyError...) propagates and fails the test

    def test_malformed_requires_entries_refuse_cleanly(self) -> None:
        range_ = ">=0.1.0"
        for label, requires in (
            ("component object", [{"component": {}, "versionRange": range_}]),
            ("component list", [{"component": ["a.b"], "versionRange": range_}]),
            ("capability empty list", [{"capability": [], "versionRange": range_}]),
            ("capability object", [{"capability": {}, "versionRange": range_}]),
            ("both keys", [{"component": "a.b", "capability": "c.d", "versionRange": range_}]),
            ("neither key", [{"versionRange": range_}]),
            ("range object", [{"component": "finance.vat_synthetic", "versionRange": {}}]),
            ("range missing", [{"component": "finance.vat_synthetic"}]),
            ("entry null", [None]), ("entry string", ["finance.vat_synthetic"]), ("entry empty", [{}]),
            ("requires object", {}), ("requires string", "x"), ("requires null", None),
        ):
            with self.subTest(requires=label):
                v = self.mutate("manifest.json", lambda m: m.update(requires=requires))
                with self.assertRaises(PackValidationError):
                    load_country_pack("SA", self.f.packs_dir, version=v)
                for environment in ("sandbox", "test"):
                    self.f._assert_loads(v, environment=environment)

    def test_malformed_registered_manifests_never_break_resolution(self) -> None:
        shapes = ({"id": {}}, {"id": []}, {"id": None}, {"id": "finance.vat_synthetic", "provides": {}},
                  {"id": "finance.vat_synthetic", "provides": [None]},
                  {"id": "finance.vat_synthetic", "provides": [{"capability": {}}]},
                  {"id": "finance.vat_synthetic", "provides": [{"capability": []}], "version": {}},
                  {"id": "finance.vat_synthetic", "version": []}, [], None, "x", 7)
        v = self.mutate("manifest.json", lambda m: m.update(
            requires=[{"component": "finance.vat_synthetic", "versionRange": ">=0.1.0"},
                      {"capability": "finance.vat.synthetic_cap", "versionRange": ">=0.1.0"}]))
        for index, shape in enumerate(shapes):
            with self.subTest(shape=shape):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                (Path(tmp.name) / "x").mkdir()
                (Path(tmp.name) / "x" / "manifest.json").write_text(json.dumps(shape), encoding="utf-8")
                with patch.object(certification, "COMPONENTS_ROOT", Path(tmp.name)):
                    with self.assertRaisesRegex(PackValidationError, "requires"):
                        load_country_pack("SA", self.f.packs_dir, version=v)

    def test_mutated_manifest_and_evidence_fields_never_raise(self) -> None:
        version = self.f._write("certified", "verified_official")
        for filename in ("manifest.json", "evidence.json"):
            original = self.f._record(version, filename)
            targets = [(key,) for key in original]
            targets += [(key, inner) for key, value in original.items() if isinstance(value, dict) for inner in value]
            for target in targets:
                for bad in self.BAD_VALUES:
                    record = json.loads(json.dumps(original))
                    holder = record
                    for part in target[:-1]:
                        holder = holder[part]
                    holder[target[-1]] = bad
                    self.f._save(version, filename, record)
                    with self.subTest(file=filename, field=".".join(target), value=bad):
                        self.production(version)
            self.f._save(version, filename, original)
        self.f._assert_loads(version)

    def test_malformed_blocker_and_fact_entries_never_raise(self) -> None:
        version = self.f._write("certified", "verified_official")
        original = self.f._record(version, "evidence.json")
        for key in ("goLiveBlockers", "pendingRefs", "factsOutsideSchema", "facts"):
            for bad in self.BAD_VALUES:
                for entry in (bad, {"id": bad, "status": bad, "paths": bad, "resolution": bad, "sources": bad,
                                    "ref": bad, "claim": bad}):
                    record = json.loads(json.dumps(original))
                    record[key] = [entry]
                    self.f._save(version, "evidence.json", record)
                    with self.subTest(key=key, entry=entry):
                        self.production(version)
