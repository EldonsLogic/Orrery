import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evstream import default_registry, validate_event
from evstream.registry import KINDS, SCHEMA_DIR
from ev_helpers import DATA, concrete_type, make, stamp

CONTRACT = Path(__file__).resolve().parents[4] / "contracts" / "events.md"
# Backticked tokens in contract section 3 that are not event types.
NOT_TYPES = {"<domain>.<past_tense_verb>"}
# Intentional exclusions: none. Platform events are included with kind "platform".
EXCLUDED: set = set()


def contract_types():
    text = CONTRACT.read_text(encoding="utf-8")
    sec = text.split("## 3. Event types", 1)[1].split("\n## 4.", 1)[0]
    toks = set(re.findall(r"`([<>a-z_]+\.[<>a-z_]+)`", sec))
    return toks - NOT_TYPES


def test_all_schema_files_are_valid_json_schemas():
    files = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert len(files) >= 6
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        for name, sub in doc.get("$defs", {}).items():
            Draft202012Validator.check_schema(sub)


def test_registry_refs_resolve_and_kinds_known():
    reg = default_registry()
    for t in reg.entries():
        assert t.kind in KINDS
        Draft202012Validator.check_schema(reg.data_schema(t.data_schema))


def test_registry_covers_every_contract_type():
    found = contract_types()
    assert len(found) > 50, "contract parse failed"
    keys = set(default_registry().keys())
    missing = (found - EXCLUDED) - keys
    assert not missing, f"types in contracts/events.md missing from types.json: {sorted(missing)}"


def test_registry_has_no_invented_types():
    extra_ok = {"build.sandbox_ready", "build.simulation_completed", "build.cutover_started"}  # build-states.md
    keys = set(default_registry().keys())
    assert keys - contract_types() <= extra_ok


def test_every_registry_type_has_a_passing_sample():
    reg = default_registry()
    assert set(reg.keys()) == set(DATA), set(reg.keys()) ^ set(DATA)
    for key in reg.keys():
        ev = make(key)
        r = validate_event(stamp(ev, 1), reg)
        assert r.ok and not r.unknown_type, (key, r.as_dict())
        assert ev["schema_version"] == reg.lookup(concrete_type(key)).schema_version


def test_pattern_types_match_any_entity_but_not_reserved_domains():
    reg = default_registry()
    assert reg.lookup("purchase_order.transitioned").kind == "record"
    assert reg.lookup("auth.created") is None and reg.lookup("tenant.deleted") is None
    assert reg.lookup("nodot") is None and reg.lookup(5) is None and reg.lookup("a.b.c") is None


def test_chat_turn_forbids_content():
    ev = make("chat.turn_completed")
    ev["data"] = {**ev["data"], "content": "hello"}
    assert not validate_event(stamp(ev, 1)).ok


def test_support_access_needs_reason_and_expiry():
    ev = make("support.access_requested")
    del ev["data"]["expires_at"]
    r = validate_event(stamp(ev, 1))
    assert any(i.code == "EVS-DATA-001" for i in r.errors)


def test_envelope_additional_properties_only_on_data():
    env = json.loads((SCHEMA_DIR / "envelope.schema.json").read_text())
    assert env["additionalProperties"] is False
    assert "additionalProperties" not in env["properties"]["data"]
    for k in ("actor", "source", "subject", "trace"):
        assert env["properties"][k]["additionalProperties"] is False
    assert set(env["required"]) == {"event_id", "type", "schema_version", "occurred_at", "tenant_id", "sequence",
                                    "actor", "source", "correlation_id", "data", "data_class"}


@pytest.mark.parametrize("mutate,code", [
    (lambda e: e.pop("event_id"), "EVS-ENV-001"),
    (lambda e: e.update(event_id="not-a-ulid"), "EVS-ENV-001"),
    (lambda e: e.pop("tenant_id"), "EVS-ENV-001"),
    (lambda e: e.update(tenant_id="t a"), "EVS-ENV-001"),
    (lambda e: e.pop("actor"), "EVS-ENV-001"),
    (lambda e: e["actor"].update(kind="robot"), "EVS-ENV-001"),
    (lambda e: e["source"].pop("service"), "EVS-ENV-001"),
    (lambda e: e.update(sequence=0), "EVS-ENV-001"),
    (lambda e: e.update(sequence="5"), "EVS-ENV-001"),
    (lambda e: e.update(occurred_at="yesterday"), "EVS-ENV-001"),
    (lambda e: e.update(data_class="secret"), "EVS-ENV-001"),
    (lambda e: e.update(data=[]), "EVS-ENV-001"),
    (lambda e: e.update(extra_field=1), "EVS-ENV-001"),
    (lambda e: e.update(schema_version=0), "EVS-ENV-001"),
    (lambda e: e.update(correlation_id=""), "EVS-ENV-001"),
    (lambda e: e.update(subject=None), "EVS-SUBJ-001"),
    (lambda e: e.update(subject={"entity": "x"}), "EVS-ENV-001"),
    (lambda e: e.update(causation_id=e["event_id"]), "EVS-CAUSE-002"),
    (lambda e: e.update(tenant_id="platform"), "EVS-TENANT-002"),
])
def test_envelope_invalid_matrix(mutate, code):
    ev = stamp(make("<entity>.created"), 3)
    mutate(ev)
    r = validate_event(ev)
    assert not r.ok and code in {i.code for i in r.errors}, r.as_dict()


def test_valid_envelope_with_optional_fields_absent():
    ev = stamp(make("<entity>.created"), 3)
    for k in ("recorded_at", "causation_id", "trace"):
        ev.pop(k, None)
    assert validate_event(ev).ok


def test_non_events_never_raise():
    for bad in [None, 5, "x", [], {}, {"data": {"a": object()}}, {"data": 5}, b"x"]:
        r = validate_event(bad)
        assert not r.ok


def test_unknown_type_is_accepted_but_flagged():
    ev = stamp(make("<entity>.created"), 1)
    ev["type"] = "loyalty.points_expired"
    r = validate_event(ev)
    assert r.ok and r.unknown_type and r.warnings[0].code == "EVS-TYPE-001"


def test_unknown_type_with_extra_data_fields_ok_and_unknown_data_fields_ignored():
    ev = stamp(make("<entity>.created"), 1)
    ev["data"]["new_additive_field"] = 1
    assert validate_event(ev).ok


def test_older_schema_version_warns_not_fails():
    ev = stamp(make("meter.storage"), 1)
    ev["schema_version"] = 2
    r = validate_event(ev)
    assert r.ok and any(i.code == "EVS-TYPE-002" for i in r.warnings)


def test_trace_rules():
    ev = stamp(make("agent.run_started"), 1)
    ev["trace"] = None
    assert any(i.code == "EVS-TRACE-001" for i in validate_event(ev).errors)
    ev = stamp(make("<entity>.created"), 1)
    ev["actor"]["kind"] = "agent"
    assert any(i.code == "EVS-TRACE-001" for i in validate_event(ev).errors)
    ev = stamp(make("<entity>.created"), 1)
    ev["trace"] = {"model_id": "m", "prompt_version": "p", "tool": None, "audit_id": None}
    assert validate_event(ev).ok
    ev = stamp(make("meter.ai_usage"), 1)
    ev["trace"] = {"model_id": None}
    assert any(i.code == "EVS-TRACE-001" for i in validate_event(ev).errors)


def test_platform_scope():
    ev = make("component.published")
    assert ev["tenant_id"] == "platform"
    assert validate_event(stamp(ev, 1)).ok
    ev["tenant_id"] = "t_acme"
    assert any(i.code == "EVS-TENANT-002" for i in validate_event(stamp(ev, 1)).errors)
