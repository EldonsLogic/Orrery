import json

from registry import Registry
from registry_helpers import BLUEPRINT, REGISTRY_DIR
from validator import ValidationContext, validate


def _bp():
    return json.loads(BLUEPRINT.read_text(encoding="utf-8"))


def test_round_trip_through_validator_zero_errors():
    reg = Registry.load(REGISTRY_DIR)
    bp = _bp()
    ctx = ValidationContext(registry=reg.as_validation_context_registry(), entitlements=set())
    rep = validate(bp, ctx)
    assert rep.errors == [], [str(e) for e in rep.errors]
    assert not any(w.code.startswith("BP-CMP") for w in rep.warnings)


def test_blueprint_components_compatible():
    reg = Registry.load(REGISTRY_DIR)
    bp = _bp()
    results = reg.compatible(bp["components"], bp["meta"]["engineTarget"])
    assert len(results) == len(bp["components"])
    assert all(r.ok for r in results), [r.as_dict() for r in results if not r.ok]
    assert [r.component for r in results] == sorted(r.component for r in results)
    assert all(r.resolved_version for r in results)


def test_adapter_and_version_set_failures():
    reg = Registry.load(REGISTRY_DIR)
    comps = [{"id": "core.item", "versionRange": "^0.1.0"}]
    r = reg.compatible(comps, {"adapter": "other_engine", "versionSet": "set-example"})[0]
    assert not r.ok and "adapter" in r.reasons[0]
    r = reg.compatible(comps, {"adapter": "change_engine", "versionSet": "set-unknown"})[0]
    assert not r.ok and "version set" in r.reasons[0]
    r = reg.compatible(comps, {"adapter": "other_engine", "versionSet": "set-unknown"})[0]
    assert len(r.reasons) == 2
    r = reg.compatible(comps, {"adapter": "change_engine"})[0]
    assert r.ok  # versionSet is optional


def test_missing_component_range_and_target():
    reg = Registry.load(REGISTRY_DIR)
    target = {"adapter": "change_engine", "versionSet": "set-example"}
    comps = [{"id": "core.nothing", "versionRange": "*"}, {"id": "core.item", "versionRange": "^5.0.0"},
             {"id": "core.item", "versionRange": "nonsense"}, {"id": 3}, "x"]
    results = reg.compatible(comps, target)
    assert len(results) == 5 and not any(r.ok for r in results)
    assert all(r.reasons for r in results)
    r = reg.compatible([{"id": "core.item", "versionRange": "^0.1.0"}], None)[0]
    assert r.ok and any("not checked" in n for n in r.notes)
    assert reg.compatible("not a list", target) == []
