"""Golden artifact, contract rules, determinism, idempotence and no mutation for the BPL-005 trading fixture.

Where each expected value in fixtures/trading-distribution.expected-artifact.json comes from (it was derived by a
separate script written from the contract, without importing the compiler, then compared with the compiler output):
- artifactSchema, kind, compiler, inverse null, base null, diffHash null, signature null: compiled-artifact.schema.json
  (initial build: base null forces inverse null and kind forward; diffHash null when base is null).
- blueprint.id, target.revision, engineTarget: the fixture's meta. target.hash ("$blueprintHash"): sha256 of the
  fixture's canonical JSON, recomputed below with hashlib (contract 9.2).
- components: one per fixture binding, sorted by id, version = the only fixture manifest version (0.1.0).
- steps: contract 9.3 (one settings.set per company, compliance and i18n.defaultLocale/labelOverrides property;
  *.add/upsert/enable per top-level element with the Blueprint node verbatim, "$fromBlueprint" pointers here),
  9.4 phases and order, 9.5 ddlImpact (entity.add additive, the rest none), impacts from the bpdiff classification
  table in services/blueprint/diff/README.md (entities data_shape; roles, approvals access; company country, crNumber,
  vatNumber, locale and all of compliance: compliance; i18n except defaultLocale cosmetic; the rest config).
- skippedOps: 9.3 Skipped list (meta, branding, i18n glossary, each integration).
- postConditions: 9.7 (exists per step subject, count_equals per collection, order_equals for entity fields and
  workflow states, ids numbered in pointer order).
- risk: counts per impact of the 90 ops (85 steps + 5 skipped; /meta as a whole object is config), maxImpact by the
  bpdiff severity order, touchesLedgerOrTax from the fixture manifests (certification.touchesLedgerOrTax or rigid).
- artifactId and integrity.contentHash: recorded from the compiler once every other field matched; test 3 proves
  they equal sha256 of the canonical artifact as contract 9.1 defines it.
"""
import copy
import hashlib
import os
import subprocess
import sys

import cmp_helpers as H
from bpdiff.model import node_at
from compiler import plan_view, to_bytes


def _resolve(value, bp):
    if isinstance(value, dict):
        if set(value) == {"$fromBlueprint"}:
            return copy.deepcopy(node_at(bp, value["$fromBlueprint"].split("/")[1:]))
        return {k: _resolve(v, bp) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, bp) for v in value]
    if value == "$blueprintHash":
        return "sha256:" + hashlib.sha256(H.canonical(bp)).hexdigest()
    return value


def _art():
    r = H.compile_fixture()
    assert r.ok, [str(i) for i in r.errors]
    return r.artifact


def test_golden_artifact_matches_expected_file():
    bp = H.blueprint()
    assert _art() == _resolve(H.load(H.EXPECTED), bp)


def test_artifact_validates_against_the_contract_schema():
    errors = sorted(H.ARTIFACT_VALIDATOR.iter_errors(_art()), key=str)
    assert not errors, errors[:3]


def test_content_hash_and_id_follow_contract_9_1():
    a = _art()
    body = {k: v for k, v in a.items() if k not in ("artifactId", "integrity")}
    assert a["integrity"]["contentHash"] == H.sha(body)
    assert a["artifactId"] == "art_" + a["integrity"]["contentHash"][7:39]


def test_ordering_rules_of_x_validator_rules():
    a = _art()
    steps = a["steps"]
    assert [s["seq"] for s in steps] == list(range(1, len(steps) + 1))
    keys = [(s["phase"], s["pointer"], s["kind"]) for s in steps]
    assert keys == sorted(keys)
    ids = [c["id"] for c in a["components"]]
    assert ids == sorted(set(ids))
    assert [s["pointer"] for s in a["skippedOps"]] == sorted(s["pointer"] for s in a["skippedOps"])
    assert [p["id"] for p in a["postConditions"]] == sorted(p["id"] for p in a["postConditions"])
    assert all(s["sourceOps"] == sorted(s["sourceOps"]) for s in steps)


def test_every_blueprint_element_and_setting_is_accounted_for_once():
    a, bp = _art(), H.blueprint()
    sources = [o for s in a["steps"] for o in s["sourceOps"]] + [s["pointer"] for s in a["skippedOps"]]
    assert len(sources) == len(set(sources)) == a["risk"]["total"]
    for section in ("locations", "components", "entities", "roles", "workflows", "approvals", "reports"):
        for node in bp[section]:
            assert f"/{section}/{node['id']}" in sources
    for section in ("company", "compliance"):
        for prop in bp[section]:
            assert f"/{section}/{prop}" in sources


def test_definitions_are_blueprint_nodes_verbatim_including_money_precision():
    a, bp = _art(), H.blueprint()
    step = next(s for s in a["steps"] if s["pointer"] == "/entities/sales_order")
    assert step["params"]["definition"] == next(e for e in bp["entities"] if e["id"] == "sales_order")
    money = [f for f in step["params"]["definition"]["fields"] if f["type"] == "money"]
    assert money and all(f["precision"] == 2 for f in money)


def test_no_number_in_the_artifact_steps_is_absent_from_the_blueprint():
    """Rigid zone: the compiler invents no figure, rate or rule; every number in a step comes from the Blueprint."""
    a, bp = _art(), H.blueprint()
    allowed = set(H.numbers(bp))
    params_numbers = H.numbers([s["params"] for s in a["steps"]])
    assert params_numbers and set(params_numbers) <= allowed


def test_risk_flags_ledger_tax_and_team_review():
    r = _art()["risk"]
    assert r["touchesLedgerOrTax"] and r["requiresTeamReview"] and r["touchesCompliance"]
    assert r["needsDdlPlanGate"] and r["irreversibleSteps"] == 0


def test_at_least_one_post_condition_per_step_subject():
    a = _art()
    checked = {p["pointer"] for p in a["postConditions"]}
    assert {s["pointer"] for s in a["steps"]} <= checked


def test_no_secret_keys_tenant_id_or_engine_names():
    a = _art()
    text = H.canonical({"steps": a["steps"], "postConditions": a["postConditions"]}).decode("utf-8").lower()
    for word in ("frappe", "erpnext", "password", "secret", "tenantid", "tenant_id"):
        assert word not in text


def test_determinism_two_runs_byte_identical():
    assert to_bytes(H.compile_fixture().artifact) == to_bytes(H.compile_fixture().artifact)


def test_determinism_with_registry_loaded_from_disk():
    from registry import Registry
    a = H.compile_fixture(reg=Registry.load(H.REGISTRY_DIR)).artifact
    assert to_bytes(a) == to_bytes(_art())


def test_determinism_across_processes_with_different_hash_seeds(tmp_path):
    outs = []
    for seed in ("0", "12345"):
        out = tmp_path / f"a{seed}.json"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(H.REPO / "services" / "blueprint")}
        subprocess.run([sys.executable, "-m", "compiler", str(H.FIXTURE), "--mapping", str(H.MAPPING), "--registry",
                        str(H.REGISTRY_DIR), "--environment", "sandbox", "--out", str(out)], check=True, env=env,
                       cwd=H.REPO, capture_output=True)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1] == to_bytes(_art())


def test_idempotent_compile_and_plan_view():
    a1, a2 = _art(), _art()
    assert a1["artifactId"] == a2["artifactId"]
    assert plan_view(a1) == plan_view(a2)


def test_inputs_are_not_mutated():
    bp, mp, reg = H.blueprint(), H.mapping(), H.registry()
    before = (copy.deepcopy(bp), copy.deepcopy(mp), reg.as_validation_context_registry())
    assert H.compile_fixture(bp, reg, mp).ok
    assert (bp, mp, reg.as_validation_context_registry()) == before


def test_returned_artifact_shares_no_state_with_inputs_or_later_runs():
    bp = H.blueprint()
    a = H.compile_fixture(bp=bp).artifact
    a["steps"][40]["params"]["definition"]["labels"]["en"] = "changed"
    assert bp == H.blueprint()
    assert H.compile_fixture().artifact == _resolve(H.load(H.EXPECTED), H.blueprint())


def test_production_compile_with_certified_components_and_verified_mapping():
    bp, reg, mp = H.production_inputs()
    r = H.compile_fixture(bp, reg, mp, environment="production")
    assert r.ok, [str(i) for i in r.errors]
    assert r.artifact["steps"] == _art()["steps"]
