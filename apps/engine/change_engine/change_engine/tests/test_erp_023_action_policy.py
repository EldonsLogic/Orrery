"""ERP-023 policy decisions, approval binding and engine write admission."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sqlite3

import pytest

from change_engine.adapter import AdapterError, ChangeEngineAdapter, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.adapter import SimulatedFrappeRuntime
from change_engine.adapter.frappe_backend import shadow_user_email

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


@pytest.fixture
def policy():
    # Import at test time so the adapter regression can also fail on the old tree.
    from change_engine.guarded_apply import action_policy_enforcer

    return action_policy_enforcer


@pytest.fixture
def setup(policy, tmp_path):
    request = policy.ActionRequest(
        "tenant-a", "request-a", "AP-FIN-01", 1, "sec-019-v1", "key-a",
        {"delivery_ids": ["delivery-a"], "customer": "customer-a",
         "lines": [{"item": "item-a", "quantity": 2, "price": "20.00", "discount": "0.00"}],
         "total": "40.00", "currency": "SAR"},
        {"delivery-a": 3},
    )
    submitter = policy.Principal("finance-a", "human", frozenset({"finance"}))
    drafter = policy.Principal("agent-a", "agent", frozenset(), "owner-b")
    approver = policy.Principal("owner-a", "human", frozenset({"owner"}))
    approval = policy.Approval(
        "approval-a", request.tenant_id, request.action_id, request.table_version,
        policy.payload_hash(request, submitter.id), approver, NOW + timedelta(hours=1),
        "approved", step_up=True,
    )
    context = policy.ActionContext(
        request.tenant_id, request.request_id, request.action_id, submitter, drafter,
        in_scope=True, active=True, approvals=(approval,), amount="40.00", currency="SAR",
    )
    path = tmp_path / "action-policy.sqlite3"
    return request, context, path


def guard_for(policy, context, path, *, table=None, clock=lambda: NOW):
    return policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(invoice_cap="100.00", currency="SAR") if table is None else table(),
        lambda session, request: context if session == "trusted-session" else None,
        policy.ActionPolicyStore(path),
        clock=clock,
    )


def admit(guard, request):
    return guard.authorize("trusted-session", request)


def test_jcs_key_order_utf8_and_decimal_text(policy, setup):
    request, context, _ = setup
    assert policy.canonical_json({"\ue000": 1, "😀": {"ب": True, "a": "10.00"}}) == (
        '{"😀":{"a":"10.00","ب":true},"\ue000":1}'.encode()
    )
    compact = (
        '{"action_id":"AP-FIN-01","action_version":1,"idempotency_key":"key-a",'
        '"initiator_id":"finance-a","payload":{"currency":"SAR","customer":"customer-a",'
        '"delivery_ids":["delivery-a"],"lines":[{"discount":"0.00","item":"item-a",'
        '"price":"20.00","quantity":2}],"total":"40.00"},"request_id":"request-a",'
        '"table_version":"sec-019-v1","target_revisions":{"delivery-a":3},"tenant_id":"tenant-a"}'
    )
    assert policy.payload_hash(request, context.submitter.id) == "sha256:" + sha256(compact.encode()).hexdigest()
    reordered = replace(request, payload=dict(reversed(list(request.payload.items()))))
    assert policy.payload_hash(reordered, context.submitter.id) == policy.payload_hash(request, context.submitter.id)


@pytest.mark.parametrize("value", [1.0, float("nan"), float("inf"), True, 1, "1e3", "NaN", "Infinity"])
def test_malformed_amount_refused(policy, setup, value):
    request, context, path = setup
    request = replace(request, payload={**request.payload, "total": value})
    with pytest.raises(ValueError):
        policy.payload_hash(request, context.submitter.id)
    assert admit(guard_for(policy, context, path), request) is None


@pytest.mark.parametrize(("action", "role", "fields", "targets", "allowed"), [
    ("AP-SALES-01", "sales", {"customer": "c", "lines": [{"item": "i", "quantity": 1,
        "price": "9.00", "discount": "0.00"}], "total": "9.00", "currency": "SAR"}, {"c": 1}, True),
    ("AP-SALES-02", "owner", {}, {}, False),
    ("AP-STOCK-01", "warehouse", {"order_id": "o", "warehouse": "w",
        "lines": [{"item": "i", "quantity": 1}], "amount": "10.00", "currency": "SAR"}, {"o": 2}, True),
    ("AP-FIN-01", "finance", None, None, True),
    ("AP-PAY-01", "owner", {}, {}, False),
    ("AP-PERM-01", "owner", {"target_user": "other", "roles_before": ["sales"],
        "roles_after": ["warehouse"], "scopes": ["w"], "limits_before": {}, "limits_after": {}},
        {"other": 1}, False),
    ("unknown", "owner", {}, {}, False),
])
def test_starter_actions(policy, setup, action, role, fields, targets, allowed):
    request, context, path = setup
    request = replace(request, action_id=action, payload=request.payload if fields is None else fields,
                      target_revisions=request.target_revisions if targets is None else targets)
    actor = replace(context.submitter, roles=frozenset({role}))
    context = replace(context, submitter=actor, action_id=action, approvals=(), threshold="50.00" if
                      action in {"AP-STOCK-01", "AP-FIN-01"} else None,
                      amount=request.payload.get("amount", request.payload.get("total")))
    guard = guard_for(policy, context, path, table=lambda: policy.starter_table(
        stock_cap="100.00", invoice_cap="100.00", currency="SAR"))
    assert (admit(guard, request) is not None) == allowed
    assert guard.store.audit_log()[0].decision == ("allow" if allowed else "deny")


@pytest.mark.parametrize("change", [
    {"table_version": ""}, {"table_version": "other"}, {"tenant_id": ""}, {"tenant_id": "tenant-b"},
    {"action_version": True}, {"action_version": 2}, {"request_id": ""}, {"idempotency_key": "key-b"},
    {"target_revisions": {"delivery-a": 4}}, {"target_revisions": {}},
])
def test_invalid_or_changed_binding_cannot_execute(policy, setup, change):
    request, context, path = setup
    assert admit(guard_for(policy, context, path), replace(request, **change)) is None


def test_tampered_line_and_forged_approval_binding(policy, setup):
    request, context, path = setup
    payload = {**request.payload, "lines": [{**request.payload["lines"][0], "price": "20.01"}]}
    assert admit(guard_for(policy, context, path), replace(request, payload=payload)) is None
    for field, value in [("tenant_id", "tenant-b"), ("table_version", "old"),
                         ("action_id", "AP-STOCK-01"), ("payload_hash", "sha256:" + "0" * 64)]:
        bad = replace(context.approvals[0], **{field: value})
        assert admit(guard_for(policy, replace(context, approvals=(bad,)), path), request) is None


@pytest.mark.parametrize("change", [
    {"status": "pending"}, {"status": "cancelled"}, {"status": "rejected"}, {"status": "expired"},
    {"status": "failed"}, {"status": "consumed"}, {"expires_at": NOW}, {"step_up": False},
])
def test_unusable_approval(policy, setup, change):
    request, context, path = setup
    context = replace(context, approvals=(replace(context.approvals[0], **change),))
    assert admit(guard_for(policy, context, path), request) is None


def test_sod_and_exact_approver_count(policy, setup):
    request, context, path = setup
    approval = context.approvals[0]
    for approver in (
        replace(approval.approver, id=context.submitter.id),
        replace(approval.approver, id=context.drafter.id),
        replace(approval.approver, id=context.drafter.owner_id),
        replace(approval.approver, kind="agent", owner_id="owner-b"),
        replace(approval.approver, roles=frozenset({"finance"})),
    ):
        candidate = replace(context, approvals=(replace(approval, approver=approver),))
        assert admit(guard_for(policy, candidate, path), request) is None
    editor = replace(context, editor_ids=frozenset({approval.approver.id}))
    assert admit(guard_for(policy, editor, path), request) is None
    duplicate = replace(approval, id="approval-b")
    tightened = replace(context, approvals_required=2, approvals=(approval, duplicate))
    assert admit(guard_for(policy, tightened, path), request) is None
    distinct = replace(duplicate, approver=replace(approval.approver, id="owner-c"))
    assert admit(guard_for(policy, replace(tightened, approvals=(approval, distinct)), path), request)


@pytest.mark.parametrize("change", [
    {"in_scope": False}, {"active": False}, {"currency": "USD"}, {"tenant_id": "tenant-b"}, {"approvals_required": 0}, {"threshold": "100.01"},
    {"threshold": True}, {"amount": "0.00"}, {"submitter": None}, {"drafter": None},
])
def test_missing_identity_scope_or_loosened_limit(policy, setup, change):
    request, context, path = setup
    assert admit(guard_for(policy, replace(context, **change), path), request) is None


def test_floor_and_revoked_role(policy, setup):
    request, context, path = setup
    agent = replace(context.submitter, kind="agent", owner_id="owner-b")
    for actor in (agent, replace(context.submitter, roles=frozenset())):
        assert admit(guard_for(policy, replace(context, submitter=actor, threshold="100.00",
                                              approvals_required=0, approvals=()), path), request) is None
    # A valid independent human approval still does not let an agent submit.
    approval = replace(context.approvals[0], payload_hash=policy.payload_hash(request, agent.id))
    assert admit(guard_for(policy, replace(context, submitter=agent, approvals=(approval,)), path), request) is None


def test_permission_change_requires_second_owner_and_cannot_target_self(policy, setup):
    request, context, path = setup
    owner = replace(context.submitter, roles=frozenset({"owner"}))
    request = replace(request, action_id="AP-PERM-01", payload={
        "target_user": owner.id, "roles_before": [], "roles_after": ["owner"], "scopes": [],
        "limits_before": {}, "limits_after": {}}, target_revisions={owner.id: 1})
    approval = replace(context.approvals[0], action_id=request.action_id,
                       payload_hash=policy.payload_hash(request, owner.id))
    context = replace(context, action_id=request.action_id, submitter=owner, amount=None, approvals=(approval,))
    assert admit(guard_for(policy, context, path), request) is None
    request = replace(request, payload={**request.payload, "target_user": "other"}, target_revisions={"other": 1})
    context = replace(context, approvals=(replace(approval, payload_hash=policy.payload_hash(request, owner.id)),))
    capped = replace(request, payload={**request.payload, "limits_after": {"AP-FIN-01": "100.01"}})
    capped_context = replace(context, approvals=(replace(approval, payload_hash=policy.payload_hash(capped, owner.id)),))
    assert admit(guard_for(policy, capped_context, path), capped) is None
    assert admit(guard_for(policy, context, path), request)


def test_handler_missing_is_audited(policy, setup):
    request, context, path = setup
    guard = guard_for(policy, context, path)
    adapter = ChangeEngineAdapter(action_policy=guard)
    with pytest.raises(AdapterError, match="^permission_denied$"):
        adapter.execute_action("trusted-session", request)
    assert guard.store.audit_log()[-1].decision == "deny"


def test_durable_single_use_is_atomic_across_adapters(policy, setup):
    request, context, path = setup
    guards = [guard_for(policy, context, path) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda guard: admit(guard, request), guards))
    assert sum(result is not None for result in results) == 1
    reopened = guard_for(policy, context, path)
    assert admit(reopened, request) is None
    new = replace(request, request_id="request-b", idempotency_key="key-b")
    reused = replace(context.approvals[0], payload_hash=policy.payload_hash(new, context.submitter.id))
    assert admit(guard_for(policy, replace(context, request_id="request-b", approvals=(reused,)), path), new) is None
    assert [record.decision for record in reopened.store.audit_log()] == ["allow", "deny", "deny", "deny"]


def test_invalid_tables_and_lookup_failure_audited(policy, setup):
    request, context, path = setup
    table = policy.starter_table()
    options = [lambda: None, lambda: replace(table, version=""), lambda: replace(table, rows=()),
               lambda: replace(table, rows=table.rows[:-1]), lambda: 1 / 0]
    for load in options:
        assert admit(guard_for(policy, context, path, table=load), request) is None
    guard = guard_for(policy, context, path)
    assert guard.authorize("untrusted-session", request) is None
    assert admit(guard_for(policy, context, path, clock=lambda: None), request) is None
    assert {entry.decision for entry in guard.store.audit_log()} == {"deny"}


def test_break_glass_has_time_box_reason_and_immutable_audit(policy, setup):
    request, context, path = setup
    request = replace(request, break_glass_reason="  Delivery continuity  ")
    owner = replace(context.submitter, roles=frozenset({"owner", "break_glass"}))
    context = replace(context, submitter=owner, approvals=(), break_glass_until=NOW + timedelta(minutes=5),
                      break_glass_step_up=True)
    for invalid in (replace(context, submitter=replace(owner, roles=frozenset({"owner"}))),
                    replace(context, break_glass_until=NOW), replace(context, break_glass_until=None),
                    replace(context, break_glass_step_up=False)):
        assert admit(guard_for(policy, invalid, path), request) is None
    guard = guard_for(policy, context, path)
    assert admit(guard, replace(request, break_glass_reason="   ")) is None
    admitted = admit(guard, request)
    record = guard.store.audit_log()[-1]
    assert record.decision == "break_glass" and record.break_glass
    assert record.reason == "Delivery continuity"
    assert record.drafter == context.drafter and record.submitter == owner and record.approvers == ()
    assert record.timestamp == NOW and record.table_version == request.table_version
    assert record.payload_hash == policy.payload_hash(request, owner.id)
    assert admitted.submitter_id == owner.id
    with pytest.raises(FrozenInstanceError):
        record.reason = "rewritten"
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM action_policy_audit")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT OR REPLACE INTO action_policy_audit VALUES (1, '{}')")


@pytest.mark.parametrize("action", ["AP-SALES-02", "AP-PAY-01", "AP-BPL-01"])
def test_unreviewed_and_specialized_actions_are_disabled(policy, setup, action):
    request, context, path = setup
    table = policy.starter_table()
    rule = next(row for row in table.rows if row.action_id == action)
    assert not rule.enabled
    altered = replace(table, rows=tuple(replace(row, enabled=True) if row == rule else row for row in table.rows))
    # An invalid platform table disables even an otherwise valid approval.
    assert admit(guard_for(policy, context, path, table=lambda: altered), request) is None


def test_unconfigured_adapter_refuses_business_action():
    adapter = ChangeEngineAdapter()
    with pytest.raises(AdapterError, match="permission_denied"):
        adapter.execute_action("trusted-session", None)


def test_adapter_uses_bound_snapshot_and_admits_before_effect(policy, setup):
    request, context, path = setup
    guard = guard_for(policy, context, path)

    class Backend:
        def execute_as_caller(self, tenant, caller, run):
            assert tenant == "tenant-a"
            assert caller == {"service": "operate_gateway", "onBehalfOf": {"kind": "user", "id": "finance-a"}}
            return run(object())

    def post_invoice(backend, bound):
        record = guard.store.audit_log()[-1]
        assert record.decision == "allow"
        assert record.approvers == (context.approvals[0].approver,)
        request.payload["lines"][0]["price"] = "99.00"
        assert bound.payload["lines"][0]["price"] == "20.00"
        raise RuntimeError("private backend details")

    adapter = ChangeEngineAdapter(frappe_backend=Backend(), action_policy=guard,
                                  action_handlers={"AP-FIN-01": post_invoice})
    with pytest.raises(AdapterError, match="^engine_unavailable$") as error:
        adapter.execute_action("trusted-session", request)
    assert not error.value.details
    with pytest.raises(AdapterError, match="^permission_denied$"):
        adapter.execute_action("trusted-session", request)


def test_unwritable_audit_blocks_effect(policy, setup):
    request, context, path = setup
    guard = guard_for(policy, context, path)
    path.unlink()
    assert admit(guard, request) is None


def test_approval_expiry_is_rechecked_at_durable_admission(policy, setup):
    request, context, path = setup
    times = iter((NOW, context.approvals[0].expires_at))
    guard = guard_for(policy, context, path, clock=lambda: next(times))
    assert admit(guard, request) is None
    assert guard.store.audit_log()[-1].decision == "deny"


def test_business_write_uses_real_backend_impersonation(policy, setup):
    request, context, path = setup
    runtime = SimulatedFrappeRuntime()
    tenant = runtime.ensure_site("alpha")
    user = shadow_user_email(context.submitter.id)
    tenant.rows["tabUser"][user] = {"name": user, "enabled": 1, "roles": ["finance"]}
    backend = FrappeRuntimeBackend(FrappeSiteResolver(site_map={request.tenant_id: "alpha"}),
                                   frappe_factory=lambda: runtime)
    seen = []

    def post(engine, action):
        seen.append((engine.local.site, engine.session.user, action.payload["total"]))
        return "posted"

    adapter = ChangeEngineAdapter(frappe_backend=backend, action_policy=guard_for(policy, context, path),
                                  action_handlers={request.action_id: post})
    assert adapter.execute_action("trusted-session", request) == "posted"
    assert seen == [("alpha", user, "40.00")]
    assert runtime.session.user == "Administrator"
