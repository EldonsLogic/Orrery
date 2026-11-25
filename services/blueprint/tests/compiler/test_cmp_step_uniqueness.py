"""Step uniqueness (contract 9.4, ADR-0057 Q-51, Q-52): settings.set is keyed on (kind, pointer, params.property)."""
import pytest

import cmp_helpers as H
from compiler.steps import _step, duplicate_step_keys

SUBJECT = {"kind": "settings_company", "id": "company"}


def _set(pointer, prop):
    return _step("settings.set", SUBJECT, pointer, "low", {"property": prop, "after": "x"}, "/company" + prop)


def test_same_section_different_properties_are_valid():
    assert duplicate_step_keys([_set("/company", "/name"), _set("/company", "/currency")]) == []


def test_same_section_same_property_twice_is_refused():
    assert duplicate_step_keys([_set("/company", "/name"), _set("/company", "/name")]) == [("settings.set", "/company", "/name")]


def test_other_kinds_still_unique_on_kind_and_pointer():
    a = _step("entity.add", SUBJECT, "/entities/x", "low", {"definition": {}}, "/entities/x")
    assert duplicate_step_keys([a, dict(a)]) == [("entity.add", "/entities/x")]


def test_label_overrides_compiles_as_settings_set_and_compiled_steps_are_unique():
    bp = H.blueprint()
    bp["i18n"]["labelOverrides"] = {"invoice": {"ar": "x", "en": "x"}}
    r = H.compile_fixture(bp=bp)
    assert r.ok, H.codes(r)
    steps = r.artifact["steps"]
    props = [s["params"]["property"] for s in steps if s["kind"] == "settings.set" and s["pointer"] == "/i18n"]
    assert "/labelOverrides" in props
    assert duplicate_step_keys(steps) == []


def test_set_property_steps_with_different_properties_are_still_duplicates():
    def sp(prop):
        return _step("entity.set_property", SUBJECT, "/entities/x", "low", {"property": prop, "after": 1}, "/entities/x")
    assert duplicate_step_keys([sp("/a"), sp("/b")]) == [("entity.set_property", "/entities/x")]


def test_duplicate_step_key_refuses_the_compile(monkeypatch):
    import compiler.core as core
    real = core.steps_from_ops

    def dup(ops):
        steps, skipped, issues = real(ops)
        return steps + [dict(steps[0])], skipped, issues
    monkeypatch.setattr(core, "steps_from_ops", dup)
    r = H.compile_fixture()
    assert not r.ok
    assert H.codes(r) == {"CMP-ART-006"}
