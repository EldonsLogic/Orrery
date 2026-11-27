# ADR-0077: Payments connector: bring your own gateway, hosted checkout only, no card data

Status: Proposed
Owner: eldon
Approved by: Eldon 2026-11-27 (proposer); partner pending (review on this PR)

## Context
[ADR-0076](ADR-0076-phase-1-module-scope.md) item 10 adds a payments connector to phase 1 (plan row DSC-021; build DSC-023 at G2). Companies in the four markets hold accounts with their own gateways; the contract models the webhook schemes of Stripe, HyperPay, Tap and Moyasar from each one's documentation (contract section 5.2, sources accessed 2026-11-27). Which gateways operate in which market is UNVERIFIED (Q-693). Payments are money and sit on the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)). The contract is [connector-payments.md](../../contracts/connector-payments.md), Contract 4 gains `payment.*` event types ([events.md](../../contracts/events.md) section 3).

## Decision
1. **Bring your own gateway.** Each company connects its own gateway account. Seshna has no merchant account, is never the merchant of record and never holds, routes or settles funds. Money moves only between the payer, the gateway and the company.
2. **Hosted redirect only in v1.** Seshna creates a checkout session and sends the payer to the gateway's hosted page. Embedding the gateway's own fields in a Seshna page (`hosted_fields`) is deferred until after v1 (item 3). Charging stored or gateway-issued tokens is out of v1 (a later ADR may add it once token origin and PCI scope are settled, Q-692). No card number (PAN), CVV, expiry or track data is ever received, logged or stored by Seshna. A provider adapter that would need raw card data is refused (`PAY-CAP-001`).
3. **PCI DSS.** The PCI SSC ties SAQ A eligibility to every payment page element coming directly from a PCI DSS validated third-party provider (FAQ 1292, https://www.pcisecuritystandards.org/faqs/1292/, accessed 2026-11-27). For a merchant page that embeds a provider's payment form, FAQ 1588 adds that the page must be protected from script attacks (techniques like PCI DSS 6.4.3 and 11.6.1), and says the criterion does not apply when the payer is redirected (https://www.pcisecuritystandards.org/faqs/1588/, accessed 2026-11-27). In `hosted_fields` that page would be ours, and its controls (CSP, SRI, a script inventory, change detection) are a body of work of their own; so v1 redirects only. That Seshna itself is outside PCI DSS scope is UNVERIFIED: the source addresses merchant SAQ eligibility, and the SSC's e-commerce guidance says a service that can affect the security of the payment flow may count toward a merchant's scope (https://listings.pcisecuritystandards.org/pdfs/best_practices_securing_ecommerce.pdf, accessed 2026-11-27). A QSA opinion is open (Q-692).
4. **Credentials per tenant.** Gateway API keys are class S11, read only by that tenant's payments job identity; webhook verification secrets are class S13, read only by the receiving endpoint ([secrets management](../security/secrets-management.md)). Neither is ever in the Blueprint, events, logs, prompts or errors. Connect stages each secret write-once and binds its fingerprint into the approval; the account id comes from a provider probe. On suspected exposure the connection is disabled at once; the customer's Owner rotates keys at the gateway and reconnects.
5. **Webhooks.** Every inbound webhook is authenticated by its gateway's own scheme before its body is used. Only a timestamp inside the signed material gets a replay window; other schemes are marked unprotected and rely on dedupe plus the re-read. Dedupe uses the event id, or the provider object id plus status plus amount, never a body hash alone; the marker commits only with a successful apply. A sweep re-reads open payments in case webhooks are missed. An unverifiable webhook is dropped and audited; it never changes a record. The gateway's status is re-read through its API before every status change, and the re-read status is what is applied.
6. **Payment records.** One idempotency key per checkout and per refund; each payment links to the invoice or order it settles. A second delivery or retry never creates a second payment.
7. **Refunds, voids and gateway connection are R4; ledger posting is R4 except an exact single-invoice match (R3, item 11).** Human approval always, never agent-creatable: an agent may prepare only a draft checkout for a human to submit, never a refund, void, connect or posting, not even as a draft ([tool-api](../../contracts/tool-api.md) section 11). The approver is not the initiator, step-up is required, and the approval binds the full action-policy section 5 set ([action-policy table](../security/action-policy-table.md) rows AP-PAY-01 to AP-PAY-05, proposed). Over-collected or unallocated money is refunded on its own R4 basis, without a credit note.
8. **Amounts.** Integer minor units plus ISO 4217 currency, computed by deterministic code from the invoice or order; the model never computes or proposes an amount. A gateway amount that differs from the expected one is a mismatch, never a silent correction.
9. **Untrusted content.** Everything a gateway returns (descriptions, payer names, error text, metadata) is untrusted data ([connector interface](../../contracts/connector-interface.md) section 3.3).
10. **Fail closed.** A missing credential, unknown status, failed verification, currency or amount mismatch, or gateway timeout leaves the record unpaid and raises an error; no payment is assumed.
11. **Reconciliation and posting.** A capture never posts to the ledger by itself; deterministic rigid-zone code drafts the receipt in the payment's own currency, and a human posts it (AP-PAY-05). Q-723 (Eldon, 2026-11-27; partner to confirm): a receipt that exactly matches one open invoice (same tenant, currency and amount, one invoice, not partial) is R3, a human submits it as for AP-FIN-01; anything else (partial, several invoices, over or under payment, unallocated, a currency difference) stays R4 with a second approver. Reconciliation of gateway payments, refunds and fees against the ledger is deterministic code in the rigid zone; it matches, it never guesses, and unmatched lines go to a human.
12. **Go-live, not build.** Each customer's gateway account and merchant approval are that customer's go-live items. Builds and tests use gateway sandboxes and synthetic data only. The environment (sandbox or live) belongs to the connection, is proven against the key mode at connect and is never taken from a request; dev and preview hosts hold sandbox connections only.

## Alternatives rejected
- A Seshna merchant account or payment facilitator model: card data, settlement, licensing and AML duties in four markets (ADR-0076).
- Card fields on Seshna pages posting to the gateway (direct post): the PCI SSC treats pages with merchant-origin elements as not SAQ A eligible (FAQ 1292).
- Gateway-hosted fields embedded in a Seshna page in v1: our page would need the script-attack controls of FAQ 1588; deferred to a later ADR.
- Gateway tokens in v1: a token produced by gateway script on a Seshna-origin page is the merchant-origin case above; deferred (security review, #393).
- One shared platform key per gateway: one breach exposes every tenant, and Seshna would act for companies it cannot verify.
- Trusting webhook bodies without verification or a status re-read: forged "paid" events would release goods.

## Consequences
- Easier: no card data, no funds held, one contract that new gateways implement.
- Harder: one adapter per gateway, each with its own signing scheme and sandbox; each customer must open and get approval for a gateway account before go-live.
- Must do: DSC-023 builds the first adapter against this contract (sandbox only); a security review of the contract by a different model (Tier 3: money and tenancy).

## Open questions
Q-692 (QSA scoping opinion), Q-693 (which gateway first), Q-694 (fees and payouts in reconciliation), Q-723 (posting row risk class, answered by Eldon 2026-11-27; partner to confirm).

## Supersedes
none
