"""ERP-033: sole-owner self-approval fallback (Q-41, Q-42, Q-563; TC-22, TC-23).

The fact "no other human holds the approving role" comes only from the trusted
`ActionContext.tenant_role_holders` that the server-side resolver fills, never from the payload.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)
SOLE = {"owner": frozenset({"owner-a"}), "tenant_admin": frozenset()}


@pytest.fixture
def policy():
    from change_engine.guarded_apply import action_policy_enforcer

    return action_policy_enforcer


def build(policy, path, action="AP-FIN-01", drafter="agent", holders=SOLE):
    """A request whose only possible approver (owner-a) is excluded by SOD-NOT-AGENT-OWNER or SOD-DIFF."""
    if action == "AP-FIN-01":
        payload = {"delivery_ids": ["delivery-a"], "customer": "customer-a", "total": "40.00", "currency": "SAR",
                   "lines": [{"item": "item-a", "quantity": 2, "price": "20.00", "discount": "0.00"}]}
        targets, role, amount = {"delivery-a": 3}, "finance", "40.00"
    else:
        payload = {"order_id": "order-a", "warehouse": "w", "amount": "10.00", "currency": "SAR",
                   "lines": [{"item": "item-a", "quantity": 1}]}
        targets, role, amount = {"order-a": 2}, "warehouse", "10.00"
    request = policy.ActionRequest("tenant-a", "request-a", action, 1, "sec-019-v1", "key-a", payload, targets)
    if drafter == "agent":  # Q-563: the agent belongs to the sole owner, a staff member submits.
        submitter = policy.Principal("staff-a", "human", frozenset({role}))
        author = policy.Principal("agent-a", "agent", frozenset(), "owner-a")
    else:  # Q-41: the owner initiates their own request.
        submitter = policy.Principal("owner-a", "human", frozenset({"owner", role}))
        author = submitter
    approver = policy.Principal("owner-a", "human", frozenset({"owner"}))
    approval = policy.Approval("approval-a", "tenant-a", action, "sec-019-v1",
                               policy.payload_hash(request, submitter.id), approver, NOW + timedelta(hours=1),
                               "approved", step_up=True)
    context = policy.ActionContext("tenant-a", "request-a", action, submitter, author, in_scope=True, active=True,
                                   approvals=(approval,), amount=amount, currency="SAR",
                                   tenant_role_holders=holders)
    return request, context, path / "policy.sqlite3"


def guard_for(policy, context, path):
    return policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(stock_cap="100.00", invoice_cap="100.00", currency="SAR"),
        lambda session, request: context if session == "trusted-session" else None,
        policy.ActionPolicyStore(path), clock=lambda: NOW)


def admit(guard, request):
    return guard.authorize("trusted-session", request, session_tenant_id="tenant-a")


def last_reason(guard):
    return guard.store.audit_log()[-1].reason


@pytest.mark.parametrize("action", ["AP-FIN-01", "AP-STOCK-01"])
@pytest.mark.parametrize("drafter", ["agent", "human"])
def test_tc22_sole_owner_self_approval_is_allowed_and_flagged(policy, tmp_path, action, drafter):
    request, context, path = build(policy, tmp_path, action, drafter)
    guard = guard_for(policy, context, path)
    admitted = admit(guard, request)
    assert admitted is not None and admitted.self_approved is True
    record = guard.store.audit_log()[-1]
    assert (record.decision, record.self_approved) == ("allow", True)
    assert record.approvers == (context.approvals[0].approver,)


@pytest.mark.parametrize("action", ["AP-FIN-01", "AP-STOCK-01"])
def test_missing_step_up_is_denied(policy, tmp_path, action):
    request, context, path = build(policy, tmp_path, action)
    context = replace(context, approvals=(replace(context.approvals[0], step_up=False),))
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


@pytest.mark.parametrize("holders", [
    pytest.param({"owner": frozenset({"owner-a", "owner-b"}), "tenant_admin": frozenset()}, id="second-owner"),
    pytest.param({"owner": frozenset({"owner-a"}), "tenant_admin": frozenset({"admin-b"})}, id="second-admin"),
])
@pytest.mark.parametrize("drafter", ["agent", "human"])
def test_tc23_second_human_holding_the_role_denies_even_if_unavailable(policy, tmp_path, holders, drafter):
    # Role holding, not availability: the resolver lists the absent or suspended person too.
    request, context, path = build(policy, tmp_path, drafter=drafter, holders=holders)
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


@pytest.mark.parametrize("holders", [
    pytest.param(None, id="unresolved"),
    pytest.param({}, id="empty-map"),
    pytest.param({"owner": frozenset({"owner-a"})}, id="role-missing-from-map"),
    pytest.param({"owner": frozenset({"owner-a"}), "tenant_admin": None}, id="role-not-a-set"),
    pytest.param({"owner": {"owner-a"}, "tenant_admin": frozenset()}, id="mutable-set"),
    pytest.param({"owner": frozenset(), "tenant_admin": frozenset()}, id="approver-not-listed"),
    pytest.param({"owner": frozenset({"owner-b"}), "tenant_admin": frozenset()}, id="approver-not-the-holder"),
    pytest.param({"owner": frozenset({"owner-a", ""}), "tenant_admin": frozenset()}, id="blank-id"),
    pytest.param(["owner-a"], id="not-a-map"),
])
def test_untrusted_or_malformed_role_holder_fact_fails_closed(policy, tmp_path, holders):
    request, context, path = build(policy, tmp_path, holders=holders)
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


def test_payload_cannot_claim_to_be_a_sole_owner(policy, tmp_path):
    request, context, path = build(policy, tmp_path, holders=None)
    request = replace(request, payload={**request.payload, "sole_owner": True, "tenant_role_holders": ["owner-a"]})
    context = replace(context, approvals=(replace(
        context.approvals[0], payload_hash=policy.payload_hash(request, context.submitter.id)),))
    assert admit(guard_for(policy, context, path), request) is None


def test_tc23_r4_permission_change_never_self_approved(policy, tmp_path):
    owner = policy.Principal("owner-a", "human", frozenset({"owner"}))
    request = policy.ActionRequest("tenant-a", "request-a", "AP-PERM-01", 1, "sec-019-v1", "key-a", {
        "target_user": "user-x", "roles_before": [], "roles_after": ["sales"], "scopes": [],
        "limits_before": {}, "limits_after": {}}, {"user-x": 1})
    approval = policy.Approval("approval-a", "tenant-a", "AP-PERM-01", "sec-019-v1",
                               policy.payload_hash(request, owner.id), owner, NOW + timedelta(hours=1),
                               "approved", step_up=True)
    context = policy.ActionContext("tenant-a", "request-a", "AP-PERM-01", owner, owner, in_scope=True, active=True,
                                   approvals=(approval,), tenant_role_holders=SOLE)
    guard = guard_for(policy, context, tmp_path / "policy.sqlite3")
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


def test_tc23_r4_invoice_cancellation_never_self_approved(policy, tmp_path):
    # The sole owner's own agent drafts the cancellation of a posted invoice (reversal of history).
    request = policy.ActionRequest("tenant-a", "request-a", "AP-FIN-02", 1, "sec-019-v1", "key-a", {
        "invoice_id": "invoice-a", "reason": "Duplicate", "total": "40.00", "currency": "SAR"}, {"invoice-a": 4})
    submitter = policy.Principal("staff-a", "human", frozenset({"finance"}))
    approver = policy.Principal("owner-a", "human", frozenset({"owner"}))
    approval = policy.Approval("approval-a", "tenant-a", "AP-FIN-02", "sec-019-v1",
                               policy.payload_hash(request, submitter.id), approver, NOW + timedelta(hours=1),
                               "approved", step_up=True)
    context = policy.ActionContext("tenant-a", "request-a", "AP-FIN-02", submitter,
                                   policy.Principal("agent-a", "agent", frozenset(), "owner-a"), in_scope=True,
                                   active=True, approvals=(approval,), amount="40.00", currency="SAR",
                                   tenant_role_holders=SOLE)
    guard = guard_for(policy, context, tmp_path / "policy.sqlite3")
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


def test_fallback_needs_a_row_that_requires_a_different_approver(policy, tmp_path):
    # A tenant tightening AP-SALES-01 (SOD-NONE by default) does not create a self-approval route.
    request = policy.ActionRequest("tenant-a", "request-a", "AP-SALES-01", 1, "sec-019-v1", "key-a", {
        "customer": "customer-a", "total": "9.00", "currency": "SAR",
        "lines": [{"item": "item-a", "quantity": 1, "price": "9.00", "discount": "0.00"}]}, {"customer-a": 1})
    submitter = policy.Principal("owner-a", "human", frozenset({"owner"}))
    approval = policy.Approval("approval-a", "tenant-a", "AP-SALES-01", "sec-019-v1",
                               policy.payload_hash(request, submitter.id), submitter, NOW + timedelta(hours=1),
                               "approved", step_up=True)
    context = policy.ActionContext("tenant-a", "request-a", "AP-SALES-01", submitter, submitter, in_scope=True,
                                   active=True, approvals=(approval,), approvals_required=1,
                                   tenant_role_holders=SOLE)
    assert admit(guard_for(policy, context, tmp_path / "policy.sqlite3"), request) is None


def test_two_required_approvals_cannot_be_met_by_one_sole_owner(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    second = replace(context.approvals[0], id="approval-b")
    context = replace(context, approvals_required=2, approvals=(context.approvals[0], second))
    assert admit(guard_for(policy, context, path), request) is None


@pytest.mark.parametrize("approver", [
    pytest.param(dict(roles=frozenset({"tenant_admin"})), id="non-owner-role"),
    pytest.param(dict(kind="agent", owner_id="owner-a"), id="agent-approver"),
])
def test_only_the_tenant_owner_may_use_the_fallback(policy, tmp_path, approver):
    request, context, path = build(policy, tmp_path)
    holders = {"owner": frozenset(), "tenant_admin": frozenset({"owner-a"})}
    actor = replace(context.approvals[0].approver, **approver)
    context = replace(context, tenant_role_holders=holders,
                      approvals=(replace(context.approvals[0], approver=actor),))
    assert admit(guard_for(policy, context, path), request) is None


def test_unexcluded_approver_is_unchanged_and_not_flagged(policy, tmp_path):
    # The agent belongs to someone else, so a different owner approves as before; the new fact is not needed.
    for holders in (None, SOLE):
        (tmp_path / str(holders is None)).mkdir()
        request, context, path = build(policy, tmp_path / str(holders is None), holders=holders)
        drafter = replace(context.drafter, owner_id="owner-b")
        context = replace(context, drafter=drafter, tenant_role_holders=holders,
                          approvals=(replace(context.approvals[0], approver=replace(
                              context.approvals[0].approver, id="owner-c")),))
        guard = guard_for(policy, context, path)
        admitted = admit(guard, request)
        assert admitted is not None and admitted.self_approved is False
        assert guard.store.audit_log()[-1].self_approved is False


def test_submitter_still_cannot_approve_when_another_owner_exists(policy, tmp_path):
    # The submitter may not approve their own request, with or without the role-holder fact.
    request, context, path = build(policy, tmp_path)
    submitter = replace(context.submitter, roles=frozenset({"finance", "owner"}))
    approval = replace(context.approvals[0], payload_hash=policy.payload_hash(request, submitter.id),
                       approver=replace(context.approvals[0].approver, id=submitter.id))
    context = replace(context, submitter=submitter, drafter=replace(context.drafter, owner_id="owner-b"),
                      approvals=(approval,), tenant_role_holders={
                          "owner": frozenset({submitter.id, "owner-b"}), "tenant_admin": frozenset()})
    assert admit(guard_for(policy, context, path), request) is None


def test_flag_survives_the_audit_store_and_only_marks_admitted_fallbacks(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is not None
    other = replace(request, request_id="request-b", idempotency_key="key-b")
    stale = replace(context.approvals[0], id="approval-b", step_up=False,
                    payload_hash=policy.payload_hash(other, context.submitter.id))
    denied = replace(context, request_id="request-b", approvals=(stale,))
    assert admit(guard_for(policy, denied, path), other) is None
    reopened = policy.ActionPolicyStore(path).audit_log()
    assert [(entry.decision, entry.self_approved) for entry in reopened] == [("allow", True), ("deny", False)]


# --- Review fixes (#306) -------------------------------------------------------------------------
# Finding 1: the exclusion is lifted only for the initiator (Q-41) or the owner of the drafting agent
# (Q-563), never because the owner authored or edited somebody else's request.

OWNER = {"id": "owner-a", "kind": "human", "roles": frozenset({"owner"})}


def rebind(policy, request, context, **changes):
    """Replace context fields and re-bind the approval to the (possibly new) submitter."""
    context = replace(context, **changes)
    approval = replace(context.approvals[0], payload_hash=policy.payload_hash(request, context.submitter.id))
    return replace(context, approvals=(approval,))


def staff(policy, name, action):
    role = "finance" if action == "AP-FIN-01" else "warehouse"
    return policy.Principal(name, "human", frozenset({role}))


@pytest.mark.parametrize("action", ["AP-FIN-01", "AP-STOCK-01"])
def test_staff_initiated_draft_authored_by_the_owner_is_denied(policy, tmp_path, action):
    request, context, path = build(policy, tmp_path, action)
    context = rebind(policy, request, context, submitter=staff(policy, "staff-a", action),
                     drafter=policy.Principal(**OWNER))
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"
    assert guard.store.audit_log()[-1].self_approved is False


@pytest.mark.parametrize("drafter", [
    pytest.param("staff-a", id="drafted-by-submitter"),
    pytest.param("staff-b", id="drafted-by-another-human"),
])
def test_staff_initiated_human_draft_edited_by_the_owner_is_denied(policy, tmp_path, drafter):
    request, context, path = build(policy, tmp_path, "AP-FIN-01")
    context = rebind(policy, request, context, submitter=staff(policy, "staff-a", "AP-FIN-01"),
                     drafter=staff(policy, drafter, "AP-FIN-01"), editor_ids=frozenset({"owner-a"}))
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


@pytest.mark.parametrize("agent_owner", ["owner-b", "owner-a"])
def test_agent_draft_edited_by_the_owner_is_denied(policy, tmp_path, agent_owner):
    # Another person's agent, or the approver's own agent that the approver then edited: still not a second person.
    request, context, path = build(policy, tmp_path, "AP-FIN-01")
    context = replace(context, drafter=replace(context.drafter, owner_id=agent_owner),
                      editor_ids=frozenset({"owner-a"}))
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is None
    assert last_reason(guard) == "ineligible_approver"


@pytest.mark.parametrize("action", ["AP-FIN-01", "AP-STOCK-01"])
def test_owner_initiator_may_self_approve_whoever_drafted(policy, tmp_path, action):
    # Q-41: the initiator is the owner; a staff member or another owner's agent drafted it.
    request, context, path = build(policy, tmp_path, action)
    owner = policy.Principal("owner-a", "human", frozenset({"owner"}) | staff(policy, "x", action).roles)
    context = rebind(policy, request, context, submitter=owner, drafter=staff(policy, "staff-b", action))
    admitted = admit(guard_for(policy, context, path), request)
    assert admitted is not None and admitted.self_approved is True


def test_owner_initiator_who_also_edited_may_self_approve(policy, tmp_path):
    request, context, path = build(policy, tmp_path, "AP-FIN-01", "human")
    context = replace(context, editor_ids=frozenset({"owner-a"}))
    admitted = admit(guard_for(policy, context, path), request)
    assert admitted is not None and admitted.self_approved is True


def test_owner_initiator_with_another_owners_agent_draft_may_self_approve(policy, tmp_path):
    request, context, path = build(policy, tmp_path, "AP-FIN-01")
    owner = policy.Principal("owner-a", "human", frozenset({"owner", "finance"}))
    context = rebind(policy, request, context, submitter=owner,
                     drafter=replace(context.drafter, owner_id="owner-b"))
    admitted = admit(guard_for(policy, context, path), request)
    assert admitted is not None and admitted.self_approved is True


# Finding 3: a self-approved allow that the store downgrades to a deny never keeps the flag.

def clock_from(*steps):
    """First call is the enforcer's read, the next the store's re-check; a callable step raises or returns."""
    queue = list(steps)

    def clock():
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, Exception):
            raise step
        return step
    return clock


@pytest.mark.parametrize("second, reason", [
    pytest.param(NOW + timedelta(hours=2), "expired", id="expiry"),
    pytest.param(RuntimeError("clock down"), "clock_unavailable", id="clock-failure"),
    pytest.param(datetime(2026, 11, 22), "clock_unavailable", id="naive-clock"),
    pytest.param(NOW - timedelta(seconds=1), "clock_unavailable", id="clock-went-back"),
])
def test_downgraded_self_approval_is_a_flagless_denial(policy, tmp_path, second, reason):
    request, context, path = build(policy, tmp_path)
    guard = policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(stock_cap="100.00", invoice_cap="100.00", currency="SAR"),
        lambda session, req: context, policy.ActionPolicyStore(path), clock=clock_from(NOW, second))
    assert admit(guard, request) is None
    record = guard.store.audit_log()[-1]
    assert (record.decision, record.reason, record.self_approved) == ("deny", reason, False)


def test_replayed_self_approval_is_a_flagless_denial(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    guard = guard_for(policy, context, path)
    assert admit(guard, request) is not None
    assert admit(guard, request) is None
    first, replay = guard.store.audit_log()
    assert (first.decision, first.self_approved) == ("allow", True)
    assert (replay.decision, replay.reason, replay.self_approved) == ("deny", "replay", False)


# Finding 2: the periodic review report input, read from the persisted journal.

def variant(policy, request, context, name, *, tenant="tenant-a", **changes):
    """Another admissible request of the same shape: its own ids, bound hash and (optionally) tenant."""
    request = replace(request, tenant_id=tenant, request_id=f"request-{name}", idempotency_key=f"key-{name}")
    context = replace(context, tenant_id=tenant, request_id=f"request-{name}", **changes)
    approval = replace(context.approvals[0], id=f"approval-{name}", tenant_id=tenant,
                       payload_hash=policy.payload_hash(request, context.submitter.id))
    return request, replace(context, approvals=(approval,))


def admit_at(policy, path, request, context, when, tenant="tenant-a"):
    guard = policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(stock_cap="100.00", invoice_cap="100.00", currency="SAR"),
        lambda session, req: context, policy.ActionPolicyStore(path), clock=lambda: when)
    return guard.authorize("trusted-session", request, session_tenant_id=tenant)


def ids(report):
    return [record.request_id for record in report]


def test_self_approved_report_lists_only_this_tenants_allowed_self_approvals(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    assert admit_at(policy, path, *variant(policy, request, context, "self"), NOW) is not None
    # A normal approval by a different owner, a denial and another tenant's self-approval.
    normal_request, normal = variant(policy, request, context, "normal")
    other = replace(normal.approvals[0].approver, id="owner-c")
    normal = replace(normal, approvals=(replace(normal.approvals[0], approver=other),))
    assert admit_at(policy, path, normal_request, normal, NOW) is not None
    denied_request, denied = variant(policy, request, context, "denied")
    denied = replace(denied, approvals=(replace(denied.approvals[0], step_up=False),))
    assert admit_at(policy, path, denied_request, denied, NOW) is None
    foreign = variant(policy, request, context, "foreign", tenant="tenant-b")
    assert admit_at(policy, path, *foreign, NOW, tenant="tenant-b") is not None

    store = policy.ActionPolicyStore(path)
    window = (NOW - timedelta(days=1), NOW + timedelta(days=1))
    report = store.self_approved_report("tenant-a", *window)
    assert ids(report) == ["request-self"]
    assert all(r.tenant_id == "tenant-a" and r.decision == "allow" and r.self_approved for r in report)
    assert ids(store.self_approved_report("tenant-b", *window)) == ["request-foreign"]
    assert store.self_approved_report("tenant-c", *window) == ()


def test_self_approved_report_window_is_half_open_and_time_ordered(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    minutes = {"late": 20, "early": 0, "middle": 10}  # appended out of time order on purpose
    for name, minute in minutes.items():
        assert admit_at(policy, path, *variant(policy, request, context, name),
                        NOW + timedelta(minutes=minute)) is not None
    store = policy.ActionPolicyStore(path)
    everything = store.self_approved_report("tenant-a", NOW, NOW + timedelta(hours=1))
    assert ids(everything) == ["request-early", "request-middle", "request-late"]
    assert ids(store.self_approved_report("tenant-a", NOW + timedelta(minutes=10), NOW + timedelta(minutes=20))) \
        == ["request-middle"]
    assert ids(store.self_approved_report("tenant-a", NOW - timedelta(minutes=5), NOW)) == []


def test_self_approved_report_excludes_downgraded_records(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    assert admit_at(policy, path, *variant(policy, request, context, "ok"), NOW) is not None
    # Same approval replayed on a new request: denied as a replay, flag cleared.
    again_request, again = variant(policy, request, context, "again")
    again = replace(again, approvals=(replace(again.approvals[0], id="approval-ok"),))
    assert admit_at(policy, path, again_request, again, NOW) is None
    store = policy.ActionPolicyStore(path)
    assert ids(store.self_approved_report("tenant-a", NOW - timedelta(days=1), NOW + timedelta(days=1))) == ["request-ok"]


@pytest.mark.parametrize("tenant, since, until", [
    pytest.param("", NOW, NOW + timedelta(days=1), id="blank-tenant"),
    pytest.param(None, NOW, NOW + timedelta(days=1), id="no-tenant"),
    pytest.param(7, NOW, NOW + timedelta(days=1), id="non-text-tenant"),
    pytest.param("tenant-a", datetime(2026, 11, 22), NOW + timedelta(days=1), id="naive-since"),
    pytest.param("tenant-a", NOW, datetime(2026, 11, 23), id="naive-until"),
    pytest.param("tenant-a", "2026-11-22", NOW + timedelta(days=1), id="text-since"),
    pytest.param("tenant-a", NOW + timedelta(days=1), NOW, id="reversed-window"),
    pytest.param("tenant-a", NOW, NOW, id="empty-window"),
])
def test_self_approved_report_rejects_invalid_arguments(policy, tmp_path, tenant, since, until):
    request, context, path = build(policy, tmp_path)
    assert admit_at(policy, path, *variant(policy, request, context, "ok"), NOW) is not None
    with pytest.raises(ValueError):
        policy.ActionPolicyStore(path).self_approved_report(tenant, since, until)


def test_self_approved_report_exposes_no_payload(policy, tmp_path):
    request, context, path = build(policy, tmp_path)
    assert admit_at(policy, path, *variant(policy, request, context, "ok"), NOW) is not None
    (record,) = policy.ActionPolicyStore(path).self_approved_report("tenant-a", NOW, NOW + timedelta(days=1))
    assert type(record).__name__ == "ActionAudit" and not hasattr(record, "payload")
    assert "customer-a" not in repr(record)
