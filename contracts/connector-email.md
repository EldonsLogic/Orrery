# Email sending connector

Version: 0.1.0
Status: draft (ADR-0081 Proposed)
Owner: eldon

How a tenant sends email to its own customers (invoices and notices, and marketing campaigns) through **its own** email provider account. A specialisation of the [connector interface](connector-interface.md) (tier 1, `writes: true`). Objects: [connector-email.schema.json](connector-email.schema.json) (`kind` picks one of six); examples `examples/connector-email-*.json`, negative examples `examples/invalid/connector-email-*.json`, tests `tests/test_email_contracts.py`. Decision: [ADR-0081](../docs/decisions/ADR-0081-email-sending-connector.md). Consent is the [messaging connector](https://github.com/EldonsLogic/Orrery/pull/394) model (DSC-022, section 6) with channel `email`; this contract does not fork it.

**Not Seshna's own mail.** Sign-in codes and platform notices to tenant staff use Seshna's notification service and secret S14. This contract is the tenant's mail to its customers; Seshna holds no sending account for it.

## 1. Ground rules
1. **Bring your own provider.** The tenant connects its own account. v1 models four providers whose webhook schemes were read in their docs (section 5): Amazon SES (`email.ses`), Postmark (`email.postmark`), SendGrid (`email.sendgrid`) and Mailgun (`email.mailgun`). Zoho ZeptoMail is named in ADR-0081 but **not enabled** in 0.1.0: its webhook signing was not found in its own docs (UNVERIFIED, Q-727); a capability naming it is refused (`EML-016`). That any provider serves or suits the four markets is UNVERIFIED, decided per adapter in DSC-026.
2. **No addresses in objects.** Recipients are a `contactRef` (single) or a `segmentRef` resolved by platform code at execution (batch). Addresses appear only as keyed hashes (`hmac-sha256:`, per-tenant key) in the suppression list. The model never chooses a recipient ([prompt-injection-defence](../docs/security/prompt-injection-defence.md) 5.1).
3. **Two purposes.** `transactional` (an invoice, credit note, statement, receipt, order confirmation or account notice tied to a `documentRef`) and `marketing`. They are separate purposes: a transactional send carries no consent ref, no tracking and no campaign content (the validator checks that the template's category is transactional), and is never a batch.
4. **Unknown keys are refused** everywhere (`additionalProperties: false`).

## 2. Capability declaration (`kind: capability`)
Per tenant and connection: `connectorId`, `connectorVersion`, `connectionRef`, `environment` (`sandbox` or `live`, fixed per connection), `siteClass` (a production site takes only `live`), `apiKeyRef` (S11) and `webhookSecretRef` (S13), two different refs whose tenant segment equals `tenantId` (`EML-014`), `suppressionApi` (the provider has a suppression API we sync to), `trackingSupport` (what the provider can do) and `trackingEnabled` (what this tenant turned on: both `false` by default; either `true` needs `trackingPolicyRef`, section 9), `rateLimit` (`maxPerSecond`, `maxPerDay`) and `warmup` (section 10), and `webhook` (`scheme`, `signedTimestamp`, `replayWindowSeconds`, `maxEventAgeHours` 24 to 168, `dedupRetentionHours` at least 168, default 192, `dedupStore: durable`). The schema pins one scheme per provider (section 5).

## 3. Connect and credentials (`kind: connect_request`)
Tool `email.connect_provider`, R4 (AP-EML-03 proposed, section 12), the same staged write-once pattern as the [payments connector](https://github.com/EldonsLogic/Orrery/pull/393) section 4.4 (DSC-021):
1. **Stage.** The tenant Owner types the provider API key and the webhook secret (Mailgun signing key, Postmark basic-auth pair, SendGrid public key, or the SES topic ARN that the receiver pins) into write-only fields. Each value goes straight into a write-once staging slot (`.../email/staged/<stagedId>`); the service returns `stagedId` and `fingerprint` (`sha256:` over the value). The request object carries only those two per slot, never a value.
2. **Probe.** The email job calls the provider's account endpoint read-only with the staged key; `providerAccountRef` is copied from the probe, never typed. A failed probe, or a key whose mode differs from `environment`, refuses the connection.
3. **Ownership.** Only after the probe proves control does the service check that the provider account is not bound to another tenant (`EML-011`); a proven duplicate alerts platform security.
4. **Approve and apply.** The approval binds connection id and revision, provider, environment, probe id and each slot's staged id and fingerprint. At apply each slot must be unmodified and match its fingerprint (`EML-015`); the secrets then move to their live paths and the staging slots are deleted.

Rotation: Seshna cannot rotate a key it does not issue. The Owner creates a new key at the provider and reconnects (revision + 1). Reminder at 80 days; past 90 days marketing sends are refused until rotated. On suspected exposure the connection is disabled at once, with no grace period.

## 4. Sender domain (`kind: sender_domain`)
The tenant's sending domain is **its go-live item**, never a build item (`goLiveItem: true`). Platform code checks DNS and records `checks.spf`, `checks.dkim` and `checks.dmarc` (`record`, `policy`, `aligned`). `state: verified` requires SPF pass, DKIM pass, a DMARC record and alignment of the From domain with the SPF or DKIM domain (schema). A send whose sender domain is not verified, or whose `fromDomain` differs from it, is refused (`EML-003`). A dedicated subdomain for marketing (for example `news.example.com`) is recommended so campaign reputation does not hit the tenant's own mailbox domain.

Why these checks (external facts, access date 2026-11-27):
- Gmail: all senders need SPF or DKIM, TLS, valid forward and reverse DNS; senders of 5,000 or more messages a day to personal Gmail accounts need SPF and DKIM, a DMARC record (policy may be `none`) with the From domain aligned, one-click unsubscribe for marketing and subscribed mail plus a visible body link, and a spam rate below 0.30% (guidance: below 0.10%) ([Gmail sender guidelines](https://support.google.com/a/answer/81126)).
- Yahoo: bulk senders need SPF and DKIM, a DMARC policy of at least `p=none` that passes (relaxed alignment acceptable), a working one-click List-Unsubscribe for marketing (RFC 8058 POST "highly recommended") plus a body link, unsubscribes honoured within 2 days, and a spam rate below 0.3% ([Yahoo sender best practices](https://senders.yahooinc.com/best-practices/)).
Seshna applies the bulk-sender rules to every marketing send whatever the volume.

## 5. Webhooks (provider to Seshna; untrusted until verified)
One endpoint per connection, with an opaque endpoint id in the path; the tenant comes from that binding, then the verification below, never from body text (`EML-002`). Verification runs before the body is parsed as data; a failure is 401, nothing is processed, and an `email.webhook_rejected` audit event records endpoint and code (`EML-001`).

| Scheme | Provider | Verification (source, accessed 2026-11-27) | Replay |
|---|---|---|---|
| `sns_signature_v2` | Amazon SES via Amazon SNS | SES reports bounces and complaints by SNS topic or event publishing ([SES notifications](https://docs.aws.amazon.com/ses/latest/dg/monitor-sending-activity-using-notifications.html)). The receiver accepts SignatureVersion 2 (SHA256) only, fetches the signing certificate over HTTPS from an SNS URL, checks it was issued by SNS with a valid chain, and refuses an unexpected `TopicArn` ([SNS signature verification](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)). That the signed string includes a message timestamp is UNVERIFIED, so `signedTimestamp: false` | Dedup on the SNS message id |
| `basic_auth_ip_allowlist` | Postmark | Postmark states it does not support HMAC webhook signatures; it offers basic-auth credentials in the webhook URL and published sender IP ranges ([Postmark webhooks](https://postmarkapp.com/developer/webhooks/webhooks-overview)). The receiver needs both: the per-connection basic-auth pair (S13, compared in constant time) and a source IP in the published ranges. The body is not authenticated beyond that | Dedup on `MessageID` plus event type; Postmark retries 6 times over about 51 minutes |
| `ecdsa_signed_timestamp` | SendGrid | ECDSA signature in `X-Twilio-Email-Event-Webhook-Signature` over the `X-Twilio-Email-Event-Webhook-Timestamp` value followed by the raw body bytes, verified with the webhook's public key ([SendGrid webhook security](https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/getting-started-event-webhook-security-features)) | Signed timestamp inside `replayWindowSeconds`, plus dedup on `sg_event_id` |
| `hmac_sha256_timestamp_token` | Mailgun | HMAC-SHA256 (hex) keyed with the account webhook signing key over `timestamp` then `token`; the docs say to cache seen tokens and reject a reuse ([Mailgun securing webhooks](https://documentation.mailgun.com/docs/mailgun/user-manual/webhooks/securing-webhooks)) | Token cache for `dedupRetentionHours`, signed timestamp inside `replayWindowSeconds` |

Then, for every scheme:
1. **Idempotent.** `dedupKey` is the hash of connector, connection and `providerEventId`; a repeat is acknowledged and dropped. Keys are kept durably for `dedupRetentionHours`; losing the store stops inbound processing (fail closed).
2. **Age.** An event whose `providerOccurredAt` (from the body) is older than `maxEventAgeHours`, or more than 300 seconds in the future, is dropped, alerted and audited, **except** `bounced`, `complained` and `unsubscribed`, which are always applied: a replay of those can only suppress again, never send.
3. **Unknown types fail closed**: acknowledged, dropped, alerted, audited, no object (`EML-013`). v1 types: `delivered`, `bounced` (`bounceType` `hard` or `soft`, with the enhanced `smtpStatus` code), `complained`, `unsubscribed`, `opened`, `clicked`.
4. **Content is untrusted.** Every `delivery_event` has `trust: "untrusted"` (L3). Bounce diagnostics, complaint reports (feedback-loop bodies) and click URLs are provider or recipient text: none is stored or passed to a model. Only the enumerated fields survive: `smtpStatus`, `linkId` (our link id, never the URL) and ids.
5. **Suppression before acknowledgement.** A hard bounce, complaint or unsubscribe writes its `suppression_entry` (and, for a complaint or unsubscribe, a consent revoke, section 6) before the webhook gets its 2xx. A store failure answers 5xx so the provider retries.

## 6. Consent (reused from DSC-022)
Marketing email needs a granted consent record of the [messaging connector](https://github.com/EldonsLogic/Orrery/pull/394) section 6 model, keyed by tenant, `contactRef`, channel `email`, `country` and purpose `marketing`: append-only, ordered by `recordedAt`, `supersedes` naming the latest record, and **only the contact's own opt-in lifts a contact's revoke**. A single marketing send names `consentRef`; a batch is checked per recipient at execution, and a recipient without a granted record is skipped and counted, never sent (`EML-004`). Channel `email` is not yet in DSC-022's channel enum: adding it is a one-value change to that schema, made by whichever of DSC-022 and DSC-025 merges second (Q-728). Mapping:
- One-click or body-link unsubscribe: a revoke with `revokedBy: contact_request`.
- Complaint (the recipient pressed "spam"): a revoke with `revokedBy: provider_block`.
Transactional mail needs no marketing consent; its basis is the tenant's contract with the customer (lawful basis per market UNVERIFIED, LEG-003).

## 7. Suppression list (`kind: suppression_entry`)
Seshna's list is authoritative; the provider's list is synced (`providerSync`) where `suppressionApi` is true, and never trusted alone. For example SES suppresses only hard bounces and complaints on its account list, and Gmail sends SES no complaint data ([SES account-level suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html), accessed 2026-11-27).
| Reason | Scope | When | Lifted by |
|---|---|---|---|
| `hard_bounce` | `all` | At once, from the verified event | `address_reverified` (a tenant user records a corrected, re-verified address) |
| `soft_bounce_repeated` | `all` | After 3 soft bounces in 72 hours (placeholder, Q-729) | `address_reverified` |
| `complaint` | `all` | At once | `contact_opt_in` only |
| `unsubscribe` | `marketing` | At once (RFC 8058 POST, body link, or provider event) | `contact_opt_in` only |
| `manual` | either | A tenant user adds it | A tenant user |

Entries are append-only: a lift is a new entry with `state: lifted`, `supersedes` the active one, `liftBasis` and `liftedBy`. A complaint or unsubscribe lift must name `liftConsentRef` (the contact's new opt-in, `capturedBy: contact`, later than the suppression) and `liftedBy` a contact id (`ctc_`), never a tenant user (schema). A send to a suppressed recipient is refused at execution (`EML-005`). Suppression entries are kept while the contact exists plus the audit minimum.

## 8. Send request (`kind: send_request`)
Tool `email.send_transactional` (AP-EML-01 proposed) or `email.send_campaign` (AP-EML-02 proposed). Every send carries `idempotencyKey` (ULID, Tool API section 6), `connectionRef`, `senderDomainRef`, `fromLocalPart` and `fromDomain`, `purpose`, `mode` (`single` with `contactRef`, or `campaign_batch` with `batch`: `batchId`, `segmentRef`, `recipientCount`, `recipientSetHash`, recomputed at execution), `country`, `templateId`, `language` (`ar` or `en`), capped `params`, `tracking`, `sandbox` and `payloadHash` (sha256 of the canonical send without `payloadHash`, `confirmationId`, `approvalId` and `sentBy`; recomputed at confirmation and execution, a mismatch voids both, as in DSC-022).

**Who sends.** `origin` is `human` or `agent_draft`; both need `sentBy` (a `usr_` id) and `confirmationId` (the gesture over the rendering of `payloadHash`); an agent draft names `draftedBy` (`agt_`). There is no auto-send.

**Risk class: interim.** Every send reaches a person outside the tenant, so none is R1 (action-policy section 4). Until SEC accepts AP-EML rows, `riskClass` is `R3` (fail closed, Q-726). **Marketing** is R3 with `origin: human` and a required `approvalId` (never null), exactly as DSC-022's marketing templates: never agent-created, not even as a draft. Transactional sends may be agent-drafted; a human confirms each.

**Unsubscribe headers (marketing, required).** Per [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html) (accessed 2026-11-27):
- `List-Unsubscribe` with one HTTPS URI (`headers.listUnsubscribe`, pattern `https://<host>/u/<opaque token>`); a mailto URI is optional (`listUnsubscribeMailto`).
- `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (`headers.listUnsubscribePost`, const).
- Both headers covered by the DKIM signature and listed in its `h=` tag (`dkimSignsUnsubscribeHeaders: true`); without it receivers should not offer one-click.
- `bodyUnsubscribeLink: true`: a visible link in the body (Gmail and Yahoo, section 4). Missing or wrong: `EML-006`.

The token is random (at least 128 bits), one per send and recipient, stored hashed. The endpoint accepts an HTTPS POST whose body is `List-Unsubscribe=One-Click`, needs no cookie or login, **never redirects** (RFC 8058: a redirect can turn the POST into a GET), answers 200 and applies the unsubscribe at once (well inside Yahoo's 2 days). It is an untrusted inbound surface: it can only unsubscribe the one recipient its token names, records a `delivery_event` with scheme `one_click_token`, and is rate-limited. A GET shows a confirmation page and changes nothing.

## 9. Open and click tracking (off by default)
Both off for every tenant until a tenant admin opts in per connection (`trackingEnabled`, `trackingPolicyRef`). Transactional mail is never tracked (schema). When enabled:
- **Clicks** rewrite links to our redirect with a `linkId`; the event keeps `linkId`, never the URL or query.
- **Opens** use a tracking pixel, which reads the recipient's device. No pixel is inserted for a recipient in a country whose pack requires consent for tracking, unless the contact holds a granted tracking consent. Whether PDPL (KSA, Qatar), UAE PDPL or Egypt's law requires consent for open tracking is UNVERIFIED pending counsel (LEG-012); until answered, all four phase-1 countries count as consent-required (fail closed, `EML-010`).
- Open counts are noisy (image proxies and privacy features open mail automatically; UNVERIFIED for any figure) and never drive a deterministic decision on their own (BPL-066 decides A/B winner rules).

## 10. Rate limits and warm-up
Sends are paced by the connection's `rateLimit` (below the provider's own quota) and by tenant budget caps (`EML-007`, retry after the window). A new connection or sender domain starts in `warmup.state: warming` with `marketingDailyCap` (placeholder schedule: 50 a day, doubling daily while complaint rate stays below 0.1% and hard-bounce rate below 2%; Q-729). Transactional mail is not capped by warm-up. At or above a 0.3% complaint rate (the Gmail and Yahoo ceiling, section 4) campaign sends on the connection pause and the Owner is alerted.

## 11. Error codes
| Code | Meaning | Retry |
|---|---|---|
| `EML-001` | Webhook signature, basic auth, token or source IP check failed | no |
| `EML-002` | Unknown or unbound endpoint or connection | no |
| `EML-003` | Sender domain not verified (SPF, DKIM, DMARC alignment) or From domain mismatch | no |
| `EML-004` | No granted email marketing consent for this contact and country | no |
| `EML-005` | Recipient suppressed for this purpose | no |
| `EML-006` | Marketing send without valid RFC 8058 headers or body unsubscribe link | no |
| `EML-007` | Rate, warm-up or tenant budget cap reached | after the window |
| `EML-008` | Provider refused or failed the send | per provider code, with backoff |
| `EML-009` | Content refused by the outbound filter (engine name, secret pattern, unapproved link) | no |
| `EML-010` | Tracking not allowed (tenant not opted in, or consent-required country without tracking consent) | no |
| `EML-011` | Provider account already bound to another tenant | no |
| `EML-012` | Sandbox connection, recipient not on the test allowlist | no |
| `EML-013` | Unknown webhook event type (dropped, alerted, audited) | no |
| `EML-014` | A ref (secret, connection, domain, contact, consent, segment, template) belongs to another tenant | no |
| `EML-015` | Staged secret modified or fingerprint mismatch at apply | no; stage again |
| `EML-016` | Provider not supported in this version (no verified webhook scheme) | no |

## 12. Tenancy, secrets, data class and audit
- **Tenancy.** A connection and its provider account bind to one tenant (`EML-011`). Every ref resolves inside the object's tenant (`EML-014`).
- **Secrets** ([secrets-management](../docs/security/secrets-management.md)): API keys are S11, readable only by that tenant's email send job; webhook verification material is S13, readable only by the receiving endpoint, which never reads S11. Both are C4: never in the Blueprint, events, logs, prompts or errors.
- **Data class** ([data-classification](../docs/security/data-classification.md)): recipient addresses and contact refs are C2 with the PD tag; rendered email bodies are C2 + PD, kept by the provider and by us only as long as the transcript class in [data-retention](../docs/security/data-retention.md) allows (placeholder: shortest until counsel sets it); templates are C2. The suppression list is C2 + PD, stored as keyed hashes. Event data is `personal` and carries no address, subject line or body.
- **Proposed action-policy rows (for SEC, Q-726):** AP-EML-01 transactional send to one contact (R3, human submits, agent may draft); AP-EML-02 marketing campaign or single marketing send (R3, human submits, approval required, never agent-drafted); AP-EML-03 connect or rotate a provider (R4, a second Owner or admin, step-up, as AP-PAY-04); AP-EML-04 enable open or click tracking (R4, Owner, step-up).
- **Audit.** Every send and every webhook writes an audit record with the Tool API section 8 fields plus `purpose`, `mode`, `templateId`, `consentRef` or `batch`, `sentBy`, `draftedBy`, `confirmationId`, `approvalId`, `payloadHash`, `tracking`, and for webhooks `scheme`, `providerEventId` and `dedupKey`.
- **Events** (contract 4, [events.md](events.md) "Email events"): `email.send_requested`, `email.delivered`, `email.bounced`, `email.complained`, `email.unsubscribed`, `email.opened`, `email.clicked`, `email.suppressed`, `email.suppression_lifted`, `email.webhook_rejected`.

## 13. Sandbox rules
`environment: sandbox` connections use the provider's test or sandbox mode, synthetic contacts and data only (RULES 46). Every send names `testAllowlistRef` and goes only to addresses on that per-tenant allowlist (`EML-012`); a live send names none. A sandbox connection never runs in a production site class (schema). Customer sender domains, DNS records and provider production access (for example leaving the SES sandbox) are go-live items, not build items (ADR-0076 item 12).
