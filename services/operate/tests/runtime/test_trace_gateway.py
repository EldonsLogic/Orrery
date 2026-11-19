import json

from conftest import CALLER, DEFS, FakeTools, Script, Sink, reply
from runtime import (AgentLoop, Limits, MemoryTraceStore, SequentialIds, StoreEventSink, TickClock, ToolResponse,
                     resolve_allowlist)
from runtime.agui_adapter import AguiRuntimeAdapter
from runtime.gateway_port import GatewayModelPort

from agui import Approval, Dependencies, Principal
from agui.audit import Auditor
from agui.core import handle_request
from evstream import MemoryStore
from gateway import BudgetPolicy, GatewayContext, GatewayMeter, MeteredGatewayRouter, ModelRoute, ProviderResponse


def script():
    return Script(reply("", [("sales_order.get", {"id": "SO-1", "email": "a@b.test", "note": "x" * 200})]),
                  reply("", [("purchase_order.cancel", {"id": "PO-1"})]), reply("final"))


def _tools():
    return FakeTools({"purchase_order.cancel": ToolResponse("pending_approval", None, {"id": "ap_1"}, None, "aud_2")})


def _run(sc, events=None, ids=None):
    traces, ids = MemoryTraceStore(), ids or SequentialIds()
    loop = AgentLoop(model=sc, tools=_tools(), allow=resolve_allowlist(DEFS, ("sales",)), limits=Limits(),
                     clock=TickClock(), ids=ids, traces=traces, events=events)
    res = loop.run(caller=CALLER, run_id="run_1", user_text="go")
    return res, traces.spans("t_acme", "run_1"), traces


def test_trace_completeness_and_redaction():
    res, spans, traces = _run(script())
    kinds = [s.kind for s in spans]
    assert kinds.count("model") == res.steps == 2 and kinds.count("tool") == 2 and kinds[-1] == "run"
    tool = [s for s in spans if s.kind == "tool"]
    assert [(s.tool, s.risk_class, s.outcome) for s in tool] == [("sales_order.get", "R0", "ok"),
                                                                 ("purchase_order.cancel", "R2", "pending_approval")]
    assert tool[0].args_redacted["email"] == "[redacted]" and tool[0].args_redacted["note"].startswith("[200 chars")
    assert tool[0].args_hash.startswith("sha256:") and tool[1].approval_id == "ap_1" and tool[1].audit_id == "aud_2"
    assert all(s.span_id and s.run_id == "run_1" and s.ended_ms >= s.started_ms for s in spans)
    assert sum(s.input_tokens for s in spans if s.kind == "model") == spans[-1].input_tokens == 200
    assert traces.spans("t_other", "run_1") == []  # tenant-scoped


def test_determinism_same_script_same_trace():
    a = [s.to_dict() for s in _run(script())[1]]
    b = [s.to_dict() for s in _run(script())[1]]
    assert a == b and len(a) == 5


def test_events_are_valid_evstream_events():
    store, ids = MemoryStore(), SequentialIds()
    _run(script(), StoreEventSink(store, ids), ids)  # the store validates every event on append
    evs = store.read("t_acme")
    assert [e["type"] for e in evs] == ["agent.run_started", "agent.tool_proposed", "agent.tool_proposed",
                                       "agent.run_completed"]
    assert all(e["actor"]["id"] == "u_1" and e["trace"]["model_id"] == "fake-model" for e in evs)


def _gateway(budget):
    meter, n = GatewayMeter(default_budget=budget), {"i": 0}

    def transport(route, req, ctx):
        n["i"] += 1
        return ProviderResponse(output=reply("", [("sales_order.get", {"id": f"SO-{n['i']}"})]),
                                input_tokens=400, output_tokens=100, model_id="m-mid")
    router = MeteredGatewayRouter(meter=meter, routes={"mid": ModelRoute("mid", "m-mid", "p")}, transport=transport)
    ctx = GatewayContext(tenant_id="t_acme", actor_kind="user", actor_id="u_1", correlation_id="run_1",
                         role_ids=("sales",), session_id="s1")
    return meter, GatewayModelPort(router, ctx, est_input_tokens=100, est_output_tokens=100)


def test_budget_exhaustion_mid_run_through_gateway_precheck():
    meter, port = _gateway(BudgetPolicy(max_total_tokens=1300))
    sink, traces = Sink(), MemoryTraceStore()
    loop = AgentLoop(model=port, tools=FakeTools(), allow=resolve_allowlist(DEFS, ("sales",)),
                     limits=Limits(max_steps=10), clock=TickClock(), ids=SequentialIds(), traces=traces, events=sink)
    res = loop.run(caller=CALLER, run_id="run_1", user_text="go")
    assert (res.status, res.stop_reason, res.error_code) == ("stopped", "budget", "budget_exceeded")
    assert res.steps == 3 and len(meter.calls_for_tenant("t_acme")) == 3  # the fourth call is refused before dispatch
    assert [t for t in sink.types() if t.startswith("agent.budget")] == ["agent.budget_exceeded"]
    assert [x.outcome for x in traces.spans("t_acme", "run_1") if x.kind == "model"] == ["ok", "ok", "ok", "budget_stop"]


def test_gateway_port_rejects_non_reply_output():
    router = MeteredGatewayRouter(meter=GatewayMeter(), routes={"mid": ModelRoute("mid", "m-mid")},
                                  transport=lambda *a: ProviderResponse("raw text", 1, 1))
    ctx = GatewayContext(tenant_id="t_acme", actor_kind="user", actor_id="u_1", correlation_id="c")
    loop = AgentLoop(model=GatewayModelPort(router, ctx), tools=FakeTools(), allow=resolve_allowlist(DEFS, ("sales",)),
                     limits=Limits(), clock=TickClock(), ids=SequentialIds(), traces=MemoryTraceStore())
    assert loop.run(caller=CALLER, run_id="r", user_text="x").error_code == "internal_error"


class _Verifier:
    def verify(self, token, tenant_id):
        return Principal("t_acme", "u_1", ("sales",), "s1")


class _Approvals:
    def pending(self, p):
        return [Approval("ap_1", "Cancel PO-1", "pending")]

    def get(self, p, aid):
        return None


def _stream(sc, tools):
    store = MemoryStore()
    rt = AguiRuntimeAdapter(model=sc, tools=tools, tool_defs=lambda t: DEFS, clock=TickClock(), ids=SequentialIds(),
                            traces=MemoryTraceStore(), model_id="fake-model", prompt_version="p1")
    deps = Dependencies(verifier=_Verifier(), runtime=rt, approvals=_Approvals(), auditor=Auditor(store, rt),
                        resolve_tenant=lambda h: "t_acme")
    body = json.dumps({"threadId": "th1", "runId": "r1", "messages": [{"id": "1", "role": "user", "content": "hi"}],
                       "state": {}, "tools": [], "context": [], "forwardedProps": {}}).encode()
    resp = handle_request(deps, method="POST", headers={"authorization": "Bearer x"}, host="h", body=body)
    frames = b"".join(resp.body).decode()
    return [json.loads(f[6:]) for f in frames.split("\n\n") if f.startswith("data: ")], store


def test_agui_adapter_streams_only_allowlisted_events_and_interrupts():
    tools = _tools()
    evs, store = _stream(Script(reply("Checking.", [("purchase_order.cancel", {"id": "PO-1"})])), tools)
    types = [e["type"] for e in evs]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert {"TEXT_MESSAGE_START", "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"} <= set(types)
    assert any(e.get("name") == "approval.pending" and e["value"]["approvalId"] == "ap_1" for e in evs)
    assert evs[-1]["outcome"]["type"] == "interrupt"
    assert tools.requests[0].propose and tools.requests[0].role_ids == ("sales",)
    audited = [e["type"] for e in store.read("t_acme")]
    assert audited.count("agent.run_started") == 1 and "meter.ai_usage" in audited  # no duplicate run events


def test_agui_adapter_budget_and_failure_mapping():
    always = Script(lambda q: reply("", [("sales_order.get", {"id": f"S{len(q.steps)}"})]))
    evs, _ = _stream(always, FakeTools())
    assert any(e.get("delta") == "errors.budget_exceeded" for e in evs) and evs[-1]["type"] == "RUN_FINISHED"
    evs, _ = _stream(Script(RuntimeError("boom frappe")), FakeTools())
    err = [e for e in evs if e["type"] == "RUN_ERROR"][0]
    assert err["code"] == "internal_error" and "frappe" not in json.dumps(evs)
