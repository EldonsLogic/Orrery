import copy

from registry import Registry, admit
from registry_helpers import REGISTRY_DIR, codes, fixture_manifest, variant


def test_all_sixteen_fixtures_admitted():
    reg = Registry.load(REGISTRY_DIR)
    assert reg.ok and reg.issues == []
    assert len(reg.list_components()) == 16
    assert reg.list_components() == sorted(reg.list_components())


def test_invalid_schema_rejected():
    m = variant(kind="nonsense")
    reg = Registry.from_manifests([m])
    assert codes(reg.errors) == ["REG-001"] and reg.list_components() == []


def test_unknown_extra_field_rejected():
    reg = Registry.from_manifests([variant(extra="x")])
    assert codes(reg.errors) == ["REG-001"]


def test_licence_not_recorded():
    reg = Registry.from_manifests([variant(licence={"spdx": "  "})])
    assert "REG-002" in codes(reg.errors) and reg.list_components() == []
    reg = Registry.from_manifests([variant(licence={"spdx": "NOASSERTION"})])
    assert "REG-002" in codes(reg.errors)
    reg = Registry.from_manifests([variant(licence={"spdx": "MIT"})])
    assert reg.ok


def test_licence_missing_is_schema_error():
    m = variant()
    del m["licence"]
    assert "REG-001" in codes(Registry.from_manifests([m]).errors)


def test_third_party_copyleft():
    tp = [{"name": "lib", "spdx": "AGPL-3.0-only", "source": "https://example.invalid/lib"}]
    assert "REG-009" in codes(Registry.from_manifests([variant(licence={"spdx": "MIT", "thirdParty": tp, "copyleftReviewed": True})]).errors)
    tp[0]["spdx"] = "GPL-3.0-only"
    assert "REG-009" in codes(Registry.from_manifests([variant(licence={"spdx": "MIT", "thirdParty": tp})]).errors)
    assert Registry.from_manifests([variant(licence={"spdx": "MIT", "thirdParty": tp, "copyleftReviewed": True})]).ok


def test_duplicate_id_version_different_content():
    a = fixture_manifest("core.item")
    b = copy.deepcopy(a)
    b["description"] = "A different fictional description for the same version."
    reg = Registry.from_manifests([a, b])
    assert codes(reg.errors) == ["REG-003"]
    assert "core.item" not in reg.list_components()


def test_duplicate_identical_content_is_collapsed():
    a = fixture_manifest("core.item")
    reg = Registry.from_manifests([a, copy.deepcopy(a)])
    assert reg.ok and reg.versions("core.item") == ["0.1.0"]


def _requiring(**req):
    return variant("sales.quote", requires=[req])


def test_unknown_requires_warns_then_errors_in_strict():
    m = _requiring(component="core.nothing_here", versionRange="^1.0.0")
    reg = Registry.from_manifests([m])
    assert reg.ok and codes(reg.warnings) == ["REG-004"] and reg.list_components() == ["sales.quote"]
    strict = Registry.from_manifests([m], strict=True)
    assert codes(strict.errors) == ["REG-004"] and strict.list_components() == []
    cap = _requiring(capability="nothing.here.at_all", versionRange="^1.0.0")
    assert codes(Registry.from_manifests([cap]).warnings) == ["REG-004"]


def test_unsatisfiable_requires_is_error():
    item = fixture_manifest("core.item")
    m = _requiring(component="core.item", versionRange="^9.0.0")
    reg = Registry.from_manifests([item, m])
    assert codes(reg.errors) == ["REG-005"]
    assert reg.list_components() == ["core.item"]
    bad_range = _requiring(component="core.item", versionRange="1.0.0 - 2.0.0")
    assert codes(Registry.from_manifests([item, bad_range]).errors) == ["REG-005"]


def test_satisfiable_requires_by_component_and_capability():
    item = fixture_manifest("core.item")
    cap = item["provides"][0]["capability"]
    ok1 = variant("sales.quote", requires=[{"component": "core.item", "versionRange": "^0.1.0"}])
    ok2 = variant("sales.credit_note", requires=[{"capability": cap, "versionRange": ">=0.1.0"}])
    reg = Registry.from_manifests([item, ok1, ok2], strict=True)
    assert reg.ok and len(reg.list_components()) == 3


def test_certified_without_ci_evidence_rejected():
    cert = {"level": "certified", "reviewedBy": ["example-reviewer"], "certifiedAt": "2026-11-01T08:00:00Z",
            "evidence": [{"kind": "review", "ref": "example-review-1"}]}
    reg = Registry.from_manifests([variant(certification=cert)])
    assert codes(reg.errors) == ["REG-006"]
    cert["evidence"].append({"kind": "ci_run", "ref": "example-run-1"})
    assert Registry.from_manifests([variant(certification=cert)]).ok


def test_regulated_needs_sandbox_evidence_when_test_is_blocking():
    tests = [{"id": "sandbox", "kind": "compliance_sandbox", "path": "tests/s.py", "blocking": True}]
    cert = {"level": "regulated", "reviewedBy": ["example-reviewer"], "certifiedAt": "2026-11-01T08:00:00Z",
            "evidence": [{"kind": "ci_run", "ref": "example-run-1"}]}
    assert codes(Registry.from_manifests([variant(tests=tests, certification=cert)]).errors) == ["REG-006"]
    cert["evidence"].append({"kind": "compliance_sandbox", "ref": "example-sandbox-1"})
    assert Registry.from_manifests([variant(tests=tests, certification=cert)]).ok


def test_draft_admitted_with_warning():
    reg = Registry.from_manifests([variant(certification={"level": "draft"})])
    assert reg.ok and codes(reg.warnings) == ["REG-010"]


def test_garbage_input_fails_closed():
    admitted, issues = admit([])
    assert admitted == [] and issues == []
    reg = Registry.from_manifests([None, 5, [], {"id": 3}])
    assert reg.list_components() == []
