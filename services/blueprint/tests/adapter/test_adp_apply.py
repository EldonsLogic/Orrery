"""ADP-C-034 to ADP-C-050: apply (journaled, recoverable) and quarantine."""
import copy

import pytest

from adapter import testkit as t
from conftest import assert_no_effect, event_types, optional

FAILED = {"blueprint.apply_failed"}


def result_of(resp):
    assert resp["ok"], resp
    return resp["result"]


def planned(h, art, tenant="t_alpha"):
    return result_of(t.plan(h, art, tenant))


def raw_apply(h, art, token, approvals=None, tenant="t_alpha", k=None, who=t.USER):
    return h.call("apply", t.ctx(tenant, who=who), {"idempotencyKey": k or t.key(), "artifact": art, "planToken": token,
                                                    "approvals": approvals or {"changeApproved": t.ulid()}})


# ---------------------------------------------------------------- plan token and approvals
def test_adp_c_034_plan_token_checks(h):
    t.site_at_rev1(h, "t_alpha")
    t.site_at_rev1(h, "t_beta")
    art, other = t.sample("add-field"), t.sample("add-workflow-state")
    expired = planned(h, art)["planToken"]
    ttl = h.call("capabilities", t.ctx("platform"), {})["result"]["limits"]["planTokenTtlSeconds"]
    optional(h.advance_time, ttl + 1)
    for token in ("pln_" + "z" * 24, planned(h, art, "t_beta")["planToken"], planned(h, other)["planToken"], expired):
        before, ev = t.snapshot(h), len(h.events())
        resp = raw_apply(h, art, token)  # missing, foreign tenant, foreign artifact, expired
        assert t.code_of(resp) == "plan_token_invalid", token
        assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)


def test_adp_c_035_stale_token_after_other_change(h):
    t.site_at_rev1(h)
    art, other = t.sample("add-field"), t.sample("add-workflow-state")
    token = planned(h, art)["planToken"]
    assert t.apply_artifact(h, other)["result"]["status"] == "applied"
    before, ev = t.snapshot(h), len(h.events())
    assert t.code_of(raw_apply(h, art, token)) == "plan_token_invalid"
    assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)


def test_adp_c_036_missing_approvals(h):
    t.provision(h)
    build = t.initial_build()
    plan = planned(h, build)
    if plan["verdict"] != "needs_gate_approval":
        pytest.skip("initial build needs no gate on this adapter")
    before, ev = t.snapshot(h), len(h.events())
    assert t.code_of(raw_apply(h, build, plan["planToken"], {"changeApproved": t.ulid()})) == "approval_missing"
    assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)
    team = t.variant([t.field_step("customer", "n9")], requiresTeamReview=True)
    t.site_at_rev1(h, "t_beta")
    tp = planned(h, team, "t_beta")
    assert t.code_of(raw_apply(h, team, tp["planToken"], {"changeApproved": t.ulid()}, "t_beta")) == "approval_missing"
    ok = raw_apply(h, team, tp["planToken"], {"changeApproved": t.ulid(), "teamReviewed": t.ulid()}, "t_beta")
    assert ok["result"]["status"] == "applied"


def test_adp_c_037_rejected_plan(h):
    t.site_at_rev1(h)
    art = t.variant([t.field_step("customer", "n1"), t.entity_step(t.PROTECTED[0])])
    plan = planned(h, art)
    assert plan["verdict"] == "rejected"
    before, ev = t.snapshot(h), len(h.events())
    resp = raw_apply(h, art, plan["planToken"])
    err = t.error_of(resp)
    assert err["code"] == "plan_rejected"
    blocked = next(step for step in plan["steps"] if step["disposition"] == "blocked")
    assert err["details"] == {"stepSeq": blocked["seq"], "reasonCode": "protected_subject"}
    assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)


# ---------------------------------------------------------------- the happy path
def check_applied(h, art, tenant="t_alpha"):
    out = result_of(t.apply_artifact(h, art, tenant))
    assert out["status"] == "applied" and out["operation"] == "apply" and out["artifactId"] == art["artifactId"]
    assert {s["status"] for s in out["steps"]} == {"applied"} and len(out["steps"]) == len(art["steps"])
    assert out["postConditions"] and all(p["passed"] for p in out["postConditions"])
    assert out["site"]["applied"] == {"artifactId": art["artifactId"], "revision": art["blueprint"]["target"]}
    assert out["exportHash"] == t.export(h, tenant)["exportHash"]
    assert [s["stage"] for s in out["stages"]] == ["acquire", "inspect", "prepare", "execute", "reconcile", "finalize"]
    assert out["site"]["state"] == "ready" and out["site"]["lockedBy"] is None
    return out


def test_adp_c_038_sample_chains(h):
    t.provision(h, "t_alpha")
    t.provision(h, "t_beta")
    for art in (t.initial_build(), t.sample("add-field"), t.sample("remove-field")):
        check_applied(h, art, "t_alpha")
    for art in (t.initial_build(), t.sample("add-workflow-state")):
        check_applied(h, art, "t_beta")


def test_adp_c_039_replay_returns_stored_outcome(h):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    plan = planned(h, art)
    approvals = {"changeApproved": t.ulid()}
    key = t.key()
    first = raw_apply(h, art, plan["planToken"], approvals, k=key)
    after, ev = t.snapshot(h), len(h.events())
    again = raw_apply(h, art, plan["planToken"], approvals, k=key)
    assert again["replayed"] is True and first["replayed"] is False
    assert again["result"] == first["result"]
    assert t.snapshot(h) == after and len(h.events()) == ev


def test_adp_c_040_same_key_other_input(h):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    plan = planned(h, art)
    key = t.key()
    assert raw_apply(h, art, plan["planToken"], k=key)["result"]["status"] == "applied"
    before, ev = t.snapshot(h), len(h.events())
    assert t.code_of(raw_apply(h, art, plan["planToken"], {"changeApproved": t.ulid()}, k=key)) == "idempotency_conflict"
    assert_no_effect(h, "t_alpha", before, ev)


def test_adp_c_041_already_applied(h):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    plan = planned(h, art)
    assert raw_apply(h, art, plan["planToken"])["result"]["status"] == "applied"
    before, ev = t.snapshot(h), len(h.events())
    again = raw_apply(h, art, plan["planToken"])
    assert again["result"]["status"] == "already_applied" and again["result"]["exportHash"]
    assert t.snapshot(h) == before and len(h.events()) == ev


def test_adp_c_042_concurrent_apply(h):
    t.site_at_rev1(h)
    art = t.sample("add-field")
    token = planned(h, art)["planToken"]
    seen = {}

    def second():
        seen["status"] = t.status(h)
        seen["resp"] = raw_apply(h, art, token)

    optional(h.on_lock_held, second)
    first = raw_apply(h, art, token)
    assert first["result"]["status"] == "applied"
    assert seen["status"]["state"] == "applying" and seen["status"]["lockedBy"]
    err = seen["resp"]["error"]
    assert err["code"] == "concurrent_change" and err["retryable"] and err["retryAfterMs"] >= 0
    assert t.status(h)["state"] == "ready"
    assert event_types(h).count("blueprint.applied") == 2  # initial build and this apply, not the refused one


# ---------------------------------------------------------------- failure and recovery
def failed_outcome(h, fault_args, art=None):
    t.site_at_rev1(h)
    art = art or t.two_fields()
    before, ev = t.snapshot(h), len(h.events())
    h.fault(**fault_args)
    out = result_of(t.apply_artifact(h, art))
    return out, before, ev


def test_adp_c_043_fault_at_step_compensates(h):
    out, before, ev = failed_outcome(h, {"stage": "execute", "step_seq": 2})
    assert out["status"] == "compensated" and out["error"]["code"] == "engine_unavailable"
    assert [s["status"] for s in out["steps"]] == ["compensated", "failed"]
    assert out["site"]["applied"] == t.status(h)["applied"] and out["site"]["state"] == "ready"
    assert out["exportHash"] == before[0] and t.snapshot(h) == before
    assert event_types(h, ev) == ["blueprint.apply_failed"]
    assert t.apply_artifact(h, t.two_fields())["result"]["status"] == "applied"  # nothing is stuck


def test_adp_c_043_fault_in_initial_build(h):
    t.provision(h)
    before = t.snapshot(h)
    h.fault("execute", step_seq=7)
    out = result_of(t.apply_artifact(h, t.initial_build()))
    assert out["status"] == "compensated"
    assert [s["status"] for s in out["steps"]][:6] == ["compensated"] * 6 and out["steps"][6]["status"] == "failed"
    assert {s["status"] for s in out["steps"][7:]} == {"not_run"}
    assert t.snapshot(h) == before


def test_adp_c_044_postcondition_fault(h):
    out, before, ev = failed_outcome(h, {"stage": "reconcile", "post_condition_id": "pc_002"})
    assert out["status"] == "compensated"
    assert out["error"]["code"] == "postcondition_failed" and out["error"]["details"]["postConditionId"] == "pc_002"
    assert {"id": "pc_002", "passed": False} in out["postConditions"]
    assert {s["status"] for s in out["steps"]} == {"compensated"}
    assert t.snapshot(h) == before and event_types(h, ev) == ["blueprint.apply_failed"]


def test_adp_c_045_fault_during_compensation_blocks_site(h):
    out, before, ev = failed_outcome(h, {"stage": "execute", "step_seq": 2, "during_compensation": True})
    assert out["status"] == "recovery_required" and out["error"]["code"] == "recovery_required"
    assert out["site"]["state"] == "recovery_required" and t.status(h)["state"] == "recovery_required"
    assert event_types(h, ev) == ["blueprint.apply_failed"]
    art = t.sample("add-field")
    plan = t.plan(h, art)["result"]
    assert plan["verdict"] == "rejected"
    assert t.code_of(raw_apply(h, art, plan["planToken"])) == "recovery_required"
    assert t.code_of(t.rollback(h, art)) == "recovery_required"
    assert h.call("health", t.ctx(), {})["result"]["status"] == "down"
    assert h.call("export_config", t.ctx(), {})["ok"]  # reading stays possible


def test_adp_c_045_fault_in_postcondition_compensation(h):
    out, _, _ = failed_outcome(h, {"stage": "reconcile", "post_condition_id": "pc_001", "during_compensation": True})
    assert out["status"] == "recovery_required" and t.status(h)["state"] == "recovery_required"


def test_adp_c_045_finalize_fault_blocks_site(h):
    out, _, ev = failed_outcome(h, {"stage": "finalize"})
    assert out["status"] == "recovery_required" and t.status(h)["state"] == "recovery_required"


def test_adp_c_046_prepare_fault_is_failed_clean(h):
    out, before, ev = failed_outcome(h, {"stage": "prepare"})
    assert out["status"] == "failed_clean" and out["error"]["code"]
    assert {s["status"] for s in out["steps"]} == {"not_run"}
    assert t.snapshot(h) == before and event_types(h, ev) == ["blueprint.apply_failed"]


def test_adp_c_047_deadline_expiry_never_runs_a_step_twice(h):
    t.site_at_rev1(h)
    art = t.two_fields()
    plan = planned(h, art)
    approvals = {"changeApproved": t.ulid()}
    key = t.key()
    h.fault("deadline", step_seq=2)
    first = raw_apply(h, art, plan["planToken"], approvals, k=key)
    assert t.code_of(first) in {"timeout", None}
    again = raw_apply(h, art, plan["planToken"], approvals, k=key)
    assert again["ok"] and again["result"]["status"] in {"in_progress", "applied"}
    fields = [f["id"] for f in t.export(h)["export"]["sections"]["entities"][0]["fields"]]
    assert fields.count("note_a") <= 1 and fields.count("note_b") <= 1
    if again["result"]["status"] == "applied":
        assert {"note_a", "note_b"} <= set(fields)
        assert event_types(h).count("blueprint.applied") == 2  # initial build and this apply, once each
    assert t.status(h)["state"] in {"ready", "applying"}


# ---------------------------------------------------------------- quarantine, restore, no data loss
FIELD = "/entities/customer/fields/payment_terms_days"


def customer_fields(h):
    entities = t.export(h)["export"]["sections"]["entities"]
    return [f["id"] for f in next(e for e in entities if e["id"] == "customer")["fields"]]


def test_adp_c_048_removal_is_quarantine_and_data_survives(h):
    t.site_at_rev1(h)
    assert t.apply_artifact(h, t.sample("add-field"))["result"]["status"] == "applied"
    h.data_probe(FIELD, 30)
    assert t.apply_artifact(h, t.sample("remove-field"))["result"]["status"] == "applied"
    assert "payment_terms_days" not in customer_fields(h)
    assert {"pointer": FIELD, "state": "quarantined"} in t.export(h)["retained"]
    assert h.data_probe(FIELD) == 30
    assert t.rollback(h, t.sample("remove-field"))["result"]["status"] == "applied"
    assert "payment_terms_days" in customer_fields(h) and h.data_probe(FIELD) == 30
    assert not t.export(h)["retained"]


def test_adp_c_049_restore_same_definition_blocks_different(h):
    t.site_at_rev1(h)
    add = t.sample("add-field")
    assert t.apply_artifact(h, add)["result"]["status"] == "applied"
    h.data_probe(FIELD, 45)
    assert t.rollback(h, add)["result"]["status"] == "applied"
    assert {"pointer": FIELD, "state": "quarantined"} in t.export(h)["retained"]
    different = t.sample("add-field")
    different["steps"][0]["params"]["definition"]["max"] = 999
    plan = planned(h, t.seal(different))
    assert plan["steps"][0]["disposition"] == "blocked" and plan["steps"][0]["reasonCode"] == "definition_conflict"
    assert plan["verdict"] == "rejected"
    preview = planned(h, add)
    assert t.plan(h, add, op="preview")["result"]["delta"] == [{"change": "restore", "pointer": FIELD}]
    assert t.apply_artifact(h, add)["result"]["status"] == "applied"
    assert h.data_probe(FIELD) == 45 and preview["verdict"] == "auto_approved"
    assert not t.export(h)["retained"]


def test_adp_c_050_nothing_removes_stored_data(h):
    t.site_at_rev1(h)
    t.apply_artifact(h, t.sample("add-field"))
    h.data_probe(FIELD, 7)
    t.apply_artifact(h, t.sample("remove-field"))
    t.rollback(h, t.sample("remove-field"))
    t.rollback(h, t.sample("add-field"))
    h.fault("execute", step_seq=2)
    t.apply_artifact(h, t.two_fields())
    assert optional(h.dropped_data) == []
    assert h.data_probe(FIELD) == 7
