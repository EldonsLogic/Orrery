# ADR-0005: Human review gate for first clients; free-first with entitlements built in

Status: Accepted
Owner: eldon
Approved by: Eldon; partner review pending (GOV-013)

## Context
AI-built configuration for real businesses can be wrong. Pricing is untested ([../strategy/07-pricing.md](../strategy/07-pricing.md)); early adoption matters more than early revenue per seat.

## Decision
Every client build passes a mandatory human team review (state `team_reviewed`) before it is built and again before `live`. The gate may loosen per tier later, by ADR. Go-to-market is free-first: everything is unlocked at first, but plans, entitlements and usage metering exist from day one so gating can be switched on without rework. Setup is still sold as a fixed-price paid pilot (no free pilots, strategy/08).

## Alternatives rejected
- Fully automatic go-live: unacceptable error risk.
- Paywall from day one: slows learning.

## Consequences
- Needs a review queue and console (PLT-012, PLT-013).
- Metering and entitlements are G2 work (PLT-006, PLT-007).
- Review hours are tracked in the autonomy metrics.

## Supersedes
none
