"""Shared checks over every real country pack under `packs/` (CMP-028, CMP-029, CMP-031).

One convention for all packs: per-fact sources live in `evidence.json` beside `pack.json`, because
`pack.schema.json` has no per-fact evidence field and caps `notes` at 500 characters. Pack-specific
facts stay in each pack's own test module (`test_pack_<cc>.py` or similar).
"""

from __future__ import annotations

from datetime import date
import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from components.compliance.country_pack import load_country_pack, validate_pack
from components.compliance.country_pack.tests.pack_checks import (
    EVIDENCE_LABELS,
    EVIDENCED_AREAS,
    LOADER_ARTIFACT,
    MANIFEST_SCHEMA,
    MATHS_KEY,
    NUMERIC_LEAVES,
    PACKS_DIR,
    REPO_ROOT,
    arabic_strings,
    blueprint_modes,
    certifiability_violations,
    covered,
    evidence_entries,
    get,
    keys,
    labelled,
    leaves,
    load_triplet,
    manifest_text_violations,
    pending,
    rate_like_violations,
    read_json,
    real_pack_dirs,
    recorded_status_violations,
    referenced_requirements,
    repo_components,
    requires_key,
    source_violations,
)

EXPECTED_PACKS = {"ae", "eg", "qa", "sa"}
BASE_FILES = {"pack.json", "manifest.json", "evidence.json"}
# Reviewed snapshot of every entry that claims a read source (review of #267, Medium). Raising or lowering
# any label to or from these two fails until a reviewer updates this snapshot in the same PR.
SOURCED_LABELS = {
    "ae": {
        "VERIFIED-OFFICIAL": {"eInvoicing.mode", "blocker:uae_e_invoicing"},
        "SECONDARY": set(),
    },
    "eg": {"VERIFIED-OFFICIAL": {"eInvoicing.authority"}, "SECONDARY": set()},
    "qa": {"VERIFIED-OFFICIAL": set(), "SECONDARY": set()},
    "sa": {
        "VERIFIED-OFFICIAL": {"eInvoicing.required|eInvoicing.authority", "blocker:zatca_phase2"},
        "SECONDARY": {
            "tax.vatSupported|tax.taxCodesRef",
            "eInvoicing.mandatoryDocumentLanguages|printFormats.mandatoryLanguages",
        },
    },
}
# Packs whose research held facts the pack schema has no field for, and how many (review of #267, Low).
FACTS_OUTSIDE_SCHEMA = {"ae": 0, "eg": 1, "qa": 3, "sa": 0}


class _AllPacks(unittest.TestCase):
    def setUp(self) -> None:
        self.dirs = real_pack_dirs()
        self.data = {f"{d.parent.name}/{d.name}": (d, *load_triplet(d)) for d in self.dirs}


class TestLayout(_AllPacks):
    def test_every_phase_one_pack_is_checked(self) -> None:
        self.assertEqual({d.parent.name for d in self.dirs}, EXPECTED_PACKS)

    def test_version_folder_holds_only_the_convention_files(self) -> None:
        # No SOURCES.md or README.md source tables: evidence.json is the one place for sources.
        for key, (vdir, _, manifest, _) in self.data.items():
            allowed = set(BASE_FILES)
            strings_file = manifest.get("i18n", {}).get("stringsFile")
            if strings_file:
                allowed.add(strings_file)
                self.assertTrue((vdir / strings_file).is_file(), strings_file)
            with self.subTest(pack=key):
                self.assertEqual({p.name for p in vdir.iterdir()}, allowed)

    def test_real_root_holds_no_test_only_pack(self) -> None:
        for key, (_, pack, _, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertIs(pack.get("testOnly"), False)

    def test_packs_load_validate_and_point_at_evidence(self) -> None:
        for key, (vdir, pack, _, evidence) in self.data.items():
            with self.subTest(pack=key):
                loaded = load_country_pack(pack["countryCode"], PACKS_DIR, version=vdir.name, environment="test")
                self.assertEqual(validate_pack(loaded), [])
                self.assertEqual(vdir.parent.name, pack["packId"])
                self.assertEqual(vdir.name, pack["version"])
                self.assertEqual(pack["componentId"], f"country.{pack['packId']}")
                self.assertEqual((evidence["packId"], evidence["version"]), (pack["packId"], pack["version"]))
                self.assertIn("evidence.json", pack["notes"])

    def test_packs_readme_is_generic(self) -> None:
        text = (PACKS_DIR / "README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# "))
        self.assertIn("components/compliance/country_pack/packs/", text)
        self.assertIn("evidence.json", text)
        self.assertIn("test_pack_<cc>.py", text)
        self.assertIn("test_country_packs.py", text)
        self.assertNotIn("test_pack_sa_ae.py", text)  # generic, so other packs' tests fit


class TestEvidence(_AllPacks):
    def test_every_fact_has_a_label_and_sources(self) -> None:
        today = date.today().isoformat()
        for key, (_, pack, _, evidence) in self.data.items():
            for eid, fact in evidence_entries(evidence):
                with self.subTest(pack=key, fact=eid):
                    self.assertIn(fact["status"], EVIDENCE_LABELS)
                    self.assertTrue(fact["claim"])
                    for path in fact.get("paths", [fact["backs"]] if fact.get("backs") else []):
                        get(pack, path)  # every cited path exists in the pack
                    sources = fact.get("sources", [])
                    self.assertEqual([v for s in sources for v in source_violations(s, today)], [])
                    if fact["status"] in ("VERIFIED-OFFICIAL", "SECONDARY"):
                        read = [s for s in sources if "accessed" in s]
                        self.assertTrue(read, f"{fact['status']} needs a read source with an access date")
                    if fact["status"] == "PLATFORM-DEFAULT":
                        self.assertTrue(fact.get("ref"), "a platform default names the decision or doc")

    def test_unread_rule_is_structural(self) -> None:
        # Review of #267 (Low): an unread source is marked `"read": false`, not recognised by note wording.
        today = date.today().isoformat()
        unread = {"url": "https://example.org/a", "read": False, "note": "snippet per research 2.4"}
        self.assertEqual(source_violations(unread, today), [])
        for label, src in {
            "unread with date": dict(unread, accessed="2026-11-18"),
            "unread without note": {"url": "https://example.org/a", "read": False},
            "read true": dict(unread, read=True, accessed="2026-11-18"),
            "reworded snippet keeps date": {"url": "https://example.org/a", "accessed": "2026-11-18",
                                            "note": "snippet per egypt-research.md 2.4"},
            "excerpt keeps date": {"url": "https://example.org/a", "accessed": "2026-11-18",
                                   "note": "Search Excerpt only"},
            "no date no flag": {"url": "https://example.org/a", "note": "seen once"},
            "future date": {"url": "https://example.org/a", "accessed": "2999-01-01"},
            "http": {"url": "http://example.org/a", "accessed": "2026-11-18"},
        }.items():
            with self.subTest(mutation=label):
                self.assertTrue(source_violations(src, today))

    def test_every_unread_source_in_the_packs_is_flagged(self) -> None:
        for key, (_, _, _, evidence) in self.data.items():
            for eid, entry in evidence_entries(evidence):
                for src in entry.get("sources", []):
                    with self.subTest(pack=key, fact=eid, url=src["url"]):
                        self.assertIs("accessed" in src, src.get("read", True))

    def test_sourced_labels_are_pinned(self) -> None:
        for key, (_, pack, _, evidence) in self.data.items():
            with self.subTest(pack=key):
                for label, expected in SOURCED_LABELS[pack["packId"]].items():
                    self.assertEqual(labelled(evidence, label), expected, label)

    def test_label_pin_has_teeth(self) -> None:
        _, _, _, evidence = self.data["eg/0.1.0"]
        raised = json.loads(json.dumps(evidence))
        next(f for f in raised["facts"] if f["paths"] == ["tax.filingPeriods"])["status"] = "VERIFIED-OFFICIAL"
        self.assertNotEqual(labelled(raised, "VERIFIED-OFFICIAL"), SOURCED_LABELS["eg"]["VERIFIED-OFFICIAL"])
        self.assertTrue(recorded_status_violations(raised))

    def test_recorded_status_agrees_with_label(self) -> None:
        for key, (_, _, _, evidence) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual(recorded_status_violations(evidence), [])

    def test_facts_outside_schema_are_kept(self) -> None:
        for key, (_, pack, _, evidence) in self.data.items():
            with self.subTest(pack=key):
                expected = FACTS_OUTSIDE_SCHEMA[pack["packId"]]
                if expected:
                    self.assertIn("factsOutsideSchema", evidence)
                self.assertEqual(len(evidence.get("factsOutsideSchema", [])), expected)
                for fact in evidence.get("factsOutsideSchema", []):
                    self.assertNotIn("paths", fact, "a fact outside the schema backs no pack path")

    def test_every_leaf_is_evidenced(self) -> None:
        for key, (_, pack, _, evidence) in self.data.items():
            paths = [p for fact in evidence["facts"] for p in fact["paths"]]
            for area in EVIDENCED_AREAS:
                for leaf, _ in leaves(pack[area], area):
                    with self.subTest(pack=key, leaf=leaf):
                        self.assertTrue(covered(leaf, paths), f"{leaf} has no evidence entry")

    def test_coverage_check_has_teeth(self) -> None:
        _, pack, _, evidence = self.data["qa/0.1.0"]
        paths = [p for fact in evidence["facts"] if "eInvoicing.archiveRetentionYears" not in fact["paths"]
                 for p in fact["paths"]]
        self.assertFalse(covered("eInvoicing.archiveRetentionYears", paths))

    def test_pending_refs_are_declared(self) -> None:
        for key, (_, pack, _, evidence) in self.data.items():
            declared = {(p["path"], p["value"]) for p in evidence["pendingRefs"]}
            found = {(path, val) for path, val in leaves(pack) if isinstance(val, str) and val.startswith("pending:")}
            for idx, tpl in enumerate(pack["printFormats"]["templates"]):
                if tpl["templateRef"].startswith("pending:"):
                    found.add((f"printFormats.templates[{idx}].templateRef", tpl["templateRef"]))
            with self.subTest(pack=key):
                self.assertLessEqual(found, declared)  # every pending: value is declared
                for p in evidence["pendingRefs"]:  # declared refs may also name ids that do not resolve yet
                    self.assertEqual(get(pack, p["path"]), p["value"])
                    self.assertTrue(p["blockedBy"])

    def test_go_live_blockers_are_declared_and_unresolvable(self) -> None:
        ids, caps = repo_components()
        for key, (_, _, _, evidence) in self.data.items():
            for blocker in evidence["goLiveBlockers"]:
                with self.subTest(pack=key, blocker=blocker["id"]):
                    self.assertTrue(blocker["blockedBy"])
                    self.assertTrue(blocker["refs"])
                    if "requires" in blocker:
                        kind, name = requires_key(blocker["requires"])
                        self.assertNotIn(name, ids if kind == "component" else caps, "placeholder must not resolve yet")

    def test_arabic_labels_marked_unreviewed(self) -> None:
        for key, (vdir, pack, manifest, evidence) in self.data.items():
            listed = {(a["file"], a["path"]): a for a in evidence["arabicLabels"]}
            found = {("pack.json", p): t for p, t in arabic_strings(pack)}
            found.update({("manifest.json", p): t for p, t in arabic_strings(manifest)})
            strings_file = manifest.get("i18n", {}).get("stringsFile")
            if strings_file:
                found.update({(strings_file, p): t for p, t in arabic_strings(read_json(vdir / strings_file))})
            with self.subTest(pack=key):
                self.assertTrue(found)
                self.assertEqual(set(listed), set(found))
                for label, text in found.items():
                    self.assertEqual(listed[label]["text"], text)
                    self.assertEqual(listed[label]["review"], "unreviewed")
                    self.assertEqual(listed[label]["rule"], "ADR-0033")


class TestStatus(_AllPacks):
    def test_status_matches_level_and_evidence_unverified_while_pending(self) -> None:
        for key, (_, pack, manifest, evidence) in self.data.items():
            cert = manifest["certification"]
            with self.subTest(pack=key):
                self.assertEqual(pack["status"], cert["level"])
                self.assertIs(cert["touchesLedgerOrTax"], True)
                self.assertEqual(cert["reviewedBy"], [])
                self.assertTrue(pending(evidence), "every pack still has pending references")
                self.assertEqual(pack["evidenceStatus"], "unverified")
                self.assertEqual(certifiability_violations(pack, manifest, evidence), [])

    def test_pending_references_keep_packs_uncertifiable(self) -> None:
        for key, (_, pack, manifest, evidence) in self.data.items():
            with self.subTest(pack=key):
                for level in ("reviewed", "certified", "regulated"):
                    self.assertTrue(certifiability_violations(dict(pack, status=level), manifest, evidence), level)
                    cert = dict(manifest["certification"], level=level)
                    self.assertTrue(certifiability_violations(pack, dict(manifest, certification=cert), evidence))
                raised = dict(pack, evidenceStatus="verified_official")
                self.assertTrue(certifiability_violations(raised, manifest, evidence))


class TestManifests(_AllPacks):
    def test_manifest_valid_and_matches_pack(self) -> None:
        validator = Draft202012Validator(read_json(MANIFEST_SCHEMA), format_checker=FormatChecker())
        for key, (_, pack, manifest, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual([e.message for e in validator.iter_errors(manifest)], [])
                self.assertEqual(manifest["id"], pack["componentId"])
                self.assertEqual(manifest["version"], pack["version"])
                self.assertEqual(manifest["name"], pack["name"])
                self.assertEqual(manifest["kind"], "rigid")
                self.assertEqual(manifest["parameters"], [])
                self.assertTrue(manifest["tests"])
                for test in manifest["tests"]:
                    self.assertFalse(test["path"].startswith(("/", ".")), "test path is repo-root relative")
                    self.assertTrue((REPO_ROOT / test["path"]).is_file(), test["path"])

    def test_requires_equals_referenced_components(self) -> None:
        # The compiler fails closed on unmet `requires`, so every component a pack points at,
        # including ones that do not exist yet, must be listed there, and nothing else.
        for key, (_, pack, manifest, evidence) in self.data.items():
            expected = referenced_requirements(pack, evidence)
            required = [requires_key(r) for r in manifest["requires"]]
            with self.subTest(pack=key):
                self.assertTrue(expected)
                self.assertNotIn(("component", pack["componentId"]), expected)
                self.assertEqual(len(required), len(set(required)), "no duplicate requires")
                self.assertEqual(set(required), expected)
                for blocker in evidence.get("goLiveBlockers", []):  # a blocker's entry is copied verbatim
                    if "requires" in blocker:
                        self.assertIn(blocker["requires"], manifest["requires"])

    def test_one_provides_convention(self) -> None:
        for key, (_, pack, manifest, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual(
                    manifest["provides"],
                    [{"capability": f"country.{pack['packId']}.pack_metadata", "artifacts": [LOADER_ARTIFACT]}],
                )


class TestDeclarativeOnly(_AllPacks):
    def test_no_maths_keys_or_stray_numbers(self) -> None:
        for key, (_, pack, _, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual([k for k in keys(pack) if MATHS_KEY.search(k)], [])
                for path, val in leaves(pack):
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        self.assertIn(path, NUMERIC_LEAVES)

    def test_no_rate_like_strings_in_locked_values_notes_or_names(self) -> None:
        modes = blueprint_modes()
        self.assertIn("zatca_phase1", modes)
        for key, (_, pack, _, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual(rate_like_violations(pack, modes), [])

    def test_rate_like_mutations_are_caught(self) -> None:
        modes = blueprint_modes()
        for key, (_, base, _, _) in self.data.items():
            mutations = {
                "taxCodesRef": ("tax", "taxCodesRef", "vat:0.15"),
                "mode": ("eInvoicing", "mode", "standard_15_pct"),
                "retention": ("eInvoicing", "archiveRetentionYears", 15),
                "retention zero": ("eInvoicing", "archiveRetentionYears", 0),
                "artifact": ("coaTemplate", "artifactRef", "chart_vat_5pct.json"),
                "range": ("coaTemplate", "versionRange", "0.15"),
                "pattern": ("tax", "vatNumberPattern", "15%"),
                "currency": ("localeDefaults", "currency", "SAR15"),
                "notes percent": (None, "notes", "Not for tenants: VAT 15% (ADR-0033)."),
                "notes digits": (None, "notes", "VAT is 5 percent, see evidence.json."),
                "notes years": (None, "notes", "Keep 5yr retention, see evidence.json."),
                "notes phase rate": (None, "notes", "Phase 2 applies at 15 percent, see evidence.json."),
                "name": ("name", "en", "Country pack 14%"),
            }
            for label, (area, field, value) in mutations.items():
                with self.subTest(pack=key, mutation=label):
                    pack = json.loads(json.dumps(base))
                    (pack[area] if area else pack)[field] = value
                    self.assertTrue(rate_like_violations(pack, modes))

    def test_no_rate_like_strings_in_manifest_descriptions(self) -> None:
        # Review of #267 (Low): figures live in evidence.json, not in the manifest description.
        for key, (_, _, manifest, _) in self.data.items():
            with self.subTest(pack=key):
                self.assertEqual(manifest_text_violations(manifest), [])
                for text in ("standard 14% VAT", "5-year retention", "revenue of AED 50 million"):
                    mutated = dict(manifest, description=f"{manifest['description']} {text}")
                    self.assertTrue(manifest_text_violations(mutated), text)

    def test_free_text_allows_record_ids_dates_and_versions(self) -> None:
        modes = blueprint_modes()
        _, base, _, _ = self.data["sa/0.1.0"]
        pack = dict(base, notes="ZATCA Phase 2 pending; out of v1 scope (CMP-015, ADR-0033, Q-559); accessed 2026-11-18; see evidence.json.")
        self.assertEqual(rate_like_violations(pack, modes), [])


if __name__ == "__main__":
    unittest.main()
