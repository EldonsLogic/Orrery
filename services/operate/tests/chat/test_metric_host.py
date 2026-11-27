"""OPR-006 slice 3: a chat turn calls `metric.query` end to end through the host wiring, against fixtures."""
import json

from chat_helpers import OPERATE

from agui.ports import Principal
from chat import ChatService, MemoryChatStore, loop_runtime_factory
from metrics import default_registry
from runtime import MemoryTraceStore, ModelReply, SequentialIds, TickClock, ToolCall, Usage
from runtime.host import wire_metrics

ROOT = OPERATE.parents[1]
T = "t_acme"
EVENTS = [{"event_id": "E1", "type": "document.issued", "tenant_id": T, "sequence": 1,
           "occurred_at": "2026-11-02T10:00:00Z",
           "data": {"document_id": "INV-1", "document_type": "invoice", "total": "115.005", "currency": "SAR"}}]
ARGS = {"metric": "sales.revenue", "period": "2026-11", "currency": "SAR"}


class Inner:
    def call(self, request):
        raise AssertionError("metric.query must not reach the inner port")


class Model:
    model_id, prompt_version = "fake-model", "p1"

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return ModelReply("", (ToolCall("c1", "metric.query", ARGS),), Usage(10, 5, 0, 1, "fake-model", "mid"))
        return ModelReply("done", (), Usage(10, 5, 0, 1, "fake-model", "mid"))


def run(roles):
    bp = json.loads((ROOT / "contracts/examples/blueprint-trading-minimal.json").read_text(encoding="utf-8"))
    defs_for, port = wire_metrics(bp, metrics=default_registry(), event_loader=lambda t: list(EVENTS), inner=Inner())
    model, ids, clock = Model(), SequentialIds(), TickClock()
    factory = loop_runtime_factory(model=model, tools=port, tool_defs=defs_for, clock=clock, ids=ids,
                                   traces=MemoryTraceStore())
    svc = ChatService(store=MemoryChatStore(), runtime_factory=factory, ids=ids, clock=clock)
    p = Principal(T, "u_1", roles, "tok1")
    s = svc.open_session(p)
    list(svc.send(p, s.session_id, "msg-0000001", "revenue for November?"))
    return model


def seen(model):
    return json.dumps([[d.text for d in r.data] for r in model.requests], default=str)


def test_permitted_role_gets_the_computed_value():
    model = run(("accountant",))
    assert "115.01" in seen(model) and "INV-1" not in seen(model)


def test_non_permitted_role_never_gets_a_value():
    model = run(("warehouse_keeper",))
    assert "115.01" not in seen(model)


def test_sales_rep_gets_no_company_wide_value():
    model = run(("sales_rep",))
    assert "115.01" not in seen(model)
