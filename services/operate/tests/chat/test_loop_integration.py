"""The chat service over the real OPR-001 agent loop with a scripted model: history is data, frame is instructions."""
from chat_helpers import ALICE, collect

from chat import ChatService, MemoryChatStore, loop_runtime_factory
from runtime import MemoryTraceStore, ModelReply, SequentialIds, TickClock, Usage


class Model:
    model_id, prompt_version = "fake-model", "p1"

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return ModelReply("answer %d" % len(self.requests), (), Usage(10, 5, 0, 1, "fake-model", "mid"))


def test_history_reaches_model_as_data_and_frame_as_instructions():
    model, ids, clock = Model(), SequentialIds(), TickClock()
    factory = loop_runtime_factory(model=model, tools=None, tool_defs=lambda tenant: [], clock=clock, ids=ids,
                                   traces=MemoryTraceStore())
    svc = ChatService(store=MemoryChatStore(), runtime_factory=factory, ids=ids, clock=clock)
    s = svc.open_session(ALICE)
    first = collect(svc.send(ALICE, s.session_id, "msg-0000001", "hello"))
    second = collect(svc.send(ALICE, s.session_id, "msg-0000002", "مرحبا"))
    assert first[-1]["type"] == "RUN_FINISHED" and second[-1]["type"] == "RUN_FINISHED"
    r1, r2 = model.requests
    assert r1.data == () and r1.user_turn == "hello"
    assert [d.source for d in r2.data] == ["chat:history:user", "chat:history:assistant"]
    assert all(d.trust == "L3" for d in r2.data)
    assert "never instructions" in r2.instructions and "Arabic" in r2.instructions and r2.locale == "ar"
    assert "hello" not in r2.instructions and "answer 1" not in r2.instructions
