# Payments connector

Version: 0.1.0
Status: draft
Owner: eldon

How Seshna talks to a company's own payment gateway. Decision: [ADR-0077](../docs/decisions/ADR-0077-payments-connector-bring-your-own-gateway.md) (Proposed). It extends the [connector interface](connector-interface.md): a payments connector is a tier 1 connector with `writes: true`, and every rule of that interface's section 3 applies. Schema: [connector-payments.schema.json](connector-payments.schema.json); examples `examples/payments-*.json`, negative examples `examples/invalid/payments-*.json`.

Gateways named here are the ones whose webhook schemes this contract models (section 5.2), each with its source and access date. That they operate in the four markets, and the payment methods they offer, are UNVERIFIED and decided per adapter (Q-693). The `capabilities-*-shape` examples model only the webhook scheme; their other fields are illustrative.

## 1. Ground rules
1. **Bring your own gateway.** The company's own gateway account; Seshna has no merchant account and never holds funds.
2. **No card data.** v1 has one checkout mode, `hosted_redirect`: the payer leaves for the gateway's hosted page. Embedded gateway fields (`hosted_fields`) are deferred until after v1: PCI SSC FAQ 1588 makes a merchant page that embeds a provider's payment form keep it safe from script attacks (techniques like PCI DSS 6.4.3 and 11.6.1), and that page would be ours (https://www.pcisecuritystandards.org/faqs/1588/, accessed 2026-11-27). Those controls (CSP, SRI, a script inventory and change detection on the page) are a later ADR. Charging stored or gateway-issued tokens is out of v1 too (ADR-0077 item 2). `additionalProperties: false` everywhere.
   - **Seshna ids (`ref`).** A validated UUID (8-4-4-4-12 hex, version 1 to 8, RFC variant), as [tool-api](tool-api.md) section 6 requires for idempotency keys, is accepted as is. Any other id must start alphanumeric and refuses 13 or more digits, even with runs of `- : . _` between them; ULIDs pass this rule (a test checks 20,000 random UUIDv4, UUIDv7 and ULID values).
   - **Gateway ids (`gateway_ref`)** are namespaced, `<provider>:<id>` (`examplepay:1234567890123`), and may be numeric.
   - **What the schema cannot guarantee.** A numeric gateway id cannot be told from a PAN by a pattern, and free text is not schema-checked. So code checks every string before it is persisted or logged (`PAY-DATA-001`): after removing spaces and `- : . _`, a 13 to 19 digit run that starts 2 to 6 (BIN-shaped) and passes Luhn is refused. A validated UUID keeps its dashes for this check, so its groups never merge. On a gateway ref, the delivery is kept unapplied, the payment stays in its last verified state, Finance and the Owner are alerted, and a human allocates the payment by hand (section 11). The schema alone never proves "no card data".
3. **Amounts** are `{"minor": <integer up to 2^53-1>, "currency": "<ISO 4217>"}`. A JSON number with a fraction or exponent (`10.0`, `1e3`) is never an integer (parsers load it as a decimal and refuse it). Currency is checked in code against the ISO 4217 table (DSC-023 pins its version); the schema refuses `XXX`, `XTS` and the metal and fund codes. Minor units follow ISO 4217: SAR, AED, EGP and QAR have 2; KWD, BHD and OMR have 3 (ISO 4217 list one, published 2026-09-17 by SIX, https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml, accessed 2026-11-27). Amounts come from deterministic code reading the invoice or order; never from the model and never from the gateway.
   - **Decimal strings for the approval hash** ([action-policy](../docs/security/action-policy-table.md) section 5). With exponent `e`: the integer part of `minor / 10^e`, then `.`, then the remainder left-padded to `e` digits; no point when `e` is 0; no sign, exponent or grouping. Examples: 12345 SAR is `123.45`, 5 KWD is `0.005`, 7 JPY is `7`. Integer arithmetic only.
   - **Into minor units.** A decimal source amount (an invoice's outstanding balance) with a non-zero digit beyond `e` is refused (`PAY-AMT-003`), never rounded. Trailing zeros beyond `e` are dropped.
4. **Untrusted.** Every string a gateway returns is `trust: "untrusted"` data, shown to the model only as quoted data.
5. **Fail closed.** On any doubt the payment stays unpaid and an error is raised (section 7).

## 2. Provider capability declaration (`kind: "capabilities"`)
Each adapter extends `describe()` with a capability record. The platform refuses an adapter whose record does not validate or declares `card_data: "raw"` (`PAY-CAP-001`).

| Field | Meaning |
|---|---|
| `provider` | Adapter id, dotted (`payments.moyasar`) |
| `adapter_version` | Semver of the adapter |
| `checkout_modes` | `hosted_redirect` only in v1 (section 1.2) |
| `card_data` | Always `none` |
| `methods` | Subset of `card`, `mada`, `apple_pay`, `google_pay`, `stc_pay`, `bank_transfer`, `wallet` |
| `currencies`, `countries` | ISO 4217 codes; ISO 3166 alpha-2 from `SA`, `AE`, `EG`, `QA` |
| `refunds` | `full`, `partial` or `none`; `voids` boolean |
| `key_mode_check` | How a key's test or live mode is proven at connect: `probe` (the account probe reports the mode), or `key_prefix` only where the provider documents distinct test and live key formats and its probe cannot report the mode. The account probe runs either way (section 4.4) |
| `webhook` | `scheme` and `signature_location` (section 5.2), `verifier` (`payments_job` only for `hmac_sha256_selected_fields`, else `receiver`), `replay_window_s` (30 to 600, only for `hmac_sha256_signed_timestamp`), `event_id_source` (or null), `retry_period_s` (the provider's stated retry period, or null when unknown), `dedupe_retention_days` (section 5.5; at least 35 when the retry period is unknown), `status_reread` (always `true`) |
| `sandbox` | Must be `true`: a sandbox exists and the adapter's tests run against it |

## 3. Create checkout session (`kind: "checkout_request"`)
Tool `payment.create_checkout`, risk **R3** (money movement), row `AP-PAY-01` of the [action-policy table](../docs/security/action-policy-table.md) (proposed; refund `AP-PAY-02`, void `AP-PAY-03`, connect `AP-PAY-04`, posting `AP-PAY-05`).

| Field | Rule |
|---|---|
| `idempotency_key` | Required; a reused key with other arguments is `idempotency_conflict`; the same key returns the existing checkout |
| `connection_id` | Required; the tenant's gateway connection, which fixes provider and environment |
| `links` | One or more distinct `{entity, id}` of `sales_invoice` or `sales_order` only; a duplicate link is refused. The amount is the sum of their outstanding balances computed by code |
| `amount` | Minor units and currency, recomputed by the gateway service; a caller value that differs is refused (`PAY-AMT-001`) |
| `mode` | `hosted_redirect` |
| `return_path` | A relative Seshna path (`/pay/return/...`); never a caller-supplied absolute URL |
| `expires_in_s` | 300 to 86400 |

There is no `environment` field: it comes from the connection (section 9), and a request carrying one is refused. The response carries `checkout_id`, the gateway's `hosted_url` (https, host on the adapter's allow-list) and `expires_at`. The payer's details are entered only on the gateway's page.

**One payable session per link.** Before creating a checkout for a link that has an open (unexpired, unpaid) session, the service cancels each older session at the gateway, re-reads it and marks it `cancelled` (`payment.checkout_cancelled`). If a cancellation cannot be confirmed, the new checkout is refused (`PAY-CHK-001`). A capture that still arrives on a cancelled session is recorded (section 5.6).

**Who may prepare it.** An agent may prepare only a draft `checkout_request` that a human reviews and submits (AP-PAY-01 "Draft only"). An agent can never create, draft or submit a refund, void, connect or ledger posting: those tools are `agent_creatable: false` and the evaluator refuses any agent-origin draft for AP-PAY-02 to AP-PAY-05.

**Return page.** `/pay/return/<id>` shows only the status of the server-side payment record after section 5 (or a fresh re-read); it ignores every query or redirect parameter, never marks a payment paid and never issues a receipt from them. Until verified it shows "processing".

## 4. Refund, void and connect
### 4.1 Refund and void (`kind: "refund_request"`)
Tools `payment.refund` and `payment.void`, risk **R4**: always a second, different, eligible human approver, approval expiry one hour, step-up. Fields: `idempotency_key`, `payment_id`, `action` (`refund` or `void`), `basis` and `amount` (both required for `refund`, absent for `void`), `reason_code` (`duplicate`, `customer_request`, `fraud_suspected`, `order_cancelled`, `over_collected`, `other`), `approval_id` (required).
- **Basis `credit_note`** refunds money that settled an invoice: `links` names the credit notes it settles (credit notes only); valid from `captured` or `refunded_partial`.
- **Basis `unallocated`** refunds money that settles nothing: an over-collection, an amount mismatch or a cancelled order's prepayment (state `unallocated`, section 5.6). It needs no credit note and carries no `links`; the amount is at most the unallocated balance.
- **Void** is valid only from `authorised` (`PAY-STATE-001`). While a dispute is open, refunds and voids are refused (`PAY-STATE-001`).

### 4.2 Reservation, currency and outcome
- **Reservation.** In one transaction the service locks the payment, checks `amount` is at most the basis balance (captured or unallocated) minus refunded minus pending reservations (`PAY-REFUND-001`), and records the reservation with `payment.refund_requested`. Concurrent refunds cannot exceed the balance.
- **Currency** equals the payment's (`PAY-AMT-001`).
- **Idempotency.** Same key with other arguments is `idempotency_conflict`. The key is forwarded to the gateway's idempotency header or reference; after a timeout the service re-reads by that key before any retry and never retries with a new key.
- **Outcome.** Only a gateway-reported failure releases the reservation (`payment.refund_failed`). A timeout or unknown outcome is not a failure: the refund stays pending with its reservation, and the re-read and the sweep (section 5.7) settle it to `payment.refunded` or `payment.refund_failed`.

### 4.3 Approval binding (all payment rows)
The approval named by `approval_id` holds the payload hash of [action-policy](../docs/security/action-policy-table.md) section 5, over its full fixed set: tenant id, action id and action version, table version, initiator user id, idempotency key, target record ids with the revision of each (read from the records, never from the request), and amount and currency as decimal strings (section 1.3). Extra binding fields per row:
- AP-PAY-01: connection id, link ids and revisions, expiry.
- AP-PAY-02: payment id and revision, basis, credit note ids and revisions (basis `credit_note`), reason code.
- AP-PAY-03: payment id and revision, authorised amount, reason code.
- AP-PAY-04: connection id and revision (0 for new), provider, environment, `merchant_ref`, `probe_id`, and each staged secret's slot, staged id and fingerprint.
- AP-PAY-05: payment id and revision, each link with its revision and allocated amount, currency, receipt account.

At execution the service recomputes the hash from this request, the current records and the session's tenant. It refuses (approval voided, `permission_denied`) when:
- the hash differs, or the approval is expired, consumed or voided;
- the action or table version is no longer current;
- the approver is the initiator (SOD-DIFF);
- the draft came from an agent and the approver owns or configured that agent (SOD-NOT-AGENT-OWNER, AP-PAY-01 above its limit; agents cannot draft the other rows);
- the approver no longer holds the approving role;
- the approval's step-up result (recorded beside the hash) is not a pass. R3 and R4 approvals need step-up at the approval moment.

### 4.4 Connect (`kind: "connect_request"`)
Tool `payment.connect_gateway`, R4 (`AP-PAY-04`), bound as in 4.3. The environment is fixed per connection; a different environment is a new connection.
1. **Stage.** The Owner types the gateway API key, and the webhook secret where the scheme uses one, into a write-only field. Each value goes straight into a write-once staging slot in the secret store (`.../payments/staged/<staged_id>`), which can never be updated; a new value is a new staged id. The service returns the staged id and the fingerprint (`sha256:` over the value). For `body_secret_token` Seshna generates the token (at least 128 random bits) and the Owner pastes it into the gateway's dashboard.
2. **Probe.** The payments job uses the staged key to call the provider's account endpoint, read-only. The probe record (`probe_id`) holds the account id and, where reported, the key mode. `merchant_ref` is copied from the probe, never typed. A mode that differs from the declared `environment`, an unknown key format or a failed probe refuses the connection (`PAY-ENV-001`).
3. **Ownership.** Only after the probe has proven that the key controls the account does the service check that the account is not connected to another tenant (`PAY-CRED-002`). An unproven `merchant_ref` can never block another tenant. A proven duplicate also alerts the platform security on-call: two tenants holding keys to one account is a shared or leaked key.
4. **Approve and apply.** The approval binds the staged ids and fingerprints. At apply the service checks each staged slot is unmodified and still matches its approved fingerprint, re-runs the probe and compares the account id. It then moves the secrets to their live paths (section 8) and deletes the staging slots. Any difference refuses the apply; nothing can be swapped between approval and apply.

## 5. Webhook verification (in this order, all before using the body as data)
### 5.1 Ingress and tenant binding
- **Ingress limits.** Body cap 64 KiB (413 before any parsing), with the same cap after decryption, and a rate limit per endpoint id and per source address (429). These are counted as platform metrics, not one audit row each.
- **Tenant binding.** The webhook URL carries an opaque endpoint id (`/hooks/pay/whk_<at least 22 base62 characters, 128 random bits or more>`), mapped in the control plane to one tenant and one gateway connection. Unknown id: 404 and a platform counter only; no tenant audit row and the id is not stored.

### 5.2 Authenticity, per scheme
Compared in constant time. Failure: `PAY-HOOK-001`, dropped.

| `scheme` | Gateway (source, accessed 2026-11-27) | Check | Replay |
|---|---|---|---|
| `hmac_sha256_signed_timestamp` | Stripe ([docs](https://docs.stripe.com/webhooks)) | Header `Stripe-Signature`: `t` and every `v1`; HMAC-SHA256 with the endpoint secret over `t`, `.` and the raw body; other entries ignored | Signed timestamp |
| `aes256gcm_encrypted_body` | HyperPay ([docs](https://hyperpay.docs.oppwa.com/tutorials/webhooks)) | The body is hex AES-256-GCM ciphertext; IV in `X-Initialization-Vector`, tag in `X-Authentication-Tag`; 256-bit key from the webhook secret. A tag failure is `PAY-HOOK-001`; the plaintext is parsed only after the tag verifies | Unprotected |
| `hmac_sha256_selected_fields` | Tap ([docs](https://developers.tap.company/docs/webhook)) | Header `hashstring`: HMAC-SHA256 over `x_id`, `x_amount`, `x_currency`, `x_gateway_reference`, `x_payment_reference`, `x_status` and `x_created` (invoices: `x_updated` in place of the two references), with the amount at the currency's decimals. The key is the secret API key, so the receiver never checks it: it verifies ingress and binding, then queues the raw body for the payments job, which verifies the hashstring before reading any other field (`verifier: payments_job`) | Unprotected |
| `body_secret_token` | Moyasar ([docs](https://docs.moyasar.com/api/other/webhooks/webhook-reference)) | Field `secret_token` in the JSON body equals the stored token. The body is parsed strictly under the cap, and no other field is read before the compare. Nothing else in the body is authenticated | Unprotected |

**Unsupported in v1:** PayTabs (its callback signing was not found in the support article read, https://support.paytabs.com/en/support/solutions/articles/60000711358-what-is-response-url-vs-ipn-url-, accessed 2026-11-27; UNVERIFIED), and every other gateway until its scheme is added to this table by a contract change. The old generic `secret_token` header, `rsa_sha256` and `ed25519` entries are removed because no named gateway uses them.

### 5.3 Replay
Only `hmac_sha256_signed_timestamp` has the timestamp inside the signed material; it must be inside `replay_window_s` (`PAY-HOOK-002`). Every other scheme is marked unprotected: a timestamp in a header or in an unsigned or transaction field proves nothing about delivery time. A replay there is harmless only because the re-read status is applied (5.4) and an applied change is never applied twice (5.5). HyperPay's 30-day retries (5.5) therefore pass, since no window applies.

### 5.4 Status re-read
Before every status change (any state), the service re-reads the payment and its refunds and disputes from the gateway API with the tenant's key. It applies the re-read status, never the webhook's, and checks amount, currency, the `checkout_id` it issued and the environment. A dedupe marker never skips the re-read. If the re-read fails, nothing changes and no marker is written (`PAY-GW-001`); the receiver answers 5xx so the gateway retries, and the sweep (5.7) also covers it.
- **Mismatch with money captured** (amount, currency, checkout or another tenant's metadata, `PAY-AMT-002`): the payment moves to `unallocated` (`payment.held_unallocated`, reason `amount_mismatch`) and Finance and the Owner are alerted. Nothing is applied to the links.
- **Mismatch with no money captured:** the payment stays in its last verified state and `payment.reconciliation_mismatch` (`PAY-AMT-002`) alerts a human. A mismatch never becomes `payment.failed`.

### 5.5 Dedupe and idempotent apply
- **Dedupe key.** The gateway event id from `event_id_source`. When there is none: provider object id plus status plus amount, from the authenticated body; never a body hash alone. HyperPay's guidance is the same: transaction id and status.
- **Commit point.** The marker check is a read. The marker is written in the same database transaction as the apply. When the re-read shows nothing new, the marker is written after the successful re-read. A failed re-read or apply writes no marker. A duplicate is acknowledged (`PAY-HOOK-003`) only after its re-read showed nothing new.
- **Retention.** `dedupe_retention_days` is at least max(7, the provider's retry period plus 5 days); with an unknown period, at least 35. HyperPay retries daily for up to 30 days (docs above), so 35 days. Moyasar retries five times over about two hours (docs above), so 7. Stripe retries for up to three days in live mode (docs above), so 8. Tap's period is not stated (UNVERIFIED), so 35.
- **Apply keys.** A status change applies once per `(connection, gateway_payment_ref, status)`. A refund (Seshna's or external) applies once per `(connection, gateway_refund_ref)` with its amount. So a second partial refund is a new key: it applies, updates the balance and the reservation, and emits `payment.refunded`, even though the status stays `refunded_partial`. A known refund id with a different amount is `PAY-AMT-002` (human).

### 5.6 States and transitions
States: `created`, `authorised`, `captured`, `unallocated`, `refunded_partial`, `refunded`, `failed`, `expired`, `voided`, `cancelled`. A dispute is a flag on the payment, not a state. Every move needs the re-read, except the two moves marked human or code. Moves not listed are refused (`PAY-STATE-001`).

| From | To | When |
|---|---|---|
| `created` | `authorised`, `captured`, `failed`, `expired`, `cancelled` | Re-read; `cancelled` when a newer checkout replaces the session (section 3) |
| `failed`, `expired` | `authorised`, `captured` | The re-read shows a later successful attempt on the same session (a payer retry) |
| `cancelled` | `captured` | A capture on a cancelled session whose links are all still open; any newer open session on those links is then cancelled |
| `authorised` | `captured`, `voided`, `expired` | Re-read; a void by AP-PAY-03 or made in the gateway dashboard |
| any of the above | `unallocated` | A capture on links already settled (`over_collected`), or a mismatch with money captured (`amount_mismatch`) |
| `captured`, `refunded_partial` | `unallocated` | Code: a linked sales order is cancelled before it is invoiced (`order_cancelled`) |
| `captured`, `refunded_partial` | `refunded_partial`, `refunded` | Each new gateway refund id (5.5) |
| `unallocated` | `unallocated`, `refunded` | Each new gateway refund id; `refunded` when the unallocated balance reaches zero |
| `unallocated` | `captured` | Human: the balance is allocated to open links and posted (AP-PAY-05, section 11) |

- **Refunds and voids made in the gateway dashboard** are found by the re-read, the sweep or reconciliation. The money has already moved, so they are applied with `origin: "external"`. Finance and the Owner are alerted; the ledger effect (a credit note or adjustment) is posted by a human through the normal finance path, never automatically.
- **Chargebacks and disputes.** `payment.disputed` (`opened`, `won`, `lost`) alerts Finance and the Owner at once. While a dispute is open, refunds and voids are refused. A lost dispute's reversal is applied like a refund, keyed by the gateway's dispute id, with `origin: "chargeback"`; its ledger effect is posted by a human.

### 5.7 Sweep for missed webhooks
A deterministic poller re-reads, with the same rules as 5.4 to 5.6:
- every payment in `created`, `authorised`, `failed`, `expired` or `cancelled`, every 5 minutes until its checkout expiry plus 1 hour, then hourly for 72 hours;
- every pending refund, every 5 minutes for 1 hour, then hourly until settled, with a human alert after 24 hours;
- every `captured`, `refunded_partial` or `unallocated` payment once a day for 30 days, which catches dashboard refunds and disputes whose webhooks were lost.

After that, settlement reconciliation (section 10) catches the rest. These intervals are design values for the partner to accept.

## 6. Payment-status events
Contract 4 types, `data_class: "financial"`, emitted by the gateway service only after section 5 passed. `data`: `payment_id`, `checkout_id`, `links`, `amount`, `provider`, `environment`, `gateway_payment_ref` (namespaced, opaque; optional only on the two checkout events, before the gateway has one). Never payer names, card fragments or gateway free text. Shape: `kind: "payment_event"` in the schema; registered in `services/blueprint/events/schemas/types.json` with the `payment` domain reserved, so no engine record event can claim it.

| Type | Extra data | Error codes allowed |
|---|---|---|
| `payment.checkout_created`, `payment.checkout_cancelled` | - | - |
| `payment.authorised`, `payment.captured`, `payment.expired` | - | - |
| `payment.failed` | `failure_code` | `PAY-GW-002` (declined) |
| `payment.held_unallocated` | `unallocated_reason` (`amount_mismatch`, `over_collected`, `order_cancelled`) | - |
| `payment.refund_requested` | `refund_id`; `gateway_refund_ref` once known | - |
| `payment.refunded` | `refund_id`, `gateway_refund_ref`, `origin` (`seshna`, `external`, `chargeback`); `amount` is the refund's | - |
| `payment.refund_failed` | `refund_id`, `failure_code` | `PAY-GW-002` |
| `payment.voided` | `origin` | - |
| `payment.disputed` | `dispute_status` | - |
| `payment.webhook_rejected` | `endpoint_id`, `error_code`; no `payment_id`, `checkout_id`, `links`, `amount` or gateway ref, no body | `PAY-HOOK-001`, `PAY-HOOK-002`, `PAY-ENV-001`, `PAY-DATA-001` |
| `payment.reconciliation_mismatch` | `error_code`; optional `payment_id`, `gateway_payment_ref`, `amount` | `PAY-AMT-002`, `PAY-RECON-001`, `PAY-DATA-001` |

## 7. Error codes
Tool API codes stay as in [tool-api](tool-api.md) section 7; payment failures add a `domain` block with these codes.

| Code | Meaning | Retryable |
|---|---|---|
| `PAY-CAP-001` | Adapter capability record invalid or not card-data-free | no |
| `PAY-CRED-001` | No gateway credential for this tenant and environment, or the connection is disabled | no |
| `PAY-CRED-002` | Probe-proven gateway account already connected to another tenant | no |
| `PAY-CHK-001` | An older open checkout on this link could not be cancelled | no |
| `PAY-DATA-001` | A card-number-shaped value reached the service | no |
| `PAY-AMT-001` | Caller amount or currency differs from the computed one | no |
| `PAY-AMT-002` | Gateway amount, currency, checkout, environment or refund amount differs | no (human) |
| `PAY-AMT-003` | A decimal source amount has more precision than the currency's exponent | no |
| `PAY-HOOK-001` | Webhook signature, tag or token missing or invalid | no |
| `PAY-HOOK-002` | Signed webhook timestamp outside the replay window | no |
| `PAY-HOOK-003` | Webhook already processed, and its re-read showed nothing new (acknowledged) | no |
| `PAY-STATE-001` | Status move not allowed from the current state, or refused while a dispute is open | no |
| `PAY-REFUND-001` | Refund exceeds the refundable balance | no |
| `PAY-GW-001` | Gateway timeout or 5xx; the payment stays in its last verified state | yes, with backoff |
| `PAY-GW-002` | Gateway declined (reason code kept, gateway text untrusted) | no |
| `PAY-ENV-001` | Sandbox and live mixed, or key mode not proven (section 9) | no |
| `PAY-RECON-001` | Settlement line unmatched (section 10) | no (human) |

## 8. Tenancy binding, secrets and audit
- Tenant id comes from the authenticated session or, for webhooks, from the endpoint id map; never from a request or webhook body ([tenancy](../docs/architecture/tenancy-and-identity.md)). A gateway payment whose metadata names another tenant's checkout is `PAY-AMT-002`.
- **API keys** (refund-capable) are class S11 at `{env}/tenant/{tenantId}/payments/{connection}/api_key`, readable only by that tenant's payments job identity.
- **Webhook verification secrets** are class S13 at `{env}/tenant/{tenantId}/payments/{connection}/webhook`, readable only by the receiving endpoint. The receiver never reads S11. Tap has no separate secret (5.2), so its webhooks are verified by the payments job. Neither class appears in events, logs, prompts, errors or the Blueprint ([secrets management](../docs/security/secrets-management.md)).
- **Rotation.** Seshna cannot rotate a key it does not issue. The customer's Owner creates a new key in the gateway's dashboard and reconnects (AP-PAY-04 with new staged secrets). Seshna reminds the Owner and Finance at 80 days. Past 90 days, or after a staff change, refunds and voids on the connection are refused (`PAY-CRED-001`) until it is rotated. A planned webhook secret rotation may keep the old secret for at most 24 hours.
- **Exposure.** On suspected exposure of either secret, Seshna disables the connection at once, with no grace period: the old secret stops verifying immediately, and missed webhooks are recovered by gateway retries and the sweep. Seshna alerts the Owner, who revokes the key at the gateway and reconnects.
- **Audit.** Every tool call writes the tool-api section 8 audit record. Every webhook to a known endpoint, verified or not, writes an audit record: endpoint id, provider event id, verification result, error code, hash of the raw body, and no body. Retention follows audit-class events.

## 9. Test mode and sandbox
- Each connection has `environment` `sandbox` or `live`, declared and proven at connect (section 4.4) and fixed. Every call takes it from the connection, never from the request. Sandbox and live credentials, webhook secrets and endpoint ids are separate. A sandbox webhook on a live connection, or the reverse, is `PAY-ENV-001`.
- Dev and preview hosts accept only sandbox connections and synthetic data (RULES 46): code reads the host class from deployment config and refuses a `live` connection there (`PAY-ENV-001`). Live connections exist only on production tenants after the customer's own gateway account is approved (a go-live item, ADR-0076 item 11).
- Sandbox payments never post to a live ledger; their events carry `environment: "sandbox"`.

## 10. Reconciliation
Deterministic code matches gateway settlement lines (payments, refunds, fees, chargebacks) to payment records and ledger entries by `gateway_payment_ref` and amount. Anything unmatched raises `payment.reconciliation_mismatch` (`PAY-RECON-001`) for a human; nothing is auto-posted to close a gap. Fee and payout posting is open (Q-694).

## 11. Ledger posting (rigid zone)
- **A capture never posts to the ledger by itself.** No webhook, re-read, sweep or reconciliation run posts anything (human floor, [ADR-0027](../docs/decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md)).
- **Draft.** After `payment.captured`, deterministic rigid-zone code (ledger, RULES 21 and 30; never model-written) prepares a draft receipt that allocates the captured amount to the links' outstanding balances. The model never computes or proposes an allocation.
- **Approval.** A human posts it under `AP-PAY-05` (proposed); the risk class is set by deterministic code from the draft (Q-723, Eldon 2026-11-27, partner to confirm):
  - **R3, exact match.** A receipt that exactly matches one open invoice: same tenant, same currency, one sales invoice, allocated in full (not partial), and the allocated amount equals the net captured amount. A human submits it, the same class as posting a sales invoice (`AP-FIN-01`), and it stays human-originated (an agent may not draft it).
  - **R4, anything else.** A partial allocation, several invoices or an order, an over or under payment, an `unallocated` or held payment, or any currency difference: a second, different human approver, step-up, one hour.
  - In both classes a capture never posts by itself; only a human submit posts.
- **Currency.** The payment currency must equal each linked document's currency; any difference refuses the draft (`PAY-AMT-001`). There is no currency conversion in v1. The allocated total equals captured minus refunded, in minor units (section 1.3).
- **Manual allocation.** The same row allocates an `unallocated` payment, or one held by `PAY-DATA-001`, to open links chosen by a human.
