import json
import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(OPERATE))
sys.path.insert(0, str(OPERATE.parents[1] / "services/blueprint/events"))

from agui import Approval, Dependencies, Principal, RuntimeUsage  # noqa: E402
from agui.audit import Auditor  # noqa: E402
from evstream import MemoryStore  # noqa: E402

HOST = "acme.example.test"


class FakeVerifier:
    def __init__(self):
        self.tokens = {"tok-a": Principal("t_acme", "u_1", ("sales",), "s1"),
                       "tok-b": Principal("t_other", "u_9", ("owner",), "s2"),
                       "tok-u2": Principal("t_acme", "u_2", ("sales",), "s3")}
        self.revoked = set()

    def verify(self, token, tenant_id):
        p = self.tokens.get(token)
        if p is None or p.tenant_id != tenant_id or token in self.revoked:
            raise ValueError("bad token details that must not leak: frappe")
        return p


class FakeApprovals:
    def __init__(self):
        self.items = {"ap_1": Approval("ap_1", "Approve order SO-17", "pending")}
        self.decide_calls = 0

    def pending(self, p):
        return [a for a in self.items.values() if a.status == "pending"]

    def get(self, p, aid):
        return self.items.get(aid)

    def decide(self, *a, **k):  # must never be reached from the stream endpoint
        self.decide_calls += 1


class FakeRuntime:
    model_id, prompt_version = "fake-model", "p1"

    def __init__(self, script=None):
        self.script, self.seen = script, []

    def run(self, ctx):
        self.seen.append(ctx)
        if self.script is not None:
            if isinstance(self.script, Exception):
                raise self.script
            return list(self.script)
        return [{"type": "TEXT_MESSAGE_START", "messageId": "m1", "role": "assistant"},
                {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m1", "delta": "مرحبا hello"},
                {"type": "TEXT_MESSAGE_END", "messageId": "m1"},
                RuntimeUsage("fake-model", "small", 10, 5)]


@pytest.fixture
def make():
    def _make(script=None):
        store = MemoryStore()
        rt = FakeRuntime(script)
        deps = Dependencies(verifier=FakeVerifier(), runtime=rt, approvals=FakeApprovals(), auditor=Auditor(store, rt),
                            resolve_tenant=lambda h: {HOST: "t_acme", "other.example.test": "t_other"}.get(h))
        return deps, store
    return _make


def body(**kw):
    d = {"threadId": "th1", "runId": "r1", "messages": [{"id": "1", "role": "user", "content": "hi"}],
         "state": {}, "tools": [], "context": [], "forwardedProps": {}}
    d.update(kw)
    return json.dumps(d).encode()


def collect(res):
    raw = b"".join(res.body).decode()
    return [json.loads(f[6:]) for f in raw.split("\n\n") if f.startswith("data: ")], raw
