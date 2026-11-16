"""ADP-C-013 to ADP-C-024: capabilities, site lifecycle, artifact checks."""
import copy
import json

import pytest

from adapter import testkit as t
from adapter.contract import CONTRACTS, canon
from conftest import assert_no_effect, optional

EXPORTED_KEYS = {"settings_company", "settings_compliance", "settings_intl", "component", "location", "entity", "field",
                 "relation", "role", "workflow", "state", "transition", "approval", "report"}  # contract 5.1 (0.1.2)

ARTIFACT_OPS = ["plan", "preview", "apply", "rollback"]


def call_with(h, op, artifact, tenant="t_alpha"):
    """Send `artifact` through any artifact-taking operation. apply gets an unissued plan token."""
    if op == "apply":
        return h.call(op, t.ctx(tenant), {"idempotencyKey": t.key(), "artifact": artifact, "planToken": "pln_" + "c" * 24,
                                          "approvals": {"changeApproved": t.ulid()}})
    if op == "rollback":
        return t.rollback(h, artifact, tenant)
    return h.call(op, t.ctx(tenant), {"artifact": artifact})


def test_adp_c_013_capabilities_lists_every_kind_sorted_and_stable(h):
    kinds = json.loads((CONTRACTS / "compiled-artifact.schema.json").read_text())["$defs"]["stepKind"]["enum"]
    first = h.call("capabilities", t.ctx("platform"), {})["result"]
    second = h.call("capabilities", t.ctx("t_alpha"), {})["result"]
    listed = [k["kind"] for k in first["stepKinds"]]
    assert listed == sorted(kinds) and len(set(listed)) == len(listed)
    assert set(first["exportedProperties"]) == EXPORTED_KEYS  # section 5.1 fixes the key names
    assert canon(first) == canon(second)
    assert first["features"]["previewPredictsExport"] is True  # required of the fake (ADP-C-032)


def test_adp_c_014_provision_reaches_ready(h):
    resp = t.provision(h, site_class="sandbox")
    status = resp["result"]
    assert status["state"] == "ready" and status["siteClass"] == "sandbox"
    assert status["engineTarget"] == t.ENGINE_TARGET and status["blueprintId"] == t.BLUEPRINT_ID
    assert status["applied"] is None and status["lockedBy"] is None
    assert t.status(h) == status


def test_adp_c_015_provision_replay_and_new_key(h):
    key = t.key()
    first = t.provision(h, k=key)
    again = t.provision(h, k=key)
    assert again["replayed"] is True and again["result"] == first["result"]
    t.apply_artifact(h, t.initial_build())
    other = t.provision(h)  # new key, same parameters
    assert other["ok"] and other["replayed"] is False
    assert other["result"]["applied"] is not None, "no second (empty) site was created"
    assert t.provision(h, k=key)["replayed"] is True


def test_adp_c_016_provision_different_target(h):
    t.provision(h)
    second_set = h.call("capabilities", t.ctx("platform"), {})["result"]["versionSets"]
    if len(second_set) > 1:
        other = {**t.ENGINE_TARGET, "versionSet": next(v for v in second_set if v != t.ENGINE_TARGET["versionSet"])}
        assert t.code_of(t.provision(h, target=other)) == "site_exists_different_target"
    assert t.code_of(t.provision(h, blueprint_id="another-blueprint-9")) == "site_exists_different_target"
    assert t.status(h)["blueprintId"] == t.BLUEPRINT_ID


@pytest.mark.parametrize("state", ["provisioning", "failed"])
@pytest.mark.parametrize("op", ["plan", "preview", "apply", "export_config"])
def test_adp_c_017_site_not_ready(h, op, state):
    t.provision(h)
    optional(h.set_site_state, "t_alpha", state)
    art = t.sample("add-field")
    inputs = {"export_config": {}, "plan": {"artifact": art}, "preview": {"artifact": art},
              "apply": {"idempotencyKey": t.key(), "artifact": art, "planToken": "pln_" + "d" * 24,
                        "approvals": {"changeApproved": t.ulid()}}}
    assert t.code_of(h.call(op, t.ctx(), inputs[op])) == "site_not_ready"


def mutated(art, how):
    art = copy.deepcopy(art)
    if how == "param":
        art["steps"][0]["params"]["definition"]["max"] = 366
    elif how == "pointer":
        art["steps"][0]["pointer"] += "x"
    elif how == "risk":
        art["risk"]["total"] += 1
    elif how == "hash":
        art["integrity"]["contentHash"] = "sha256:" + "1" * 64
    elif how == "id":
        art["artifactId"] = "art_" + "2" * 32
    return art


@pytest.mark.parametrize("op", ARTIFACT_OPS)
@pytest.mark.parametrize("how", ["param", "pointer", "risk", "hash", "id"])
def test_adp_c_018_integrity(h, op, how):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = call_with(h, op, mutated(t.sample("add-field"), how))
    assert t.code_of(resp) == "artifact_integrity_failed"
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("op", ARTIFACT_OPS)
def test_adp_c_019_schema_invalid_artifact(h, op):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    del art["steps"]
    before, ev = t.snapshot(h), len(h.events())
    resp = call_with(h, op, t.seal(art))
    assert t.code_of(resp) == "invalid_request" and resp["error"]["details"]["fields"]
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("op", ARTIFACT_OPS)
def test_adp_c_020_unknown_artifact_schema(h, op):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    art["artifactSchema"] = "0.9.0"
    resp = call_with(h, op, t.seal(art))
    assert t.code_of(resp) == "unsupported_contract_version" and resp["error"]["details"]["supported"]


@pytest.mark.parametrize("op", ARTIFACT_OPS)
@pytest.mark.parametrize("which", ["adapter", "unknown_set", "other_set"])
def test_adp_c_021_engine_target(h, op, which):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    if which == "adapter":
        art["engineTarget"]["adapter"] = "otherengine"
    elif which == "unknown_set":
        art["engineTarget"]["versionSet"] = "set-unknown"
    else:
        sets = h.call("capabilities", t.ctx("platform"), {})["result"]["versionSets"]
        if len(sets) < 2:
            return  # one version set: the unknown_set case above already covers a version set the adapter lacks
        art["engineTarget"]["versionSet"] = next(v for v in sets if v != "set-example")
    before, ev = t.snapshot(h), len(h.events())
    resp = call_with(h, op, t.seal(art))
    assert t.code_of(resp) == "unsupported_engine_target"
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("op", ["plan", "preview"])
def test_adp_c_022_blueprint_mismatch(h, op):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    art["blueprint"]["id"] = "some-other-blueprint-001"
    assert t.code_of(call_with(h, op, t.seal(art))) == "blueprint_mismatch"
    assert t.code_of(t.apply_artifact(h, t.sample("add-field"), token="pln_" + "e" * 24)) == "plan_token_invalid"


@pytest.mark.parametrize("op", ["plan", "preview"])
def test_adp_c_023_base_mismatch(h, op):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = call_with(h, op, t.sample("remove-field"))  # base revision 2, site is on 1
    assert t.code_of(resp) == "base_revision_mismatch"
    assert_no_effect(h, "t_alpha", before, ev)
    # an initial build (base null) on a built site is also a base mismatch
    assert t.code_of(call_with(h, op, t.initial_build())) == "base_revision_mismatch"


def test_adp_c_023_apply_with_wrong_base(h):
    t.site_at_rev1(h)
    resp = h.call("apply", t.ctx(), {"idempotencyKey": t.key(), "artifact": t.sample("remove-field"),
                                     "planToken": "pln_" + "f" * 24, "approvals": {"changeApproved": t.ulid()}})
    assert t.code_of(resp) in {"base_revision_mismatch", "plan_token_invalid"}


@pytest.mark.parametrize("op", ARTIFACT_OPS)
def test_adp_c_024_limits(h, op):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    many = t.sample("add-field")
    many["steps"] = [{**many["steps"][0], "seq": i} for i in range(1, 502)]
    big = t.sample("add-field")
    big["steps"][0]["params"]["definition"]["labels"]["en"] = "x" * (1024 * 1024 + 10)
    huge = t.sample("add-field")
    huge["steps"][0]["params"]["definition"]["labels"]["en"] = "x" * (2 * 1024 * 1024 + 10)
    for art in (many, big, huge):
        resp = call_with(h, op, art)
        err = t.error_of(resp)
        assert err["code"] == "limit_exceeded"
        d = err["details"]
        assert d["limit"] and d["actual"] > d["allowed"]
    assert_no_effect(h, "t_alpha", before, ev)


def test_adp_c_024_members_limit(h):
    t.site_at_rev1(h)
    members = [{"memberRef": f"m_{i:08d}", "status": "active", "roleIds": ["owner"]} for i in range(1001)]
    resp = h.call("sync_members", t.ctx(), {"idempotencyKey": t.key(), "mode": "full", "syncVersion": 1, "members": members})
    assert t.code_of(resp) == "limit_exceeded"
