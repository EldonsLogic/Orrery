"""PR #190 review: tenant binding (H2), idempotency and repeats (M2), fail-closed body (M4), scrubber (M5),
budget projection (M6), per-run interrupts (M7), session taint (M8), trace redaction (M9), double metering."""
import json

from conftest import CALLER, DEFS, FakeTools, Script, Sink, reply
from runtime import (AgentLoop, Caller, Limits, MemoryTraceStore, ModelReply, SequentialIds, TaintState, TickClock,
                     ToolResponse, Usage, args_hash, redact_args, resolve_allowlist, sanitise_text)
from runtime.agui_adapter import AguiRuntimeAdapter
from runtime.gateway_port import GatewayModelPort, estimate_input_tokens, gateway_model_for
from runtime.loop import idempotency_key

from agui import Approval, Dependencies, Principal
from agui.audit import Auditor
from agui.core import handle_request
from evstream import MemoryStore
from gateway import BudgetPolicy, GatewayMeter, MeteredGatewayRouter, ModelRoute, ProviderResponse

GET = ("sales_order.get", {"id": "SO-1"})


def _router(meter, seen):
    def transport(route, req, ctx):
        seen.append((ctx.tenant_id, ctx.correlation_id, ctx.actor_id))
        n = len(seen)
        return ProviderResponse(output=reply("", [("sales_order.get", {"id": f"SO-{n}"})]),
                                input_tokens=400, output_tokens=100, model_id="m-mid")
    return MeteredGatewayRouter(meter=meter, routes={"mid": ModelRoute("mid", "m-mid", "p")}, transport=transport)


def test_two_tenants_interleaved_meter_and_budget_on_their_own_tenant():
    meter, seen = GatewayMeter(), []
    meter.set_tenant_budget("t_beta", BudgetPolicy(max_total_tokens=1200))
    model_for = gateway_model_for(_router(meter, seen), est_input_tokens=10, est_output_tokens=10)
    runs = {}
    for tenant, user in (("t_acme", "u_a"), ("t_beta", "u_b")):
        p = Principal(tenant, user, ("sales",), f"s_{tenant}")
        loop = AgentLoop(model=model_for(p, f"run_{tenant}"), tools=FakeTools(),
                         allow=resolve_allowlist(DEFS, ("sales",)), limits=Limits(max_steps=4), clock=TickClock(),
                         ids=SequentialIds(), traces=MemoryTraceStore())
        runs[tenant] = loop.stream(caller=Caller(tenant, user, ("sales",), f"s_{tenant}"), run_id=f"run_{tenant}",
                                   user_text="go")
    results, live = {}, dict(runs)
    while live:  # interleave the two generators event by event
        for t, g in list(live.items()):
            try:
                ev = next(g)
                if ev.kind == "done":
                    results[t] = ev.result
            except StopIteration:
                del live[t]
    assert results["t_acme"].stop_reason == "max_steps" and results["t_beta"].stop_reason == "budget"
    assert len(meter.calls_for_tenant("t_acme")) == 4 and len(meter.calls_for_tenant("t_beta")) == 2
    assert {(t, c, a) for t, c, a in seen} == {("t_acme", "run_t_acme", "u_a"), ("t_beta", "run_t_beta", "u_b")}


def test_port_bound_to_another_tenant_fails_closed():
    meter, seen = GatewayMeter(), []
    port = gateway_model_for(_router(meter, seen))(Principal("t_beta", "u_b", ("sales",)), "r")
    loop = AgentLoop(model=port, tools=FakeTools(), allow=resolve_allowlist(DEFS, ("sales",)), limits=Limits(),
                     clock=TickClock(), ids=SequentialIds(), traces=MemoryTraceStore())
    r = loop.run(caller=CALLER, run_id="r", user_text="x")
    assert (r.status, r.error_code) == ("failed", "internal_error") and seen == []


def test_precheck_uses_request_size_and_cost_is_projected(env):
    from runtime import ModelRequest
    small = ModelRequest("", "hi", (), (), (), False)
    big = ModelRequest("", "x" * 30_000, (), (), (), False)
    assert 5 <= estimate_input_tokens(small, 5) < 100
    assert estimate_input_tokens(big, 5) >= 10_000
    meter, seen = GatewayMeter(), []
    meter.set_tenant_budget("t_acme", BudgetPolicy(max_total_tokens=5_000))
    port = gateway_model_for(_router(meter, seen), est_input_tokens=10, est_output_tokens=10)(
        Principal("t_acme", "u_1", ("sales",)), "r")
    loop = AgentLoop(model=port, tools=FakeTools(), allow=resolve_allowlist(DEFS, ("sales",)), limits=Limits(),
                     clock=TickClock(), ids=SequentialIds(), traces=MemoryTraceStore())
    assert loop.run(caller=CALLER, run_id="r", user_text="x" * 30_000).stop_reason == "budget" and seen == []
    r = env.run(Script(lambda q: reply("", [("sales_order.get", {"id": f"SO-{len(q.steps)}"})], cost=600)),
                limits=Limits(max_cost_micro_usd=1000))
    assert (r.stop_reason, r.steps, r.usage.cost_micro_usd) == ("max_cost", 1, 600)  # never overshoots the cap


def test_over_cap_reply_dispatches_nothing(env):
    big = Script(lambda q: reply("", [("sales_order.get", {"id": f"SO-{len(q.steps)}"})], tokens=(5000, 5000)))
    r = env.run(big, limits=Limits(max_total_tokens=12_000, est_input_tokens=10, est_output_tokens=10))
    assert r.stop_reason == "max_tokens" and len(env.tools.requests) == 1


def test_idempotency_key_is_deterministic_and_identical_writes_run_once(env):
    assert idempotency_key("r", 1, "t", {"a": 1, "b": 2}) == idempotency_key("r", 1, "t", {"b": 2, "a": 1})
    assert idempotency_key("r", 1, "t", {"a": 1}) != idempotency_key("r", 1, "t", {"a": 2})
    upd = ("sales_order.update", {"id": "SO-1", "qty": 2})
    env.run(Script(reply("", [upd]), reply("", [upd]), reply("done")))
    assert [q.tool for q in env.tools.requests] == ["sales_order.update"]
    keys = [q.idempotency_key for q in env.tools.requests]
    env.run(Script(reply("", [upd]), reply("done")))
    assert [q.idempotency_key for q in env.tools.requests] == keys  # a replayed run reuses the key
    env.run(Script(reply("", [GET]), reply("", [GET]), reply("done")))
    assert len(env.tools.requests) == 2  # reads keep the max_repeat_calls allowance


def test_malformed_replies_and_body_faults_fail_closed(env):
    bad = [ModelReply("x", (), Usage(-5, 0, 0, 0)), ModelReply("x", None, Usage()), "not a reply",
           ModelReply("x", (), None)]
    for b in bad:
        r = env.run(Script(lambda q, b=b: b))
        assert (r.status, r.error_code) == ("failed", "internal_error"), b
    loop = env.make(Script(reply("", [GET])))
    loop.allow.classify = lambda *a: (_ for _ in ()).throw(KeyError("tabSales frappe"))
    r = loop.run(caller=CALLER, run_id="run_9", user_text="x")
    spans = env.traces.spans("t_acme", "run_9")
    assert (r.status, r.error_code) == ("failed", "internal_error") and spans[-1].kind == "run"
    assert "agent.run_failed" in env.sink.types() and "frappe" not in json.dumps([s.to_dict() for s in spans])


def test_scrubber_keeps_ordinary_words_and_redacts_only_the_span():
    plain = "table tablet tabs SQL export report.py <!DOCTYPE html> doctype"
    assert sanitise_text(plain, 1000) == (plain, ())
    text, flags = sanitise_text("see tabSales Order via frappe.client, total 10.00", 1000)
    assert "internal_detail_withheld" in flags and "total 10.00" in text and " Order" in text
    assert "tabSales" not in text and "frappe" not in text


def test_session_taint_is_carried_in_and_out(env):
    tools = FakeTools({"sales_order.update": ToolResponse("pending_approval", None, {"id": "ap_2"})})
    r = env.run(Script(reply("", [("sales_order.update", {"id": "SO-1"})])), tools=tools,
                taint=TaintState(True, ("tool:sales_order.get",)))
    assert tools.requests[0].propose and r.taint_state.sources == ("tool:sales_order.get",)
    r2 = env.run(Script(reply("", [GET]), reply("ok")))
    assert r2.taint_state == TaintState(True, ("tool:sales_order.get",))


def test_redaction_by_value_and_salted_hash():
    red = redact_args({"q": "+966 55 123 4567", "note": "SA0380000000608010167519", "customer": "a@b.co",
                       "national_id": "1", "iqama": "2", "nested": [{"search": "1234567890"}], "date": "2026-11-19",
                       "qty": 3, "status": "open"})
    assert all(red[k] == "[redacted]" for k in ("q", "note", "customer", "national_id", "iqama"))
    assert red["nested"] == [{"search": "[redacted]"}] and (red["date"], red["qty"], red["status"]) == (
        "2026-11-19", 3, "open")
    assert args_hash("x", None) is None and args_hash("x", b"a") != args_hash("x", b"b")


class _Verifier:
    def __init__(self, p):
        self.p = p

    def verify(self, token, tenant_id):
        return self.p


class _Approvals:
    def pending(self, p):
        return [Approval("ap_old", "stale", "pending"), Approval("ap_1", "Cancel PO-1", "pending")]

    def get(self, p, aid):
        return None


def _stream(rt, tenant="t_acme"):
    store = MemoryStore()
    deps = Dependencies(verifier=_Verifier(Principal(tenant, "u_1", ("sales",), "s1")), runtime=rt,
                        approvals=_Approvals(), auditor=Auditor(store, rt), resolve_tenant=lambda h: tenant)
    body = json.dumps({"threadId": "th1", "runId": "r1", "messages": [{"id": "1", "role": "user", "content": "hi"}],
                       "state": {}, "tools": [], "context": [], "forwardedProps": {}}).encode()
    resp = handle_request(deps, method="POST", headers={"authorization": "Bearer x"}, host="h", body=body)
    frames = b"".join(resp.body).decode()
    return [json.loads(f[6:]) for f in frames.split("\n\n") if f.startswith("data: ")], store


def _adapter(tools=None, **kw):
    return AguiRuntimeAdapter(tools=tools or FakeTools({"purchase_order.cancel": ToolResponse(
        "pending_approval", None, {"id": "ap_1"})}), tool_defs=lambda t: DEFS, clock=TickClock(),
        ids=SequentialIds(), traces=MemoryTraceStore(), model_id="fake-model", prompt_version="p1", **kw)


def test_adapter_interrupts_only_on_this_runs_approvals():
    evs, _ = _stream(_adapter(model=Script(reply("", [("purchase_order.cancel", {"id": "PO-1"})]))))
    assert [i["id"] for i in evs[-1]["outcome"]["interrupts"]] == ["ap_1"]
    evs, _ = _stream(_adapter(model=Script(reply("done"))))
    assert evs[-1]["outcome"] == {"type": "success"}  # stale pending approvals are not this run's interrupt


def test_adapter_needs_approval_is_not_an_auth_error():
    calls = [("sales_invoice.submit", {"id": f"INV-{i}"}) for i in range(3)]
    evs, _ = _stream(_adapter(model=Script(reply("", calls))))
    assert evs[-1]["type"] == "RUN_FINISHED" and not [e for e in evs if e["type"] == "RUN_ERROR"]
    assert any(e.get("delta") == "errors.needs_approval" for e in evs)


def test_adapter_builds_the_port_per_principal_and_never_meters_twice():
    meter, seen = GatewayMeter(), []
    got = []

    def model_for(p, run_id):
        got.append((p.tenant_id, run_id))
        return gateway_model_for(_router(meter, seen))(p, run_id)
    rt = _adapter(model_for=model_for, limits=Limits(max_steps=2))
    _, store = _stream(rt, "t_beta")
    assert got == [("t_beta", "r1")] and len(meter.calls_for_tenant("t_beta")) == 2
    assert meter.calls_for_tenant("t_acme") == ()
    assert "meter.ai_usage" not in [e["type"] for e in store.read("t_beta")]  # the gateway metered it already
    _, store = _stream(_adapter(model=Script(reply("done"))))
    assert "meter.ai_usage" in [e["type"] for e in store.read("t_acme")]  # unmetered usage is reported once


def test_trace_store_spans_and_sink_for_unknown_tools_stay_clean():
    sink = Sink()
    loop = AgentLoop(model=Script(reply("", [("x" * 300, {})]), reply("ok")), tools=FakeTools(),
                     allow=resolve_allowlist(DEFS, ("sales",)), limits=Limits(), clock=TickClock(),
                     ids=SequentialIds(), traces=MemoryTraceStore(), events=sink)
    loop.run(caller=CALLER, run_id="r", user_text="x")
    assert [d["tool"] for _, t, d, _ in sink.items if t == "agent.tool_proposed"] == ["unknown"]
