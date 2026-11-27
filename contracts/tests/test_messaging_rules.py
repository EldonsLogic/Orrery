"""Reference checks for the connector-messaging validator rules JSON Schema cannot express (#394 review at b872370e).

Each test pins one finding: H1 (a contact STOP stays in force across the chain), M3 (a send is bound to its
conversation, sender and sandbox), M4 (a first-record STOP and its scope), M5 (an old STOP never ends a later grant),
M6 (per-channel timestamp format; Instagram blocked), M7 (status webhooks are deduplicated on message, status and
time), M8 (auto-reply refusal and tracing), M9 (data class, retention, production hold), M10 (keyword consent only
from signed, dated callbacks), L13 (batch approval binding). Fictional data only.
Run: python3 -m pytest contracts/tests -q
"""
import pytest

from test_messaging_contracts import (C, CONTACT_REVOKE, DOC, GRANT, REGRANT, SCHEMA, STOP, V, chain_refusal, load,
                                      sha, standing_revoke, tenant_grant)

RULES = " ".join(SCHEMA["x-validator-rules"])
CAP = load(C / "examples/connector-messaging-capability-whatsapp.json")
CONV = load(C / "examples/connector-messaging-conversation-open.json")
INBOUND = load(C / "examples/connector-messaging-inbound-text.json")
DRAFT = load(C / "examples/connector-messaging-send-agent-draft-reply.json")
AUTO = load(C / "examples/connector-messaging-send-auto-reply.json")
MKT = load(C / "examples/connector-messaging-send-marketing-template.json")
STATUS = load(C / "examples/connector-messaging-status-failed.json")
FIRST_STOP = load(C / "examples/connector-messaging-consent-first-stop.json")


def copied(r):
    return {"consentId": r["consentId"], "revokedBy": r["revokedBy"], "revokedAt": r["revokedAt"]}


def tenant_revoke(**kw):
    return {**GRANT, "consentId": "cns_0042_mkt_tr1", "state": "revoked", "capturedBy": "tenant_user",
            "method": "in_person", "evidenceHash": sha("tenant revoke"), "capturedAt": "2026-01-10T10:00:00Z",
            "recordedAt": "2026-01-10T10:00:02Z", "revokedAt": "2026-01-10T10:00:00Z", "revokedBy": "tenant_user",
            "supersedes": STOP["consentId"], **kw}


# H1: the two-step lift from the review: tenant revoke over the STOP, then a tenant grant after that revoke.
def test_h1_tenant_revoke_cannot_supersede_a_contact_stop():
    assert V.is_valid(tenant_revoke())
    assert chain_refusal([GRANT, STOP], tenant_revoke()) == "a tenant revoke cannot supersede a revoke"


def test_h1_a_stop_stays_in_force_even_under_a_later_revoke():
    tr = tenant_revoke()  # suppose it had been appended (older data, or a bug): the STOP still stands
    assert standing_revoke([GRANT, STOP, tr])["consentId"] == STOP["consentId"]
    lift = tenant_grant(supersedes=tr["consentId"], afterRevocation=copied(tr), recordedAt="2026-03-01T10:00:02Z")
    assert V.is_valid(lift)  # the schema alone lets it through: the chain rule refuses it
    assert chain_refusal([GRANT, STOP, tr], lift) == "afterRevocation is not the standing revoke"
    own = {**REGRANT, "supersedes": tr["consentId"], "afterRevocation": copied(STOP), "recordedAt": "2026-03-01T10:00:02Z"}
    assert chain_refusal([GRANT, STOP, tr], own) is None
    assert standing_revoke([GRANT, STOP, tr, own]) is None
    assert "standing" in RULES and "never by a tenant user" in RULES


# M4: a STOP may be the key's first record, and its scope is defined.
def test_m4_a_stop_can_be_the_first_record():
    assert V.is_valid(FIRST_STOP) and FIRST_STOP["supersedes"] is None
    assert chain_refusal([], FIRST_STOP) is None
    after = tenant_grant(supersedes=FIRST_STOP["consentId"], afterRevocation=copied(FIRST_STOP),
                         contactRef=FIRST_STOP["contactRef"], channel=FIRST_STOP["channel"])
    assert chain_refusal([FIRST_STOP], after) == "schema"  # only the contact's own opt-in lifts it


def stop_keys(channel):
    """The keys one STOP revokes: every purpose, on the channel it arrived on, in every phase-1 country."""
    purposes = SCHEMA["$defs"]["consentRecord"]["properties"]["purpose"]["enum"]
    return [(channel, country, purpose) for country in SCHEMA["$defs"]["country"]["enum"] for purpose in purposes]


def test_m4_stop_scope_and_no_country_default():
    assert len(stop_keys("whatsapp")) == 8
    section = DOC.split("## 6. Consent records", 1)[1].split("\n## ", 1)[0]
    assert "STOP scope" in section and "every purpose" in section and "no country" in section


# M5: a replayed or late STOP sent before a later grant does not end it.
def test_m5_old_stop_cannot_end_a_later_grant():
    replay = {**STOP, "consentId": "cns_0042_mkt_r2", "supersedes": REGRANT["consentId"],
              "recordedAt": "2026-02-05T10:00:00Z", "evidenceHash": sha("replayed stop")}
    assert replay["providerSentAt"] < REGRANT["recordedAt"]
    assert chain_refusal([GRANT, STOP, REGRANT], replay) == "stop older than the grant"
    fresh = {**replay, "providerSentAt": "2026-02-05T09:59:58Z", "revokedAt": "2026-02-05T09:59:58Z"}
    assert chain_refusal([GRANT, STOP, REGRANT], fresh) is None
    assert "providerSentAt is earlier" in RULES


# M3: a send is bound to its conversation, its sender account and the capability's sandbox flag.
def send_refusal(send, conv, cap, standing):
    if send["riskClass"] is None:
        return "riskClass null"
    if send["channelAccountRef"] != cap["channelAccountRef"] or send["sandbox"] != cap["sandbox"]:
        return "sender or sandbox mismatch"
    if conv is not None and any(send[k] != conv[k] for k in ("contactRef", "channel", "channelAccountRef")):
        return "MSG-015"
    if send["mode"] == "session_reply" and ((conv or {}).get("state") == "blocked" or standing is not None):
        return "MSG-006"
    return None


def test_m3_channel_account_is_required_and_hashed():
    assert "channelAccountRef" in SCHEMA["$defs"]["sendRequest"]["required"]
    assert DRAFT["channelAccountRef"] == CAP["channelAccountRef"]


@pytest.mark.parametrize("send,conv,standing,reason", [
    (DRAFT, CONV, None, None),
    (DRAFT, {**CONV, "contactRef": "ct_0099"}, None, "MSG-015"),
    (DRAFT, {**CONV, "channel": "messenger"}, None, "MSG-015"),
    (DRAFT, {**CONV, "state": "blocked"}, None, "MSG-006"),
    (DRAFT, CONV, STOP, "MSG-006"),
    (MKT, None, None, None),
    ({**MKT, "sandbox": False}, None, None, "sender or sandbox mismatch"),
    ({**MKT, "channelAccountRef": "ca_wa_other"}, None, None, "sender or sandbox mismatch"),
])
def test_m3_send_binding(send, conv, standing, reason):
    assert send_refusal(send, conv, CAP, standing) == reason


# M8: auto-reply is refused while riskClass is null, and every check it needs is traceable.
POLICY = {"autoReplyPolicyRef": "arp_wa_test_1", "confidenceThreshold": 0.85}
CLEAN = {**INBOUND, "messageId": "msg_0003", "content": {**INBOUND["content"], "flags": []}}


def auto_reply_refusal(send, inbound, policy, replied_windows, window):
    if send["inboundMessageId"] != inbound["messageId"] or send["conversationId"] != inbound["conversationId"]:
        return "not the triggering message"
    if inbound["content"]["flags"]:
        return "inbound has flags"
    if send["confidenceThreshold"] != policy["confidenceThreshold"] or send["confidence"] < policy["confidenceThreshold"]:
        return "threshold is not the policy's"
    if (send["conversationId"], window) in replied_windows:
        return "one per window"
    return None


def test_m8_auto_reply_refused_for_null_risk_class():
    assert V.is_valid(AUTO) and AUTO["riskClass"] is None
    assert send_refusal(AUTO, CONV, CAP, None) == "riskClass null"


@pytest.mark.parametrize("send,inbound,windows,reason", [
    ({**AUTO, "inboundMessageId": "msg_0003"}, CLEAN, set(), None),
    (AUTO, INBOUND, set(), "inbound has flags"),
    ({**AUTO, "inboundMessageId": "msg_0003", "confidenceThreshold": 0.9}, CLEAN, set(), "threshold is not the policy's"),
    ({**AUTO, "inboundMessageId": "msg_0003"}, CLEAN, {("conv_0001", CONV["windowOpenUntil"])}, "one per window"),
    ({**AUTO, "inboundMessageId": "msg_0009"}, CLEAN, set(), "not the triggering message"),
])
def test_m8_auto_reply_checks(send, inbound, windows, reason):
    assert auto_reply_refusal(send, inbound, POLICY, windows, CONV["windowOpenUntil"]) == reason


def test_m8_floor_adr_is_recorded():
    adr = (C.parent / "docs/decisions/ADR-0078-messaging-and-sms-connector.md").read_text(encoding="utf-8")
    plan = (C.parent / "docs/PLAN.md").read_text(encoding="utf-8")
    oq = (C.parent / "docs/open-questions.md").read_text(encoding="utf-8")
    for text in (adr, next(l for l in plan.splitlines() if l.startswith("| DSC-024 ")),
                 next(l for l in oq.splitlines() if l.startswith("| Q-720 "))):
        assert "floor ADR" in text and "ADR-0027" in text


# M7: status webhooks carry provenance, and dedup is keyed on message, status and provider time.
def status_dedup_key(st):
    w = st["webhook"]
    return sha("|".join([st["channel"], st["channelAccountRef"], st["providerMessageId"], st["status"],
                         str(w["providerTimestampRaw"])]))


def test_m7_status_dedup_key():
    assert STATUS["webhook"]["dedupKey"] == status_dedup_key(STATUS)
    later = {**STATUS, "status": "read", "webhook": {**STATUS["webhook"], "providerTimestampRaw": "1767261700"}}
    assert status_dedup_key(later) != status_dedup_key(STATUS)
    seen, metered = set(), set()
    for st in (STATUS, STATUS, later):  # a replay is dropped; meter.message_sent once per message
        key = status_dedup_key(st)
        if key in seen:
            continue
        seen.add(key)
        metered.add(st["messageId"])
    assert len(seen) == 2 and metered == {STATUS["messageId"]}


# M10: keyword consent only from a signed, dated callback.
def keyword_grant_refusal(record, inbound):
    if record["state"] != "granted" or record["method"] not in ("chat_keyword", "sms_keyword"):
        return None
    if inbound is None or inbound["messageId"] != record["sourceMessageId"]:
        return "no source message"
    if not inbound["webhook"]["signatureVerified"]:
        return "unsigned callback"
    if inbound["providerSentAt"] is None:
        return "undated callback"
    return None


def test_m10_keyword_grants_need_signed_dated_callbacks():
    src = {**CLEAN, "messageId": REGRANT["sourceMessageId"]}
    assert keyword_grant_refusal(REGRANT, src) is None
    path = {**src, "webhook": {**src["webhook"], "verification": "secret_path_ip_allowlist", "signatureVerified": False}}
    assert keyword_grant_refusal(REGRANT, path) == "unsigned callback"
    assert keyword_grant_refusal(REGRANT, {**src, "providerSentAt": None}) == "undated callback"
    assert keyword_grant_refusal(REGRANT, None) == "no source message"
    assert "verification" in SCHEMA["$defs"]["inboundMessage"]["properties"]["webhook"]["required"]


# M6: per-channel timestamp format; Instagram blocked until its webhook page is read.
def test_m6_messenger_numeric_timestamp_and_instagram_blocked():
    msgr = {**INBOUND, "channel": "messenger", "providerTimestampRaw": 1458692752478,
            "webhook": {**INBOUND["webhook"], "verification": "meta_hmac_sha256"}}
    assert V.is_valid(msgr)
    assert not V.is_valid({**msgr, "providerTimestampRaw": "1458692752478"})
    assert not V.is_valid({**INBOUND, "channel": "instagram"})
    assert "msg.meta_instagram" not in SCHEMA["$defs"]["capability"]["properties"]["connectorId"]["enum"]
    assert "messenger-platform/webhooks" in DOC and "Instagram is blocked" in DOC


# M9: classification, retention and the production hold.
def test_m9_data_class_retention_and_hold():
    assert INBOUND["content"]["dataClass"] == "C3"
    section = DOC.split("## 11.", 1)[1].split("\n## ", 1)[0]
    for needle in ("C3", "PD", "data_class", "outbound", "region", "LEG-003", "LEG-012", "D-10"):
        assert needle in section, needle
    assert "shortest placeholder" not in DOC
    dc = (C.parent / "docs/security/data-classification.md").read_text(encoding="utf-8")
    assert "connector-messaging" in dc


# L13: a batch send is bound to the approved manifest of per-send hashes.
def test_l13_batch_manifest_binds_each_send():
    b = MKT["batch"]
    assert b["manifestHash"] == sha("\n".join(sorted([MKT["payloadHash"]]))) and b["size"] == 1
    assert MKT["approvalId"]
    assert "manifestHash" in RULES and "step-up" in DOC
