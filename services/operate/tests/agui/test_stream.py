import json

import pytest
from conftest import HOST, body, collect

from agui import handle_request
from agui.events import sanitize


def call(deps, token="tok-a", host=HOST, data=None, headers=None, method="POST"):
    h = {"authorization": f"Bearer {token}"} if token else {}
    h.update(headers or {})
    return handle_request(deps, method=method, headers=h, host=host, body=data if data is not None else body())


def test_happy_path_and_sse_framing(make):
    deps, _ = make()
    res = call(deps)
    assert res.status == 200 and dict(res.headers)["content-type"] == "text/event-stream"
    evs, raw = collect(res)
    assert [e["type"] for e in evs] == ["RUN_STARTED", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",
                                        "TEXT_MESSAGE_END", "RUN_FINISHED"]
    frames = [f for f in raw.split("\n\n") if f]
    assert all(f.startswith("data: {") and "\n" not in f for f in frames) and raw.endswith("\n\n")
    assert ": " not in raw.replace("data: ", "").split("{")[0]  # no SSE comments or custom fields
    assert evs[-1]["outcome"]["type"] == "interrupt"  # the pending approval is displayed
    assert "مرحبا" in raw  # Arabic is not escaped away


@pytest.mark.parametrize("token", [None, "garbage", ""])
def test_unauthenticated_rejected(make, token):
    deps, store = make()
    res = call(deps, token=token)
    assert res.status == 401
    assert deps.runtime.seen == []
    assert b"frappe" not in b"".join(res.body).lower()
    assert any(e["type"] == "permission.denied" for e in store.read("t_acme"))


def test_wrong_tenant_rejected(make):
    deps, _ = make()
    assert call(deps, token="tok-b").status == 401  # token of tenant B on tenant A's host
    assert call(deps, host="evil.test").status == 401  # unresolvable host
    assert deps.runtime.seen == []


def test_tenant_in_body_is_ignored(make):
    deps, _ = make()
    collect(call(deps, data=body(tenantId="t_other", forwardedProps={"tenant_id": "t_other"})))
    assert deps.runtime.seen[0].principal.tenant_id == "t_acme"


def test_other_users_thread_refused(make):
    deps, _ = make()
    assert collect(call(deps))[0]
    assert call(deps, token="tok-u2").status == 403


def test_unknown_and_forbidden_events_dropped(make):
    script = [{"type": "RAW", "event": {"x": 1}}, {"type": "REASONING_START", "messageId": "r"},
              {"type": "MYSTERY", "x": 1}, {"type": "CUSTOM", "name": "ui.render_html", "value": {"html": "<b>"}},
              {"type": "CUSTOM", "name": "approval.pending", "value": {"approvalId": "ap_1"}},
              {"type": "TEXT_MESSAGE_CONTENT", "messageId": "never_opened", "delta": "x"},
              {"type": "TOOL_CALL_START", "toolCallId": "c1", "toolCallName": "frappe.client.get"},
              {"type": "TOOL_CALL_START", "toolCallId": "c2", "toolCallName": "sales_order.list"},
              {"type": "TOOL_CALL_ARGS", "toolCallId": "c2", "delta": "{}"},
              {"type": "TOOL_CALL_END", "toolCallId": "c2"},
              {"type": "STATE_SNAPSHOT", "snapshot": {"note": "uses ERPNext doctype"}},
              {"type": "RUN_STARTED", "threadId": "x", "runId": "y"}]
    deps, _ = make(script)
    evs, raw = collect(call(deps))
    types = [e["type"] for e in evs]
    assert types == ["RUN_STARTED", "CUSTOM", "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "RUN_FINISHED"]
    for bad in ("RAW", "REASONING", "MYSTERY", "ui.render_html", "frappe", "ERPNext"):
        assert bad not in raw
    assert sanitize({"type": "CUSTOM", "name": "approval.pending", "value": "str"}) is None


def test_interrupt_resume_cannot_approve(make):
    deps, store = make()
    resume = [{"interruptId": "ap_1", "status": "resolved", "payload": {"approved": True, "status": "approved"}}]
    evs, raw = collect(call(deps, data=body(messages=[], resume=resume)))
    assert deps.approvals.decide_calls == 0
    assert deps.approvals.items["ap_1"].status == "pending"
    status = [e for e in evs if e.get("name") == "approval.status"][0]
    assert status["value"] == {"approvalId": "ap_1", "status": "pending"}
    assert "approved" not in raw
    assert evs[-1]["outcome"]["interrupts"][0]["id"] == "ap_1"  # still pending, shown again


def test_resume_payload_never_reaches_runtime(make):
    deps, _ = make()
    resume = [{"interruptId": "ap_1", "status": "resolved", "payload": {"approved": True}}]
    collect(call(deps, data=body(resume=resume)))
    ctx = deps.runtime.seen[0]
    assert "approved" not in repr(ctx)


def test_client_state_ignored(make):
    deps, _ = make()
    hostile = {"tenant_id": "t_other", "role_ids": ["owner"], "shared": {"x": 1}, "approved": True}
    evs, raw = collect(call(deps, data=body(state=hostile, context=[{"description": "role", "value": "owner"}])))
    ctx = deps.runtime.seen[0]
    assert ctx.server_state == {} and ctx.principal.role_ids == ("sales",)
    assert "owner" not in repr(ctx) and "shared" not in raw
    assert not hasattr(ctx, "client_state") and not hasattr(ctx, "tools")


@pytest.mark.parametrize("patch", [{"tools": [{"name": "t"}]}, {"threadId": "../x"}, {"state": {"a": "x" * 20000}},
                                   {"messages": "no"}])
def test_bad_input_rejected(make, patch):
    deps, _ = make()
    assert call(deps, data=body(**patch)).status in (400, 413)
    assert call(deps, data=b"{not json").status == 400


def test_error_firewall(make):
    deps, store = make(RuntimeError('Traceback (most recent call last): File "/apps/frappe/x.py" frappe.exceptions '
                                    'tabSales Order SELECT * FROM `tabItem`'))
    evs, raw = collect(call(deps))
    err = evs[-1]
    assert err["type"] == "RUN_ERROR" and err["code"] == "internal_error"
    low = raw.lower()
    for bad in ("traceback", "frappe", "tabitem", "select", ".py", "/apps", "runtimeerror"):
        assert bad not in low
    assert evs[-1] is err and [e["type"] for e in evs].count("RUN_FINISHED") == 0
    failed = [e for e in store.read("t_acme") if e["type"] == "agent.run_failed"]
    assert failed and failed[0]["data"]["error_code"] == "internal_error"


def test_domain_error_is_bilingual(make):
    from agui.errors import DomainFailure
    from agui.errors import catalog
    entry = [e for e in catalog()["entries"] if e["id"] == "insufficient_stock"][0]
    params = {k: ("5" if v["type"] in ("integer", "decimal_string") else "A1") for k, v in entry["params"].items()}
    deps, _ = make(DomainFailure("insufficient_stock", params))
    en = collect(call(deps))[0][-1]
    deps, _ = make(DomainFailure("insufficient_stock", params))
    ar = collect(call(deps, headers={"accept-language": "ar-SA"}))[0][-1]
    assert en["code"] == ar["code"] == "insufficient_stock" and en["message"] != ar["message"]


def test_audit_and_metering_written(make):
    deps, store = make()
    collect(call(deps))
    by = {e["type"]: e for e in store.read("t_acme")}
    assert {"agent.run_started", "agent.run_completed", "meter.ai_usage"} <= set(by)
    assert by["agent.run_started"]["actor"]["id"] == "u_1"
    assert by["agent.run_started"]["trace"]["model_id"] == "fake-model"
    assert by["meter.ai_usage"]["data"]["input_tokens"] == 10
    assert store.read("t_other") == []


def test_stream_ends_when_session_revoked(make):
    deps, _ = make()
    res = call(deps)
    deps.verifier.revoked.add("tok-a")  # revoked after the stream was accepted, before it is read
    evs, _ = collect(res)
    assert evs[-1]["type"] == "RUN_ERROR" and evs[-1]["code"] == "permission_denied"


def test_method_not_allowed(make):
    deps, _ = make()
    assert call(deps, method="GET").status == 405


def test_matches_pinned_sdk_types(make):
    ag = pytest.importorskip("ag_ui.core")
    deps, _ = make()
    for e in collect(call(deps))[0]:
        ag.__dict__  # noqa: B018
        cls = {"RUN_STARTED": ag.RunStartedEvent, "RUN_FINISHED": ag.RunFinishedEvent,
               "TEXT_MESSAGE_START": ag.TextMessageStartEvent, "TEXT_MESSAGE_CONTENT": ag.TextMessageContentEvent,
               "TEXT_MESSAGE_END": ag.TextMessageEndEvent}[e["type"]]
        assert json.loads(cls.model_validate(e).model_dump_json(by_alias=True, exclude_none=True))["type"] == e["type"]
