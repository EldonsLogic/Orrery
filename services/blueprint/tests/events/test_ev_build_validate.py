import pytest

from evstream import EventError, build_event, validate_event
from evstream.validate import (MAX_DATA_BYTES, MAX_DATA_DEPTH, MAX_DATA_KEYS, MAX_DATA_NODES,
                               WHOLE_RECORD_MARKER)
from ev_helpers import SUBJ, ctx, make, stamp, FakeClock


def code_of(fn):
    with pytest.raises(EventError) as e:
        fn()
    return e.value.code


def b(data, **kw):
    kw.setdefault("subject", SUBJ)
    return build_event(ctx(), "sales_order.updated", data, **kw)


def test_build_sets_platform_fields():
    clock = FakeClock()
    ev = build_event(ctx(blueprint_revision=12, component="core.sales_order@0.1.3"), "sales_order.updated",
                     {"changes": {"status": "open"}}, subject=SUBJ, clock=clock)
    assert ev["tenant_id"] == "t_acme" and ev["actor"] == {"kind": "user", "id": "u_1", "role_ids": ["sales_rep"],
                                                           "on_behalf_of": None}
    assert ev["source"] == {"service": "operate", "component": "core.sales_order@0.1.3", "blueprint_revision": 12}
    assert ev["schema_version"] == 1 and ev["data_class"] == "business" and "sequence" not in ev
    assert ev["occurred_at"].endswith("Z") and ev["recorded_at"] > ev["occurred_at"]
    assert len(ev["event_id"]) == 26 and ev["correlation_id"] == "chat_turn_1"


def test_default_data_class_comes_from_registry():
    assert make("document.issued")["data_class"] == "financial"
    assert make("meter.active_user")["data_class"] == "operational"


def test_tenant_id_only_from_context():
    assert code_of(lambda: b({}, tenant_id="t_other")) == "EVS-TENANT-001"
    assert code_of(lambda: b({"tenant_id": "t_acme"})) == "EVS-TENANT-001"  # even its own
    assert code_of(lambda: b({"nested": {"deep": [{"tenantId": "t_other"}]}})) == "EVS-TENANT-001"
    assert code_of(lambda: b({"Tenant-ID": "x"})) == "EVS-TENANT-001"
    assert code_of(lambda: b({"ref": "t_other"})) == "EVS-TENANT-001"  # heuristic: looks like a tenant id
    assert code_of(lambda: b({"ref": "tenant-xyz"}, known_tenant_ids=["tenant-xyz"])) == "EVS-TENANT-001"
    assert b({"ref": "t_acme"})["data"] == {"ref": "t_acme"}  # own id as a value is fine


def test_platform_stamped_fields_refused():
    for k in ("sequence", "actor", "source", "recorded_at", "schema_version", "bogus"):
        assert code_of(lambda: b({}, **{k: 1})) == "EVS-FIELD-001"


def test_producers_cannot_use_unknown_types_or_bad_ids():
    assert code_of(lambda: build_event(ctx(), "made_up.thing", {})) == "EVS-TYPE-001"
    assert code_of(lambda: b({}, event_id="nope")) == "EVS-ENV-001"
    assert code_of(lambda: build_event(ctx("platform"), "sales_order.updated", {}, subject=SUBJ)) == "EVS-TENANT-002"
    assert code_of(lambda: build_event(ctx(), "component.published", {})) == "EVS-TENANT-002"


def test_event_id_can_be_supplied_for_retries():
    a = b({}, event_id="01J8ZK3AAAAAAAAAAAAAAAAAAA")
    assert a["event_id"] == "01J8ZK3AAAAAAAAAAAAAAAAAAA"


def test_build_does_not_alias_input():
    d = {"changes": {"a": 1}}
    ev = b(d)
    d["changes"]["a"] = 2
    assert ev["data"]["changes"]["a"] == 1


def test_agent_actor_needs_trace():
    assert code_of(lambda: build_event(ctx(kind="agent"), "sales_order.updated", {}, subject=SUBJ)) == "EVS-TRACE-001"


def test_size_cap():
    big = {"changes": {"x": "a" * (MAX_DATA_BYTES + 1)}}
    assert code_of(lambda: b(big)) == "EVS-DATA-002"
    ok = {"changes": {"x": "a" * (MAX_DATA_BYTES - 200)}}
    assert b(ok)


def test_size_cap_counts_utf8_bytes():
    assert code_of(lambda: b({"changes": {"x": "ع" * (MAX_DATA_BYTES // 2)}})) == "EVS-DATA-002"


def test_node_cap():
    assert code_of(lambda: b({"changes": {"l": list(range(MAX_DATA_NODES + 1))}})) == "EVS-DATA-002"


def test_depth_cap_and_cycles_do_not_recurse():
    d = cur = {}
    for _ in range(MAX_DATA_DEPTH + 2):
        cur["n"] = {}
        cur = cur["n"]
    assert code_of(lambda: b(d)) == "EVS-DATA-003"
    cyc = {}
    cyc["self"] = cyc
    assert code_of(lambda: b(cyc)) == "EVS-DATA-003"
    deep = [[]]
    for _ in range(100000):
        deep = [deep]
    r = validate_event({"data": {"x": deep}})
    assert not r.ok  # no RecursionError


def test_non_json_values_rejected():
    for bad in [{"a": object()}, {"a": {1, 2}}, {"a": b"x"}, {"a": float("nan")}, {1: "x"}]:
        assert code_of(lambda: b(bad)) in ("EVS-DATA-005", "EVS-ENV-001")


def test_whole_record_heuristic():
    flat = {f"k{i}": i for i in range(MAX_DATA_KEYS + 1)}
    assert code_of(lambda: b(flat)) == "EVS-DATA-004"
    assert b({f"k{i}": i for i in range(MAX_DATA_KEYS)})
    nested = {"a": {f"k{i}": 1 for i in range(25)}, "b": {f"j{i}": 1 for i in range(20)}}
    assert code_of(lambda: b(nested)) == "EVS-DATA-004"  # nested keys count too
    assert code_of(lambda: b({"record": {"name": "x"}})) == "EVS-DATA-004"
    assert code_of(lambda: b({"changes": {WHOLE_RECORD_MARKER: True, "a": 1}})) == "EVS-DATA-004"
    assert b({"record": "SO-1"})  # a string id under that key is fine


def test_personal_minimisation_rule():
    def p(data):
        return build_event(ctx(), "auth.signed_in", data, data_class="personal")
    assert p({"method": "password"})
    for bad in [{"email": "a@b.co"}, {"x": "a@b.co"}, {"full_name": "Layla"}, {"iban": "SA0380000000608010167519"},
                {"x": "SA0380000000608010167519"}, {"x": "+966 5 5555 5555"}, {"x": "y" * 65}, {"n": {"phone": "1"}}]:
        assert code_of(lambda: p(bad)) == "EVS-DATA-006", bad
    # the same values in a business event are not subject to the personal rule
    assert build_event(ctx(), "sales_order.updated", {"changes": {"email": "a@b.co"}}, subject=SUBJ)


def test_financial_class_also_minimised():
    assert code_of(lambda: build_event(ctx(), "document.issued", {"einvoice_status": "x", "account_number": "1"},
                                       subject=SUBJ)) == "EVS-DATA-006"


def test_class_downgrade_warns():
    ev = stamp(make("document.issued"), 1)
    ev["data_class"] = "operational"
    r = validate_event(ev)
    assert r.ok and any(i.code == "EVS-CLASS-001" for i in r.warnings)


def test_validate_flags_producer_sequence_when_unstamped():
    ev = make("<entity>.created")
    assert validate_event(ev, stamped=False).ok
    ev["sequence"] = 7
    assert any(i.code == "EVS-SEQ-001" for i in validate_event(ev, stamped=False).errors)


def test_validate_detects_tenant_values_in_stored_events():
    ev = stamp(make("<entity>.updated"), 1)
    ev["data"]["changes"] = {"owner": "t_other"}
    assert any(i.code == "EVS-TENANT-001" for i in validate_event(ev).errors)


def test_error_messages_are_clipped():
    ev = stamp(make("<entity>.created"), 1)
    ev["correlation_id"] = "z" * 100000
    r = validate_event(ev)
    assert not r.ok and all(len(i.message) <= 200 for i in r.errors)
