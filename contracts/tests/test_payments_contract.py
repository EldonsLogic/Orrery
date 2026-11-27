"""Schema tests for the payments connector contract (DSC-021, contracts/connector-payments.md, ADR-0077).

Valid examples must pass; every payments file in examples/invalid/ must fail, and must fail for the reason
its name gives (one targeted change from a valid example). The Luhn rule is a reference check for DSC-023;
the service's own checks stay authoritative. Run: uv run --with jsonschema --with pytest python3 -m pytest contracts/tests -q
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((C / "connector-payments.schema.json").read_text(encoding="utf-8"))
V = Draft202012Validator(SCHEMA)
VALID = sorted((C / "examples").glob("payments-*.json"))
INVALID = sorted((C / "examples" / "invalid").glob("payments-*.json"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def luhn_card_like(s):
    """True for a 13 to 19 digit run passing the Luhn check (PAY-DATA-001)."""
    digits = "".join(ch for ch in s if ch.isdigit())
    if not 13 <= len(digits) <= 19 or digits != s.replace(" ", "").replace("-", ""):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


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
    md = (C / "connector-payments.md").read_text(encoding="utf-8")
    assert "Version: 0.1.0" in md


def test_every_kind_has_valid_and_invalid_examples():
    kinds = {load(p)["kind"] for p in VALID}
    assert kinds == {"capabilities", "checkout_request", "refund_request", "payment_event"}
    assert len(INVALID) >= 8


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_pass_and_carry_no_card_data(path):
    doc = load(path)
    assert list(V.iter_errors(doc)) == []
    assert not any(luhn_card_like(s) for s in strings(doc))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_fail(path):
    assert not V.is_valid(load(path))


def test_luhn_reference():
    assert luhn_card_like("4111111111111111")
    assert not luhn_card_like("4111111111111112")
    assert not luhn_card_like("SINV-00042")


def test_card_data_never_declarable():
    caps = SCHEMA["$defs"]["capabilities"]["properties"]
    assert caps["card_data"] == {"const": "none"}
    assert caps["sandbox"] == {"const": True}
    assert caps["webhook"]["properties"]["status_reread"] == {"const": True}
    for name in ("capabilities", "checkout_request", "refund_request", "payment_event"):
        assert SCHEMA["$defs"][name]["additionalProperties"] is False


def test_refund_always_needs_approval():
    assert "approval_id" in SCHEMA["$defs"]["refund_request"]["required"]
