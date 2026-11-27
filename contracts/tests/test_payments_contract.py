"""Schema tests for the payments connector contract (DSC-021, contracts/connector-payments.md, ADR-0077).

Valid examples must pass; every payments file in examples/invalid/ must fail with the keyword and at the path
listed in EXPECTED (one targeted change from a valid example). JSON is loaded with non-integers as Decimal,
so `10.0` is not an integer (section 1.3). `card_like`, `to_decimal_string` and `to_minor` are reference
implementations for DSC-023; the service's own checks stay authoritative.
Run: uv run --with jsonschema --with pytest python3 -m pytest contracts/tests -q
"""
import json
import os
import re
import uuid
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
    "capabilities-hosted-fields": ("enum", "checkout_modes/1"),
    "capabilities-signed-timestamp-no-window": ("required", "webhook"),
    "capabilities-unsigned-scheme-with-window": ("not", "webhook"),
    "capabilities-fields-scheme-at-receiver": ("const", "webhook/verifier"),
    "capabilities-unknown-retry-short-retention": ("minimum", "webhook/dedupe_retention_days"),
    "capabilities-header-secret-token": ("enum", "webhook/scheme"),
    "capabilities-no-key-mode-check": ("required", ""),
    "checkout-absolute-return-url": ("pattern", "return_path"),
    "checkout-card-field": ("additionalProperties", ""),
    "checkout-decimal-amount": ("type", "amount/minor"),
    "checkout-integral-float": ("type", "amount/minor"),
    "checkout-environment-from-request": ("additionalProperties", ""),
    "checkout-credit-note-link": ("enum", "links/0/entity"),
    "checkout-dashed-pan-key": ("not", "idempotency_key"),
    "checkout-multi-separator-pan-key": ("not", "idempotency_key"),
    "checkout-test-currency": ("not", "amount/currency"),
    "checkout-minor-too-large": ("maximum", "amount/minor"),
    "checkout-no-connection": ("required", ""),
    "checkout-duplicate-links": ("uniqueItems", "links"),
    "checkout-hosted-fields": ("enum", "mode"),
    "event-card-digits-in-ref": ("pattern", "gateway_payment_ref"),
    "event-unprefixed-gateway-ref": ("pattern", "gateway_payment_ref"),
    "event-failed-without-code": ("required", ""),
    "event-failed-mismatch-code": ("enum", "failure_code"),
    "event-rejected-without-endpoint": ("required", ""),
    "event-rejected-with-payment-id": ("not", ""),
    "event-short-endpoint-id": ("pattern", "endpoint_id"),
    "event-captured-without-gateway-ref": ("required", ""),
    "event-refunded-without-refund-ref": ("required", ""),
    "refund-no-approval": ("required", ""),
    "refund-without-amount": ("required", ""),
    "refund-credit-note-basis-without-links": ("required", ""),
    "refund-unallocated-with-credit-note": ("not", ""),
    "connect-secret-in-request": ("additionalProperties", ""),
    "connect-no-fingerprint": ("required", "staged_secrets/0"),
}

# capability shapes of the gateways the contract models (section 5.2); provider -> scheme
NAMED_SCHEMES = {
    "payments.examplepay": "hmac_sha256_signed_timestamp",
    "payments.moyasar": "body_secret_token",
    "payments.hyperpay": "aes256gcm_encrypted_body",
    "payments.tap": "hmac_sha256_selected_fields",
}

# ISO 4217 minor units (SIX list one, published 2026-09-17, accessed 2026-11-27)
EXPONENTS = {"SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "KWD": 3, "BHD": 3, "OMR": 3, "JPY": 0}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def errors_for(doc):
    """Errors against the one $def named by `kind` (avoids the oneOf wrapper)."""
    sub = {k: v for k, v in SCHEMA.items() if k != "oneOf"} | {"$ref": f"#/$defs/{doc['kind']}"}
    return list(Draft202012Validator(sub).iter_errors(doc))


def card_like(s):
    """PAY-DATA-001: after removing spaces and - : . _, a 13 to 19 digit run that starts 2 to 6 and passes Luhn.

    A validated UUID is checked with its dashes kept (section 1.2), so its 8-4-4-4-12 groups never merge."""
    if UUID_RE.fullmatch(s):
        runs = re.findall(r"[0-9]+", s)
    else:
        runs = re.findall(r"[0-9]+", re.sub(r"[\s\-:._]", "", s))
    for run in runs:
        if 13 <= len(run) <= 19 and run[0] in "23456":
            total = sum((n - 9 if n > 9 else n) for n in (int(d) * (2 if i % 2 else 1) for i, d in enumerate(reversed(run))))
            if total % 10 == 0:
                return True
    return False


UUID_RE = re.compile(SCHEMA["$defs"]["ref"]["if"]["pattern"])


def to_decimal_string(minor, exponent):
    """Section 1.3: minor units to the action-policy hash form, integer arithmetic only."""
    if exponent == 0:
        return str(minor)
    whole, frac = divmod(minor, 10 ** exponent)
    return f"{whole}.{frac:0{exponent}d}"


def to_minor(text, exponent):
    """Section 1.3: a decimal source amount to minor units; excess precision is refused (PAY-AMT-003), never rounded."""
    m = re.fullmatch(r"(0|[1-9][0-9]*)(?:\.([0-9]+))?", text)
    if not m:
        raise ValueError("PAY-AMT-003")
    whole, frac = m.group(1), m.group(2) or ""
    if frac.rstrip("0")[exponent:]:
        raise ValueError("PAY-AMT-003")
    frac = (frac + "0" * exponent)[:exponent]
    return int(whole) * 10 ** exponent + (int(frac) if exponent else 0)


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


def uuid7():
    ms = int.from_bytes(os.urandom(6), "big")
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms << 80) | (0x7 << 76) | ((rand >> 68) & 0xFFF) << 64 | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return str(uuid.UUID(int=value))


def ulid():
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = int.from_bytes(os.urandom(16), "big")
    return "".join(alphabet[(value >> (5 * i)) & 31] for i in reversed(range(26)))


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
    for pan in ("4111111111111111", "4111-1111-1111-1111", "4111:1111:1111:1111", "4111--1111--1111--1111",
                "examplepay:4111111111111111"):
        assert card_like(pan), pan
    for ok in ("4111111111111112", "SINV-00042", "examplepay:1234567890123", "chk_01J9A7Q2"):
        assert not card_like(ok), ok


def test_schema_alone_does_not_stop_a_prefixed_pan():
    """Stated limit (section 1.2): a gateway ref may be numeric, so only code-side PAY-DATA-001 stops this."""
    doc = load(C / "examples" / "payments-event-captured-numeric-ref.json")
    doc["gateway_payment_ref"] = "examplepay:4111111111111111"
    assert V.is_valid(doc) and card_like(doc["gateway_payment_ref"])


def test_ref_accepts_random_uuids_and_ulids():
    """M12: tool-api section 6 keys are UUID or ULID; none may be refused by the schema or by PAY-DATA-001."""
    ref = Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/ref"})
    for make in (lambda: str(uuid.uuid4()), uuid7, ulid):
        for _ in range(20000):
            key = make()
            assert ref.is_valid(key), key
            assert not card_like(key), key
    assert ref.is_valid(str(uuid.uuid4()).upper())
    assert not ref.is_valid("41111111-1111-1111-1111-111111111111")  # version nibble 1 but variant 1: not a UUID


def test_named_gateway_schemes_are_modelled():
    """M8: one capability shape per modelled gateway scheme, each valid."""
    seen = {}
    for p in VALID:
        doc = load(p)
        if doc["kind"] == "capabilities":
            seen[doc["provider"]] = doc["webhook"]["scheme"]
    assert seen == NAMED_SCHEMES
    md = (C / "connector-payments.md").read_text(encoding="utf-8")
    assert "Unsupported in v1" in md and "PayTabs" in md


def test_decimal_string_for_the_approval_hash():
    """M14: minor units to decimal strings at the currency's exponent; excess precision refused."""
    cases = [(12345, "SAR", "123.45"), (5, "KWD", "0.005"), (100, "BHD", "0.100"), (7, "JPY", "7"), (1, "QAR", "0.01")]
    for minor, cur, text in cases:
        assert to_decimal_string(minor, EXPONENTS[cur]) == text
        assert to_minor(text, EXPONENTS[cur]) == minor
    assert to_minor("1150.000", 2) == 115000
    for bad, cur in (("10.005", "SAR"), ("1.2345", "KWD"), ("7.5", "JPY"), ("-1.00", "SAR"), ("1e3", "SAR"), (" 1.00", "SAR")):
        with pytest.raises(ValueError):
            to_minor(bad, EXPONENTS[cur])


def test_card_data_never_declarable():
    caps = SCHEMA["$defs"]["capabilities"]["properties"]
    assert caps["card_data"] == {"const": "none"}
    assert caps["sandbox"] == {"const": True}
    assert caps["webhook"]["properties"]["status_reread"] == {"const": True}
    assert caps["checkout_modes"]["items"]["enum"] == ["hosted_redirect"]
    for name in KINDS:
        assert SCHEMA["$defs"][name]["additionalProperties"] is False


def test_money_moves_need_approval_and_environment_is_never_requested():
    for name in ("refund_request", "connect_request"):
        assert "approval_id" in SCHEMA["$defs"][name]["required"]
    assert "environment" not in SCHEMA["$defs"]["checkout_request"]["properties"]
    assert "connection_id" in SCHEMA["$defs"]["checkout_request"]["required"]
