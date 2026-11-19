import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
for p in (OPERATE, OPERATE.parent, OPERATE.parents[1] / "services/blueprint/events"):
    sys.path.insert(0, str(p))

from runtime import (AgentLoop, Caller, Limits, MemoryTraceStore, ModelReply, SequentialIds, TickClock, ToolCall,  # noqa: E402
                     ToolResponse, Usage, resolve_allowlist)

CALLER = Caller("t_acme", "u_1", ("sales",), "s1")


def tool(name, risk="R0", roles=("sales",), agent=True, **kw):
    d = {"name": name, "risk_class": risk, "agent_creatable": agent, "requires": {"roles": list(roles)},
         "description": f"{name} tool", "input_schema": {"type": "object"}}
    d.update(kw)
    return d


DEFS = [
    tool("sales_order.get"), tool("sales_order.list"), tool("sales_order.update", "R1"),
    tool("purchase_order.cancel", "R2"), tool("sales_invoice.submit", "R3"),
    tool("customer.update_bank_details", "R4", agent=False), tool("approval.decide", "R3", agent=False),
    tool("owner_only.get", roles=("owner",)),
    tool("sales_order.transition", "R2", transitions=[
        {"id": "deliver", "kind": "advance", "risk_class": "R1", "agent_creatable": True, "allowed_roles": ["sales"]},
        {"id": "approve_large", "kind": "approve", "risk_class": "R2", "agent_creatable": False,
         "allowed_roles": ["sales"]}]),
]


class Script:
    """Scripted ModelPort: each item is a ModelReply or a callable(request) -> ModelReply. Records requests."""
    model_id, prompt_version = "fake-model", "p1"

    def __init__(self, *items):
        self.items, self.requests = list(items), []

    def complete(self, request):
        self.requests.append(request)
        it = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(it, Exception):
            raise it
        return it(request) if callable(it) else it


class FakeTools:
    def __init__(self, responses=None, supports_propose=True):
        self.responses, self.requests, self.supports_propose = responses or {}, [], supports_propose

    def call(self, req):
        self.requests.append(req)
        r = self.responses.get(req.tool, ToolResponse("ok", {"id": "SO-1", "total": "10.00"}, audit_id="aud_1"))
        if isinstance(r, Exception):
            raise r
        return r(req) if callable(r) else r


class Sink:
    def __init__(self):
        self.items = []

    def emit(self, tenant_id, subject, type, data, trace):
        self.items.append((tenant_id, type, data, trace))

    def types(self):
        return [t for _, t, _, _ in self.items]


def reply(text="", calls=(), tokens=(100, 50), cost=10):
    return ModelReply(text, tuple(ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(calls)),
                      Usage(tokens[0], tokens[1], 0, cost, "fake-model", "mid"))


@pytest.fixture
def env():
    class E:
        pass
    e = E()
    e.clock, e.ids, e.traces, e.sink = TickClock(), SequentialIds(), MemoryTraceStore(), Sink()

    def make(model, tools=None, limits=None, defs=DEFS, roles=("sales",), assistant=None, cancel=None, caller=None,
             salt=b"test-salt"):
        e.tools = tools or FakeTools()
        e.model = model
        allow = resolve_allowlist(defs, roles, assistant)
        e.loop = AgentLoop(model=model, tools=e.tools, allow=allow, limits=limits or Limits(), clock=e.clock,
                           ids=e.ids, traces=e.traces, events=e.sink, cancel=cancel, hash_salt=salt)
        return e.loop

    def run(model, text="show order SO-1", taint=None, **kw):
        loop = make(model, **{k: v for k, v in kw.items() if k != "caller"})
        return loop.run(caller=kw.get("caller") or CALLER, run_id="run_1", user_text=text, instructions="SYS",
                        taint=taint)
    e.make, e.run = make, run
    return e
