import copy
import json
import threading

import pytest

from evstream import EventError, MemoryStore, export_tenant_jsonl, find_gaps, validate_event, verify_chain
from ev_helpers import FakeClock, make, stamp


def code_of(fn):
    with pytest.raises(EventError) as e:
        fn()
    return e.value.code


def fill(store, tenant, n):
    return [store.append(make("<entity>.updated", tenant=tenant)) for _ in range(n)]


def test_store_assigns_strict_per_tenant_sequence():
    s = MemoryStore(clock=FakeClock())
    a = fill(s, "t_a", 3)
    b = fill(s, "t_b", 2)
    assert [e["sequence"] for e in a] == [1, 2, 3] and [e["sequence"] for e in b] == [1, 2]
    assert validate_event(a[0]).ok  # stored events are complete, stamped events


def test_producer_sequence_rejected():
    s = MemoryStore()
    ev = make("<entity>.created")
    ev["sequence"] = 99
    assert code_of(lambda: s.append(ev)) == "EVS-SEQ-001"
    assert s.read("t_acme") == []


def test_store_stamps_recorded_at_and_does_not_mutate_input():
    s = MemoryStore(clock=FakeClock())
    ev = make("<entity>.created")
    before = copy.deepcopy(ev)
    out = s.append(ev)
    assert ev == before and "sequence" not in ev
    assert out["recorded_at"] != ev["recorded_at"]


def test_invalid_events_rejected_and_nothing_stored():
    s = MemoryStore()
    ev = make("<entity>.created")
    ev["data"] = {"tenant_id": "t_x"}
    assert code_of(lambda: s.append(ev)) == "EVS-TENANT-001"
    assert code_of(lambda: s.append("nope")) == "EVS-ENV-002"
    assert s.read("t_acme") == []


def test_dedupe_is_idempotent():
    s = MemoryStore()
    ev = make("<entity>.created")
    a = s.append(ev)
    b = s.append(ev)               # producer retry
    c = s.append(a)                # redelivery of the stored form
    assert a == b == c and len(s.read("t_acme")) == 1 and s.last_sequence("t_acme") == 1


def test_event_id_reuse_with_other_content_or_tenant_rejected():
    s = MemoryStore()
    ev = make("<entity>.created")
    s.append(ev)
    changed = {**ev, "data": {"changed_fields": ["other"]}}
    assert code_of(lambda: s.append(changed)) == "EVS-DUP-002"
    other = {**ev, "tenant_id": "t_evil"}
    assert code_of(lambda: s.append(other)) == "EVS-DUP-001"
    assert s.read("t_evil") == []


def test_returned_events_are_copies():
    s = MemoryStore()
    out = s.append(make("<entity>.created"))
    out["data"]["changed_fields"].append("x")
    out["tenant_id"] = "t_evil"
    got = s.read("t_acme")[0]
    assert got["data"]["changed_fields"] == ["status"] and got["tenant_id"] == "t_acme"
    got["actor"]["id"] = "hacked"
    assert s.read("t_acme")[0]["actor"]["id"] == "u_1"
    assert s.get("t_acme", got["event_id"])["actor"]["id"] == "u_1"


def test_no_update_or_delete_api():
    public = {n for n in dir(MemoryStore) if not n.startswith("_")}
    assert public == {"append", "read", "get", "gaps", "last_sequence"}


def test_read_paging_and_limits():
    s = MemoryStore()
    fill(s, "t_acme", 5)
    assert [e["sequence"] for e in s.read("t_acme", 0, 2)] == [1, 2]
    assert [e["sequence"] for e in s.read("t_acme", 2, 100)] == [3, 4, 5]
    assert s.read("t_acme", 5) == [] and s.read("t_none") == []
    for args in [("t_acme", -1, 1), ("t_acme", 0, 0), ("t_acme", "0", 1), ("t_acme", 0, True), (None, 0, 1)]:
        assert code_of(lambda: s.read(*args)) == "EVS-READ-001"


def test_cross_tenant_isolation():
    s = MemoryStore()
    a = fill(s, "t_a", 3)
    fill(s, "t_b", 3)
    for after in (0, 1, 2):
        assert {e["tenant_id"] for e in s.read("t_a", after, 1000)} == {"t_a"}
        assert {e["tenant_id"] for e in s.read("t_b", after, 1000)} == {"t_b"}
    assert s.get("t_b", a[0]["event_id"]) is None
    assert s.get("t_a", a[0]["event_id"]) is not None
    assert {e["event_id"] for e in s.read("t_a")}.isdisjoint({e["event_id"] for e in s.read("t_b")})


def test_causation_correction_events():
    s = MemoryStore()
    orig = s.append(make("<entity>.updated"))
    fix = s.append(make("<entity>.updated", causation_id=orig["event_id"]))
    assert fix["causation_id"] == orig["event_id"] and fix["sequence"] == 2
    assert code_of(lambda: s.append(make("<entity>.updated", causation_id="01J8ZK3AAAAAAAAAAAAAAAAAAA"))) == "EVS-CAUSE-001"
    # another tenant's event does not count, and the error does not say it exists
    other = s.append(make("<entity>.updated", tenant="t_b"))
    assert code_of(lambda: s.append(make("<entity>.updated", causation_id=other["event_id"]))) == "EVS-CAUSE-001"
    assert s.last_sequence("t_acme") == 2


def test_gaps_detection():
    s = MemoryStore()
    fill(s, "t_acme", 5)
    assert s.gaps("t_acme") == [] and s.gaps("t_none") == []
    del s._by_tenant["t_acme"][2]           # simulate loss in the backing store
    del s._by_tenant["t_acme"][4]
    assert s.gaps("t_acme") == [(2, 2), (4, 4)]
    assert find_gaps([3, 4, 8]) == [(1, 2), (5, 7)] and find_gaps([]) == []


def test_concurrent_appends_keep_sequence_dense():
    s = MemoryStore()
    evs = [make("<entity>.updated") for _ in range(60)]
    ts = [threading.Thread(target=lambda e=e: s.append(e)) for e in evs]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(e["sequence"] for e in s.read("t_acme", 0, 1000)) == list(range(1, 61))


def test_export_is_deterministic_and_single_tenant():
    s = MemoryStore(clock=FakeClock())
    fill(s, "t_a", 3)
    fill(s, "t_b", 2)
    out = export_tenant_jsonl(s, "t_a")
    assert out == export_tenant_jsonl(s, "t_a")
    lines = out.splitlines()
    assert len(lines) == 3 and out.endswith("\n")
    evs = [json.loads(line) for line in lines]
    assert {e["tenant_id"] for e in evs} == {"t_a"} and [e["sequence"] for e in evs] == [1, 2, 3]
    assert all(line == json.dumps(json.loads(line), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
               for line in lines)
    assert export_tenant_jsonl(s, "t_none") == ""
    assert verify_chain(evs) == []


def test_export_pages_past_one_page():
    s = MemoryStore()
    fill(s, "t_a", 3)
    import evstream.export as ex
    ex.PAGE = 2
    try:
        assert len(export_tenant_jsonl(s, "t_a").splitlines()) == 3
    finally:
        ex.PAGE = 500


def test_verify_chain_detects_problems():
    s = MemoryStore()
    evs = fill(s, "t_acme", 5)
    codes = lambda x: [i.code for i in verify_chain(x)]
    assert codes(evs) == []
    assert codes(evs[:2] + evs[3:]) == ["EVS-SEQ-002"]
    assert codes([evs[1], evs[0]]) == ["EVS-SEQ-002", "EVS-SEQ-003"]
    assert codes([evs[0], evs[0]]) == ["EVS-SEQ-003"]
    assert codes(evs[1:]) == ["EVS-SEQ-002"] and verify_chain(evs[1:], start=2) == []
    other = fill(s, "t_b", 1)[0]
    assert "EVS-TENANT-003" in codes([evs[0], other])
    assert codes([{"x": 1}, "junk"]) == ["EVS-SEQ-003", "EVS-SEQ-003"]
