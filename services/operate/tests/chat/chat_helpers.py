import json
import sys
from pathlib import Path

OPERATE = Path(__file__).resolve().parents[2]
for p in (OPERATE, OPERATE.parent, OPERATE.parents[1] / "services/blueprint/events"):
    sys.path.insert(0, str(p))

from agui.ports import Principal, RuntimeUsage  # noqa: E402
from chat import ChatLimits, ChatService, MemoryChatStore  # noqa: E402
from runtime import SequentialIds, TickClock  # noqa: E402

ALICE = Principal("t_acme", "u_1", ("sales",), "tok1")
BOB = Principal("t_acme", "u_2", ("sales",), "tok2")
OTHER = Principal("t_other", "u_1", ("owner",), "tok9")


def text_events(text, mid="m1"):
    return [{"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": text},
            {"type": "TEXT_MESSAGE_END", "messageId": mid}]


class FakeRuntime:
    """Scripted AgentRuntime: `script` is a list of events, an exception, or a callable(ctx) -> iterable."""
    model_id, prompt_version = "fake-model", "p1"

    def __init__(self, script):
        self.script, self.ctxs = script, []

    def run(self, ctx):
        self.ctxs.append(ctx)
        s = self.script(ctx) if callable(self.script) else self.script
        if isinstance(s, Exception):
            raise s
        return s


class Factory:
    def __init__(self, script=None):
        self.script, self.setups, self.runtime = script, [], None

    def __call__(self, setup):
        self.setups.append(setup)
        self.runtime = FakeRuntime(self.script if self.script is not None else text_events("hello"))
        return self.runtime


class Audit:
    def __init__(self):
        self.items = []

    def emit(self, tenant_id, subject, type, data, trace):
        self.items.append((tenant_id, subject, type, data, trace))

    def types(self):
        return [i[2] for i in self.items]


def make(script=None, store=None, limits=ChatLimits(), router=None, audit=None, ids=None):
    f, a = Factory(script), audit or Audit()
    clock = TickClock(step=0.001)
    svc = ChatService(store=store or MemoryChatStore(), runtime_factory=f, ids=ids or SequentialIds(), clock=clock,
                      audit=a, limits=limits, router=router)
    return svc, f, a, clock


def collect(gen):
    return list(gen)


def texts(events):
    return "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")


def last(events):
    return events[-1]
