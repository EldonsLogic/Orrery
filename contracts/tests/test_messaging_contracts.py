"""Schema tests for the messaging and SMS connector contract (DSC-022, contracts/connector-messaging.md, ADR-0078).

Valid examples must pass. Every connector-messaging file in examples/invalid/ must fail for its stated reason: the
EXPECTED table pairs each file with the JSON Schema keyword and the property that must appear in a failing error
(validated against the object's own $defs subschema, so an unrelated failure does not keep the test green), and,
where the runtime refuses it with a catalog code, that code. Also checks that the Markdown and JSON versions agree,
that example hashes are real sha256 values and not reused, the reference rules for payload hashes, credential refs
and consent re-grants, and that every event type the contract names is a row of the event tables in events.md.
Run: python3 -m pytest contracts/tests -q
"""
import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((C / "connector-messaging.schema.json").read_text(encoding="utf-8"))
DOC = (C / "connector-messaging.md").read_text(encoding="utf-8")
V = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)
VALID = sorted(C.glob("examples/connector-messaging-*.json"))
INVALID = sorted(C.glob("examples/invalid/connector-messaging-*.json"))
DEFS = {"capability": "capability", "conversation": "conversation", "inbound_message": "inboundMessage",
        "send_request": "sendRequest", "delivery_status": "deliveryStatus", "consent_record": "consentRecord"}
CONTACT_REVOKE = {"contact_keyword", "contact_request", "provider_block"}

# file stem (after connector-messaging-) -> (keyword, property that must appear in the error path or message, code)
EXPECTED = {
    "auto-reply-template": ("const", "mode", None),
    "capability-media-inbound": ("enum", "inboundContent", None),
    "consent-revoked-no-date": ("required", "revokedAt", None),
    "inbound-trusted": ("const", "trust", None),
    "inbound-unverified-webhook": ("const", "signatureVerified", "MSG-001"),
    "marketing-as-r1": ("const", "riskClass", None),
    "marketing-by-agent": ("const", "origin", None),
    "reply-without-conversation": ("required", "conversationId", None),
    "status-failed-no-code": ("required", "errorCode", None),
    "template-no-consent": ("required", "consentRef", "MSG-005"),
    "marketing-null-approval": ("type", "approvalId", None),
    "auto-reply-free-text": ("not", "text", None),
    "auto-reply-sms": ("enum", "channel", None),
    "auto-reply-no-policy": ("required", "autoReplyPolicyRef", None),
    "auto-reply-low-threshold": ("minimum", "confidenceThreshold", None),
    "human-send-no-confirmation": ("required", "confirmationId", None),
    "agent-draft-no-approver": ("required", "sentBy", None),
    "utility-as-r1": ("const", "riskClass", None),
    "session-reply-untainted": ("const", "tainted", None),
    "send-no-country": ("required", "country", None),
    "regrant-by-tenant-after-stop": ("const", "capturedBy", None),
    "consent-revoked-no-supersedes": ("type", "supersedes", None),
    "capability-meta-replay-window": ("type", "replayWindowSeconds", None),
    "capability-dedup-retention-short": ("minimum", "dedupRetentionHours", None),
    "capability-sandbox-in-production": ("const", "sandbox", None),
    "sandbox-send-no-allowlist": ("required", "testAllowlistRef", "MSG-012"),
    "sms-session-reply": ("const", "mode", "MSG-003"),
    "inbound-no-flags": ("required", "flags", None),
    "inbound-unknown-event-type": ("enum", "eventType", "MSG-013"),
}


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def stem(p):
    return p.stem.removeprefix("connector-messaging-")


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
            and (prop in [str(x) for x in e.absolute_path] or prop in e.message)]
    assert hits, f"{path.name}: no {keyword} error on {prop}; got {[(e.validator, list(e.absolute_path)) for e in sub_errors(obj)]}"


def test_versions_agree():
    assert re.search(r"^Version: (\S+)$", DOC, re.M).group(1) == SCHEMA["version"]
    assert SCHEMA["$id"].endswith(":" + SCHEMA["version"])


def test_error_codes_in_catalog():
    catalog = set(re.findall(r"^\| `(MSG-\d{3})` \|", DOC, re.M))
    assert len(catalog) >= 14
    used = {load(p).get("errorCode") for p in VALID + INVALID} - {None}
    used |= {code for _, _, code in EXPECTED.values() if code}
    assert used and used <= catalog


def test_event_types_are_table_rows():
    events = (C / "events.md").read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| `([a-z_]+\.[a-z_]+)` \|", events, re.M))
    msg_section = events.split("### Messaging events", 1)[1].split("\n### ", 1)[0]
    msg_rows = set(re.findall(r"^\| `([a-z_]+\.[a-z_]+)` \|", msg_section, re.M))
    section = DOC.split("## 10. Audit and events", 1)[1].split("\n## ", 1)[0]
    named = set(re.findall(r"`((?:message|consent|meter)\.[a-z_]+)`", section))
    assert named, "the contract names its events"
    assert {n for n in named if not n.startswith("meter.")} <= msg_rows
    assert {n for n in named if n.startswith("meter.")} <= rows


def test_hashes_are_real_and_not_reused():
    seen = {}
    for p in VALID:
        o = load(p)
        if o["kind"] == "inbound_message" and "text" in o["content"]:
            assert o["content"]["contentHash"] == sha(o["content"]["text"])
        if o["kind"] == "send_request":
            canon = {k: v for k, v in o.items() if k not in ("payloadHash", "confirmationId", "approvalId")}
            assert o["payloadHash"] == sha(json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        for v in re.findall(r"sha256:[0-9a-f]{64}", json.dumps(o)):
            assert seen.setdefault(v, p.name) == p.name, f"{v} reused in {p.name} and {seen[v]}"


def test_credential_ref_tenant_segment_matches_tenant():
    for p in VALID + INVALID:
        o = load(p)
        if "credentialRef" in o:
            assert o["credentialRef"].split("/")[3] == o["tenantId"], p.name


def test_regrant_after_contact_stop_needs_contact_opt_in_after_revoke():
    regrants = [load(p) for p in VALID if load(p).get("afterRevocation")]
    assert regrants, "a valid re-grant example exists"
    for o in regrants:
        prior = o["afterRevocation"]
        assert o["supersedes"] == prior["consentId"]
        assert o["capturedAt"] > prior["revokedAt"]
        if prior["revokedBy"] in CONTACT_REVOKE:
            assert o["capturedBy"] == "contact"
    bad = load(C / "examples/invalid/connector-messaging-regrant-by-tenant-after-stop.json")
    assert bad["afterRevocation"]["revokedBy"] in CONTACT_REVOKE and not V.is_valid(bad)


def test_validator_rules_cover_review_findings():
    rules = " ".join(SCHEMA["x-validator-rules"])
    for needle in ("credentialRef", "another tenant", "windowOpenUntil is null", "latest record", "test allowlist",
                   "production", "confidenceThreshold", "approvedTextId", "payloadHash", "eventType"):
        assert needle in rules, needle
