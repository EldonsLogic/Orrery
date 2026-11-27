"""Schema tests for the email sending connector contract (DSC-025, contracts/connector-email.md, ADR-0081).

Valid examples must pass. Every connector-email file in examples/invalid/ must fail for its stated reason: EXPECTED pairs
each file with the JSON Schema keyword and the property that must appear in a failing error's path or message (checked
against the object's own $defs subschema, so an unrelated failure cannot keep the test green) and, where the runtime
refuses it with a catalog code, that code. Also checks that the Markdown and JSON agree, that example hashes are real,
that secrets never appear in objects, and that the event types the contract names are registered.
Run: python3 -m pytest contracts/tests -q
"""
import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
ROOT = C.parent
SCHEMA = json.loads((C / "connector-email.schema.json").read_text(encoding="utf-8"))
DOC = (C / "connector-email.md").read_text(encoding="utf-8")
V = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)
VALID = sorted(C.glob("examples/connector-email-*.json"))
INVALID = sorted(C.glob("examples/invalid/connector-email-*.json"))
DEFS = {"capability": "capability", "connect_request": "connectRequest", "sender_domain": "senderDomain",
        "send_request": "sendRequest", "delivery_event": "deliveryEvent", "suppression_entry": "suppressionEntry"}
HASH_EXCLUDED = ("payloadHash", "confirmationId", "approvalId", "sentBy")

# file stem (after connector-email-) -> (keyword, property in the error path or message, runtime code or None)
EXPECTED = {
    "agent-draft-self-confirmed": ("pattern", "sentBy", None),
    "capability-dedup-in-memory": ("const", "dedupStore", None),
    "capability-dedup-retention-short": ("minimum", "dedupRetentionHours", None),
    "capability-key-in-webhook-slot": ("pattern", "webhookSecretRef", "EML-014"),
    "capability-postmark-hmac": ("const", "scheme", None),
    "capability-sandbox-in-production": ("const", "environment", None),
    "capability-tracking-no-policy": ("required", "trackingPolicyRef", "EML-010"),
    "capability-zeptomail": ("enum", "connectorId", "EML-016"),
    "connect-not-r4": ("const", "riskClass", None),
    "connect-one-staged-secret": ("minItems", "stagedSecrets", None),
    "connect-secret-in-request": ("additionalProperties", "apiKey", None),
    "domain-verified-dkim-fail": ("const", "dkim", "EML-003"),
    "domain-verified-unaligned": ("const", "aligned", "EML-003"),
    "event-click-with-url": ("additionalProperties", "url", None),
    "event-complaint-no-consent-revoke": ("required", "consentRevocationRef", None),
    "event-diagnostic-text": ("additionalProperties", "diagnostic", None),
    "event-hard-bounce-no-suppression": ("required", "suppressionId", None),
    "event-one-click-as-bounce": ("const", "eventType", None),
    "event-trusted": ("const", "trust", None),
    "event-unknown-type": ("enum", "eventType", "EML-013"),
    "event-unverified-webhook": ("const", "signatureVerified", "EML-001"),
    "marketing-bad-unsubscribe-post": ("const", "listUnsubscribePost", "EML-006"),
    "marketing-by-agent": ("const", "origin", None),
    "marketing-http-unsubscribe": ("pattern", "listUnsubscribe", "EML-006"),
    "marketing-no-body-link": ("const", "bodyUnsubscribeLink", "EML-006"),
    "marketing-no-unsubscribe-headers": ("required", "headers", "EML-006"),
    "marketing-null-approval": ("type", "approvalId", None),
    "marketing-single-no-consent": ("required", "consentRef", "EML-004"),
    "marketing-unsubscribe-not-dkim-signed": ("const", "dkimSignsUnsubscribeHeaders", "EML-006"),
    "sandbox-send-no-allowlist": ("required", "testAllowlistRef", "EML-012"),
    "send-no-confirmation": ("required", "confirmationId", None),
    "send-recipient-address": ("additionalProperties", "to", None),
    "send-risk-r1": ("const", "riskClass", None),
    "suppression-active-no-source": ("required", "sourceEventId", None),
    "suppression-address-in-clear": ("pattern", "addressHash", None),
    "suppression-complaint-marketing-only": ("const", "scope", None),
    "suppression-lifted-by-tenant-user": ("pattern", "liftedBy", None),
    "tracking-without-policy": ("required", "trackingPolicyRef", "EML-010"),
    "transactional-batch": ("const", "mode", None),
    "transactional-no-document": ("required", "documentRef", None),
    "transactional-with-tracking": ("const", "opens", None),
}


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def stem(p):
    return p.stem.removeprefix("connector-email-")


def sha(s):
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def leaves(errors):
    for e in errors:
        yield e
        yield from leaves(e.context or [])


def sub_errors(obj):
    sub = Draft202012Validator({"$ref": f"#/$defs/{DEFS[obj['kind']]}", "$defs": SCHEMA["$defs"]},
                               format_checker=Draft202012Validator.FORMAT_CHECKER)
    return list(leaves(sub.iter_errors(obj)))


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_every_kind_has_a_valid_example():
    assert {load(p)["kind"] for p in VALID} == set(SCHEMA["properties"]["kind"]["enum"])


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples(path):
    assert [e.message for e in V.iter_errors(load(path))] == []


def test_every_invalid_example_has_an_expectation():
    assert {stem(p) for p in INVALID} == set(EXPECTED)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_fail_for_their_reason(path):
    obj = load(path)
    assert not V.is_valid(obj)
    keyword, prop, _ = EXPECTED[stem(path)]
    hits = [e for e in sub_errors(obj) if e.validator == keyword
            and (prop in [str(x) for x in e.absolute_path] or f"'{prop}'" in e.message)]
    assert hits, f"{path.name}: no {keyword} error on {prop}; got {[(e.validator, list(e.absolute_path)) for e in sub_errors(obj)]}"


def test_versions_agree():
    assert re.search(r"^Version: (\S+)$", DOC, re.M).group(1) == SCHEMA["version"]
    assert SCHEMA["$id"].endswith(":" + SCHEMA["version"])


def test_error_codes_in_catalog():
    catalog = set(re.findall(r"^\| `(EML-\d{3})` \|", DOC, re.M))
    assert len(catalog) == 16
    used = {code for _, _, code in EXPECTED.values() if code}
    assert used <= catalog
    assert set(re.findall(r"EML-\d{3}", json.dumps(SCHEMA["x-validator-rules"]))) <= catalog


def test_one_signing_scheme_per_provider():
    """Section 5: each named provider has exactly one modelled scheme; ZeptoMail is not enabled in 0.1.0."""
    connectors = SCHEMA["$defs"]["connectorId"]["enum"]
    assert "email.zeptomail" not in connectors
    pinned = {}
    for rule in SCHEMA["$defs"]["capability"]["allOf"]:
        cid = rule["if"]["properties"].get("connectorId", {}).get("const")
        if cid:
            pinned[cid] = rule["then"]["properties"]["webhook"]["properties"]["scheme"]["const"]
    assert set(pinned) == set(connectors)
    assert len(set(pinned.values())) == len(pinned)
    for scheme in pinned.values():
        assert f"`{scheme}`" in DOC


def test_hashes_are_real_and_not_reused():
    seen = {}
    for p in VALID:
        o = load(p)
        if o["kind"] == "send_request":
            canon = {k: v for k, v in o.items() if k not in HASH_EXCLUDED}
            assert o["payloadHash"] == sha(json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        for v in re.findall(r"(?<![-\w])sha256:[0-9a-f]{64}", json.dumps(o)):
            assert seen.setdefault(v, p.name) == p.name, f"{v} reused in {p.name} and {seen[v]}"


def test_secret_refs_are_split_and_tenant_bound():
    for p in VALID:
        o = load(p)
        if o["kind"] == "capability":
            assert o["apiKeyRef"].split("/")[3] == o["tenantId"] == o["webhookSecretRef"].split("/")[3]
            assert o["apiKeyRef"] != o["webhookSecretRef"]


def test_no_address_or_secret_value_in_objects():
    """Recipients are contactRef or a segment; addresses only as keyed hashes; secrets only as staged fingerprints."""
    for p in VALID:
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z0-9._%+-]+@[a-z0-9-]+\.[a-z]{2,}\"", text), p.name
        assert "synthetic-api-key" not in text, p.name


def test_marketing_examples_carry_rfc8058_headers():
    for p in VALID:
        o = load(p)
        if o["kind"] == "send_request" and o["purpose"] == "marketing":
            assert o["headers"]["listUnsubscribePost"] == "List-Unsubscribe=One-Click"
            assert o["headers"]["listUnsubscribe"].startswith("https://")
            assert o["origin"] == "human" and o["approvalId"]


def test_event_types_registered_and_listed():
    events = (C / "events.md").read_text(encoding="utf-8")
    section = events.split("### Email events", 1)[1].split("\n### ", 1)[0]
    listed = set(re.findall(r"`(email\.[a-z_]+)`", section))
    events_line = next(ln for ln in DOC.splitlines() if ln.startswith("- **Events**"))
    named = set(re.findall(r"`(email\.[a-z_]+)`", events_line))
    types = json.loads((ROOT / "services/blueprint/events/schemas/types.json").read_text(encoding="utf-8"))
    registered = {k for k in types["types"] if k.startswith("email.")}
    assert set(SCHEMA["x-event-types"]) == listed == registered == named
    assert "email" in types["reserved_domains"]
