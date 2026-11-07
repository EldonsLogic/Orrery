import pytest

from registry import Registry
from registry_helpers import REGISTRY_DIR, variant


@pytest.fixture(scope="module")
def reg():
    items = [__import__("registry_helpers").fixture_manifest("core.item")]
    items += [variant(version=v) for v in ("0.0.9", "0.2.0", "1.0.0", "1.1.0-beta.1")]
    return Registry.from_manifests(items)


def test_versions_sorted_by_semver(reg):
    assert reg.versions("core.item") == ["0.0.9", "0.1.0", "0.2.0", "1.0.0", "1.1.0-beta.1"]
    assert reg.versions("core.unknown") == []


def test_resolve_ranges(reg):
    assert reg.resolve("core.item", "^0.1.0")["version"] == "0.1.0"
    assert reg.resolve("core.item", "^0.0.9")["version"] == "0.0.9"
    assert reg.resolve("core.item", ">=0.1.0 <1.0.0")["version"] == "0.2.0"
    assert reg.resolve("core.item", ">=0.1.0")["version"] == "1.0.0"  # prerelease not picked by a plain range
    assert reg.resolve("core.item", "^0.0.9 || ^1.0.0")["version"] == "1.0.0"
    assert reg.resolve("core.item", "~0.2.0")["version"] == "0.2.0"
    assert reg.resolve("core.item", "^7.0.0") is None
    assert reg.resolve("core.unknown", "*") is None


def test_resolve_invalid_range_raises(reg):
    with pytest.raises(ValueError):
        reg.resolve("core.item", "not a range")


def test_get_returns_copy(reg):
    m = reg.get("core.item", "0.1.0")
    m["name"]["en"] = "changed"
    assert reg.get("core.item", "0.1.0")["name"]["en"] != "changed"
    assert reg.get("core.item", "9.9.9") is None


def test_provides_capability_and_function():
    full = Registry.load(REGISTRY_DIR)
    assert full.provides("compliance.zatca_sa.calculate") == [("compliance.zatca_sa", "0.1.0")]
    assert full.provides("compliance.zatca.qr_payload") == [("compliance.zatca_sa", "0.1.0")]
    assert full.provides("nothing.provides.this") == []
    assert full.provides("entity") == []  # artifact types are not names


def test_validation_context_shape():
    full = Registry.load(REGISTRY_DIR)
    ctx = full.as_validation_context_registry()
    assert list(ctx) == full.list_components()
    assert all(isinstance(v, list) and v and all(m["id"] == k for m in v) for k, v in ctx.items())
