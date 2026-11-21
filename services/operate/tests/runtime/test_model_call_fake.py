"""PLT-026: the fake model-call port follows contracts/model-call.md 0.1.0 (refusal codes, reservation lifecycle,
fallback, idempotency, metering)."""
import copy
import json
from pathlib import Path

import pytest

from runtime.model_call_fake import Entry, FakeModelCallPort, ModelCallRefused

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
REQ = json.loads((CONTRACTS / "examples/model-call-request-agent.json").read_text(encoding="utf-8"))
SESSION = REQ["caller"]

try:
    from jsonschema import Draft202012Validator
    VALIDATOR = Draft202012Validator(json.loads((CONTRACTS / "model-call.schema.json").read_text(encoding="utf-8")))
except ImportError:  # CI installs jsonschema; a bare local run still checks behaviour
    VALIDATOR = None


def valid(doc):
    if VALIDATOR is not None:
        errors = [e.message for e in VALIDATOR.iter_errors(doc)]
        assert not errors, errors
    return doc


def req(**over):
    r = copy.deepcopy(REQ)
    r.update(over)
    return r


def port(**kw):
    return FakeModelCallPort(session=copy.deepcopy(SESSION), **kw)


def refused(p, r):
    events = len(p.events)
    with pytest.raises(ModelCallRefused) as ei:
        p.complete(r)
    valid(ei.value.as_dict())
    assert all(x.state != "reserved" for x in p.reservations), "a refusal must leave no open hold"
    assert len(p.events) == events, "a refusal emits no meter event"
    return ei.value.code, ei.value.reason


def test_examples_validate_and_fake_reply_matches_schema():
    for name in ("model-call-request-agent.json", "model-call-reply.json", "model-call-refusal-budget.json"):
        valid(json.loads((CONTRACTS / "examples" / name).read_text(encoding="utf-8")))
    p = port()
    out = valid(p.complete(req()))
    assert out["kind"] == "reply" and out["trust"] == "untrusted" and out["tainted"] is True
    assert out["tier"] == "mid" and out["attempts"] == 1 and not out["fallback_used"] and not out["replayed"]
    assert p.complete(req()) == dict(out, replayed=True)  # deterministic


def test_reservation_reserve_then_commit_and_meter_event():
    p = port()
    out = p.complete(req())
    [r] = p.reservations
    assert r.state == "committed" and 0 < r.committed <= r.amount
    assert out["usage"]["cost_micro_usd"] == r.committed == p.spent["tenant"] == p.spent["run"]
    [ev] = p.events
    assert ev["type"] == "meter.ai_usage" and ev["event_id"] == out["meter_event_id"]
    assert ev["tenant_id"] == "t_acme" and ev["correlation_id"] == "run_1" and ev["data_class"] == "operational"
    assert set(ev["data"]) == {"model_id", "tier", "input_tokens", "output_tokens", "cached_tokens",
                               "cost_micro_usd", "purpose", "agent_id"}
    assert "text" not in json.dumps(ev["data"]) and REQ["blocks"][0]["text"] not in json.dumps(ev)
    try:
        import evstream
    except ImportError:
        return
    assert evstream.validate_event(ev, stamped=False).ok


def test_budget_lowers_output_limit_then_refuses_below_minimum():
    p = port(budgets={"tenant": 10**6, "session": 10**6, "run": 6_000}, reply_text="x" * 3000)
    out = p.complete(req())                       # 800 tokens do not fit; the limit drops, still >= 200
    assert out["stop_reason"] == "max_output" and 200 <= out["usage"]["output_tokens"] < 800
    assert p.spent["run"] <= 6_000
    n = len(p.reservations)
    assert refused(p, req(idempotency_key="run_1:step_2:a")) == ("budget_refused", "exceeded")
    assert len(p.reservations) == n               # nothing reserved on refusal


@pytest.mark.parametrize("kw,code", [
    ({"meter_up": False}, ("budget_refused", "meter_unavailable")),
    ({"budgets": {"tenant": 10**6, "session": 10**6}}, ("budget_refused", "policy_missing")),
    ({"kill_switch": True}, ("kill_switch_engaged", "engaged")),
    ({"kill_switch": None}, ("kill_switch_engaged", "unreachable")),
    ({"region_max_class": None}, ("region_policy_refused", "policy_missing")),
    ({"region_max_class": "C1"}, ("region_policy_refused", "data_class_not_allowed")),
    ({"chains": {t: [Entry(f"{t}-x", t, region_ok=False)] for t in ("small", "mid", "frontier")}},
     ("region_policy_refused", "no_allowed_endpoint")),
    ({"filter_up": False}, ("filter_blocked", "filter_unavailable")),
    ({"reply_text": "leaked sk-" + "A1b2C3d4" * 4}, ("filter_blocked", "secret_in_output")),
])
def test_port_state_refusals(kw, code):
    assert refused(port(**kw), req()) == code


def _block(trust, **kw):
    b = {"content_id": f"b_{trust}", "trust": trust, "text": "hi", "data_class": "C0"}
    b.update(kw)
    return b


@pytest.mark.parametrize("over,code", [
    ({"model": "some-model"}, "model_named"),
    ({"caller": dict(SESSION, tenant_id="t_other")}, "caller_mismatch"),
    ({"metadata": {"tenant_id": "t_other"}}, "tenant_in_payload"),
    ({"blocks": [{"content_id": "x", "text": "hi", "data_class": "C0"}]}, "missing_trust_label"),
    ({"blocks": [_block("user"), _block("platform")]}, "block_order"),
    ({"tier": "code"}, "schema"),
    ({"contract_version": "1.0.0"}, "schema"),
    ({"max_output_tokens": 100, "min_output_tokens": 200}, "limit"),
    ({"blocks": [_block("untrusted")]}, "schema"),           # untrusted without a source
])
def test_invalid_requests(over, code):
    assert refused(port(), req(**over)) == ("invalid_request", code)


def test_injection_tainted_and_secret_in_prompt():
    assert refused(port(), req(accepts_untrusted=False)) == ("injection_tainted", "untrusted_not_accepted")
    clean = req(accepts_untrusted=False, blocks=REQ["blocks"][:3])
    assert port().complete(clean)["tainted"] is False
    leak = req(blocks=REQ["blocks"][:3] + [_block("untrusted", source="tool:x", text="AKIA" + "ABCDEFGH" * 2)])
    assert refused(port(), leak) == ("filter_blocked", "secret_in_prompt")


def test_fallback_same_or_stronger_and_releases_failed_hold():
    p = port(down={"mid-primary", "mid-secondary"})
    out = valid(p.complete(req()))
    assert out["tier"] == "frontier" and out["attempts"] == 3 and out["fallback_used"]
    assert [x.state for x in p.reservations] == ["released", "released", "committed"]
    assert [e for _, e, _ in p.attempt_log] == ["mid-primary", "mid-secondary", "frontier-primary"]
    assert all(not e.startswith("small") for _, e, _ in p.attempt_log)   # never a weaker tier


def test_chain_exhausted_is_retryable_model_unavailable():
    p = port(down={"frontier-primary", "frontier-secondary"})
    with pytest.raises(ModelCallRefused) as ei:
        p.complete(req(tier="frontier"))
    assert (ei.value.code, ei.value.retryable) == ("model_unavailable", True)
    assert [x.state for x in p.reservations] == ["released", "released"] and p.events == [] and p.spent["run"] == 0


def test_idempotency_replay_and_conflict():
    p = port()
    first = p.complete(req())
    again = p.complete(req())
    assert again["replayed"] and again["meter_event_id"] == first["meter_event_id"]
    assert len(p.events) == 1 and len(p.reservations) == 1
    assert refused(p, req(locale="ar")) == ("invalid_request", "idempotency_conflict")


def test_caps_hold_across_calls():
    p = port(budgets={"tenant": 10**6, "session": 10**6, "run": 15_000})
    n = 0
    with pytest.raises(ModelCallRefused) as ei:
        for i in range(50):
            p.complete(req(idempotency_key=f"run_1:step_{i}:a", call_id=f"c{i}"))
            n += 1
    assert ei.value.code == "budget_refused" and n >= 1 and p.spent["run"] <= 15_000
