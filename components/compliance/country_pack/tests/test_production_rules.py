"""CMP-036 production rules: product-choice list, open blockers, record meaning (ADR-0067).

Every approval and source here is synthetic. Each test mutates one field of the signed fixture
(`test_country_pack_go_live_gate`) and checks both production refusal and sandbox/test acceptance.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from components.compliance.country_pack import PackValidationError, load_country_pack
from components.compliance.country_pack import certification, evidence as evidence_mod
from components.compliance.country_pack.tests import test_country_pack_go_live_gate as gate_tests
from components.compliance.country_pack.tests.pack_checks import certifiability_violations, get, leaves, pending

PACKS_DIR = Path(__file__).resolve().parents[1] / "packs"
RESOLVED = {"status": "resolved", "by": "EldonsLogic", "at": "2026-11-23"}
PENDING_REF = {"path": "coaTemplate.componentId", "value": "x", "blockedBy": "synthetic"}
BLOCKER = {"id": "synthetic_blocker", "claim": "synthetic", "status": "UNVERIFIED", "blockedBy": "synthetic"}


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.f = gate_tests.TestCountryPackGoLiveGate()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

    def refuse(self, version: str, reason: str) -> None:
        """Production refuses with `reason`; sandbox and test still load the same version."""
        with self.assertRaisesRegex(PackValidationError, reason):
            load_country_pack("SA", self.f.packs_dir, version=version)
        for environment in ("sandbox", "test"):
            self.f._assert_loads(version, environment=environment)

    def mutate(self, filename: str, change, status: str = "certified", label: str = "verified_official") -> str:
        v = self.f._write(status, label)
        record = self.f._record(v, filename)
        change(record)
        self.f._save(v, filename, record)
        return v

    def back_leaf(self, record: dict, pack: dict, leaf: str, status: str, **extra) -> None:
        """Move `leaf` from the signed fact into its own fact with `status`."""
        main = record["facts"][0]
        main["paths"] = [p for area in main["paths"] for p, _ in leaves(get(pack, area), area) if p != leaf]
        fact = {"paths": [leaf], "status": status, "claim": "Synthetic fact only."}
        if status != "PLATFORM-DEFAULT":
            fact["sources"] = [{"url": "https://example.org/synthetic", "accessed": "2026-01-01"}]
        record["facts"].append({**fact, **extra})

    @staticmethod
    def valid_provider(component: str, version: str, capability: str) -> dict:
        """A registered-component manifest that passes the component contract (ADR-0067 `requires`)."""
        return {
            "id": component, "version": version, "kind": "rigid", "name": {"ar": "اختبار", "en": "Synthetic provider"},
            "description": "Synthetic provider fixture only.",
            "provides": [{"capability": capability, "artifacts": [{"type": "function", "ref": "synthetic_function"}]}],
            "requires": [], "parameters": [],
            "tests": [{"id": "synthetic_test", "kind": "unit", "path": "synthetic_test.py", "blocking": True}],
            "certification": {"level": "draft", "reviewedBy": [], "touchesLedgerOrTax": False},
            "engineCompatibility": {"adapter": "change_engine", "engineRange": ">=0.1.0 <1.0.0"},
            "licence": {"spdx": "LicenseRef-Proprietary"}, "owner": {"github": "sayegh9"},
        }

    def with_default(self, leaf: str, **extra) -> str:
        v = self.f._write("certified", "verified_official")
        pack, record = self.f._record(v, "pack.json"), self.f._record(v, "evidence.json")
        self.back_leaf(record, pack, leaf, "PLATFORM-DEFAULT", ref="docs/decisions/ADR-0033-synthetic.md", **extra)
        self.f._save(v, "evidence.json", record)
        return v


class TestProductChoiceList(_Fixture):
    """Q1 option C: PLATFORM-DEFAULT backs a locked path only through a named per-market list."""

    def test_listed_path_may_be_backed_by_a_platform_default(self) -> None:
        self.f._assert_loads(self.with_default("eInvoicing.mode"))
        self.f._assert_loads(self.with_default("eInvoicing.componentId"))

    def test_unlisted_locked_leaf_is_refused(self) -> None:
        v = self.with_default("tax.vatSupported")
        self.refuse(v, "PLATFORM-DEFAULT.*tax.vatSupported.*product-choice")

    def test_a_listed_path_never_authorises_through_an_ancestor(self) -> None:
        for ancestor in ("tax", "eInvoicing"):
            with self.subTest(ancestor=ancestor):
                v = self.f._write("certified", "verified_official")
                record = self.f._record(v, "evidence.json")
                record["facts"].append({"paths": [ancestor], "status": "PLATFORM-DEFAULT",
                                        "ref": "docs/decisions/ADR-0033-synthetic.md", "claim": "synthetic"})
                self.f._save(v, "evidence.json", record)
                self.refuse(v, f"PLATFORM-DEFAULT.*{ancestor}.*product-choice")

    def test_a_listed_path_matches_exactly_and_covers_no_other_path(self) -> None:
        self.assertTrue(evidence_mod.is_product_choice_path(["printFormats.templates"], "printFormats.templates"))
        for other in ("printFormats.templates[0].componentId", "printFormats.templates[0]",
                      "printFormats.templates.x", "printFormats"):
            with self.subTest(path=other):
                self.assertFalse(evidence_mod.is_product_choice_path(["printFormats.templates"], other))
        self.assertFalse(evidence_mod.is_product_choice_path(["tax.roundingRule"], "tax"))
        self.assertFalse(evidence_mod.is_product_choice_path(["tax.round"], "tax.roundingRule"))
        self.assertFalse(evidence_mod.is_product_choice_path([], "tax.roundingRule"))

    def test_a_child_of_a_listed_path_is_refused_in_production(self) -> None:
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self._choice_file({"SA": ["tax.filingPeriods"]})):
            self.f._assert_loads(self.with_default("tax.filingPeriods"))  # the listed path itself is a list leaf
            v = self.with_default("tax.filingPeriods[0]")
            self.refuse(v, r"PLATFORM-DEFAULT.*tax\.filingPeriods\[0\].*product-choice")

    def test_platform_default_outside_locked_areas_is_unaffected(self) -> None:
        v = self.f._write("certified", "verified_official")
        record = self.f._record(v, "evidence.json")
        record["facts"].append({"paths": ["localeDefaults.week.startDay"], "status": "PLATFORM-DEFAULT",
                                "ref": "docs/architecture/calendars-and-locale.md", "claim": "synthetic"})
        self.f._save(v, "evidence.json", record)
        self.f._assert_loads(v)

    def test_list_is_per_market(self) -> None:
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self._choice_file({"AE": ["tax.roundingRule"], "SA": []})):
            self.refuse(self.with_default("tax.roundingRule"), "PLATFORM-DEFAULT.*tax.roundingRule.*product-choice")
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self._choice_file({"AE": [], "SA": ["tax.roundingRule"]})):
            self.f._assert_loads(self.with_default("tax.roundingRule"))
        with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", self._choice_file({"AE": ["tax.roundingRule"]})):
            self.refuse(self.with_default("tax.roundingRule"), "product-choice")  # market absent: nothing allowed

    def test_unusable_list_fails_closed(self) -> None:
        good = {"SA": [{"path": "tax.roundingRule", "reason": "synthetic"}]}
        bad_files = {
            "missing": None,
            "malformed": "{",
            "duplicate key": '{"markets": {"SA": [], "SA": []}}',
            "not an object": "[]",
            "unknown top key": json.dumps({"markets": good, "extra": 1}),
            "markets not object": '{"markets": []}',
            "entry not object": '{"markets": {"SA": ["tax.roundingRule"]}}',
            "entry unknown key": '{"markets": {"SA": [{"path": "tax.roundingRule", "reason": "x", "ok": true}]}}',
            "blank reason": '{"markets": {"SA": [{"path": "tax.roundingRule", "reason": " "}]}}',
            "blank provisional": '{"markets": {"SA": [{"path": "tax.roundingRule", "reason": "x", "provisional": ""}]}}',
            "empty path": '{"markets": {"SA": [{"path": "", "reason": "x"}]}}',
            "path to a root": '{"markets": {"SA": [{"path": "tax", "reason": "x"}]}}',
        }
        for label, text in bad_files.items():
            with self.subTest(file=label):
                path = Path(self.f._tmp.name) / f"choice-{label.replace(' ', '-')}.json"
                if text is not None:
                    path.write_text(text, encoding="utf-8")
                v = self.f._write("certified", "verified_official")
                with patch.object(evidence_mod, "PRODUCT_CHOICE_FILE", path):
                    with self.assertRaisesRegex(PackValidationError, "product-choice list"):
                        load_country_pack("SA", self.f.packs_dir, version=v)
                    self.f._assert_loads(v, environment="sandbox")

    def test_shipped_list_is_pinned_and_has_no_saudi_rounding_entry(self) -> None:
        listed = {market: [entry["path"] for entry in entries]
                  for market, entries in evidence_mod.product_choice_entries().items()}
        self.assertEqual(listed, {
            "SA": ["eInvoicing.componentId", "eInvoicing.mode"],
            "AE": ["tax.roundingRule"],
            "EG": [],
            "QA": ["tax.roundingRule"],
        })
        for market in ("AE", "QA"):
            rounding = next(e for e in evidence_mod.product_choice_entries()[market] if e["path"] == "tax.roundingRule")
            with self.subTest(market=market):
                self.assertTrue(rounding.get("provisional"))

    def test_saudi_rounding_cannot_be_a_platform_default_whatever_the_founders_record(self) -> None:
        """ZATCA XML Implementation Standard v1.2 section 10 sets it: statutory, so never PLATFORM-DEFAULT."""
        self.assertNotIn("tax.roundingRule", evidence_mod.active_product_choice_paths("SA", {"eldonslogic", "sayegh9"}))
        self.refuse(self.with_default("tax.roundingRule"), "PLATFORM-DEFAULT.*tax.roundingRule.*product-choice")

    def test_shipped_list_paths_exist_in_the_shipped_packs(self) -> None:
        for market, entries in evidence_mod.product_choice_entries().items():
            pack = json.loads((PACKS_DIR / market.lower() / "0.1.0" / "pack.json").read_text(encoding="utf-8"))
            for entry in entries:
                with self.subTest(market=market, path=entry["path"]):
                    get(pack, entry["path"])

    def _choice_file(self, markets: dict[str, list[str]]) -> Path:
        path = Path(self.f._tmp.name) / "choice.json"
        payload = {"markets": {m: [{"path": p, "reason": "synthetic"} for p in paths] for m, paths in markets.items()}}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class TestOpenBlockers(_Fixture):
    """Q2 option A: an open blocker or pending reference refuses production until resolved on record."""

    def test_open_entries_refuse_production(self) -> None:
        for key, entry in (("goLiveBlockers", BLOCKER), ("pendingRefs", PENDING_REF)):
            with self.subTest(key=key):
                v = self.mutate("evidence.json", lambda r: r.setdefault(key, []).append(dict(entry)))
                self.refuse(v, f"{key}\\[0\\].*open")

    def test_resolved_entries_stop_blocking(self) -> None:
        for key, entry in (("goLiveBlockers", BLOCKER), ("pendingRefs", PENDING_REF)):
            with self.subTest(key=key):
                v = self.mutate("evidence.json",
                                lambda r: r.setdefault(key, []).append({**entry, "resolution": dict(RESOLVED)}))
                self.f._assert_loads(v)

    def test_one_open_entry_among_resolved_ones_refuses(self) -> None:
        v = self.mutate("evidence.json", lambda r: r.update(
            pendingRefs=[{**PENDING_REF, "resolution": dict(RESOLVED)}, dict(PENDING_REF)]))
        self.refuse(v, r"pendingRefs\[1\].*open")

    def test_resolution_record_needs_status_who_and_when(self) -> None:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        cases = {
            "status open": dict(RESOLVED, status="open"),
            "status case": dict(RESOLVED, status="Resolved"),
            "status missing": {k: v for k, v in RESOLVED.items() if k != "status"},
            "who missing": {k: v for k, v in RESOLVED.items() if k != "by"},
            "who unknown": dict(RESOLVED, by="synthetic-nobody"),
            "who blank": dict(RESOLVED, by=" "),
            "who not text": dict(RESOLVED, by=["EldonsLogic"]),
            "when missing": {k: v for k, v in RESOLVED.items() if k != "at"},
            "when future": dict(RESOLVED, at=tomorrow),
            "when impossible": dict(RESOLVED, at="2026-02-30"),
            "when not a date": dict(RESOLVED, at="yesterday"),
            "when too old": dict(RESOLVED, at="1999-01-01"),
            "unknown key": dict(RESOLVED, revoked=True),
            "not an object": "resolved",
            "null": None,
        }
        for label, resolution in cases.items():
            with self.subTest(resolution=label):
                v = self.mutate("evidence.json", lambda r: r.update(
                    goLiveBlockers=[{**BLOCKER, "resolution": resolution}]))
                self.refuse(v, r"goLiveBlockers\[0\]")

    def test_founder_login_is_matched_case_insensitively(self) -> None:
        v = self.mutate("evidence.json", lambda r: r.update(
            goLiveBlockers=[{**BLOCKER, "resolution": dict(RESOLVED, by="SAYEGH9")}]))
        self.f._assert_loads(v)

    def test_malformed_entry_lists_are_refused(self) -> None:
        for key in ("goLiveBlockers", "pendingRefs"):
            for value in ("open", {"a": 1}, [None], ["x"], None):
                with self.subTest(key=key, value=value):
                    v = self.mutate("evidence.json", lambda r: r.update({key: value}))
                    self.refuse(v, key)

    def test_unverified_outside_entry_on_a_locked_path_refuses(self) -> None:
        # `localeDefaults` and `localeDefaults.holidays` are ancestors of a locked path, not locked themselves.
        for path in ("tax", "tax.filingPeriods", "eInvoicing.mode", "localeDefaults.holidays.calendarRef",
                     "localeDefaults.holidays", "localeDefaults"):
            with self.subTest(path=path):
                v = self.mutate("evidence.json", lambda r: r.update(
                    factsOutsideSchema=[{"claim": "synthetic", "status": "UNVERIFIED", "paths": [path]}]))
                self.refuse(v, r"factsOutsideSchema\[0\].*UNVERIFIED.*locked")

    def test_outside_entries_that_do_not_name_a_locked_path_do_not_block(self) -> None:
        for entry in ({"claim": "synthetic", "status": "UNVERIFIED", "paths": ["localeDefaults.week.startDay"]},
                      {"claim": "synthetic", "status": "SECONDARY", "paths": ["tax"],
                       "sources": [{"url": "https://example.org/synthetic", "accessed": "2026-01-01"}]}):
            with self.subTest(entry=entry):
                v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry]))
                self.f._assert_loads(v)

    def test_outside_platform_default_on_a_locked_path_needs_the_product_choice_list(self) -> None:
        entry = {"claim": "synthetic", "status": "PLATFORM-DEFAULT", "paths": ["tax.filingPeriods"],
                 "ref": "docs/decisions/ADR-0033-synthetic.md"}
        v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry]))
        self.refuse(v, r"factsOutsideSchema\[0\].*PLATFORM-DEFAULT.*tax\.filingPeriods.*product-choice")
        v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[{**entry, "paths": ["eInvoicing.mode"]}]))
        self.f._assert_loads(v)  # listed for SA
        v = self.mutate("evidence.json", lambda r: r.update(
            factsOutsideSchema=[{**entry, "paths": ["localeDefaults.week.startDay"]}]))
        self.f._assert_loads(v)  # not locked

    def test_ci_pending_check_is_not_weaker_than_production(self) -> None:
        """Low 3: CI's `pending()` must also refuse a resolution whose `by` is no founder."""
        open_entry = {**BLOCKER, "resolution": dict(RESOLVED, by="synthetic-nobody")}
        self.assertEqual(pending({"goLiveBlockers": [open_entry]}), [open_entry])
        self.assertEqual(pending({"pendingRefs": [{**PENDING_REF, "resolution": dict(RESOLVED, by="SAYEGH9")}]}), [])
        self.assertEqual(pending({"goLiveBlockers": [{**BLOCKER, "resolution": dict(RESOLVED)}]}), [])
        self.assertEqual(len(pending({"goLiveBlockers": [BLOCKER]})), 1)

    def test_malformed_outside_entries_are_refused(self) -> None:
        for entry in (None, "x", {"claim": "x"}, {"claim": "x", "status": "maybe"},
                      {"claim": "x", "status": "UNVERIFIED", "paths": "tax"},
                      {"claim": "x", "status": "UNVERIFIED", "paths": [7]},
                      {"claim": "x", "status": "UNVERIFIED", "paths": ["tax.nonexistent"]}):
            with self.subTest(entry=entry):
                v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema=[entry]))
                self.refuse(v, "factsOutsideSchema")
        v = self.mutate("evidence.json", lambda r: r.update(factsOutsideSchema="UNVERIFIED"))
        self.refuse(v, "factsOutsideSchema")

    def test_shipped_packs_stay_refused_in_production_and_load_in_sandbox(self) -> None:
        for code in ("SA", "AE", "EG", "QA"):
            with self.subTest(code=code):
                with self.assertRaises(PackValidationError) as ctx:
                    load_country_pack(code, PACKS_DIR, version="0.1.0")
                self.assertTrue(any("open" in reason and ("pendingRefs" in reason or "goLiveBlockers" in reason)
                                    for reason in ctx.exception.errors), ctx.exception.errors)
                self.assertEqual(load_country_pack(code, PACKS_DIR, version="0.1.0", environment="sandbox")["countryCode"], code)


class TestEvidenceStatusMatchesLabels(_Fixture):
    """Low 2: the pack's evidenceStatus claim must agree with the fact labels."""

    def test_verified_official_needs_official_facts(self) -> None:
        # PLATFORM-DEFAULT-only coverage is refused by the product-choice list (TestProductChoiceList).
        v = self.mutate("evidence.json", lambda record: record["facts"][0].update(status="SECONDARY"))
        self.refuse(v, "evidenceStatus.*verified_official")

    def test_one_secondary_locked_leaf_breaks_a_verified_official_claim(self) -> None:
        v = self.f._write("certified", "verified_official")
        pack, record = self.f._record(v, "pack.json"), self.f._record(v, "evidence.json")
        self.back_leaf(record, pack, "tax.filingPeriods", "SECONDARY")
        self.f._save(v, "evidence.json", record)
        self.refuse(v, "evidenceStatus.*verified_official.*tax.filingPeriods")

    def test_secondary_claim_accepts_official_and_secondary_facts(self) -> None:
        v = self.f._write("certified", "secondary")
        pack, record = self.f._record(v, "pack.json"), self.f._record(v, "evidence.json")
        self.back_leaf(record, pack, "tax.filingPeriods", "VERIFIED-OFFICIAL")
        self.f._save(v, "evidence.json", record)
        self.f._assert_loads(v)

    def test_a_listed_platform_default_does_not_break_a_verified_official_claim(self) -> None:
        self.f._assert_loads(self.with_default("eInvoicing.mode"))


class TestStrictJson(_Fixture):
    """Low 3: duplicate keys are refused (the last value must never silently win)."""

    DUPLICATE = '{"status": "certified", "status": "draft"}'

    def test_duplicate_keys_in_pack_json_are_refused_in_every_environment(self) -> None:
        v = self.f._write("certified", "verified_official")
        path = self.f.packs_dir / "sa" / v / "pack.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('"status": "certified"', '"status": "draft", "status": "certified"', 1),
                        encoding="utf-8")
        self.assertIn('"status": "draft", "status": "certified"', path.read_text(encoding="utf-8"))
        for environment in ("sandbox", "test", "production"):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(PackValidationError, "(?i)duplicate"):
                    load_country_pack("SA", self.f.packs_dir, version=v, environment=environment)

    def test_duplicate_keys_in_the_unpinned_scan_are_refused_not_skipped(self) -> None:
        v = self.f._write("certified", "verified_official")
        path = self.f.packs_dir / "sa" / v / "pack.json"
        path.write_text(path.read_text(encoding="utf-8").replace(
            '"testOnly": false', '"testOnly": true, "testOnly": false', 1), encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "(?i)duplicate"):
            load_country_pack("SA", self.f.packs_dir, environment="sandbox")

    def test_duplicate_keys_in_companions_are_refused_in_production(self) -> None:
        for filename, top, nested in (
            ("manifest.json", '"id": "country.sa", "id": "country.xx"', None),
            ("evidence.json", '"version": "9.9.9", "version"', None),
            ("evidence.json", None, '"founder": "eldon", "founder"'),
        ):
            with self.subTest(filename=filename, top=top, nested=nested):
                v = self.f._write("certified", "verified_official")
                path = self.f.packs_dir / "sa" / v / filename
                text = path.read_text(encoding="utf-8")
                if filename == "manifest.json":
                    text = text.replace('"id": "country.sa"', top, 1)
                elif top:
                    text = text.replace('"version"', top, 1)
                else:
                    text = text.replace('"founder"', nested, 1)
                path.write_text(text, encoding="utf-8")
                self.refuse(v, f"{filename}.*(?i:duplicate)")


class TestManifestMeaning(_Fixture):
    """Low 4: manifest values the contract allows but a production country pack must not have."""

    def test_wrong_kind_is_refused(self) -> None:
        v = self.mutate("manifest.json", lambda m: m.update(kind="configurable"))
        self.refuse(v, "manifest.json.kind")

    def test_touches_ledger_or_tax_must_be_true(self) -> None:
        v = self.mutate("manifest.json", lambda m: m["certification"].update(touchesLedgerOrTax=False))
        self.refuse(v, "touchesLedgerOrTax")

    def test_retired_lifecycle_is_refused_but_active_and_deprecated_are_not(self) -> None:
        retired = self.mutate("manifest.json", lambda m: m.update(
            lifecycle={"status": "retired", "migrationNote": "synthetic"}))
        self.refuse(retired, "lifecycle.status")
        for status in ("active", "deprecated"):
            with self.subTest(status=status):
                lifecycle = {"status": status, **({"migrationNote": "synthetic"} if status != "active" else {})}
                self.f._assert_loads(self.mutate("manifest.json", lambda m: m.update(lifecycle=lifecycle)))

    def test_future_certified_at_is_refused(self) -> None:
        for stamp in ("9999-01-01T00:00:00Z", (date.today() + timedelta(days=2)).isoformat() + "T00:00:00Z",
                      "2999-01-01T00:00:00+14:00"):
            with self.subTest(stamp=stamp):
                v = self.mutate("manifest.json", lambda m: m["certification"].update(certifiedAt=stamp))
                self.refuse(v, "certifiedAt")

    def test_requires_must_resolve_to_registered_components_or_capabilities(self) -> None:
        registry = tempfile.TemporaryDirectory()
        self.addCleanup(registry.cleanup)
        components = Path(registry.name)
        (components / "finance" / "vat").mkdir(parents=True)
        (components / "finance" / "vat" / "manifest.json").write_text(json.dumps(self.valid_provider(
            "finance.vat_synthetic", "0.1.0", "finance.vat.synthetic_cap")), encoding="utf-8")
        (components / "bad").mkdir()
        (components / "bad" / "manifest.json").write_text("{", encoding="utf-8")  # unreadable entries register nothing
        ok = [{"component": "finance.vat_synthetic", "versionRange": ">=0.1.0"},
              {"capability": "finance.vat.synthetic_cap", "versionRange": ">=0.1.0"}]
        for label, requires, resolves in (
            ("component and capability", ok, True),
            ("unknown component", [{"component": "finance.missing", "versionRange": ">=0.1.0"}], False),
            ("unknown capability", [{"capability": "finance.missing.cap", "versionRange": ">=0.1.0"}], False),
            ("capability named as component", [{"component": "finance.vat.synthetic_cap", "versionRange": ">=0.1.0"}], False),
        ):
            with self.subTest(requires=label):
                v = self.mutate("manifest.json", lambda m: m.update(requires=requires))
                with patch.object(certification, "COMPONENTS_ROOT", components):
                    if resolves:
                        self.f._assert_loads(v)
                    else:
                        with self.assertRaisesRegex(PackValidationError, "requires"):
                            load_country_pack("SA", self.f.packs_dir, version=v)
                for environment in ("sandbox", "test"):
                    self.f._assert_loads(v, environment=environment)

    def test_a_pack_cannot_satisfy_its_own_requirement(self) -> None:
        # A manifest inside the packs tree is not a registered component.
        v = self.mutate("manifest.json", lambda m: m.update(
            requires=[{"component": "country.sa", "versionRange": ">=0.1.0"}]))
        with patch.object(certification, "COMPONENTS_ROOT", self.f.packs_dir):
            with self.assertRaisesRegex(PackValidationError, "requires"):
                load_country_pack("SA", self.f.packs_dir, version=v)


class TestEvidenceKeySet(_Fixture):
    """Low 5: the closed key set covers the whole evidence.json, not only `certification`."""

    def test_unknown_top_level_keys_are_refused(self) -> None:
        for key, value in (("revoked", True), ("approved", True), ("signedOff", {"by": "x"})):
            with self.subTest(key=key):
                v = self.mutate("evidence.json", lambda r: r.update({key: value}))
                self.refuse(v, f"evidence.json.*unknown.*{key}")

    def test_known_keys_are_accepted(self) -> None:
        v = self.mutate("evidence.json", lambda r: r.update(
            purpose="synthetic", arabicLabels={"note": "synthetic"}, arabicReviewNote="synthetic",
            factsOutsideSchema=[], pendingRefs=[], goLiveBlockers=[]))
        self.f._assert_loads(v)

    def test_shipped_evidence_files_use_only_known_keys(self) -> None:
        for code in ("sa", "ae", "eg", "qa"):
            with self.subTest(code=code):
                record = json.loads((PACKS_DIR / code / "0.1.0" / "evidence.json").read_text(encoding="utf-8"))
                self.assertLessEqual(set(record), evidence_mod.EVIDENCE_TOP_LEVEL_KEYS)


class TestPeopleBinding(_Fixture):
    """Low 6: founder and reviewer are bound to people through the lanes.json founders map."""

    def test_founder_must_be_the_owner_s_founder(self) -> None:
        def founder_eldon(record):
            record["certification"]["founder"] = "eldon"
        v = self.mutate("evidence.json", founder_eldon)  # owner sayegh9 is the partner
        self.refuse(v, "founder.*owner")

    def test_owner_must_be_a_known_founder_login(self) -> None:
        v = self.mutate("manifest.json", lambda m: m["owner"].update(github="synthetic-owner"))
        self.refuse(v, "owner.github.*founder")

    def test_reviewer_must_be_a_founder_login(self) -> None:
        for reviewers in (["synthetic-reviewer"], ["EldonsLogic", "synthetic-reviewer"]):
            with self.subTest(reviewers=reviewers):
                v = self.mutate("manifest.json", lambda m: m["certification"].update(reviewedBy=reviewers))
                self.refuse(v, "reviewedBy.*founder")

    def test_reviewer_login_case_is_ignored(self) -> None:
        self.f._assert_loads(self.mutate("manifest.json", lambda m: m["certification"].update(reviewedBy=["eldonslogic"])))

    def test_unusable_founders_map_fails_closed(self) -> None:
        v = self.f._write("certified", "verified_official")
        for label, text in (("missing", None), ("malformed", "{"), ("no founders", "{}"),
                            ("founders not object", '{"founders": []}'),
                            ("unknown founder name", '{"founders": {"sayegh9": "partner", "EldonsLogic": "root"}}'),
                            ("duplicate key", '{"founders": {"a": "eldon", "a": "partner"}}')):
            with self.subTest(map=label):
                path = Path(self.f._tmp.name) / f"lanes-{label.replace(' ', '-')}.json"
                if text is not None:
                    path.write_text(text, encoding="utf-8")
                with patch.object(certification, "LANES_FILE", path):
                    with self.assertRaisesRegex(PackValidationError, "founders"):
                        load_country_pack("SA", self.f.packs_dir, version=v)
                    self.f._assert_loads(v, environment="sandbox")


class TestHygiene(_Fixture):
    """Low 7: deep nesting refuses cleanly; `accessed` has a lower bound."""

    def test_deeply_nested_companions_refuse_without_crashing(self) -> None:
        for depth in (500, 900, 100_000):
            nested = "[" * depth + "]" * depth
            for filename in ("manifest.json", "evidence.json"):
                with self.subTest(filename=filename, depth=depth):
                    v = self.f._write("certified", "verified_official")
                    (self.f.packs_dir / "sa" / v / filename).write_text('{"x": ' + nested + "}", encoding="utf-8")
                    with self.assertRaises(PackValidationError):
                        load_country_pack("SA", self.f.packs_dir, version=v)
                    self.f._assert_loads(v, environment="sandbox")

    def test_deeply_nested_pack_refuses_without_crashing(self) -> None:
        for depth in (500, 100_000):
            with self.subTest(depth=depth):
                v = self.f._write("certified", "verified_official")
                (self.f.packs_dir / "sa" / v / "pack.json").write_text(
                    '{"x": ' + "[" * depth + "]" * depth + "}", encoding="utf-8")
                for environment in ("sandbox", "production"):
                    with self.assertRaises(PackValidationError):
                        load_country_pack("SA", self.f.packs_dir, version=v, environment=environment)

    def test_access_date_has_a_lower_bound(self) -> None:
        today = date.today().isoformat()
        base = {"url": "https://example.org/a"}
        self.assertEqual(evidence_mod.source_violations(dict(base, accessed="2026-01-01"), today), [])
        for accessed in ("0001-01-01", "1999-12-31", "2025-12-31"):
            with self.subTest(accessed=accessed):
                self.assertTrue(any("before" in r for r in
                                    evidence_mod.source_violations(dict(base, accessed=accessed), today)))
        v = self.mutate("evidence.json", lambda r: r["facts"][0].update(
            sources=[{"url": "https://example.org/synthetic", "accessed": "0001-01-01"}]))
        self.refuse(v, "before")


class TestCiCertifiabilityCheck(unittest.TestCase):
    """The CI-only shipped-pack check agrees with production: only open entries hold a pack at `tested`."""

    def test_resolved_entries_no_longer_hold_a_pack_below_certified(self) -> None:
        pack = {"status": "certified", "evidenceStatus": "verified_official"}
        manifest = {"certification": {"level": "certified"}}
        resolved = {"goLiveBlockers": [{**BLOCKER, "resolution": dict(RESOLVED)}],
                    "pendingRefs": [{**PENDING_REF, "resolution": dict(RESOLVED)}]}
        self.assertEqual(certifiability_violations(pack, manifest, resolved), [])
        for key, entry in (("goLiveBlockers", BLOCKER), ("pendingRefs", PENDING_REF)):
            with self.subTest(key=key):
                self.assertTrue(certifiability_violations(pack, manifest, {**resolved, key: [dict(entry)]}))


if __name__ == "__main__":
    unittest.main()
