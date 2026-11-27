# Messaging and SMS connector

Version: 0.1.0
Status: draft (ADR-0078 Proposed)
Owner: eldon

How a tenant's business talks to its own customers on WhatsApp, Instagram and Facebook Messenger (Meta's business platform) and SMS, through one conversation model. A specialisation of the [connector interface](connector-interface.md) (tier 1 for Meta APIs, tier 4 trust rules for inbound text) that adds a send path. Objects: [connector-messaging.schema.json](connector-messaging.schema.json) (`kind` picks one of six); examples `examples/connector-messaging-*.json`, negative examples `examples/invalid/connector-messaging-*.json`. Decision: [ADR-0078](../docs/decisions/ADR-0078-messaging-and-sms-connector.md).

**Not the chat channel.** [OPR-015](../docs/product/opr-015-messaging-channel.md) lets a tenant's *staff* reach the Seshna chat over WhatsApp through a verified `channel_binding`. This contract is the *business-to-customer* inbox. A customer contact is never a principal: it gets no role, runs no tool and never reaches the chat runner. A number bound under OPR-015 is refused as a contact on the same channel account (MSG-010).

## 1. Channel capability declaration (`kind: capability`)
Each connector instance declares, per tenant and channel account: `connectorId` (`msg.meta_whatsapp`, `msg.meta_instagram`, `msg.meta_messenger`, `msg.sms`), `serviceWindowHours` (24 for the three Meta channels, null for SMS, which has none), `templatesRequiredOutsideWindow`, `inboundContent` (v1: `["text"]` only; media is refused with a fixed reply, as in OPR-015 section 6.3), `maxTextLength`, `readReceipts`, `credentialRef` and `sandbox`. The SMS adapter is provider-agnostic: one port, providers behind it, chosen per market by a later row.

## 2. Conversation and inbound message
- **Conversation** (`kind: conversation`): one thread per tenant, channel account and contact. `windowOpenUntil` is computed by platform code from the last inbound time plus `serviceWindowHours`, never from payload text. `state` is `open`, `closed` or `blocked` (contact blocked the business or was blocked).
- **Inbound message** (`kind: inbound_message`): `trust` is always `"untrusted"` (L3, [prompt-injection-defence](../docs/security/prompt-injection-defence.md) 2.1). Text is sanitised before labelling (3.3: control and bidi-override characters stripped, length capped) and flagged (`instruction_like`, `link`, ...). A thread holding any inbound message is tainted for every model run over it (2.4). Links are never fetched. `webhook.signatureVerified` is always true: an unverified call never becomes an object.

## 3. Send request (`kind: send_request`)
| Mode | When | Needs |
|---|---|---|
| `session_reply` | Inside an open service window (Meta channels only) | `conversationId`, `text`; no template or consent ref (the contact wrote first) |
| `template` | Outside the window, every SMS, every business-initiated message | `template` (approved id, `utility` or `marketing`, `ar` or `en`, capped params) and `consentRef` to a granted consent of a purpose that covers the category |

`origin` is `human`, `agent_draft` or `auto_reply`. An agent only drafts: an `agent_draft` is placed in the inbox and sends only on a human's gesture over the canonical payload (action-policy section 5). Authentication templates are not used (OPR-015 section 4.5).

**Risk classes** (Tool API `risk_class`; the action-policy row is SEC-owned, see ADR-0078):
- `message.send_reply` and `message.send_template` with category `utility` to one contact: R1, recipient selected by `contactRef` only (prompt-injection-defence 5.1).
- `message.send_template` with category `marketing`, any batch or campaign: R3, `origin: human`, `approvalId` required, step-up per the row; never agent-creatable.
- `auto_reply`: R1 `session_reply` only; see section 5.

All sends are writes: `idempotencyKey` (ULID) is required; same key with other arguments is `idempotency_conflict` (Tool API section 6).

## 4. Delivery status (`kind: delivery_status`)
`accepted` (provider took the request; not delivery), `sent`, `delivered`, `read`, `failed` (with `errorCode`), `expired` (no delivered status before the provider's time-to-live). Status order is not guaranteed; consumers keep the highest seen state per message and never go back from `delivered` to `sent`.

## 5. Auto-reply (per tenant, off by default)
1. A tenant admin opts in per channel account and lists intents from the platform's fixed list: `greeting_ack`, `opening_hours`, `location`, `handoff_ack`. No other intent, no figures, no records, no links except the tenant's own allowlisted domain.
2. The model only classifies the intent. The reply text is a tenant-approved fixed text (L1 configuration) for that intent, sent byte for byte. Below the confidence threshold, or on any flag, the message goes to a human as unanswered.
3. Only inside the service window, at most one auto-reply per conversation per intent per window, and per-tenant daily caps (placeholders, Q-156). A cap or an error stops auto-replies and alerts; it never falls back to a model-written send.
4. Cannot be enabled until the action-policy table has a row for it (ADR-0078 decision 4).

## 6. Consent records (`kind: consent_record`)
One record per contact, channel, country and purpose (`utility`, `marketing`), with `capturedAt`, `method`, `textVersion` and `language` of the wording shown, and `evidenceHash` of the capture (form submission, signed paper scan reference, keyword message). Revocation is a new state with `revokedAt` and `revokedBy`; STOP and its Arabic equivalents in an inbound message, or a provider block, revoke at once (OPR-015 section 9). A tenant user may record consent captured elsewhere; the platform never infers consent from a conversation. Consent records are kept while the contact exists plus the audit minimum.

## 7. Tenancy binding and credentials
- A `channel_account` (WhatsApp phone number id, Page id, Instagram account id, SMS sender id) is bound to exactly one tenant by the control plane. A second tenant claiming it is refused (MSG-011).
- Inbound webhooks resolve the tenant only from the verified recipient account id. Unknown account: drop, alert, no object (MSG-002).
- Provider tokens and app secrets live in the secret store per tenant ([secrets-management](../docs/security/secrets-management.md)); objects carry only `credentialRef`. Never in the Blueprint, events, logs or prompts.

## 8. Webhooks
1. **Verified:** Meta calls carry `X-Hub-Signature-256` (a SHA-256 signature of the payload keyed with the app secret; that it is HMAC is UNVERIFIED from the page read, see ADR-0078); the adapter compares in constant time before parsing. SMS providers are accepted only with their documented signature or a per-tenant secret path plus an IP allowlist. Fail closed: 401, nothing processed (MSG-001).
2. **Idempotent:** Meta retries for up to 36 hours and asks receivers to de-duplicate. `dedupKey` is the hash of provider, account and provider event id; a repeat is acknowledged and dropped.
3. **Replay-protected:** a call older than the replay window (placeholder 10 minutes, where the provider sends a timestamp) or with a seen `dedupKey` is refused. The window is configuration.

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

## 10. Audit and events
Every inbound and send writes an audit record (Tool API section 8 fields plus channel, direction, template id, language, consent ref, taint, cost). Content bodies never enter events: only `contentHash`. Contract 4 types added in [events.md](events.md): `message.received`, `message.send_requested`, `message.status_changed`, `consent.recorded`, `consent.revoked`, `meter.message_sent`.

## 11. Data minimisation and retention
Contact phone numbers and handles are stored sealed with a keyed hash for lookup (as OPR-015 section 5.1); objects carry `contactRef`. Message bodies follow the transcript class in [data-retention](../docs/security/data-retention.md), with the period set per market by the country pack; until counsel sets it the shortest placeholder applies. Meta and the SMS provider are sub-processors on the tenant's DPA; cross-border transfer is per market and UNVERIFIED (LEG-003).

## 12. Sandbox rules
`sandbox: true` connectors use provider test numbers and accounts, synthetic contacts and data only (RULES 46). They send only to a per-tenant test allowlist (MSG-012), never spend on live templates, and never run in a production site class. Customer Meta business verification, display names, template approvals and SMS sender registrations are go-live items, not build items (ADR-0076 decision 11).
