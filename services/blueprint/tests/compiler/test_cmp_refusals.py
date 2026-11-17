"""Fail-closed behaviour: every refusal returns codes and no artifact. Inputs are synthetic edits of the fixture."""
import copy

import pytest

import cmp_helpers as H
from compiler import artifact as art
from compiler import core
from compiler.components import resolve_components
from compiler.steps import steps_from_ops


def _edit_manifest(cid, fn):
    out = []
    for m in H.manifests():
        if m["id"] == cid:
            m = copy.deepcopy(m)
            fn(m)
        out.append(m)
    return H.registry(out)


# ------------------------------------------------------------------ Blueprint validation
def test_schema_invalid_blueprint_is_refused_with_validator_errors():
    bp = H.blueprint()
    bp["meta"]["revision"] = "one"
    r = H.compile_fixture(bp=bp)
    assert "BP-SCHEMA-001" in H.codes(r)


def test_dangling_reference_is_refused():
    bp = H.blueprint()
    bp["entities"][0]["workflow"] = "no_such_flow"
    assert "BP-REF-001" in H.codes(H.compile_fixture(bp=bp))


@pytest.mark.parametrize("value", [None, [], "text", 7])
def test_non_object_blueprint_is_refused(value):
    assert H.codes(H.compile_fixture(bp=value))


def test_non_json_value_is_refused():
    bp = H.blueprint()
    bp["meta"]["revision"] = float("nan")
    assert "CMP-INPUT-001" in H.codes(H.compile_fixture(bp=bp))


def test_missing_engine_version_set_is_refused():
    bp = H.blueprint()
    del bp["meta"]["engineTarget"]["versionSet"]
    assert H.codes(H.compile_fixture(bp=bp)) & {"CMP-BP-001", "BP-CMP-004"}


# ------------------------------------------------------------------ components
def test_missing_component_is_refused():
    reg = H.registry([m for m in H.manifests() if m["id"] != "core.customer"])
    assert "BP-CMP-001" in H.codes(H.compile_fixture(reg=reg))


def test_missing_component_is_refused_by_the_compiler_gate_too():
    bp = H.blueprint()
    reg = H.registry([m for m in H.manifests() if m["id"] != "core.customer"])
    _, issues = resolve_components(bp, reg, "sandbox")
    assert "CMP-COMP-001" in {i.code for i in issues}


def test_no_version_in_range_is_refused():
    bp = H.blueprint()
    bp["components"][0]["versionRange"] = "^9.0.0"
    assert H.codes(H.compile_fixture(bp=bp)) & {"BP-CMP-002", "CMP-COMP-002"}


def test_draft_component_is_not_eligible_in_sandbox():
    reg = _edit_manifest("core.customer", lambda m: m.update(certification={"level": "draft"}))
    assert "CMP-COMP-003" in H.codes(H.compile_fixture(reg=reg))


def test_tested_component_is_not_eligible_in_production():
    bp, _, mp = H.production_inputs()
    mans = [H.certify(m) if m["id"] != "core.customer" else m for m in H.manifests()]
    assert H.codes(H.compile_fixture(bp, H.registry(mans), mp, environment="production")) == {"CMP-COMP-003"}


def test_ledger_or_tax_component_below_production_level_is_refused():
    bp, _, mp = H.production_inputs()
    mans = [H.certify(m) if m["id"] != "stock.ledger" else m for m in H.manifests()]
    assert H.codes(H.compile_fixture(bp, H.registry(mans), mp, environment="production")) == {"CMP-COMP-004"}


def test_fixture_as_is_is_refused_for_production():
    c = H.codes(H.compile_fixture(environment="production"))
    assert {"CMP-COMP-003", "CMP-COMP-004", "CMP-MAP-005"} <= c


def test_dependency_cycle_is_refused():
    def add_cycle(m):
        m["requires"] = [{"component": "core.sales_order", "versionRange": "^0.1.0"}]
    r = H.compile_fixture(reg=_edit_manifest("core.customer", add_cycle))
    assert "CMP-COMP-007" in H.codes(r)
    assert any("core.customer -> core.sales_order -> core.customer" in i.message for i in r.errors)


def test_unresolved_dependency_is_refused():
    bp = H.blueprint()
    bp["components"] = [c for c in bp["components"] if c["id"] != "core.customer"]
    _, issues = resolve_components(bp, H.registry(), "sandbox")
    assert "CMP-COMP-006" in {i.code for i in issues}


def test_unknown_environment_is_refused():
    assert H.codes(H.compile_fixture(environment="staging")) == {"CMP-ENV-001"}


def test_registry_with_admission_errors_is_refused():
    broken = copy.deepcopy(H.manifests()[0])
    broken["id"], broken["licence"] = "zz.broken", {"spdx": "NOASSERTION"}
    assert "CMP-REG-001" in H.codes(H.compile_fixture(reg=H.registry(H.manifests() + [broken])))


def test_registry_of_the_wrong_type_is_refused():
    assert H.codes(H.compile_fixture(reg={"core.customer": []})) == {"CMP-REG-002"}


# ------------------------------------------------------------------ engine mapping
def test_unknown_top_level_mapping_key_is_refused():
    mp = H.mapping()
    mp["rates"] = {"vat": 15}
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-001"}


def test_unknown_nested_mapping_key_is_refused():
    mp = H.mapping()
    mp["entities"][0]["fields"][0]["taxRate"] = 15
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-001"}


def test_mapping_entity_not_in_blueprint_is_refused():
    mp = H.mapping()
    mp["entities"][0]["blueprintEntity"] = "no_such_entity"
    assert "CMP-MAP-002" in H.codes(H.compile_fixture(mp=mp))


def test_mapping_field_type_mismatch_is_refused():
    mp = H.mapping()
    mp["entities"][0]["fields"][0]["blueprintType"] = "integer"
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-002"}


def test_mapping_for_another_adapter_is_refused():
    mp = H.mapping()
    mp["engine"]["adapter"] = "other_engine"
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-003"}


def test_draft_mapping_with_a_different_pinned_version_set_is_refused():
    mp = H.mapping()
    mp["engine"]["versionSet"] = "set-other"
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-003"}


def test_mapping_for_another_blueprint_contract_is_refused():
    mp = H.mapping()
    mp["blueprintRef"]["contract"] = "9.9.9"
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-004"}


def test_grant_beyond_the_blueprint_role_is_refused():
    mp = H.mapping()
    mp["roles"][1]["grants"][1]["actions"].append("delete")
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-006"}


def test_ledger_effect_on_an_entity_without_ledger_component_is_refused():
    mp = H.mapping()
    customer = next(e for e in mp["entities"] if e["blueprintEntity"] == "customer")
    customer["ledgerEffect"] = "gl"
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-007"}


def test_mapping_precision_different_from_blueprint_is_refused():
    mp = H.mapping()
    field = next(f for e in mp["entities"] for f in e["fields"] if "computed" in f)
    field["computed"]["rounding"]["precision"] = 3
    assert H.codes(H.compile_fixture(mp=mp)) == {"CMP-MAP-008"}


def test_mapping_that_is_not_an_object_is_refused():
    assert H.codes(H.compile_fixture(mp=["not", "a", "mapping"])) == {"CMP-MAP-001"}


# ------------------------------------------------------------------ artifact gates
def test_engine_name_in_tenant_text_is_refused():
    bp = H.blueprint()
    bp["entities"][0]["labels"]["en"] = "Customer (ERPNext)"
    assert H.codes(H.compile_fixture(bp=bp)) == {"CMP-ART-005"}


def test_secret_like_key_in_params_is_refused():
    a = H.compile_fixture().artifact
    a["steps"][40]["params"]["definition"]["fields"][0]["apiKey"] = "x"
    assert "CMP-ART-002" in {i.code for i in art.check(art.seal(a))}


def test_tampered_artifact_fails_the_integrity_check():
    a = H.compile_fixture().artifact
    a["steps"][0]["params"]["after"] = "tampered"
    assert "CMP-ART-004" in {i.code for i in art.check(a)}


def test_step_limit_is_enforced():
    a = H.compile_fixture().artifact
    a["steps"] = a["steps"] * 6
    assert "CMP-ART-003" in {i.code for i in art.check(art.seal(a))}


def test_operation_without_a_compile_rule_is_refused():
    ops = [{"op": "add", "path": ["unknownSection", "x"], "pointer": "/unknownSection/x", "impact": "config",
            "subject": {"kind": "blueprint", "id": None, "parents": []}, "after": 1},
           {"op": "replace", "path": ["company", "country"], "pointer": "/company/country", "impact": "compliance",
            "subject": {"kind": "company", "id": None, "parents": []}, "before": "SA", "after": "AE"}]
    _, _, issues = steps_from_ops(ops)
    assert [i.code for i in issues] == ["CMP-ART-001", "CMP-ART-001"]


def test_internal_failure_refuses_and_never_emits(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("bug")
    monkeypatch.setattr(core.bpdiff, "diff", boom)
    r = H.compile_fixture()
    assert H.codes(r) == {"CMP-INTERNAL-001"} and r.artifact is None


def test_refusal_errors_are_sorted_and_deterministic():
    r1, r2 = H.compile_fixture(environment="production"), H.compile_fixture(environment="production")
    keys = [(i.code, i.path, i.message) for i in r1.errors]
    assert keys == sorted(keys) and r1.errors == r2.errors
    assert r1.as_dict()["ok"] is False and "artifact" not in r1.as_dict()
