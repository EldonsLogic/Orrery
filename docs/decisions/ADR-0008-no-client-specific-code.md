# ADR-0008: No client-specific code; component factory; autonomy metrics

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
We build the first clients ourselves, which is how a product company turns into a software house ([../strategy/08-product-vs-software-house.md](../strategy/08-product-vs-software-house.md)).

## Decision
No client-specific code, ever. A need no component covers becomes a candidate component built once for everyone through the component factory: gap, AI-drafted request with spec and tests, engineer review and certification, library, reuse by all tenants. Every build delivers the live system, new or improved components, and new eval cases and mappings. Manual steps go in an exceptions register. Metrics (autonomy rate, human hours, reuse ratio) are tracked and gate selling: if autonomy stalls for two consecutive clients, we stop selling and fix the platform. Contracts include an anonymised-reuse clause; no customer data crosses tenants, only generalised patterns are promoted.

## Alternatives rejected
- Allow small per-client patches: the slope to a services company.
- Skip metrics: no early warning.

## Consequences
- Needs the factory (BPL-014 to BPL-017) and metrics (GOV-016, BPL-022).
- Some deals will be declined or priced as explicit exceptions.
- Legal clause needed (LEG-013).

## Supersedes
none
