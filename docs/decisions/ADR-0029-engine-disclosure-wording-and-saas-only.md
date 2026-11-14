# ADR-0029: Engine disclosure wording and SaaS-only delivery

Status: Proposed
Owner: eldon
Approved by: pending (partner review; counsel confirms the wording)

## Context
ADR-0016 keeps the engine invisible on every customer-visible surface. Invisible in the product is not the same as claiming the engine is ours: the accounting core is open-source software we host, and contracts, warranties and diligence reviews depend on what we say. On-premises or sovereign delivery requests will come, and the engine's licence terms matter for them ([ADR-0002](ADR-0002-seed-engine-frappe-erpnext.md), NOTICE.md).

## Decision
- Customer-visible surfaces stay engine-free (ADR-0016 unchanged).
- In contracts, due diligence and investor conversations we never imply we wrote the accounting engine. Standard wording, subject to counsel: "The platform is our own product: our builder, guardrails, component library and interface. The accounting core runs on a mature open-source ERP engine that we host and maintain. We share the full component list under NDA."
- Delivery stays SaaS only (ADR-0002). A request for on-premises or sovereign-cloud delivery needs a separate legal, security, product, support and cost decision and stays blocked until counsel has answered the GPL boundary (LEG-006, LEG-017); it is never an automatic exception.

## Alternatives rejected
- Say the engine is ours: false, and discoverable.
- Disclose the engine in the product: contradicts ADR-0016 and the product identity.
- Promise on-premises for any country that asks: engine licence and support consequences unknown (blocked by LEG-017).

## Consequences
- Counsel reviews the wording and the GPL boundary (LEG rows already planned).
- Sales and investor material uses the standard wording.

## Supersedes
None. Clarifies ADR-0016 and ADR-0002.
