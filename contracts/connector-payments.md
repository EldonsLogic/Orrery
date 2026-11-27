# Payments connector

Version: 0.1.0
Status: draft
Owner: eldon

How Seshna talks to a company's own payment gateway (Moyasar, Tap, HyperPay, PayTabs, Stripe and others). Decision: [ADR-0077](../docs/decisions/ADR-0077-payments-connector-bring-your-own-gateway.md) (Proposed). It extends the [connector interface](connector-interface.md): a payments connector is a tier 1 connector with `writes: true`, and every rule of that interface's section 3 applies. Schema: [connector-payments.schema.json](connector-payments.schema.json); examples `examples/payments-*.json`, negative examples `examples/invalid/payments-*.json`.

## 1. Ground rules
1. **Bring your own gateway.** The company's own gateway account; Seshna has no merchant account and never holds funds.
2. **No card data.** Only the gateway's hosted checkout (redirect or the gateway's own hosted fields) or a gateway-issued token. No field in this contract can carry a PAN, CVV, expiry or track data; `additionalProperties: false` everywhere, and any string matching a card number (13 to 19 digits passing the Luhn check) is refused before storage or logging (`PAY-DATA-001`).
3. **Amounts** are `{"minor": <integer>, "currency": "<ISO 4217>"}`. Minor units follow ISO 4217 exponents (SAR, AED, EGP, QAR: 2; KWD, BHD, OMR: 3). Amounts come from deterministic code reading the invoice or order; never from the model and never from the gateway.
4. **Untrusted.** Every string a gateway returns is `trust: "untrusted"` data, shown to the model only as quoted data.
5. **Fail closed.** On any doubt the payment stays unpaid and an error is raised (section 7).

## 2. Provider capability declaration (`kind: "capabilities"`)
Each adapter extends `describe()` with a capability record. The platform refuses an adapter whose record does not validate or declares `card_data: "raw"` (`PAY-CAP-001`).

| Field | Meaning |
|---|---|
| `provider` | Adapter id, dotted (`payments.moyasar`) |
| `adapter_version` | Semver of the adapter |
| `checkout_modes` | Non-empty subset of `hosted_redirect`, `hosted_fields`, `token` |
| `card_data` | Always `none` |
| `methods` | Subset of `card`, `mada`, `apple_pay`, `google_pay`, `stc_pay`, `bank_transfer`, `wallet` |
| `currencies`, `countries` | ISO 4217 codes; ISO 3166 alpha-2 from `SA`, `AE`, `EG`, `QA` |
| `refunds` | `full`, `partial` or `none`; `voids` boolean |
| `webhook` | `scheme` (`hmac_sha256`, `rsa_sha256`, `ed25519`, `secret_token`), `signature_header`, `timestamp_header` (or null), `replay_window_s` (30 to 600), `status_reread` (always `true`, section 5.4) |
| `sandbox` | Must be `true`: a sandbox exists and the adapter's tests run against it |

`secret_token` (a shared token echoed in a header, no body signature) is the weakest scheme: with it the status re-read (section 5.4) is the only proof of payment.

## 3. Create checkout session (`kind: "checkout_request"`)
Tool `payment.create_checkout`, risk **R3** (money movement), never executed by an agent without human submission ([action-policy table](../docs/security/action-policy-table.md)).

| Field | Rule |
|---|---|
| `idempotency_key` | Required; reused key with other arguments is `idempotency_conflict` |
| `links` | One or more `{entity, id}` of `sales_invoice` or `sales_order`; the amount is the sum of their outstanding balances computed by code |
| `amount` | Minor units and currency, recomputed by the gateway service; a caller value that differs is refused (`PAY-AMT-001`) |
| `mode` | One of the provider's `checkout_modes` |
| `return_path` | A relative Seshna path (`/pay/return/...`); never a caller-supplied absolute URL |
| `expires_in_s` | 300 to 86400 |
| `environment` | `sandbox` or `live` (section 9) |

The response carries `checkout_id`, the gateway's `hosted_url` (https, host on the adapter's allow-list) and `expires_at`. The payer's details are entered only on the gateway's page.

## 4. Refund and void (`kind: "refund_request"`)
Tools `payment.refund` and `payment.void`, risk **R4**: always a second, different, eligible human approver, never agent-creatable (`agent_creatable: false`), approval expiry one hour. Fields: `idempotency_key`, `payment_id`, `action` (`refund` or `void`), `amount` (required for `refund`, at most the captured amount minus earlier refunds, computed by code), `reason_code` (`duplicate`, `customer_request`, `fraud_suspected`, `order_cancelled`, `other`), `approval_id` (required). A refund also needs `links` to the credit note it settles. Connecting or changing a gateway account (credentials, webhook secret) is also R4, its own tool `payment.connect_gateway`.

## 5. Webhook verification (in this order, all before parsing the body as data)
1. **Tenant binding.** The webhook URL carries an opaque endpoint id (`/hooks/pay/<endpoint_id>`), mapped in the control plane to one tenant and one gateway connection. Unknown id: 404, audited, nothing else.
2. **Signature.** Computed over the raw bytes with the tenant's webhook secret and the declared scheme, compared in constant time. Failure: `PAY-HOOK-001`, dropped.
3. **Replay.** Timestamp inside `replay_window_s` (`PAY-HOOK-002`), and the gateway event id not seen before for this connection (`PAY-HOOK-003` is a duplicate: acknowledged, no change). Markers kept at least 7 days.
4. **Status re-read.** Before a payment becomes `captured` or `refunded`, the service re-reads the payment from the gateway API with the tenant's key and checks amount, currency, the `checkout_id` it issued and the environment. Any difference: `PAY-AMT-002`, the payment stays unpaid and a human is alerted.
5. **Idempotent apply.** A state change is applied once, keyed by `(connection, gateway_payment_id, status)`; states only move forward (`created -> authorised -> captured -> refunded_partial -> refunded`, plus `failed`, `expired`, `voided`). A backward move is refused (`PAY-STATE-001`).

## 6. Payment-status events
Contract 4 types, `data_class: "financial"`, emitted by the gateway service only after section 5 passed. `data`: `payment_id`, `checkout_id`, `links`, `amount`, `provider`, `environment`, `gateway_payment_ref` (opaque); never payer names, card fragments or gateway free text. Shape: `kind: "payment_event"` in the schema.

`payment.checkout_created`, `payment.authorised`, `payment.captured`, `payment.failed` (data adds `failure_code` from section 7), `payment.expired`, `payment.refund_requested`, `payment.refunded`, `payment.voided`, `payment.webhook_rejected` (audit, data: endpoint id, error code, no body), `payment.reconciliation_mismatch`.

## 7. Error codes
Tool API codes stay as in [tool-api](tool-api.md) section 7; payment failures add a `domain` block with these codes.

| Code | Meaning | Retryable |
|---|---|---|
| `PAY-CAP-001` | Adapter capability record invalid or not card-data-free | no |
| `PAY-CRED-001` | No gateway credential for this tenant and environment | no |
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
| `PAY-ENV-001` | Sandbox and live mixed (section 9) | no |

## 8. Tenancy binding and audit
- Tenant id comes from the authenticated session or, for webhooks, from the endpoint id map; never from a request or webhook body ([tenancy](../docs/architecture/tenancy-and-identity.md)). A gateway payment whose metadata names another tenant's checkout is `PAY-AMT-002`.
- Credentials live at `{env}/tenant/{tenantId}/payments/{connection}` (S11), readable only by that tenant's payments job identity; never in events, logs, prompts, errors or the Blueprint.
- Every tool call writes the tool-api section 8 audit record; every webhook, verified or not, writes an audit record (endpoint id, provider event id, verification result, error code, hash of the raw body, no body). Retention follows audit-class events.

## 9. Test mode and sandbox
- Each connection has `environment` `sandbox` or `live`, fixed at connect time; sandbox and live credentials, webhook secrets and endpoint ids are separate. A sandbox webhook on a live connection, or the reverse, is `PAY-ENV-001`.
- Dev and preview hosts accept only sandbox connections and synthetic data (RULES 46). Live connections exist only on production tenants after the customer's own gateway account is approved (a go-live item, ADR-0076 item 11).
- Sandbox payments never post to a live ledger; their events carry `environment: "sandbox"`.

## 10. Reconciliation
Deterministic code matches gateway settlement lines (payments, refunds, fees) to payment records and ledger entries by `gateway_payment_ref` and amount. Anything unmatched raises `payment.reconciliation_mismatch` for a human; nothing is auto-posted to close a gap. Fee and payout posting is open (Q-694).
