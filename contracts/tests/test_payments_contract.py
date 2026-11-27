"""Schema tests for the payments connector contract (DSC-021, contracts/connector-payments.md, ADR-0077).

Valid examples must pass; every payments file in examples/invalid/ must fail with the keyword and at the path
listed in EXPECTED (one targeted change from a valid example). JSON is loaded with non-integers as Decimal,
so `10.0` is not an integer (section 1.3). `card_like` is the reference PAY-DATA-001 check for DSC-023; the
service's own checks stay authoritative. Run: uv run --with jsonschema --with pytest python3 -m pytest contracts/tests -q
"""
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((C / "connector-payments.schema.json").read_text(encoding="utf-8"))
V = Draft202012Validator(SCHEMA)
VALID = sorted((C / "examples").glob("payments-*.json"))
INVALID = sorted((C / "examples" / "invalid").glob("payments-*.json"))
KINDS = {"capabilities", "checkout_request", "refund_request", "payment_event", "connect_request"}

# file stem -> (failing keyword, failing instance path)
EXPECTED = {
    "capabilities-long-replay-window": ("maximum", "webhook/replay_window_s"),
    "capabilities-no-sandbox": ("const", "sandbox"),
    "capabilities-raw-card-data": ("const", "card_data"),
    "capabilities-token-mode": ("enum", "checkout_modes/1"),
    "capabilities-hmac-no-timestamp": ("type", "webhook/timestamp_header"),
    "capabilities-no-key-mode-check": ("required", ""),
    "checkout-absolute-return-url": ("pattern", "return_path"),
    "checkout-card-field": ("additionalProperties", ""),
    "checkout-decimal-amount": ("type", "amount/minor"),
    "checkout-integral-float": ("type", "amount/minor"),
    "checkout-environment-from-request": ("additionalProperties", ""),
    "checkout-credit-note-link": ("enum", "links/0/entity"),
    "checkout-dashed-pan-key": ("not", "idempotency_key"),
    "checkout-test-currency": ("not", "amount/currency"),
    "checkout-minor-too-large": ("maximum", "amount/minor"),
    "event-card-digits-in-ref": ("pattern", "gateway_payment_ref"),
    "event-unprefixed-gateway-ref": ("pattern", "gateway_payment_ref"),
    "event-failed-without-code": ("required", ""),
    "event-rejected-without-endpoint": ("required", ""),
    "refund-no-approval": ("required", ""),
    "refund-without-amount": ("required", ""),
    "connect-secret-in-request": ("additionalProperties", ""),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def errors_for(doc):
    """Errors against the one $def named by `kind` (avoids the oneOf wrapper)."""
    sub = {k: v for k, v in SCHEMA.items() if k != "oneOf"} | {"$ref": f"#/$defs/{doc['kind']}"}
    return list(Draft202012Validator(sub).iter_errors(doc))


def card_like(s):
    """PAY-DATA-001: after removing spaces and - : . _, a 13 to 19 digit run that starts 2 to 6 and passes Luhn."""
    for run in re.findall(r"[0-9]+", re.sub(r"[\s\-:._]", "", s)):
        if 13 <= len(run) <= 19 and run[0] in "23456":
            total = sum((n - 9 if n > 9 else n) for n in (int(d) * (2 if i % 2 else 1) for i, d in enumerate(reversed(run))))
            if total % 10 == 0:
                return True
    return False


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def test_schema_is_valid_and_versioned():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["version"] == "0.1.0"
    assert "Version: 0.1.0" in (C / "connector-payments.md").read_text(encoding="utf-8")


def test_every_kind_has_valid_and_invalid_examples():
    assert {load(p)["kind"] for p in VALID} == KINDS
    assert {load(p)["kind"] for p in INVALID} == KINDS
    assert {p.stem.removeprefix("payments-") for p in INVALID} == set(EXPECTED)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_pass_and_carry_no_card_data(path):
    doc = load(path)
    assert list(V.iter_errors(doc)) == []
    assert not any(card_like(s) for s in strings(doc))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_fail_for_their_reason(path):
    doc = load(path)
    assert not V.is_valid(doc)
    keyword, where = EXPECTED[path.stem.removeprefix("payments-")]
    found = {(e.validator, "/".join(map(str, e.absolute_path))) for e in errors_for(doc)}
    assert (keyword, where) in found, found


def test_card_guard_reference():
    for pan in ("4111111111111111", "4111-1111-1111-1111", "4111:1111:1111:1111", "examplepay:4111111111111111"):
        assert card_like(pan), pan
    for ok in ("4111111111111112", "SINV-00042", "examplepay:1234567890123", "chk_01J9A7Q2"):
        assert not card_like(ok), ok


def test_schema_alone_does_not_stop_a_prefixed_pan():
    """Stated limit (section 1.2): a gateway ref may be numeric, so only code-side PAY-DATA-001 stops this."""
    doc = load(C / "examples" / "payments-event-captured-numeric-ref.json")
    doc["gateway_payment_ref"] = "examplepay:4111111111111111"
    assert V.is_valid(doc) and card_like(doc["gateway_payment_ref"])


def test_card_data_never_declarable():
    caps = SCHEMA["$defs"]["capabilities"]["properties"]
    assert caps["card_data"] == {"const": "none"}
    assert caps["sandbox"] == {"const": True}
    assert caps["webhook"]["properties"]["status_reread"] == {"const": True}
    assert "token" not in caps["checkout_modes"]["items"]["enum"]
    for name in KINDS:
        assert SCHEMA["$defs"][name]["additionalProperties"] is False


def test_money_moves_need_approval_and_environment_is_never_requested():
    for name in ("refund_request", "connect_request"):
        assert "approval_id" in SCHEMA["$defs"][name]["required"]
    assert "environment" not in SCHEMA["$defs"]["checkout_request"]["properties"]
