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
    "capability-meta-replay-window": ("type", "replayWindowSeconds", None),
    "capability-dedup-retention-short": ("minimum", "dedupRetentionHours", None),
    "capability-sandbox-in-production": ("const", "sandbox", None),
    "sandbox-send-no-allowlist": ("required", "testAllowlistRef", "MSG-012"),
    "sms-session-reply": ("const", "mode", "MSG-003"),
    "inbound-no-flags": ("required", "flags", None),
    "inbound-unknown-event-type": ("enum", "eventType", "MSG-013"),
    "consent-no-recorded-at": ("required", "recordedAt", None),
    "auto-reply-risk-r3": ("const", "riskClass", None),
    "agent-draft-self-confirmed": ("pattern", "sentBy", None),
    "template-in-thread-untainted": ("const", "tainted", None),
    "capability-dedup-in-memory": ("const", "dedupStore", None),
    "capability-event-age-too-long": ("maximum", "maxEventAgeHours", None),
    "capability-meta-no-payload-timestamp": ("const", "payloadTimestamp", None),
    "inbound-meta-no-provider-time": ("type", "providerSentAt", None),
    "inbound-meta-bad-timestamp-format": ("pattern", "providerTimestampRaw", None),
    "inbound-meta-timestamp-not-string": ("type", "providerTimestampRaw", None),
    "capability-dedup-retention-no-margin": ("minimum", "dedupRetentionHours", None),
    # #394 review 3 (b872370e)
    "send-no-channel-account": ("required", "channelAccountRef", None),
    "auto-reply-no-inbound": ("required", "inboundMessageId", None),
    "capability-instagram-blocked": ("enum", "connectorId", None),
    "capability-whatsapp-short-age": ("const", "maxEventAgeHours", None),
    "capability-whatsapp-window-168": ("const", "serviceWindowHours", None),
    "capability-one-credential": ("required", "webhookSecretRef", None),
    "inbound-messenger-timestamp-string": ("type", "providerTimestampRaw", None),
    "inbound-path-secret-as-signed": ("const", "signatureVerified", "MSG-001"),
    "inbound-no-data-class": ("required", "dataClass", None),
    "status-no-webhook": ("required", "webhook", None),
    "consent-keyword-no-source": ("required", "sourceMessageId", None),
    "consent-stop-no-provider-time": ("required", "providerSentAt", None),
    "batch-send-no-approval": ("required", "approvalId", None),
}
HASH_EXCLUDED = ("payloadHash", "confirmationId", "approvalId", "sentBy", "batch")


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
            canon = {k: v for k, v in o.items() if k not in HASH_EXCLUDED}
            assert o["payloadHash"] == sha(json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        for v in re.findall(r"sha256:[0-9a-f]{64}", json.dumps(o)):
            assert seen.setdefault(v, p.name) == p.name, f"{v} reused in {p.name} and {seen[v]}"


def test_credential_refs_are_split_and_tenant_bound():
    """L14 (S13, Q-695): the send token and the webhook secret are two refs with different readers."""
    props = SCHEMA["$defs"]["capability"]["properties"]
    assert "credentialRef" not in props and {"tokenRef", "webhookSecretRef"} <= set(props)
    for p in VALID + INVALID:
        o = load(p)
        if "tokenRef" in o:
            assert o["tokenRef"].split("/")[3] == o["tenantId"], p.name
        if "webhookSecretRef" in o and o["webhookSecretRef"].startswith("secret://tenant/"):
            assert o["webhookSecretRef"].split("/")[3] == o["tenantId"], p.name
        if "tokenRef" in o and "webhookSecretRef" in o:
            assert o["tokenRef"] != o["webhookSecretRef"], p.name


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
    for needle in ("tokenRef", "webhookSecretRef", "another tenant", "windowOpenUntil is null", "latest record", "test allowlist",
                   "production", "confidenceThreshold", "approvedTextId", "payloadHash", "eventType", "recordedAt",
                   "supersedes names the latest", "providerSentAt", "durable", "dedupRetentionHours is at least maxEventAgeHours", "10 or 13 digits", "riskClass null", "sentBy differs",
                   "tainted is set by platform code", "contactRef, channel and channelAccountRef equal", "blocked",
                   "inboundMessageId", "standing", "providerSentAt is earlier", "first record", "verification",
                   "maxEventAgeHours plus 1", "first receipt", "manifestHash", "unknown counts as C3", "LEG-012"):
        assert needle in rules, needle


def test_payload_hash_excludes_the_confirming_user():
    rule = next(r for r in SCHEMA["x-validator-rules"] if r.startswith("payloadHash"))
    for field in HASH_EXCLUDED:
        assert field in rule, field


def test_drafter_never_confirms_own_draft():
    props = SCHEMA["$defs"]["sendRequest"]["properties"]
    assert props["sentBy"]["pattern"].startswith("^usr_") and props["draftedBy"]["pattern"].startswith("^agt_")
    for p in VALID:
        o = load(p)
        if o.get("origin") == "agent_draft":
            assert o["sentBy"] != o["draftedBy"], p.name


def test_auto_reply_has_no_risk_class_until_its_row():
    for p in VALID:
        o = load(p)
        if o["kind"] == "send_request":
            assert o["riskClass"] == (None if o["origin"] == "auto_reply" else "R3"), p.name
    assert "AP-MSG-04" in (C.parent / "docs/security/action-policy-table.md").read_text(encoding="utf-8")


# M3, the consent chain: a reference implementation of the validator rules "supersedes names the latest record"
# and "ordering by recordedAt", over the history of one key (tenant, contact, channel, country, purpose).
KEY = ("tenantId", "contactRef", "channel", "country", "purpose")


def chain_refusal(history, new):
    """Why platform code refuses to append `new` to `history`, or None when it is accepted."""
    if not V.is_valid(new):
        return "schema"
    same_key = [r for r in history if all(r[k] == new[k] for k in KEY)]
    if not same_key:
        return None if new["supersedes"] is None else "supersedes a record that does not exist"
    head = max(same_key, key=lambda r: r["recordedAt"])
    if new["supersedes"] != head["consentId"]:
        return "supersedes is not the latest record"
    if new["recordedAt"] <= head["recordedAt"]:
        return "recordedAt not after the latest record"
    if new["state"] == "revoked":
        if head["state"] == "revoked" and new["revokedBy"] == "tenant_user":
            return "a tenant revoke cannot supersede a revoke"
        if (new["revokedBy"] == "contact_keyword" and head["state"] == "granted"
                and new["providerSentAt"] < head["recordedAt"]):
            return "stop older than the grant"
        return None
    standing = standing_revoke(same_key)
    target = standing or (head if head["state"] == "revoked" else None)
    if target is not None:
        copied = {"consentId": target["consentId"], "revokedBy": target["revokedBy"], "revokedAt": target["revokedAt"]}
        if new.get("afterRevocation") != copied:
            return "afterRevocation is not the standing revoke" if standing else "afterRevocation is not the superseded revoke"
    return None


def standing_revoke(records):
    """The latest contact or provider revoke not yet lifted by the contact's own opt-in (H1, #394 review 3)."""
    standing = None
    for r in sorted(records, key=lambda r: r["recordedAt"]):
        if r["state"] == "revoked" and r["revokedBy"] in CONTACT_REVOKE:
            standing = r
        elif (r["state"] == "granted" and standing is not None and r["capturedBy"] == "contact"
              and (r.get("afterRevocation") or {}).get("consentId") == standing["consentId"]):
            standing = None
    return standing


GRANT = {"kind": "consent_record", "tenantId": "t_demo_trading", "consentId": "cns_0042_mkt", "contactRef": "ct_0042",
         "channel": "whatsapp", "country": "SA", "purpose": "marketing", "state": "granted",
         "capturedAt": "2025-12-01T10:00:00Z", "recordedAt": "2025-12-01T10:00:03Z", "capturedBy": "contact",
         "method": "web_form", "textVersion": "mkt-ar-1", "language": "ar",
         "evidenceHash": "sha256:" + "1" * 64, "supersedes": None}
STOP = load(C / "examples/connector-messaging-consent-revoked.json")
REGRANT = load(C / "examples/connector-messaging-consent-regrant-by-contact.json")


def tenant_grant(**kw):
    return {**GRANT, "consentId": "cns_0042_mkt_t1", "capturedBy": "tenant_user", "method": "in_person",
            "evidenceHash": "sha256:" + "2" * 64, "capturedAt": "2026-03-01T10:00:00Z",
            "recordedAt": "2026-03-01T10:00:02Z", **kw}


def test_consent_chain_accepts_the_example_history():
    assert chain_refusal([], GRANT) is None
    assert chain_refusal([GRANT], STOP) is None
    assert chain_refusal([GRANT, STOP], REGRANT) is None


@pytest.mark.parametrize("history,new,reason", [
    # the #394 re-review bypass: after a STOP, a tenant user records a fresh grant with supersedes null
    ([GRANT, STOP], tenant_grant(), "supersedes is not the latest record"),
    # pointing at the old grant, skipping the STOP
    ([GRANT, STOP], tenant_grant(supersedes="cns_0042_mkt"), "supersedes is not the latest record"),
    # chaining to the STOP without the platform-copied afterRevocation
    ([GRANT, STOP], tenant_grant(supersedes="cns_0042_mkt_r1"), "afterRevocation is not the standing revoke"),
    # backdating capturedAt before the STOP does not move the record in the order: recordedAt decides
    ([GRANT, STOP], tenant_grant(supersedes="cns_0042_mkt", capturedAt="2025-12-15T10:00:00Z"),
     "supersedes is not the latest record"),
    # a second first record for a key that already has one
    ([GRANT], {**GRANT, "consentId": "cns_0042_mkt_b", "recordedAt": "2026-03-01T10:00:00Z"},
     "supersedes is not the latest record"),
    # a recordedAt that is not after the latest record (platform clock only moves forward per key)
    ([GRANT, STOP], {**REGRANT, "recordedAt": "2026-01-01T11:00:01Z"}, "recordedAt not after the latest record"),
])
def test_consent_chain_refuses(history, new, reason):
    assert chain_refusal(history, new) == reason


def test_tenant_grant_after_stop_with_afterrevocation_fails_schema():
    copied = {"consentId": STOP["consentId"], "revokedBy": STOP["revokedBy"], "revokedAt": STOP["revokedAt"]}
    assert chain_refusal([GRANT, STOP], tenant_grant(supersedes=STOP["consentId"], afterRevocation=copied)) == "schema"


# M7, replay: the window comes from the provider time in the signed body; the age limit sits inside dedup retention.
def test_window_is_computed_from_provider_time():
    from datetime import datetime, timedelta
    t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    conv = load(C / "examples/connector-messaging-conversation-open.json")
    inbound = load(C / "examples/connector-messaging-inbound-text.json")
    cap = load(C / "examples/connector-messaging-capability-whatsapp.json")
    assert inbound["providerSentAt"] != inbound["webhook"]["receivedAt"]
    assert conv["lastInboundAt"] == inbound["providerSentAt"]
    assert t(conv["windowOpenUntil"]) == t(inbound["providerSentAt"]) + timedelta(hours=cap["serviceWindowHours"])


def webhook_refusal(wh):
    """Reference for the validator rule JSON Schema cannot express: retention covers the age limit."""
    if wh["maxEventAgeHours"] is not None and wh["dedupRetentionHours"] < wh["maxEventAgeHours"] + 1:
        return "retention-below-age"
    return None


def test_event_age_limit_sits_inside_dedup_retention():
    wh = SCHEMA["$defs"]["capability"]["properties"]["webhook"]["properties"]
    assert wh["maxEventAgeHours"]["minimum"] > 36  # above the generic Graph API retry period (UNVERIFIED, Q-721)
    # WhatsApp retries for up to 7 days (Meta, 2026-11-27): age 7 days plus a 24 h margin, retention one hour more
    # than the age limit so the 300 s future skew cannot land a replay just after eviction (L11)
    assert wh["dedupRetentionHours"]["minimum"] == 193
    assert wh["maxEventAgeHours"]["maximum"] == 192
    assert wh["maxEventAgeHours"]["maximum"] + 1 <= wh["dedupRetentionHours"]["minimum"]
    assert wh["dedupStore"]["const"] == "durable"


def test_whatsapp_example_uses_the_192_hour_default():
    wh = load(C / "examples/connector-messaging-capability-whatsapp.json")["webhook"]
    assert wh["maxEventAgeHours"] == 192 and wh["dedupRetentionHours"] >= 193
    assert webhook_refusal(wh) is None


def test_retention_shorter_than_event_age_is_refused_by_the_validator():
    wh = dict(load(C / "examples/connector-messaging-capability-whatsapp.json")["webhook"])
    wh["dedupRetentionHours"] = 193
    wh["maxEventAgeHours"] = 192
    assert webhook_refusal(wh) is None
    for age, ret in ((192, 192), (192, 191), (100, 100)):
        wh.update(maxEventAgeHours=age, dedupRetentionHours=ret)
        assert webhook_refusal(wh) == "retention-below-age"
    assert "dedupRetentionHours is at least maxEventAgeHours plus 1" in " ".join(SCHEMA["x-validator-rules"])


def test_meta_timestamp_is_a_string_of_10_or_13_digits():
    ok = load(C / "examples/connector-messaging-inbound-text.json")
    assert isinstance(ok["providerTimestampRaw"], str) and V.is_valid(ok)
    for bad in ("", "1749416", "17494163830", "174941638312345", "17494163a3", 1749416383):
        assert not V.is_valid({**ok, "providerTimestampRaw": bad}), bad
    for good in ("1749416383", "1749416383000"):
        assert V.is_valid({**ok, "providerTimestampRaw": good}), good
    no_raw = {k: v for k, v in ok.items() if k != "providerTimestampRaw"}
    assert not V.is_valid(no_raw)  # required on a Meta channel
    assert "UNVERIFIED" in DOC and "unix seconds" in DOC


def test_meta_sources_and_unverified_wording_are_recorded():
    for url in ("https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks",
                "https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components"):
        assert url in DOC
    assert "up to 7 days" in DOC and "X-Hub-Signature-256" in DOC and "2026-11-27" in DOC
