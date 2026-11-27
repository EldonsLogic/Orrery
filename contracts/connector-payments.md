# Payments connector

Version: 0.1.0
Status: draft
Owner: eldon

How Seshna talks to a company's own payment gateway (Moyasar, Tap, HyperPay, PayTabs, Stripe and others). Decision: [ADR-0077](../docs/decisions/ADR-0077-payments-connector-bring-your-own-gateway.md) (Proposed). It extends the [connector interface](connector-interface.md): a payments connector is a tier 1 connector with `writes: true`, and every rule of that interface's section 3 applies. Schema: [connector-payments.schema.json](connector-payments.schema.json); examples `examples/payments-*.json`, negative examples `examples/invalid/payments-*.json`.

## 1. Ground rules
1. **Bring your own gateway.** The company's own gateway account; Seshna has no merchant account and never holds funds.
2. **No card data.** Only the gateway's hosted page (`hosted_redirect`) or the gateway's own iframe (`hosted_fields`: every payment field is served from the gateway's origin, never a Seshna-served form or script). Charging stored or gateway-issued tokens is out of v1 (ADR-0077 item 2). `additionalProperties: false` everywhere. Ids Seshna issues (`ref`) refuse 13 or more digits even with `- : . _` between them; gateway ids (`gateway_ref`) are namespaced, `<provider>:<id>` (`examplepay:1234567890123`), and may be numeric. **What the schema cannot guarantee:** a numeric gateway id cannot be told from a PAN by a pattern, and free text is not schema-checked. So code checks every string before it is persisted or logged (`PAY-DATA-001`): after removing spaces and `- : . _`, a 13 to 19 digit run that starts 2 to 6 (BIN-shaped) and passes Luhn is refused; on a gateway ref the payment stays in its last verified state and a human is alerted. The schema alone never proves "no card data".
3. **Amounts** are `{"minor": <integer up to 2^53-1>, "currency": "<ISO 4217>"}`. A JSON number with a fraction or exponent (`10.0`, `1e3`) is never an integer (parsers load it as a decimal and refuse it). Currency is checked in code against the ISO 4217 table (DSC-023 pins its version); the schema refuses `XXX`, `XTS` and the metal and fund codes. Minor units follow ISO 4217 exponents (SAR, AED, EGP, QAR: 2; KWD, BHD, OMR: 3). Amounts come from deterministic code reading the invoice or order; never from the model and never from the gateway.
4. **Untrusted.** Every string a gateway returns is `trust: "untrusted"` data, shown to the model only as quoted data.
5. **Fail closed.** On any doubt the payment stays unpaid and an error is raised (section 7).

## 2. Provider capability declaration (`kind: "capabilities"`)
Each adapter extends `describe()` with a capability record. The platform refuses an adapter whose record does not validate or declares `card_data: "raw"` (`PAY-CAP-001`).

| Field | Meaning |
|---|---|
| `provider` | Adapter id, dotted (`payments.moyasar`) |
| `adapter_version` | Semver of the adapter |
| `checkout_modes` | Non-empty subset of `hosted_redirect`, `hosted_fields` (section 1.2) |
| `card_data` | Always `none` |
| `methods` | Subset of `card`, `mada`, `apple_pay`, `google_pay`, `stc_pay`, `bank_transfer`, `wallet` |
| `currencies`, `countries` | ISO 4217 codes; ISO 3166 alpha-2 from `SA`, `AE`, `EG`, `QA` |
| `refunds` | `full`, `partial` or `none`; `voids` boolean |
| `key_mode_check` | How a key's test or live mode is proven at connect: `key_prefix` (the provider's documented test and live key formats) or `probe` (a gateway call that reports the mode) |
| `webhook` | `scheme` (`hmac_sha256`, `rsa_sha256`, `ed25519`, `secret_token`), `signature_header`, `timestamp_header` (null only for `secret_token`), `event_id_source` (or null), `replay_window_s` (30 to 600), `status_reread` (always `true`, section 5.4) |
| `sandbox` | Must be `true`: a sandbox exists and the adapter's tests run against it |

`secret_token` (a shared token echoed in a header, no body signature) is the weakest scheme: with it the status re-read (section 5.4) is the only proof of payment.

## 3. Create checkout session (`kind: "checkout_request"`)
Tool `payment.create_checkout`, risk **R3** (money movement), never executed by an agent without human submission ([action-policy table](../docs/security/action-policy-table.md) row `AP-PAY-01`; refund `AP-PAY-02`, void `AP-PAY-03`, connect `AP-PAY-04`, proposed).

| Field | Rule |
|---|---|
| `idempotency_key` | Required; reused key with other arguments is `idempotency_conflict` |
| `links` | One or more `{entity, id}` of `sales_invoice` or `sales_order` only; at most one open (unexpired, not failed) checkout per link: a second returns the open one or `PAY-CHK-001`. The amount is the sum of their outstanding balances computed by code |
| `amount` | Minor units and currency, recomputed by the gateway service; a caller value that differs is refused (`PAY-AMT-001`) |
| `mode` | One of the provider's `checkout_modes` |
| `return_path` | A relative Seshna path (`/pay/return/...`); never a caller-supplied absolute URL |
| `expires_in_s` | 300 to 86400 |

There is no `environment` field: it comes from the tenant's connection (section 9), and a request carrying one is refused. The response carries `checkout_id`, the gateway's `hosted_url` (https, host on the adapter's allow-list) and `expires_at`. The payer's details are entered only on the gateway's page or iframe.

**Return page.** `/pay/return/<id>` shows only the status of the server-side payment record after section 5 (or a fresh re-read); it ignores every query or redirect parameter, never marks a payment paid and never issues a receipt from them. Until verified it shows "processing".

## 4. Refund and void (`kind: "refund_request"`)
Tools `payment.refund` and `payment.void`, risk **R4**: always a second, different, eligible human approver, never agent-creatable (`agent_creatable: false`), approval expiry one hour. Fields: `idempotency_key`, `payment_id`, `action` (`refund` or `void`), `amount` (required for `refund`), `reason_code` (`duplicate`, `customer_request`, `fraud_suspected`, `order_cancelled`, `other`), `approval_id` (required). A refund also needs `links` to the `credit_note` it settles (credit notes only).
- **Reservation.** In one transaction the service locks the payment, checks `amount` is at most captured minus refunded minus pending reservations (`PAY-REFUND-001`), and records the reservation with `payment.refund_requested`; a failed refund releases it. Concurrent refunds cannot exceed the captured amount.
- **Currency** equals the payment's (`PAY-AMT-001`). A void is valid only from `authorised`, a refund only from `captured` or `refunded_partial` (`PAY-STATE-001`).
- **Idempotency.** Same key with other arguments is `idempotency_conflict`. The key is forwarded to the gateway's idempotency header or reference; after a timeout the service re-reads by that key before any retry and never retries with a new key.
- **Approval binding.** The approval named by `approval_id` holds the payload hash of [action-policy](../docs/security/action-policy-table.md) section 5 (tenant id, action id `AP-PAY-02` or `AP-PAY-03` and its version, payment id, amount, currency, credit note id and revision, idempotency key) and an expiry (one hour). At execution the service recomputes the hash from this request and the session's tenant and refuses (approval voided, `permission_denied`) if it differs, the approval is expired or consumed, or the approver is the requester.

**Connect (`kind: "connect_request"`).** Tool `payment.connect_gateway`, R4 (`AP-PAY-04`), bound the same way. Fields: `idempotency_key`, `connection_id`, `provider`, declared `environment`, `merchant_ref` (the gateway account id), `approval_id`. Keys and webhook secrets are typed into a write-only field that goes straight to the secret store; they are never in the request. Before storing, the adapter proves the key's mode by its `key_mode_check`; a mismatch, unknown format or failed probe refuses the connection (`PAY-ENV-001`, fail closed). One gateway account connects to one tenant only (`PAY-CRED-002`).

## 5. Webhook verification (in this order, all before parsing the body as data)
0. **Ingress limits.** Body cap 64 KiB (413 before any parsing) and a rate limit per endpoint id and per source address (429). These are counted as platform metrics, not one audit row each.
1. **Tenant binding.** The webhook URL carries an opaque endpoint id (`/hooks/pay/whk_<at least 128 random bits>`), mapped in the control plane to one tenant and one gateway connection. Unknown id: 404 and a platform counter only; no tenant audit row and the id is not stored.
2. **Signature.** Computed over the raw bytes with the tenant's webhook secret and the declared scheme, compared in constant time. Failure: `PAY-HOOK-001`, dropped.
3. **Replay.** The timestamp is required for every signed scheme and must be inside `replay_window_s` (`PAY-HOOK-002`). The dedupe key is the gateway event id from `event_id_source`, or, when the gateway sends none, SHA-256 over the canonical body (RFC 8785) plus the provider object id; a key seen before for this connection is `PAY-HOOK-003` (acknowledged, no change). Markers kept at least 7 days. With no timestamp (`secret_token`) the re-read in step 4 is the only proof.
4. **Status re-read.** Before every status change (any state, not only `captured` and `refunded`), the service re-reads the payment from the gateway API with the tenant's key and applies the re-read status, never the webhook's; it checks amount, currency, the `checkout_id` it issued and the environment. Any difference: `PAY-AMT-002`, the payment stays in its last verified state and a human is alerted. If the re-read fails, nothing changes (`PAY-GW-001`, retried). A capture on a link already paid is an over-collection: `PAY-AMT-002`, held as unallocated for a human, refunded only through the R4 path.
5. **Idempotent apply.** A state change is applied once, keyed by `(connection, gateway_payment_id, status)`; states only move forward (`created -> authorised -> captured -> refunded_partial -> refunded`, plus `failed`, `expired`, `voided`). `voided` only from `authorised`. A backward move is refused (`PAY-STATE-001`).

## 6. Payment-status events
Contract 4 types, `data_class: "financial"`, emitted by the gateway service only after section 5 passed. `data`: `payment_id`, `checkout_id`, `links`, `amount`, `provider`, `environment`, `gateway_payment_ref` (namespaced, opaque); never payer names, card fragments or gateway free text. Shape: `kind: "payment_event"` in the schema.

`payment.checkout_created`, `payment.authorised`, `payment.captured`, `payment.failed` (data adds `failure_code` from section 7), `payment.expired`, `payment.refund_requested`, `payment.refunded`, `payment.voided`, `payment.webhook_rejected` (audit for a known endpoint only, data: `endpoint_id`, `error_code`, no body), `payment.reconciliation_mismatch` (data: `error_code`, optional `gateway_payment_ref` and `amount`). These two carry no `payment_id`.

## 7. Error codes
Tool API codes stay as in [tool-api](tool-api.md) section 7; payment failures add a `domain` block with these codes.

| Code | Meaning | Retryable |
|---|---|---|
| `PAY-CAP-001` | Adapter capability record invalid or not card-data-free | no |
| `PAY-CRED-001` | No gateway credential for this tenant and environment | no |
| `PAY-CRED-002` | Gateway account already connected to another tenant | no |
| `PAY-CHK-001` | An open checkout already exists for this link | no |
| `PAY-DATA-001` | A card-number-shaped value reached the service | no |
| `PAY-AMT-001` | Caller amount or currency differs from the computed one | no |
| `PAY-AMT-002` | Gateway amount, currency, checkout or environment differs | no (human) |
| `PAY-HOOK-001` | Webhook signature missing or invalid | no |
| `PAY-HOOK-002` | Webhook timestamp outside the replay window | no |
| `PAY-HOOK-003` | Webhook event already processed (acknowledged) | no |
| `PAY-STATE-001` | Status move not allowed from the current state | no |
| `PAY-REFUND-001` | Refund exceeds the refundable amount | no |
| `PAY-GW-001` | Gateway timeout or 5xx; the payment stays in its last verified state | yes, with backoff |
| `PAY-GW-002` | Gateway declined (reason code kept, gateway text untrusted) | no |
| `PAY-ENV-001` | Sandbox and live mixed, or key mode not proven (section 9) | no |
| `PAY-RECON-001` | Settlement line unmatched (section 10) | no (human) |

## 8. Tenancy binding and audit
- Tenant id comes from the authenticated session or, for webhooks, from the endpoint id map; never from a request or webhook body ([tenancy](../docs/architecture/tenancy-and-identity.md)). A gateway payment whose metadata names another tenant's checkout is `PAY-AMT-002`.
- Credentials live at `{env}/tenant/{tenantId}/payments/{connection}` (S11), readable only by that tenant's payments job identity; never in events, logs, prompts, errors or the Blueprint. Payments keys can move money (refunds), so they are rotated at least every 90 days and at once on suspected exposure or staff change; a webhook secret rotation keeps the old secret valid for at most 24 hours.
- Every tool call writes the tool-api section 8 audit record; every webhook to a known endpoint, verified or not, writes an audit record (endpoint id, provider event id, verification result, error code, hash of the raw body, no body). Retention follows audit-class events.

## 9. Test mode and sandbox
- Each connection has `environment` `sandbox` or `live`, declared and proven at connect (section 4) and fixed; every call takes it from the connection, never from the request; sandbox and live credentials, webhook secrets and endpoint ids are separate. A sandbox webhook on a live connection, or the reverse, is `PAY-ENV-001`.
- Dev and preview hosts accept only sandbox connections and synthetic data (RULES 46): code reads the host class from deployment config and refuses a `live` connection there (`PAY-ENV-001`). Live connections exist only on production tenants after the customer's own gateway account is approved (a go-live item, ADR-0076 item 11).
- Sandbox payments never post to a live ledger; their events carry `environment: "sandbox"`.

## 10. Reconciliation
Deterministic code matches gateway settlement lines (payments, refunds, fees) to payment records and ledger entries by `gateway_payment_ref` and amount. Anything unmatched raises `payment.reconciliation_mismatch` (`PAY-RECON-001`) for a human; nothing is auto-posted to close a gap. Fee and payout posting is open (Q-694).
