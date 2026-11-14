"""ADP-C-001 to ADP-C-012: envelope, security, invisibility."""
import copy
import json

import pytest

from adapter import testkit as t
from adapter.contract import canon
from conftest import assert_no_effect, event_types, leaks, optional

OPS = ["capabilities", "provision_site", "site_status", "plan", "preview", "apply", "rollback", "export_config",
       "sync_members", "health"]


def valid_input(op, artifact=None):
    artifact = artifact or t.sample("add-field")
    return {
        "capabilities": {}, "site_status": {}, "export_config": {}, "health": {},
        "provision_site": {"idempotencyKey": t.key(), "engineTarget": t.ENGINE_TARGET, "countryPack": "sa",
                           "siteClass": "production", "blueprintId": t.BLUEPRINT_ID},
        "plan": {"artifact": artifact}, "preview": {"artifact": artifact},
        "apply": {"idempotencyKey": t.key(), "artifact": artifact, "planToken": "pln_" + "a" * 24,
                  "approvals": {"changeApproved": t.ulid()}},
        "rollback": {"idempotencyKey": t.key(), "forwardArtifact": artifact, "reason": "owner_request",
                     "approvals": {"rollbackApproved": t.ulid()}},
        "sync_members": {"idempotencyKey": t.key(), "mode": "delta", "syncVersion": 1, "members": []},
    }[op]


def test_adp_c_001_every_response_validates(h):
    """Every call below is schema-checked by the harness wrapper (ok and error branches)."""
    assert h.call("capabilities", t.ctx("platform"), {})["ok"]
    assert h.call("health", t.ctx("platform"), {})["ok"]
    t.provision(h)
    build = t.site_at_rev1(h, "t_beta")
    fwd = t.sample("add-field")
    assert t.plan(h, build, "t_beta")["ok"] is False  # base mismatch: error branch
    assert t.plan(h, build)["ok"]
    assert t.plan(h, fwd, "t_beta", op="preview", includeExport=True)["ok"]
    assert t.apply_artifact(h, fwd, "t_beta")["ok"]
    assert t.rollback(h, fwd, "t_beta")["ok"]
    assert t.export(h, "t_beta") and t.status(h, "t_beta")
    sync = {"idempotencyKey": t.key(), "mode": "full", "syncVersion": 1,
            "members": [{"memberRef": "m_aaaaaaaa", "status": "active", "roleIds": ["owner"]}]}
    assert h.call("sync_members", t.ctx("t_beta"), sync)["ok"]
    assert h.call("health", t.ctx("t_beta"), {})["ok"]
    for op in OPS:  # one error branch per operation: an unknown key
        bad = {**valid_input(op), "bogus": 1}
        assert not h.call(op, t.ctx("t_beta"), bad)["ok"]


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("extra", ["tenantId", "roleIds", "caller", "password"])
def test_adp_c_002_unknown_input_key(h, op, extra):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = h.call(op, t.ctx(), {**valid_input(op), extra: "t_beta" if extra == "tenantId" else ["owner"]})
    assert t.code_of(resp) == "invalid_request"
    assert resp["error"]["details"]["fields"], "details.fields names the offending pointer"
    if valid_input(op):
        assert f"/input/{extra}" in resp["error"]["details"]["fields"]
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("bad", [None, {}, "text", {"tenantId": "t_alpha"}, "drop_caller", "bad_tenant", "extra_key"])
def test_adp_c_003_missing_or_invalid_context(h, bad):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    context = t.ctx()
    if bad == "drop_caller":
        del context["caller"]
        bad = context
    elif bad == "bad_tenant":
        context["tenantId"] = "T ALPHA; drop"
        bad = context
    elif bad == "extra_key":
        context["roleIds"] = ["owner"]
        bad = context
    resp = h.call("plan", bad, {"artifact": t.sample("add-field")})
    assert t.code_of(resp) == "invalid_request"
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("version", ["0.2.0", "1.1.1", "0.0.9", "2.0.0"])
def test_adp_c_004_other_major_minor(h, version):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = h.call("plan", t.ctx(version=version), {"artifact": t.sample("add-field")})
    assert t.code_of(resp) == "unsupported_contract_version"
    assert resp["error"]["details"]["supported"]
    assert_no_effect(h, "t_alpha", before, ev)


def test_adp_c_004_patch_may_differ(h):
    t.site_at_rev1(h)
    supported = h.call("capabilities", t.ctx("platform"), {})["result"]["contractVersions"][0].split(".")
    version = ".".join([*supported[:2], "99"])
    assert h.call("plan", t.ctx(version=version), {"artifact": t.sample("add-field")})["ok"]


def test_adp_c_005_error_shape_and_retryable(h):
    """Shape (messageKey, details keys, retryable) is also checked on every error of the suite by the wrapper."""
    site = t.site_at_rev1(h)
    seen = set()
    for resp in (h.call("plan", t.ctx(), {"artifact": 1}),
                 h.call("plan", t.ctx("t_ghost"), {"artifact": t.sample("add-field")}),
                 h.call("plan", t.ctx(service="identity"), {"artifact": t.sample("add-field")}),
                 t.plan(h, t.sample("remove-field")),
                 t.apply_artifact(h, t.sample("add-field"), token="pln_" + "b" * 24)):
        err = t.error_of(resp)
        seen.add(err["code"])
        assert err["messageKey"] == "errors.adapter." + err["code"]
    assert {"invalid_request", "tenant_not_found", "permission_denied", "base_revision_mismatch", "plan_token_invalid"} <= seen
    assert site


def test_adp_c_006_no_engine_leak_anywhere(h):
    """The wrapper scans every response of the suite. This runs a broad flow, then scans events and exports too."""
    build = t.site_at_rev1(h)
    for name in ("add-field", "remove-field"):
        assert t.apply_artifact(h, t.sample(name))["ok"]
    t.rollback(h, t.sample("remove-field"))
    assert not t.plan(h, t.sample("add-workflow-state"))["ok"]  # base mismatch: error responses are scanned too
    assert not leaks(h.events()) and not leaks(t.export(h)) and build
    assert leaks({"x": "stored in Frappe"}) and leaks({"x": "Traceback (most recent call last)"})  # scanner self-check
    assert not leaks({"adapterId": "frappe", "engineTarget": {"adapter": "frappe", "versionSet": "set-example"}})


def test_adp_c_007_tenant_isolation(h):
    t.site_at_rev1(h, "t_alpha")
    t.site_at_rev1(h, "t_beta")
    before = t.snapshot(h, "t_beta")
    fwd = t.sample("add-field")
    t.plan(h, fwd)
    t.plan(h, fwd, op="preview")
    assert t.apply_artifact(h, fwd)["ok"]
    assert t.apply_artifact(h, t.sample("remove-field"))["ok"]
    t.rollback(h, t.sample("remove-field"))
    sync = {"idempotencyKey": t.key(), "mode": "full", "syncVersion": 1,
            "members": [{"memberRef": "m_aaaaaaaa", "status": "active", "roleIds": ["owner"]}]}
    assert h.call("sync_members", t.ctx(), sync)["ok"]
    assert t.snapshot(h, "t_beta") == before


def test_adp_c_008_rollback_foreign_artifact(h):
    t.site_at_rev1(h, "t_alpha")
    t.site_at_rev1(h, "t_beta")
    fwd = t.sample("add-field")
    assert t.apply_artifact(h, fwd, "t_alpha")["result"]["status"] == "applied"
    before, ev = t.snapshot(h, "t_beta"), len(h.events())
    resp = t.rollback(h, fwd, "t_beta")
    assert t.code_of(resp) in {"artifact_not_found", "blueprint_mismatch", "rollback_not_possible"}
    assert_no_effect(h, "t_beta", before, ev, allow={"blueprint.apply_failed"})


def test_adp_c_009_tenant_without_site(h):
    art = t.sample("add-field")
    for op in OPS:
        if op in ("capabilities", "provision_site"):
            continue
        context = t.ctx("t_ghost")
        resp = h.call(op, context, valid_input(op, art))
        assert t.code_of(resp) in {"tenant_not_found", "site_not_ready"}, op
    assert h.call("capabilities", t.ctx("t_ghost"), {})["ok"]
    assert h.call("health", t.ctx("platform"), {})["ok"]


DENIED = {"health": "compiler", "site_status": "identity", "export_config": "operate_gateway", "plan": "identity",
          "preview": "identity", "provision_site": "compiler", "apply": "compiler", "rollback": "compiler",
          "sync_members": "compiler"}


@pytest.mark.parametrize("op", sorted(DENIED))
def test_adp_c_010_service_not_allowed(h, op):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = h.call(op, t.ctx(service=DENIED[op]), valid_input(op))
    assert t.code_of(resp) == "permission_denied"
    assert event_types(h, ev) == ["permission.denied"]
    assert t.snapshot(h) == before


@pytest.mark.parametrize("op", ["apply", "rollback"])
@pytest.mark.parametrize("who", [None, {"kind": "agent", "id": "agent_1"}])
def test_adp_c_011_production_needs_user_or_support(h, op, who):
    t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    resp = h.call(op, t.ctx(who=who), valid_input(op))
    assert t.code_of(resp) == "permission_denied"
    assert event_types(h, ev) == ["permission.denied"] and t.snapshot(h) == before


@pytest.mark.parametrize("op", ["apply", "rollback"])
def test_adp_c_011_support_needs_grant(h, op):
    t.site_at_rev1(h)
    resp = h.call(op, t.ctx(who={"kind": "support", "id": "support_1"}), valid_input(op))
    assert t.code_of(resp) == "invalid_request"


def test_adp_c_011_support_with_grant_and_sandbox_agent(h):
    t.site_at_rev1(h)
    support = {"kind": "support", "id": "support_1", "supportGrantId": "grant_0001"}
    assert t.apply_artifact(h, t.sample("add-field"), who=support)["result"]["status"] == "applied"
    t.site_at_rev1(h, "t_sand", site_class="sandbox")
    agent = {"kind": "agent", "id": "agent_1"}
    assert t.apply_artifact(h, t.sample("add-field"), "t_sand", who=agent)["result"]["status"] == "applied"


def test_adp_c_012_role_ids_never_change_results(h):
    t.site_at_rev1(h, "t_alpha")
    t.site_at_rev1(h, "t_beta")
    art = t.sample("add-field")
    a, b = copy.deepcopy(t.USER), {**t.USER, "roleIds": ["nobody", "everyone"]}
    c = {**t.USER, "roleIds": []}
    plans = [h.call("plan", t.ctx(who=w), {"artifact": art})["result"] for w in (a, b, c)]
    assert plans[0] == plans[1] == plans[2]
    exports = [h.call("export_config", t.ctx(who=w), {})["result"] for w in (a, b, c)]
    assert canon(exports[0]) == canon(exports[1]) == canon(exports[2])
    ra = t.apply_artifact(h, art, "t_alpha", who=a)
    rb = t.apply_artifact(h, art, "t_beta", who=b)
    assert ra["result"]["status"] == rb["result"]["status"] == "applied"
    assert ra["result"]["exportHash"] == rb["result"]["exportHash"]
