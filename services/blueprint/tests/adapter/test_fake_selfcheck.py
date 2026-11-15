"""Checks of the test kit itself (not ADP-C items): the helpers the suite relies on agree with the contract."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from adapter import testkit as t
from conftest import optional
from adapter.contract import _REGISTRY, artifact_hashes, canon
from adapter.harness import FakeHarness, make_harness

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "diff"))


def artifact_validator():
    return Draft202012Validator({"$ref": "urn:platform:contract:compiled-artifact:0.1.0"}, registry=_REGISTRY)


def test_canonical_json_matches_bpdiff():
    from bpdiff.model import canonical
    value = {"b": [1, {"z": "ع", "a": None}], "a": "x"}
    assert canon(value) == canonical(value)


def test_sample_artifacts_are_sealed_and_valid():
    for name in ("add-field", "remove-field", "add-workflow-state"):
        art = t.sample(name)
        assert artifact_hashes(art) == (art["integrity"]["contentHash"], art["artifactId"])
        assert artifact_hashes(art["inverse"]) == (art["inverse"]["integrity"]["contentHash"], art["inverse"]["artifactId"])
        assert not list(artifact_validator().iter_errors(art))


def test_derived_artifacts_validate_against_the_contract():
    for art in (t.initial_build(), t.two_fields(), t.variant([t.entity_step("general_ledger")]),
                t.variant([t.prop_step("customer", "credit_limit", "/precision", 2, 3)]),
                t.variant([t.role_step("role.disable", "accountant"), t.binding_step()])):
        assert not list(artifact_validator().iter_errors(art)), art["steps"][0]["kind"]


def test_initial_build_matches_the_sample_base_hash():
    build = t.initial_build()
    assert build["blueprint"]["target"] == t.sample("add-field")["blueprint"]["base"]
    assert [s["seq"] for s in build["steps"]] == list(range(1, len(build["steps"]) + 1))


def test_default_harness_is_the_fake(monkeypatch):
    monkeypatch.delenv("ADAPTER_HARNESS", raising=False)
    assert isinstance(make_harness(), FakeHarness)
    monkeypatch.setenv("ADAPTER_HARNESS", "adapter.harness:FakeHarness")
    assert isinstance(make_harness(), FakeHarness)


def test_a_missing_required_capability_fails_the_run_instead_of_skipping():
    import pytest
    class Bare(FakeHarness):
        def advance_time(self, seconds):
            raise NotImplementedError

    with pytest.raises(pytest.fail.Exception, match="INCOMPLETE CONFORMANCE RUN"):
        optional(Bare().advance_time, 1)


def test_the_fake_provides_every_harness_extension():
    h = FakeHarness()
    t.provision(h)
    h.on_lock_held(lambda: None)
    h.advance_time(1)
    h.set_site_state("t_alpha", "failed")
    assert isinstance(h.audit_log(), list) and h.dropped_data() == [] and isinstance(h.execution_journal(), list)
    assert isinstance(h.without_test_hooks(), FakeHarness)
