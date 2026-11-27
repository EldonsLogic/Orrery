# Messaging and SMS connector

Version: 0.1.0
Status: draft (ADR-0078 Proposed)
Owner: eldon

How a tenant's business talks to its own customers on WhatsApp, Instagram and Facebook Messenger (Meta's business platform) and SMS, through one conversation model. A specialisation of the [connector interface](connector-interface.md) (tier 1 for Meta APIs, tier 4 trust rules for inbound text) that adds a send path. Objects: [connector-messaging.schema.json](connector-messaging.schema.json) (`kind` picks one of six); examples `examples/connector-messaging-*.json`, negative examples `examples/invalid/connector-messaging-*.json`. Decision: [ADR-0078](../docs/decisions/ADR-0078-messaging-and-sms-connector.md).

**Not the chat channel.** [OPR-015](../docs/product/opr-015-messaging-channel.md) lets a tenant's *staff* reach the Seshna chat over WhatsApp through a verified `channel_binding`. This contract is the *business-to-customer* inbox. A customer contact is never a principal: it gets no role, runs no tool and never reaches the chat runner. A number bound under OPR-015 is refused as a contact on the same channel account (MSG-010).

## 1. Channel capability declaration (`kind: capability`)
Each connector instance declares, per tenant and channel account: `connectorId` (`msg.meta_whatsapp`, `msg.meta_instagram`, `msg.meta_messenger`, `msg.sms`), `serviceWindowHours` (24 for the three Meta channels, null for SMS, which has none), `templatesRequiredOutsideWindow`, `inboundContent` (v1: `["text"]` only; media is refused with a fixed reply, as in OPR-015 section 6.3), `maxTextLength`, `readReceipts`, `credentialRef` (its tenant segment must equal `tenantId`, MSG-014), `sandbox`, `siteClass` (`sandbox` or `production`; a sandbox capability in production is refused) and `webhook` (section 8). The SMS adapter is provider-agnostic: one port, providers behind it, chosen per market by a later row.

## 2. Conversation and inbound message
- **Conversation** (`kind: conversation`): one thread per tenant, channel account and contact. `windowOpenUntil` is computed by platform code from the last inbound time plus `serviceWindowHours`, never from payload text. `state` is `open`, `closed` or `blocked` (contact blocked the business or was blocked). `windowOpenUntil` is always null on SMS.
- **Inbound message** (`kind: inbound_message`): `trust` is always `"untrusted"` (L3, [prompt-injection-defence](../docs/security/prompt-injection-defence.md) 2.1). Text is sanitised before labelling (3.3: control and bidi-override characters stripped, length capped) and flagged (`instruction_like`, `link`, `opt_out_keyword`, ...); `flags` is always present, empty when the scan found nothing, so "clean" and "never scanned" differ. `contentHash` is the sha256 of the sanitised text, computed by platform code. `retentionClass` is `transcript` (section 11). A thread holding any inbound message is tainted for every model run over it (2.4). Links are never fetched. `webhook.signatureVerified` is always true: an unverified call never becomes an object.

## 3. Send request (`kind: send_request`)
| Mode | When | Needs |
|---|---|---|
| `session_reply` | Inside an open service window (Meta channels only; never SMS) | `conversationId`, `text` (or, for `auto_reply`, `approvedTextId`); no template or consent ref (the contact wrote first). A null `windowOpenUntil` refuses it (MSG-003): use a template |
| `template` | Outside the window, every SMS, every business-initiated message | `template` (approved id, `utility` or `marketing`, `ar` or `en`, capped params) and `consentRef` to a granted consent of a purpose that covers the category |

Every send also carries `country` (the consent key, section 6), `tainted`, `sandbox` and `payloadHash` (sha256 of the canonical send without `payloadHash`, `confirmationId` and `approvalId`; recomputed at confirmation and execution, a mismatch voids both, action-policy section 5).

**Who sent it.** `origin` is `human`, `agent_draft` or `auto_reply`:
- `human`: `sentBy` (the user) and `confirmationId` (the gesture over the rendering of `payloadHash`) are required.
- `agent_draft`: `draftedBy` (agent id) plus `sentBy` (the human who confirmed) and `confirmationId`. An agent only drafts; the draft sits in the inbox and sends only on that gesture.
- `auto_reply`: none of the three; it carries `autoReplyPolicyRef`, `approvedTextId`, `classifiedIntent`, `confidence` and `confidenceThreshold` instead (section 5).

These sit beside the Tool API section 8 envelope (`user_id`, `agent_id`, `arguments_hash`, `approval_id`), which must agree with them. Authentication templates are not used (OPR-015 section 4.5).

**Tainted threads (prompt-injection-defence 4.5).** A session reply always has `tainted: true`, since the thread holds inbound text. A tainted send is a saved draft that executes only on a human's confirmation gesture over the canonical payload; that is why `human` and `agent_draft` both need `confirmationId`. `auto_reply` is the one path with no gesture, so it stays off until a SEC row allows it (section 5).

**Risk classes: proposed, SEC row pending (Q-702).** Action-policy section 4 defines R1 as a change with no external effect, and every send reaches a person outside the tenant, so no send is R1. R3 is the only class whose meaning includes an external send, so until SEC sets a row every send is `riskClass: R3` (fail closed; the row may be stricter, never looser):
- `message.send_reply` and utility `message.send_template` to one contact: R3 proposed, recipient selected by `contactRef` only (prompt-injection-defence 5.1).
- `message.send_template` with category `marketing`, any batch or campaign: R3, `origin: human`, `approvalId` a required ref (never null), step-up per the row; never agent-creatable.
- `auto_reply`: R3 proposed, `session_reply` on a Meta channel only; see section 5.

All sends are writes: `idempotencyKey` (ULID) is required; same key with other arguments is `idempotency_conflict` (Tool API section 6).

## 4. Delivery status (`kind: delivery_status`)
`costMicroUsd` (integer, null until the provider reports it) feeds `meter.message_sent`. Statuses: `accepted` (provider took the request; not delivery), `sent`, `delivered`, `read`, `failed` (with `errorCode`), `expired` (no delivered status before the provider's time-to-live). Status order is not guaranteed; consumers keep the highest seen state per message and never go back from `delivered` to `sent`.

## 5. Auto-reply (per tenant, off by default)
1. A tenant admin opts in per channel account and lists intents from the platform's fixed list: `greeting_ack`, `opening_hours`, `location`, `handoff_ack`. No other intent, no figures, no records, no links except the tenant's own allowlisted domain.
2. The model only classifies the intent. The send carries no `text`: it names `autoReplyPolicyRef` (the tenant's opt-in for that channel account) and `approvedTextId` (the tenant-approved fixed text, L1 configuration, for that intent), which platform code resolves and sends byte for byte. It records `classifiedIntent`, `confidence` and the `confidenceThreshold` applied (schema floor 0.8, placeholder with Q-156). Below the threshold, or on any flag, the message goes to a human as unanswered.
3. Meta channels only (SMS has no service window), only inside the service window, at most one auto-reply per conversation per intent per window, and per-tenant daily caps (placeholders, Q-156). A cap or an error stops auto-replies and alerts; it never falls back to a model-written send.
4. Cannot be enabled until the action-policy table has a row for it (ADR-0078 decision 4).

## 6. Consent records (`kind: consent_record`)
One record per contact, channel, country and purpose (`utility`, `marketing`), with `capturedAt`, `method`, `textVersion` and `language` of the wording shown, and `evidenceHash` of the capture (form submission, signed paper scan reference, keyword message). Records are keyed by tenant, `contactRef`, `channel`, `country` and `purpose`, and are append-only: a revoke or a re-grant is a **new record** with a new `consentId` and `supersedes` set to the record it replaces (a revoke always supersedes one). The latest record by time for the key decides; a send's `consentRef` must be that record, granted, for the send's `country` (MSG-005, MSG-006). `capturedBy` says who captured it (`contact`, `tenant_user`, `provider`).
- STOP and its Arabic equivalents in an inbound message, or a provider block, revoke at once (OPR-015 section 9), as `revokedBy` `contact_keyword`, `contact_request` or `provider_block`.
- **Re-grant after a contact's revoke:** only the contact's own opt-in lifts it (`capturedBy: contact`, method `web_form`, `chat_keyword` or `sms_keyword`), never a tenant user, an import or a spreadsheet. Platform code copies the superseded revoke into `afterRevocation`; the new `capturedAt` must be after its `revokedAt`, with new evidence.
- A tenant user may record consent captured elsewhere when no contact-initiated revoke stands; the platform never infers consent from a conversation. Consent records are kept while the contact exists plus the audit minimum.

## 7. Tenancy binding and credentials
- A `channel_account` (WhatsApp phone number id, Page id, Instagram account id, SMS sender id) is bound to exactly one tenant by the control plane. A second tenant claiming it is refused (MSG-011).
- Inbound webhooks resolve the tenant only from the verified recipient account id. Unknown account: drop, alert, no object (MSG-002).
- Provider tokens and app secrets live in the secret store per tenant ([secrets-management](../docs/security/secrets-management.md)); objects carry only `credentialRef`. Never in the Blueprint, events, logs or prompts.

## 8. Webhooks
1. **Verified:** Meta calls carry `X-Hub-Signature-256` (a SHA-256 signature of the payload keyed with the app secret; that it is HMAC is UNVERIFIED from the page read, see ADR-0078); the adapter compares in constant time before parsing. SMS providers are accepted only with their documented signature or a per-tenant secret path plus an IP allowlist. Fail closed: 401, nothing processed (MSG-001).
2. **Idempotent:** Meta retries failed deliveries for up to 36 hours and asks receivers to de-duplicate ([webhooks getting started](https://developers.facebook.com/docs/graph-api/webhooks/getting-started), read for ADR-0078 on 2026-11-27, not re-fetched for this revision: UNVERIFIED). `dedupKey` is the hash of provider, account and `providerEventId`; a repeat is acknowledged and dropped. Seen keys are kept for `webhook.dedupRetentionHours` (schema minimum 72, twice Meta's retry period; default 168).
3. **Replay-protected by dedup, not by age, for Meta:** Meta's signature covers the payload, with no signed timestamp as read (UNVERIFIED), so Meta capabilities have `signedTimestamp: false` and `replayWindowSeconds: null`, and a retried call, including a late STOP, is accepted for the whole retry period. Only a provider that signs a timestamp gets a window (60 to 3600 seconds, placeholder 600, Q-698); even then an opt-out keyword is processed, never dropped for age.
4. **Unknown types fail closed:** a verified call whose `eventType` is not in the schema list (v1: `message`; statuses map to `delivery_status`) is acknowledged, dropped, alerted and audited, and becomes no object (MSG-013).

## 9. Error codes
| Code | Meaning | Retry |
|---|---|---|
| `MSG-001` | Webhook signature missing or wrong | no |
| `MSG-002` | Unknown or unbound channel account | no |
| `MSG-003` | Session reply outside the service window | no; use a template |
| `MSG-004` | Template not approved for this language and category | no |
| `MSG-005` | No granted consent for this contact, channel, country and purpose | no |
| `MSG-006` | Contact opted out or blocked | no |
| `MSG-007` | Tenant budget or rate cap reached | after the window |
| `MSG-008` | Provider refused or failed delivery | per provider code, with backoff |
| `MSG-009` | Content refused by the outbound filter (engine name, link, secret pattern) | no |
| `MSG-010` | Number is an OPR-015 staff binding on this account | no |
| `MSG-011` | Channel account already bound to another tenant | no |
| `MSG-012` | Sandbox connector, recipient not on the test allowlist | no |
| `MSG-013` | Unknown webhook event or object type (dropped, alerted, audited) | no |
| `MSG-014` | A ref (credential, account, conversation, contact, consent, template, policy) belongs to another tenant | no |

## 10. Audit and events
Every inbound and send writes an audit record: the Tool API section 8 fields plus these, each read from an object field. Direction is the `kind` (`inbound_message` or `send_request`); channel is `channel`; template id and language are `template.templateId` and `template.language`; consent ref is `consentRef` (with `country`); taint is `tainted` (always true inbound); who sent is `sentBy`, `draftedBy`, `confirmationId` and `payloadHash`, or the auto-reply fields; cost is `delivery_status.costMicroUsd`. Content bodies never enter events: only `contentHash`. Contract 4 types added in [events.md](events.md): `message.received`, `message.send_requested`, `message.status_changed`, `consent.recorded`, `consent.revoked`, `meter.message_sent`.

## 11. Data minimisation and retention
Contact phone numbers and handles are stored sealed with a keyed hash for lookup (as OPR-015 section 5.1); objects carry `contactRef`. Message bodies (`retentionClass: transcript` on every inbound message) follow the transcript class in [data-retention](../docs/security/data-retention.md), with the period set per market by the country pack; until counsel sets it the shortest placeholder applies. Meta and the SMS provider are sub-processors on the tenant's DPA; cross-border transfer is per market and UNVERIFIED (LEG-003).

## 12. Sandbox rules
`sandbox: true` connectors use provider test numbers and accounts, synthetic contacts and data only (RULES 46). They send only to a per-tenant test allowlist (MSG-012): a send with `sandbox: true` must name `testAllowlistRef`, and the validator refuses a `contactRef` not on it; a production send names none. They never spend on live templates, and never run in a production site class (the schema refuses `siteClass: production` with `sandbox: true`). Customer Meta business verification, display names, template approvals and SMS sender registrations are go-live items, not build items (ADR-0076 decision 11).
