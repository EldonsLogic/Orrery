"""ADP-C-034 to ADP-C-050: apply (journaled, recoverable) and quarantine."""
import copy
import re

import pytest

from adapter import testkit as t
from conftest import assert_no_effect, event_types, optional

FAILED = ["blueprint.apply_failed"]  # the one event of an apply rejected in inspect (8.2)


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
        assert t.rejected_error(resp)["code"] == "plan_token_invalid", token
        assert_no_effect(h, "t_alpha", before, ev, expect=FAILED)


def test_adp_c_035_stale_token_after_other_change(h):
    t.site_at_rev1(h)
    art, other = t.sample("add-field"), t.sample("add-workflow-state")
    token = planned(h, art)["planToken"]
    assert t.apply_artifact(h, other)["result"]["status"] == "applied"
    before, ev = t.snapshot(h), len(h.events())
    assert t.rejected_error(raw_apply(h, art, token))["code"] == "plan_token_invalid"
    assert_no_effect(h, "t_alpha", before, ev, expect=FAILED)


def test_adp_c_036_missing_approvals(h):
    t.provision(h)
    build = t.initial_build()
    plan = planned(h, build)
    if plan["verdict"] != "needs_gate_approval":
        return  # this adapter needs no gate for the initial build: the missing-gate case does not exist (not a skip, not a claim)
    before, ev = t.snapshot(h), len(h.events())
    assert t.rejected_error(raw_apply(h, build, plan["planToken"], {"changeApproved": t.ulid()}))["code"] == "approval_missing"
    assert_no_effect(h, "t_alpha", before, ev, expect=FAILED)
    team = t.variant([t.field_step("customer", "n9")], requiresTeamReview=True)
    t.site_at_rev1(h, "t_beta")
    tp = planned(h, team, "t_beta")
    before, ev = t.snapshot(h, "t_beta"), len(h.events())
    assert t.rejected_error(raw_apply(h, team, tp["planToken"], {"changeApproved": t.ulid()}, "t_beta"))["code"] == "approval_missing"
    assert_no_effect(h, "t_beta", before, ev, expect=FAILED)
    ok = raw_apply(h, team, tp["planToken"], {"changeApproved": t.ulid(), "teamReviewed": t.ulid()}, "t_beta")
    assert ok["result"]["status"] == "applied"


def test_adp_c_037_rejected_plan(h):
    t.site_at_rev1(h)
    art = t.variant([t.field_step("customer", "n1"), t.entity_step(t.PROTECTED[0])])
    plan = planned(h, art)
    assert plan["verdict"] == "rejected"
    before, ev = t.snapshot(h), len(h.events())
    resp = raw_apply(h, art, plan["planToken"])
    err = t.rejected_error(resp)
    assert err["code"] == "plan_rejected"
    blocked = next(step for step in plan["steps"] if step["disposition"] == "blocked")
    assert err["details"] == {"stepSeq": blocked["seq"], "reasonCode": "protected_subject"}
    assert_no_effect(h, "t_alpha", before, ev, expect=FAILED)


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
    resp = raw_apply(h, art, plan["planToken"], {"changeApproved": t.ulid()}, k=key)
    assert not resp["ok"] and resp["error"]["code"] == "idempotency_conflict"  # before the operation record (5.6.1)
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
    assert not seen["resp"]["ok"]  # refused in acquire, before the operation record exists (5.6.1)
    err = seen["resp"]["error"]
    assert err["code"] == "concurrent_change" and err["retryable"] and err["retryAfterMs"] >= 0
    assert "blueprint.apply_failed" not in event_types(h)
    assert t.status(h)["state"] == "ready"
    assert event_types(h).count("blueprint.applied") == 2  # initial build and this apply, not the refused one


# ---------------------------------------------------------------- failure and recovery
NOTE_A, NOTE_B = "/entities/customer/fields/note_a", "/entities/customer/fields/note_b"


def assert_compensated(h, before, leftovers=()):
    """Section 5.6: the active export and the site status equal the pre-apply ones; quarantined leftovers of compensated
    additions appear only in `retained`, and nothing else is retained."""
    after = t.snapshot(h)
    assert (after[0], after[2]) == (before[0], before[2])
    retained = t.export(h)["retained"]
    assert sorted(r["pointer"] for r in retained) == sorted(leftovers)
    assert all(r["state"] in ("quarantined", "disabled") for r in retained)


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
    assert out["exportHash"] == before[0]
    assert_compensated(h, before, [NOTE_A])
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
    assert_compensated(h, before, [])  # the six undone steps are settings: set back, nothing left over


def test_adp_c_043_late_fault_in_initial_build_quarantines_additions(h):
    t.provision(h)
    before = t.snapshot(h)
    build = t.initial_build()
    n = len(build["steps"])
    h.fault("execute", step_seq=n)
    out = result_of(t.apply_artifact(h, build))
    assert out["status"] == "compensated" and out["steps"][-1]["status"] == "failed"
    added = {s["pointer"] for s in build["steps"] if s["kind"] != "settings.set"} - {build["steps"][-1]["pointer"]}
    assert added
    assert_compensated(h, before, added)


def test_adp_c_071_initial_build_compensation_is_journaled_removal(h):
    """Section 5.6.2: no stored inverse, so the undo is derived from the journal: additions quarantined or disabled,
    settings set back; every undo step journaled with phase compensate, newest first; no data dropped."""
    t.provision(h)
    before, ev = t.snapshot(h), len(h.events())
    build = t.initial_build()
    k = len(build["steps"])
    h.fault("execute", step_seq=k)
    out = result_of(t.apply_artifact(h, build))
    assert out["status"] == "compensated" and out["exportHash"] == before[0]
    created = {s["pointer"] for s in build["steps"][:k - 1] if s["kind"] != "settings.set"}
    assert created and {r["pointer"] for r in t.export(h)["retained"]} == created
    assert_compensated(h, before, created)
    journal = [(e["seq"], e["phase"]) for e in optional(h.execution_journal) if e["artifactId"] == build["artifactId"]]
    ran = list(range(1, k))
    assert journal == [(s, "execute") for s in ran] + [(s, "compensate") for s in reversed(ran)]
    assert optional(h.dropped_data) == []
    assert event_types(h, ev) == ["blueprint.apply_failed"]


def test_adp_c_044_postcondition_fault(h):
    out, before, ev = failed_outcome(h, {"stage": "reconcile", "post_condition_id": "pc_002"})
    assert out["status"] == "compensated"
    assert out["error"]["code"] == "postcondition_failed" and out["error"]["details"]["postConditionId"] == "pc_002"
    assert {"id": "pc_002", "passed": False} in out["postConditions"]
    assert {s["status"] for s in out["steps"]} == {"compensated"}
    assert_compensated(h, before, [NOTE_A, NOTE_B]) and event_types(h, ev) == ["blueprint.apply_failed"]


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
    before_hash = t.export(h)["exportHash"]
    h.fault("deadline", step_seq=2)
    first = raw_apply(h, art, plan["planToken"], approvals, k=key)
    assert t.code_of(first) == "timeout"
    outcome = None
    for _ in range(5):  # a retry with the same key: in_progress while running, then the final outcome
        again = raw_apply(h, art, plan["planToken"], approvals, k=key)
        assert again["ok"], again
        outcome = again["result"]
        if outcome["status"] != "in_progress":
            break
    assert outcome["status"] in {"applied", "compensated"}, "the apply never reached an outcome after the deadline"
    ran = [(e["seq"], e["phase"]) for e in optional(h.execution_journal) if e["artifactId"] == art["artifactId"]]
    forward = [seq for seq, phase in ran if phase == "execute"]
    assert len(forward) == len(set(forward)), f"a step ran twice: {ran}"  # independent of the export
    fields = [f["id"] for f in t.export(h)["export"]["sections"]["entities"][0]["fields"]]
    if outcome["status"] == "applied":
        assert sorted(forward) == [1, 2] and [p for _, p in ran].count("compensate") == 0
        assert {"note_a", "note_b"} <= set(fields)
        assert event_types(h).count("blueprint.applied") == 2  # initial build and this apply, once each
    else:  # no partial state: everything that ran was undone, exactly once
        assert sorted(seq for seq, phase in ran if phase == "compensate") == sorted(forward)
        assert t.export(h)["exportHash"] == before_hash
    assert t.status(h)["state"] == "ready"


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


DROP = re.compile(r"(?i)\b(drop|delete\s+from|truncate)\b")


def drop_statements(evidence: list[str]) -> list[str]:
    return [stmt for stmt in evidence if DROP.search(stmt)]


def test_adp_c_050_drop_scan_catches_a_drop():
    assert drop_statements(["ALTER TABLE x DROP COLUMN y"]) and drop_statements(["delete from x"])
    assert not drop_statements(["ALTER TABLE x ADD COLUMN y NULL", "UPDATE element_state SET state = 'quarantined'"])


def test_adp_c_050_plan_evidence_has_no_drop_statement(h):
    """Engine-adapter 14, ADP-C-050: judged on the adapter's own plan evidence, not on a harness report."""
    t.site_at_rev1(h)
    add, remove = t.sample("add-field"), t.sample("remove-field")
    at_rev1 = [add, t.two_fields()]  # additions: storage statements
    checked = 0

    def scan(arts):
        nonlocal checked
        for art in arts:
            evidence = optional(h.plan_evidence, planned(h, art)["evidenceRef"])
            assert evidence, "plan evidence is empty: nothing to judge"
            assert not drop_statements(evidence), evidence
            checked += len(evidence)

    scan(at_rev1)
    assert t.apply_artifact(h, add)["result"]["status"] == "applied"
    scan([remove, add["inverse"]])  # revision 2: the removal and the rollback of the addition (both quarantine)
    assert checked == 5


def test_adp_c_050_nothing_removes_stored_data(h):
    t.site_at_rev1(h)
    t.apply_artifact(h, t.sample("add-field"))
    h.data_probe(FIELD, 7)
    t.apply_artifact(h, t.sample("remove-field"))
    t.rollback(h, t.sample("remove-field"))
    t.rollback(h, t.sample("add-field"))
    h.fault("execute", step_seq=2)
    t.apply_artifact(h, t.two_fields())
    assert h.data_probe(FIELD) == 7  # the stored value survived every operation above, quarantine and rollback included
    assert optional(h.dropped_data) == []  # the harness report agrees; it is a second witness, not the judge


# ---------------------------------------------------------------- compensation runs the stored inverse steps (section 5.6)
def two_step_over_rev2(h):
    """Site at revision 2 (payment_terms_days present with data), and a forward artifact that adds note_a and quarantines it."""
    t.site_at_rev1(h)
    assert t.apply_artifact(h, t.sample("add-field"))["result"]["status"] == "applied"
    h.data_probe(FIELD, 30)
    removal = t.sample("remove-field")["steps"][0]
    return t.variant([t.field_step("customer", "note_a"), removal], template="remove-field")


def test_compensation_runs_inverse_steps_in_reverse_and_restores_retained_data(h):
    art = two_step_over_rev2(h)
    before = t.snapshot(h)
    h.fault("reconcile", post_condition_id="pc_001")
    out = result_of(t.apply_artifact(h, art))
    assert out["status"] == "compensated" and out["error"]["code"] == "postcondition_failed"
    journal = [e for e in optional(h.execution_journal) if e["artifactId"] == art["artifactId"]]
    assert [(e["seq"], e["phase"]) for e in journal] == [(1, "execute"), (2, "execute"), (2, "compensate"), (1, "compensate")]
    assert "payment_terms_days" in customer_fields(h)  # the quarantine was undone by its inverse (field.add), data kept
    assert h.data_probe(FIELD) == 30
    assert_compensated(h, before, [NOTE_A])  # the addition's inverse quarantined it; it is retained, not active, not erased


@pytest.mark.parametrize("damage", ["missing_step", "wrong_step"])
def test_compensation_without_a_correct_inverse_is_recovery_required(h, damage):
    t.site_at_rev1(h)
    art = t.two_fields()
    inv = art["inverse"]
    if damage == "missing_step":
        inv["steps"] = [s for s in inv["steps"] if not s["pointer"].endswith("note_b")]
    else:  # same pointer, but it does not undo the addition
        wrong = next(s for s in inv["steps"] if s["pointer"].endswith("note_b"))
        wrong.update(kind="field.set_property", phase=6, params={"property": "/min", "before": None, "after": 5})
    t.seal(art)
    h.fault("reconcile", post_condition_id="pc_001")
    out = result_of(t.apply_artifact(h, art))
    assert out["status"] == "recovery_required" and out["error"]["code"] == "recovery_required"
    assert t.status(h)["state"] == "recovery_required"


def test_failed_rollback_compensates_through_the_forward_steps(h):
    t.site_at_rev1(h)
    add = t.sample("add-field")
    assert t.apply_artifact(h, add)["result"]["status"] == "applied"
    h.data_probe(FIELD, 11)
    before = t.snapshot(h)
    h.fault("reconcile", post_condition_id="pc_001")
    out = result_of(t.rollback(h, add))
    assert out["status"] == "compensated" and out["operation"] == "rollback"
    assert "payment_terms_days" in customer_fields(h) and h.data_probe(FIELD) == 11
    assert_compensated(h, before, [])
    assert t.status(h)["applied"]["artifactId"] == add["artifactId"]
