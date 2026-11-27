"""Shared fixtures for the event stream tests. Fictional data only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from evstream import Context, UlidGenerator, build_event

T0 = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


def ctx(tenant="t_acme", kind="user", **kw):
    base = dict(tenant_id=tenant, actor_kind=kind, actor_id="u_1", service="operate",
                role_ids=("sales_rep",), correlation_id="chat_turn_1")
    base.update(kw)
    return Context(**base)


_ids = UlidGenerator(clock_ms=lambda: 1_767_000_000_000)
_clock = FakeClock()
TS = "2026-01-01T09:30:00Z"
SUBJ = {"entity": "sales_order", "id": "SO-1"}
TRACE = {"model_id": "model_x", "prompt_version": "p1", "tool": "t", "audit_id": "aud_1"}

DATA = {
    "<entity>.created": {"changed_fields": ["status"]},
    "<entity>.updated": {"changes": {"status": "open"}},
    "<entity>.submitted": {}, "<entity>.cancelled": {}, "<entity>.deleted": {},
    "<entity>.transitioned": {"from": "draft", "to": "open", "transition_id": "tr_1"},
    "approval.requested": {"approval_id": "ap_1"},
    "approval.decided": {"decision": "approved", "approver": "u_2", "comment": "ok"},
    "document.issued": {"einvoice_status": "cleared"},
    "document.rejected_by_authority": {"reason_code": "r1"},
    "auth.signed_in": {"method": "password"}, "auth.sign_in_failed": {"reason_code": "bad"},
    "auth.mfa_challenged": {"method": "totp"},
    "permission.denied": {"action": "read"},
    "role.assigned": {"role_id": "sales_rep", "user_id": "u_9"},
    "role.revoked": {"role_id": "sales_rep", "user_id": "u_9"},
    "tool.called": {"audit_id": "aud_1", "tool": "sales_order.transition", "status": "ok", "latency_ms": 12,
                    "engine_refs": ["SO-1"]},
    "build.state_changed": {"from": "draft", "to": "owner_approved"},
    "support.access_requested": {"reason": "ticket 1", "expires_at": TS},
    "support.access_granted": {"reason": "ticket 1", "expires_at": TS, "grant_id": "g_1"},
    "support.access_ended": {"grant_id": "g_1"},
    "support.action_taken": {"reason": "ticket 1", "grant_id": "g_1"},
    "tenant.state_changed": {"from": "trial", "to": "active"},
    "agent.run_started": {"run_id": "r_1"}, "agent.run_completed": {"run_id": "r_1"},
    "agent.run_failed": {"run_id": "r_1", "error_code": "E1"},
    "agent.tool_proposed": {"run_id": "r_1", "tool": "x", "tainted": False},
    "agent.budget_exceeded": {"run_id": "r_1", "budget_kind": "calls"},
    "agent.output_flagged": {"run_id": "r_1", "reason_code": "injection"},
    "chat.turn_completed": {"mode": "ask", "latency_ms": 900, "input_tokens": 10, "output_tokens": 20},
    "memory.written": {"memory_id": "m_1"}, "memory.expired": {"memory_id": "m_1"},
    "eval.regression_detected": {"suite": "s1"},
    "meter.ai_usage": {"model_id": "model_x", "tier": "mid", "input_tokens": 1, "output_tokens": 2,
                       "cached_tokens": 0, "cost_micro_usd": 5, "purpose": "chat", "agent_id": None},
    "meter.active_user": {"user_id": "u_1", "day": "2026-01-01"},
    "meter.storage": {"bytes": {"records": 1, "files": 2, "backups": 3}},
    "meter.documents_issued": {"doc_type": "invoice", "count": 2},
    "meter.connector_run": {"connector_id": "c1", "rows": 3, "bytes": 4, "tier": "t1"},
    "meter.simulation_run": {"records_replayed": 100, "duration_ms": 50},
}
# families that share a sample
for _t in ("changed", "asset_uploaded", "asset_rejected"):
    DATA[f"branding.{_t}"] = {}
for _t in ("change_proposed", "change_approved", "applied", "apply_failed", "rolled_back"):
    DATA[f"blueprint.{_t}"] = {"change_id": "ch_1"}
for _t in ("review_passed", "review_rejected", "live", "sandbox_ready", "simulation_completed", "cutover_started"):
    DATA[f"build.{_t}"] = {"reviewer_id": "u_5"}
for _t in ("exported", "deleted"):
    DATA[f"data.{_t}"] = {"scope": "all"}
for _t in ("published", "deprecated", "request_created", "request_reviewed"):
    DATA[f"component.{_t}"] = {"component_id": "core.x"}
for _t in ("upgrade_canary_started", "upgrade_promoted", "upgrade_rolled_back"):
    DATA[f"engine.{_t}"] = {"canary_id": "k1"}
# payment events (contracts/connector-payments.md section 6; fictional sandbox data)
_PAY = {"payment_id": "pay_1", "checkout_id": "chk_1", "links": [{"entity": "sales_invoice", "id": "SINV-1"}],
        "amount": {"minor": 115000, "currency": "SAR"}, "provider": "payments.examplepay", "environment": "sandbox",
        "gateway_payment_ref": "examplepay:gw_1"}
for _t in ("checkout_created", "checkout_cancelled", "authorised", "captured", "expired"):
    DATA[f"payment.{_t}"] = _PAY
DATA["payment.failed"] = {**_PAY, "failure_code": "PAY-GW-002"}
DATA["payment.held_unallocated"] = {**_PAY, "unallocated_reason": "over_collected"}
DATA["payment.refund_requested"] = {**_PAY, "refund_id": "rfd_1"}
DATA["payment.refunded"] = {**_PAY, "refund_id": "rfd_1", "gateway_refund_ref": "examplepay:re_1", "origin": "seshna"}
DATA["payment.refund_failed"] = {**_PAY, "refund_id": "rfd_1", "failure_code": "PAY-GW-002"}
DATA["payment.voided"] = {**_PAY, "origin": "external"}
DATA["payment.disputed"] = {**_PAY, "dispute_status": "opened"}
DATA["payment.webhook_rejected"] = {"provider": "payments.examplepay", "environment": "sandbox",
                                    "endpoint_id": "whk_3QpZr8LmXv2NcTyBa7KdQe", "error_code": "PAY-HOOK-001"}
DATA["payment.reconciliation_mismatch"] = {"provider": "payments.examplepay", "environment": "sandbox",
                                           "error_code": "PAY-RECON-001"}

# message and consent events (contracts/connector-messaging.md section 10; fictional sandbox data, no text or numbers)
_H = "a" * 64  # bare hex: personal event data strings stay within 64 characters
DATA["message.received"] = {"message_id": "msg_1", "conversation_id": "conv_1", "channel": "whatsapp",
                            "channel_account_ref": "ca_1", "provider_event_id": "evt.1", "content_hash": _H,
                            "verification": "meta_hmac_sha256", "flags": [], "tainted": True}
DATA["message.send_requested"] = {"message_id": "msg_2", "conversation_id": "conv_1", "channel": "whatsapp",
                                  "channel_account_ref": "ca_1", "country": "SA", "mode": "session_reply",
                                  "origin": "human", "sent_by": "usr_1", "confirmation_id": "cnf_1",
                                  "payload_hash": _H, "tainted": True, "sandbox": True, "risk_class": "R3",
                                  "approval_id": None}
DATA["message.status_changed"] = {"message_id": "msg_2", "channel": "whatsapp", "channel_account_ref": "ca_1",
                                  "status": "delivered", "cost_micro_usd": None, "provider_event_id": "evt.2",
                                  "dedup_key": _H}
DATA["consent.recorded"] = {"consent_id": "cns_1", "supersedes": None, "contact_ref": "ct_1", "channel": "whatsapp",
                            "country": "SA", "purpose": "marketing", "captured_by": "contact", "method": "web_form",
                            "text_version": "mkt-ar-1"}
DATA["consent.revoked"] = {"consent_id": "cns_2", "supersedes": "cns_1", "contact_ref": "ct_1", "channel": "whatsapp",
                           "country": "SA", "purpose": "marketing", "revoked_by": "contact_keyword",
                           "source_message_id": "msg_3"}
DATA["meter.message_sent"] = {"channel": "whatsapp", "category": "session", "country": "SA",
                              "provider": "msg.meta_whatsapp", "cost_micro_usd": None}


def concrete_type(key: str) -> str:
    return key.replace("<entity>", "sales_order")


def make(key: str, tenant="t_acme", **kw):
    """Build a valid unstamped event for a registry key."""
    from evstream import default_registry
    info = default_registry().lookup(concrete_type(key))
    platform = info.scope == "platform"
    c = ctx("platform" if platform else tenant, kind="agent" if info.requires_trace else "user")
    fields = {}
    if info.requires_subject:
        fields["subject"] = SUBJ
    if info.requires_trace or c.actor_kind == "agent":
        fields["trace"] = TRACE
    fields.update(kw)
    return build_event(c, concrete_type(key), DATA[key], ids=_ids, clock=_clock, **fields)


def stamp(ev, seq):
    return {**ev, "sequence": seq}
