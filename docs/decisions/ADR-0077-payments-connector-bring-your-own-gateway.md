# ADR-0077: Payments connector: bring your own gateway, hosted checkout or tokens only, no card data

Status: Proposed
Owner: eldon
Approved by: Eldon 2026-11-27 (proposer); partner pending (review on this PR)

## Context
[ADR-0076](ADR-0076-phase-1-module-scope.md) item 10 adds a payments connector to phase 1 (plan row DSC-021; build DSC-023 at G2). Companies in the four markets already hold accounts with gateways such as Moyasar, Tap, HyperPay, PayTabs and Stripe. Payments are money and sit on the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)). The contract is [connector-payments.md](../../contracts/connector-payments.md), Contract 4 gains `payment.*` event types ([events.md](../../contracts/events.md) section 3).

## Decision
1. **Bring your own gateway.** Each company connects its own gateway account. Seshna has no merchant account, is never the merchant of record and never holds, routes or settles funds. Money moves only between the payer, the gateway and the company.
2. **Hosted checkout or tokens only.** Seshna creates a checkout session and sends the payer to the gateway's hosted page (redirect or the gateway's own hosted fields), or charges a gateway-issued token. No card number (PAN), CVV, expiry or track data is ever received, logged or stored by Seshna. A provider adapter that would need raw card data is refused (`PAY-CAP-001`).
3. **PCI DSS.** The PCI SSC ties SAQ A eligibility to every payment page element coming directly from a PCI DSS validated third-party provider (FAQ 1292, https://www.pcisecuritystandards.org/faqs/1292/, accessed 2026-11-27). Item 2 is designed to keep Seshna and its customers on that path. That Seshna itself is outside PCI DSS scope is UNVERIFIED: the source addresses merchant SAQ eligibility, and the SSC's e-commerce guidance says a service that can affect the security of the payment flow may count toward a merchant's scope (https://listings.pcisecuritystandards.org/pdfs/best_practices_securing_ecommerce.pdf, accessed 2026-11-27). A QSA opinion is open (Q-692).
4. **Credentials per tenant.** Gateway API keys and webhook secrets are per-tenant secrets in the secret store (inventory class S11, [secrets management](../security/secrets-management.md)), read only by that tenant's payments job identity, never in the Blueprint, events, logs, prompts or errors.
5. **Webhooks.** Every inbound webhook is signature-verified with the tenant's secret before parsing, replay-protected (timestamp window plus a stored event-id marker) and idempotent. An unverifiable webhook is dropped and audited; it never changes a record. The gateway's status is re-read through its API before a payment is marked captured.
6. **Payment records.** One idempotency key per checkout and per refund; each payment links to the invoice or order it settles. A second delivery or retry never creates a second payment.
7. **Refunds and voids are R4.** Human approval always, never agent-creatable ([tool-api](../../contracts/tool-api.md) section 11), the approver is not the requester.
8. **Amounts.** Integer minor units plus ISO 4217 currency, computed by deterministic code from the invoice or order; the model never computes or proposes an amount. A gateway amount that differs from the expected one is a mismatch, never a silent correction.
9. **Untrusted content.** Everything a gateway returns (descriptions, payer names, error text, metadata) is untrusted data ([connector interface](../../contracts/connector-interface.md) section 3.3).
10. **Fail closed.** A missing credential, unknown status, failed verification, currency or amount mismatch, or gateway timeout leaves the record unpaid and raises an error; no payment is assumed.
11. **Reconciliation** of gateway payments, refunds and fees against the ledger is deterministic code in the rigid zone; it matches, it never guesses, and unmatched lines go to a human.
12. **Go-live, not build.** Each customer's gateway account and merchant approval are that customer's go-live items. Builds and tests use gateway sandboxes and synthetic data only.

## Alternatives rejected
- A Seshna merchant account or payment facilitator model: card data, settlement, licensing and AML duties in four markets (ADR-0076).
- Card fields on Seshna pages posting to the gateway (direct post): the PCI SSC treats pages with merchant-origin elements as not SAQ A eligible (FAQ 1292).
- One shared platform key per gateway: one breach exposes every tenant, and Seshna would act for companies it cannot verify.
- Trusting webhook bodies without verification or a status re-read: forged "paid" events would release goods.

## Consequences
- Easier: no card data, no funds held, one contract that new gateways implement.
- Harder: one adapter per gateway, each with its own signing scheme and sandbox; each customer must open and get approval for a gateway account before go-live.
- Must do: DSC-023 builds the first adapter against this contract (sandbox only); a security review of the contract by a different model (Tier 3: money and tenancy).

## Open questions
Q-692 (QSA scoping opinion), Q-693 (which gateway first), Q-694 (fees and payouts in reconciliation).

## Supersedes
none
