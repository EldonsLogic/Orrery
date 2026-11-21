import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
for p in (OPERATE, OPERATE.parent, OPERATE.parents[1] / "services/blueprint/events"):
    sys.path.insert(0, str(p))

from memory import InMemoryStore, MemoryService, Scope  # noqa: E402
from runtime import SequentialIds, TickClock  # noqa: E402


class Sink:
    def __init__(self):
        self.events, self.fail = [], False

    def emit(self, tenant_id, subject, type, data, trace):
        if self.fail:
            raise RuntimeError("down")
        self.events.append((tenant_id, subject, type, data))


@pytest.fixture
def env():
    clock, sink, store = TickClock(1000.0, 0.0), Sink(), InMemoryStore()
    svc = MemoryService(store, clock, SequentialIds(), sink, salt=b"s")
    return svc, clock, sink, store


A = Scope("t_acme", "u_1")
A2 = Scope("t_acme", "u_2")
B = Scope("t_beta", "u_1")
