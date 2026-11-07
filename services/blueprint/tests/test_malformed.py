import copy

import pytest

from fixture_registry import load_example
from test_example import full_ctx
from validator import ValidationContext, validate


@pytest.mark.parametrize("bad", [None, 5, "text", [], [1, 2], {}, {"meta": 1}, {"entities": "x"}, True])
def test_non_blueprints_return_errors_not_exceptions(bad):
    rep = validate(bad)
    assert not rep.ok and rep.errors
    rep = validate(bad, ValidationContext(registry={}, assets={}, entitlements=set()))
    assert not rep.ok


def test_missing_sections_are_reported():
    for section in ("meta", "company", "entities", "roles", "compliance", "i18n", "branding", "locations"):
        bp = load_example()
        del bp[section]
        rep = validate(bp, full_ctx())
        assert any(e.code == "BP-SCHEMA-001" for e in rep.errors), section


def test_wrongly_typed_nested_values_never_raise():
    bp = load_example()
    bp["entities"][0]["fields"] = "nope"
    bp["workflows"][0]["states"] = [1, None, {"id": 5}]
    bp["roles"][0]["permissions"] = {"x": 1}
    bp["approvals"][0]["steps"] = [{"order": "a"}, 3]
    bp["reports"] = [None, {"metrics": "m", "visibleToRoles": 4}]
    bp["branding"]["primaryColour"] = 12
    bp["meta"]["locales"] = "ar"
    bp["company"]["locale"]["week"] = []
    rep = validate(bp, full_ctx())
    assert not rep.ok


def test_deep_garbage_does_not_crash():
    bp = load_example()
    for key in list(bp):
        mutated = copy.deepcopy(bp)
        mutated[key] = [[{"id": [1]}], {"id": {"a": 1}}, None]
        validate(mutated, full_ctx())  # must not raise
