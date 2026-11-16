"""ADP-C-061 to ADP-C-070: members, events, health, determinism."""
import json
import re

import pytest

from adapter import testkit as t
from conftest import event_types, optional

A, B, C = "m_aaaaaaaa", "m_bbbbbbbb", "m_cccccccc"


def member(ref, roles=("owner",), status="active"):
    return {"memberRef": ref, "status": status, "roleIds": list(roles)}


def sync(h, members, mode="full", version=1, key=None, tenant="t_alpha"):
    return h.call("sync_members", t.ctx(tenant, who={"kind": "system", "id": "assignments"}),
                  {"idempotencyKey": key or t.key(), "mode": mode, "syncVersion": version, "members": members})


def test_adp_c_061_full_sync(h):
    t.site_at_rev1(h)
    first = sync(h, [member(A), member(B, ["sales_rep", "accountant"])])["result"]
    assert first == {"syncVersion": 1, "created": 2, "updated": 0, "disabled": 0, "unchanged": 0}
    assert optional(h.action_probe, A)["allowed"] and h.action_probe(B)["allowed"]
    second = sync(h, [member(A), member(C, ["owner"])], version=2)["result"]
    assert second == {"syncVersion": 2, "created": 1, "updated": 0, "disabled": 1, "unchanged": 1}
    assert not h.action_probe(B)["allowed"] and h.action_probe(C)["allowed"] and h.action_probe(A)["allowed"]


def test_adp_c_062_delta_touches_only_listed(h):
    t.site_at_rev1(h)
    sync(h, [member(A), member(B)])
    out = sync(h, [member(B, status="disabled")], mode="delta", version=2)["result"]
    assert out["disabled"] == 1 and out["created"] == 0 and out["unchanged"] == 0
    assert h.action_probe(A)["allowed"] and not h.action_probe(B)["allowed"]


def test_adp_c_063_stale_version_and_replay(h):
    t.site_at_rev1(h)
    key = t.key()
    first = sync(h, [member(A)], version=5, key=key)
    for version in (5, 4):
        resp = sync(h, [member(A), member(B)], version=version)
        assert t.code_of(resp) == "stale_sync_version"
    assert not optional(h.action_probe, B)["allowed"]
    again = sync(h, [member(A)], version=5, key=key)
    assert again["replayed"] is True and again["result"] == first["result"]


def test_adp_c_064_unknown_role_changes_nothing(h):
    t.site_at_rev1(h)
    sync(h, [member(A)])
    resp = sync(h, [member(A), member(B, ["owner", "ghost_role"])], version=2)
    assert t.code_of(resp) == "unknown_role"
    assert not optional(h.action_probe, B)["allowed"] and h.action_probe(A)["allowed"]
    assert sync(h, [member(A)], version=2)["ok"], "the refused version number was not consumed"


def test_adp_c_064_inactive_role_and_role_in_use(h):
    t.site_at_rev1(h)
    sync(h, [member(A, ["accountant"])])
    disable = t.variant([t.role_step("role.disable", "accountant")])
    plan = t.plan(h, disable)["result"]
    assert plan["steps"][0]["reasonCode"] == "subject_in_use" and plan["verdict"] == "rejected"
    sync(h, [member(A, ["owner"])], version=2)  # accountant no longer used
    plan = t.plan(h, disable)["result"]
    assert plan["verdict"] == "needs_gate_approval"
    assert t.apply_artifact(h, disable)["result"]["status"] == "applied"
    assert t.code_of(sync(h, [member(A, ["accountant"])], version=3)) == "unknown_role"


def test_adp_c_065_shadow_users_cannot_authenticate(h):
    t.site_at_rev1(h)
    sync(h, [member(A), member(B, status="disabled")])
    for ref in (A, B):
        probe = optional(h.auth_probe, ref)
        assert probe["canAuthenticate"] is False and probe["emailSent"] is False
    bad = {"idempotencyKey": t.key(), "mode": "full", "syncVersion": 9,
           "members": [{**member(C), "password": "x"}, {**member(C), "email": "a@example.test"}]}
    resp = h.call("sync_members", t.ctx(), bad)
    assert t.code_of(resp) == "invalid_request"  # the schema has no field for any credential


def test_adp_c_066_disabled_member_cannot_act(h):
    t.site_at_rev1(h)
    sync(h, [member(A), member(B)])
    assert optional(h.action_probe, B)["allowed"]
    sync(h, [member(B, status="disabled")], mode="delta", version=2)
    assert h.action_probe(B)["allowed"] is False and h.action_probe(A)["allowed"] is True


def test_adp_c_067_events_once_per_terminal_outcome(h):
    t.site_at_rev1(h, "t_alpha")
    t.site_at_rev1(h, "t_beta")
    start = len(h.events())
    fwd = t.sample("add-field")
    out = t.apply_artifact(h, fwd)["result"]
    ev = h.events()[start:]
    assert [e["type"] for e in ev] == ["blueprint.applied"] and out["eventIds"] == [ev[0]["eventId"]]
    assert ev[0]["data"] == {"change_id": fwd["artifactId"], "revision": 2}
    rb = t.rollback(h, fwd)["result"]
    ev = h.events()[start + 1:]
    assert [e["type"] for e in ev] == ["blueprint.rolled_back"] and rb["eventIds"] == [ev[0]["eventId"]]
    h.fault("execute", step_seq=2)
    failed = t.apply_artifact(h, t.two_fields())["result"]
    last = h.events()[-1]
    assert last["type"] == "blueprint.apply_failed" and last["data"]["error_code"] == failed["error"]["code"]
    assert failed["eventIds"] == [last["eventId"]]
    count = len(h.events())
    t.apply_artifact(h, t.sample("add-field"), "t_beta")
    assert len(h.events()) == count + 1
    for e in h.events():
        text = json.dumps(e["data"])
        assert "t_alpha" not in text and "t_beta" not in text and "tenant" not in text.lower()
        assert set(e["data"]) <= {"change_id", "revision", "error_code", "action", "resource", "reason_code"}


def test_adp_c_068_health(h):
    assert h.call("health", t.ctx("platform"), {})["result"]["status"] == "ok"
    for tenant in ("t_ghost",):
        assert t.code_of(h.call("health", t.ctx(tenant), {})) in {"site_not_ready", "tenant_not_found"}
    t.site_at_rev1(h)
    result = h.call("health", t.ctx(), {})["result"]
    assert result["status"] == "ok" and result["checks"]


def test_adp_c_069_no_fault_hooks_in_production(h):
    caps = json.dumps(h.call("capabilities", t.ctx("platform"), {})["result"]).lower()
    assert not re.search(r"\b(fault|data_probe|auth_probe|action_probe|on_lock_held|advance_time|test_hooks|inject\w*)\b", caps)
    prod = optional(h.without_test_hooks)
    with pytest.raises(Exception):
        prod.fault("execute", step_seq=1)
    assert prod.call("capabilities", t.ctx("platform"), {})["ok"]


def test_adp_c_070_one_audit_record_per_call(h):
    t.site_at_rev1(h)
    log = optional(h.audit_log)
    ids = {r["auditId"] for r in log}
    art = t.sample("add-field")
    calls = [("capabilities", t.ctx("platform"), {}), ("site_status", t.ctx(), {}), ("export_config", t.ctx(), {}),
             ("plan", t.ctx(), {"artifact": art}), ("plan", t.ctx(), {"artifact": 1}),  # a failure writes one too
             ("health", t.ctx(), {}), ("site_status", t.ctx("t_ghost"), {})]
    for op, context, inp in calls:
        before = len(h.audit_log())
        resp = h.call(op, context, inp)
        log = h.audit_log()
        assert len(log) == before + 1 and log[-1]["auditId"] == resp["auditId"]
        assert resp["auditId"] not in ids
        ids.add(resp["auditId"])
    out = t.apply_artifact(h, art)
    assert out["auditId"] in {r["auditId"] for r in h.audit_log()}
